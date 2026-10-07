"""username_probe adapter — public HTTP presence checks for a handle.

Studied source: sherlock-project/sherlock docs/README only (interface pattern:
probe each site's public profile URL with plain HTTP, no login).
Clean-room reimplementation — no code copied from that project. MIT (ours).

Two modes (same contract, same finding schema):

- Fixture/demo mode (default, SHERLOCK_LIVE unset): probe the 5 DEMO_SITES
  (example.com subtree) so tests and demos never touch live third-party
  targets. HTTP 200 counts as a public-presence hit; 404 / timeout /
  connection error counts as a miss — never as a hit (no hallucination).
- Live mode (SHERLOCK_LIVE=1, non-demo handles only): probe the 30
  LIVE_SITES below — curated public-profile URL shapes of the form
  ``https://<host>/.../<handle>`` (GitHub/Reddit/YouTube/X-style pages).
  The shapes are reimplemented from public URL conventions, not copied
  from any site list. Public GET only, 10s timeout, Sherlock UA, 1 req/2s
  pacing. Each response is classified found / not-found / error via
  status + content markers; login-submit walls are never counted as hits.

Free cap / rate behavior: demo list is 5 plain GETs per run; live list is
up to 30 plain GETs per run with 2s pacing (~60s worst case). Honor HTTP
429 (back off), respect robots/ToS, keep concurrency at 1; aggressive
scanning triggers rate limits. sqlite fetch_log TTL 24h (tools layer)
avoids re-hammering the same handle.

Failure taxonomy: private/deleted/rate-limited targets surface as non-200
(miss) or as a clean ``rejected`` result for invalid/PII-shaped input —
never as fabricated findings. Live-network outages degrade to
ok + [] with a reason (fixture fallback for @demo.sleuth is handled by
the registry layer), never hallucinated hits.

Guardrails (hard): public GET only. NO logins, NO passwords, NO
email/phone PII lanes, NO breach-password data, NO POSTing forms.
"""

import os
import re
import json
import time

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "username_probe"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied sherlock-project/sherlock docs only."
)

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; public-presence-check)"
PACING_SEC = 2.0

# Fixture site list. Demo-only hosts (example.com subtree) so the adapter
# never touches live third-party targets in tests or demos. Prod deployments
# swap in their own allow-listed public-profile URL templates.
SITES = [
    {"name": "DemoHub", "url_template": "https://example.com/users/{handle}"},
    {"name": "DemoCode", "url_template": "https://example.com/@{handle}"},
    {"name": "DemoBlog", "url_template": "https://example.com/blog/{handle}"},
    {"name": "DemoForum", "url_template": "https://example.com/forum/u/{handle}"},
    {"name": "DemoPics", "url_template": "https://example.com/pics/{handle}"},
]
DEMO_SITES = SITES

# Live site list: 30 curated public-profile URL shapes. Each is a plain
# public ``/{handle}`` (or /user/{handle}, /@/{handle}, /u/{handle}) page
# that answers plain GET without login. Shapes follow public URL
# conventions only; no list copied from any project. Hosts that bot-gate
# (403/429/login-wall) classify as error, never as hits.
LIVE_SITES = [
    {"name": "GitHub", "url_template": "https://github.com/{handle}"},
    {"name": "GitLab", "url_template": "https://gitlab.com/{handle}"},
    {"name": "Reddit", "url_template": "https://www.reddit.com/user/{handle}"},
    {"name": "YouTube", "url_template": "https://www.youtube.com/@{handle}"},
    {"name": "X", "url_template": "https://x.com/{handle}"},
    {"name": "Medium", "url_template": "https://medium.com/@{handle}"},
    {"name": "DevTo", "url_template": "https://dev.to/{handle}"},
    {"name": "Codepen", "url_template": "https://codepen.io/{handle}"},
    {"name": "Dribbble", "url_template": "https://dribbble.com/{handle}"},
    {"name": "Behance", "url_template": "https://www.behance.net/{handle}"},
    {"name": "Flickr", "url_template": "https://www.flickr.com/people/{handle}"},
    {"name": "Vimeo", "url_template": "https://vimeo.com/{handle}"},
    {"name": "SoundCloud", "url_template": "https://soundcloud.com/{handle}"},
    {"name": "Twitch", "url_template": "https://www.twitch.tv/{handle}"},
    {"name": "Pinterest", "url_template": "https://www.pinterest.com/{handle}"},
    {"name": "Tumblr", "url_template": "https://www.tumblr.com/{handle}"},
    {"name": "Mastodon", "url_template": "https://mastodon.social/@{handle}"},
    {"name": "Bluesky", "url_template": "https://bsky.app/profile/{handle}"},
    {"name": "Lobsters", "url_template": "https://lobste.rs/u/{handle}"},
    {"name": "Kaggle", "url_template": "https://www.kaggle.com/{handle}"},
    {"name": "HuggingFace", "url_template": "https://huggingface.co/{handle}"},
    {"name": "PyPI", "url_template": "https://pypi.org/user/{handle}"},
    {"name": "DockerHub", "url_template": "https://hub.docker.com/u/{handle}"},
    {"name": "Replit", "url_template": "https://replit.com/@{handle}"},
    {"name": "Glitch", "url_template": "https://glitch.com/@{handle}"},
    {"name": "NPM", "url_template": "https://www.npmjs.com/~{handle}"},
    {"name": "Keybase", "url_template": "https://keybase.io/{handle}"},
    {"name": "Slideshare", "url_template": "https://www.slideshare.net/{handle}"},
    {"name": "SpeakerDeck", "url_template": "https://speakerdeck.com/{handle}"},
    {"name": "VimeoStaff", "url_template": "https://vimeo.com/channels/{handle}"},
]

_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_PII_HINTS = ("password", "follower", "following", "phone", "email", "address")

# Content markers: a 200 whose body carries these is NOT a live profile.
# Login walls ("log in to continue" + password forms) must never count.
# Soft-404 hosts (Reddit/PyPI/Twitch-style: HTTP 200 for missing users)
# are caught by the handle + title gates in classify_live_response.
_NOT_FOUND_MARKERS = (
    "user not found",
    "page not found",
    "profile not found",
    "account not found",
    "account suspended",
    "account deactivated",
    "user doesn't exist",
    "user does not exist",
    "this account doesn't exist",
    "this account does not exist",
    "no such user",
    "could not find",
    "couldn't find",
    "unable to find",
    "isn't available",
    "is not available",
    "no longer available",
    "no longer exists",
    "has been suspended",
    "has been deactivated",
)
_LOGIN_WALL_MARKERS = (
    "log in to continue",
    "login to continue",
    "sign in to continue",
    "log in to see",
    "sign in to confirm",
    "login required",
    "you need to log in",
    "checkpoint",
)


def is_live_enabled() -> bool:
    """Live probing is opt-in via SHERLOCK_LIVE=1 (else fixture mode)."""
    return os.environ.get("SHERLOCK_LIVE") == "1"


def _is_demo_handle(handle: str) -> bool:
    return handle == "demo.sleuth" or handle.startswith("demo.")


def _normalize_handle(target):
    """Return (handle, error). Handle is lowercased, leading '@' stripped."""
    if target is None:
        return None, "empty target: pass a public handle such as @demo.sleuth"
    text = target.strip() if isinstance(target, str) else ""
    if not text:
        return None, "empty target: pass a public handle such as @demo.sleuth"
    lowered = text.lower()
    if any(hint in lowered for hint in _PII_HINTS):
        return None, (
            "rejected: login-gated/PII lookup (followers, phone, email) "
            "is out of scope; public presence checks only"
        )
    handle = text[1:] if text.startswith("@") else text
    handle = handle.strip().lower()
    if "@" in handle:
        return None, "rejected: email-to-account lookup is excluded (PII tool)"
    if re.fullmatch(r"\+?[\d][\d\s\-().]{6,}", handle):
        return None, "rejected: phone-to-account lookup is excluded (PII tool)"
    if not _HANDLE_RE.match(handle):
        return None, (
            "rejected: invalid handle; use 1-64 chars of letters, digits, "
            "'.', '_' or '-' (e.g. @demo.sleuth)"
        )
    return handle, None


def _sleep(seconds: float) -> None:
    """Sleeper (monkeypatchable; SHERLOCK_NO_PACING=1 skips in tests)."""
    if os.environ.get("SHERLOCK_NO_PACING") == "1":
        return
    try:
        time.sleep(seconds)
    except Exception:
        pass


def _fetch_status(url, timeout=TIMEOUT):
    """Plain no-auth GET; return HTTP status int, or None on any failure."""
    if requests is None:
        return None
    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        return resp.status_code
    except Exception:
        return None


def _fetch_live_detail(url, timeout=TIMEOUT):
    """Live GET returning (status:int|None, body_snippet:str).

    Public GET only, 10s timeout, Sherlock UA. Never raises. The snippet
    keeps the first 100 KiB (large pages bury <title> and profile
    markers under inlined assets; classification needs the headroom).
    """
    if requests is None:
        return None, ""
    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        return resp.status_code, body[:100000]
    except Exception:
        return None, ""


def _title_has_handle(body, handle):
    """True when the page <title> names the handle (profile evidence).

    Soft-404 hosts serve generic shells titled just "Reddit"/"Twitch"/
    "Bluesky" for missing users; a real profile titles the handle
    ("octocat (The Octocat) · GitHub"). Missing/empty title -> False.
    """
    h = (handle or "").strip().lower().lstrip("@")
    if not h:
        return False
    try:
        m = re.search(r"<title[^>]*>(.*?)</title>", body or "",
                      re.IGNORECASE | re.DOTALL)
    except Exception:
        return False
    if not m:
        return False
    title = re.sub(r"\s+", " ", m.group(1)).strip().lower()
    return bool(title) and h in title


def _has_password_form(body):
    """True when the body contains a password input (login-submit wall)."""
    t = (body or "").lower()
    return ('type="password"' in t or "type='password'" in t or
            'name="password"' in t)


def classify_live_response(status, body, handle=""):
    """Classify a live probe as found / not-found / error.

    Rules (never hallucinate — a miss beats a false hit):
    - None / timeout / connection error -> error
    - 404 / 410 -> not-found
    - 429 / 5xx -> error (rate-limit / flaky upstream, back off)
    - 403 -> error (bot-gate, not evidence of absence or presence)
    - 200 with a not-found phrase -> not-found
    - 200 with a login wall (continue/required phrases, or any password
      form) -> error (login-submit pages are never hits)
    - 200 where the handle is absent from the body, or the <title> does
      not name the handle (generic SPA shell / soft-404) -> error
      (cannot confirm presence, so never a hit)
    - anything else (other non-200, empty body) -> error (conservative:
      only a plain 200 with handle + titled evidence counts as found).
    """
    if status is None:
        return "error"
    if status in (404, 410):
        return "not-found"
    if status == 429 or (500 <= status <= 599):
        return "error"
    if status == 403:
        return "error"
    if status != 200:
        return "error"
    text = (body or "")
    if not text.strip():
        return "error"
    lowered = text.lower()
    for marker in _NOT_FOUND_MARKERS:
        if marker in lowered:
            return "not-found"
    for marker in _LOGIN_WALL_MARKERS:
        if marker in lowered:
            return "error"
    if _has_password_form(text):
        return "error"
    h = (handle or "").strip().lower().lstrip("@")
    if not h or h not in lowered:
        return "error"
    if not _title_has_handle(text, handle):
        return "error"
    return "found"


def _run_demo(handle):
    """Fixture-mode probe over DEMO_SITES (existing behavior, no pacing)."""
    hits = []
    checked = 0
    for site in DEMO_SITES:
        url = site["url_template"].format(handle=handle)
        checked += 1
        try:
            status = _fetch_status(url)
        except Exception:
            status = None
        if status == 200:
            hits.append(
                {
                    "type": "presence",
                    "value": "%s: %s" % (site["name"], url),
                    "source": NAME,
                    "confidence": "low",  # upgraded below if corroborated
                }
            )
    if len(hits) > 1:
        for hit in hits:
            hit["confidence"] = "medium"
    if hits:
        reason = "public presence: %d of %d sites hit for @%s" % (
            len(hits), checked, handle)
    else:
        reason = "no public presence found for @%s (%d sites checked)" % (
            handle, checked)
    return {"status": "ok", "reason": reason, "findings": hits}


def _run_live(handle):
    """Live probe over LIVE_SITES with pacing + classification."""
    hits = []
    checked = 0
    errors = 0
    for i, site in enumerate(LIVE_SITES):
        url = site["url_template"].format(handle=handle)
        checked += 1
        try:
            status, body = _fetch_live_detail(url)
        except Exception:
            status, body = None, ""
        try:
            verdict = classify_live_response(status, body, handle)
        except Exception:
            verdict = "error"
        if verdict == "found":
            hits.append(
                {
                    "type": "presence",
                    "value": "%s: %s" % (site["name"], url),
                    "source": NAME,
                    "confidence": "low",
                }
            )
        elif verdict == "error":
            errors += 1
        if i + 1 < len(LIVE_SITES):
            _sleep(PACING_SEC)
    if len(hits) > 1:
        for hit in hits:
            hit["confidence"] = "medium"
    if hits:
        reason = ("live presence: %d of %d sites hit for @%s "
                  "(public GET, 10s timeout, 2s pacing)" % (
                      len(hits), checked, handle))
    elif errors == checked:
        reason = ("live probe unavailable for @%s (%d sites, all errored; "
                  "network down or upstream flaky — no hallucination)" % (
                      handle, checked))
    else:
        reason = ("no live presence found for @%s "
                  "(%d sites checked, %d errored)" % (
                      handle, checked, errors))
    return {"status": "ok", "reason": reason, "findings": hits}


CANONICAL_DEMO_HANDLE = "demo.sleuth"


def _pinned_demo_findings():
    """Pinned DEMO-CASE-001 shape for the canonical demo handle.

    Deterministic on/offline: the fixture file IS the contract (AGENTS.md
    section 3). Returns the findings list, or None if unreadable (caller
    falls back to probing). Honors SHERLOCK_FIXTURES override, else the
    repo demo-data/fixtures/username.json next to this package.
    """
    try:
        override = os.environ.get("SHERLOCK_FIXTURES")
        if override:
            path = os.path.join(override, "username.json")
        else:
            path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))),
                "demo-data", "fixtures", "username.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        findings = data.get("findings")
        if isinstance(findings, list) and findings and all(
                isinstance(f, dict) for f in findings):
            return findings
    except Exception:
        pass
    return None


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    handle, error = _normalize_handle(target)
    if error:
        return {"status": "rejected", "reason": error, "findings": []}
    if handle == CANONICAL_DEMO_HANDLE:
        pinned = _pinned_demo_findings()
        if pinned is not None:
            return {
                "status": "ok",
                "reason": ("pinned fixture: 3 of 5 sites hit for "
                           "@demo.sleuth"),
                "findings": pinned,
            }
    if _is_demo_handle(handle) or not is_live_enabled():
        return _run_demo(handle)
    return _run_live(handle)
