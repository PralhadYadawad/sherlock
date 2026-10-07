"""github_lane adapter — API-first GitHub intel for a handle.

Clean-room reimplementation, MIT (ours). Studied the GitHub REST API
docs only (endpoint shapes + rate-limit quotas below). No code copied.

API-first: every datum comes from ``https://api.github.com`` JSON —
``GET /users/{handle}`` (profile), ``GET /users/{handle}/repos``
(repositories), ``GET /users/{handle}/orgs`` (organizations),
``GET /users/{handle}/events/public`` (public commit authorship), and
``GET /search/users`` (name -> candidate-handle discovery). HTML
scraping is FORBIDDEN in this lane: the fetcher host-guards to
``api.github.com`` and refuses any other host, so ``github.com`` profile
pages are never scraped (no login walls, no bot-gates, no ToS gray
area). There is deliberately no HTML-parsing surface in this module
(JSON decoding only; no page-scraping imports of any kind).

Key model: optional per-operator token via the ``SHERLOCK_GITHUB_TOKEN``
environment variable (each operator pastes their own free-tier PAT;
``DUMMY_...`` placeholders are treated as missing so tests and demos
never authenticate). The token travels only in the ``Authorization``
header and is never logged, never echoed in reasons, never persisted.
Anonymous calls stay fully functional inside the anon quota.

Free caps (vendor statements, re-check at signup):
- Core REST (users/repos/orgs/events): 60 req/hr anonymous per IP,
  5,000 req/hr with a token.
- Search (``/search/users``): 10 req/min anonymous (code search shares
  the 10/min pool per the 2023-03-10 changelog; this lane never calls
  code search).
One ``run()`` costs 1 GET for a valid miss (profile 404 stops the lane)
and at most 4 GETs for a handle hit (profile + repos + orgs + events),
sequential, ``PACING_SEC = 1.0`` apart (``SHERLOCK_NO_PACING=1`` skips
sleeps in tests), 10s timeout each, Sherlock UA, 24h ``fetch_log``
cache at the tools layer.

Per-user bucket coordination: enforced in ``server/tools.py``
``throttle_check(user_id)`` (anonymous 5/min, authenticated 30/min, 60s
window). The orchestrator MUST gate entity searches there before calling
this lane. This module stays standalone on purpose — it does NOT import
``tools`` or ``registry`` (the orchestrator wires this lane next
phase). Documented here, not implemented here.

Failure taxonomy (never hallucinated findings):
- ``rejected`` + []: empty/non-string/over-long/PII-shaped input;
  429 (rate-limited) with the Retry-After note when sent; 403 with an
  exhausted quota (``X-RateLimit-Remaining: 0`` or a "rate limit"
  message) with the token + cache hint; other 403/4xx/5xx; timeout.
  Exhaustion stops the run immediately — no further sub-lane calls, no
  hammering. Every exhaustion reason carries a cache hint (the
  orchestrator serves cache).
- ``ok`` + []: profile 404 (valid miss: no such user), search with zero
  items, or a readable profile with no parseable fields (degraded lanes).
- ``ok`` + findings: profile/repos/orgs/public-commit-emails. All
  findings are ``low`` confidence (single-source public metadata never
  identifies alone; corroborate before asserting). Commit emails come
  ONLY from authorship already published in public push events
  (``users.noreply`` shield addresses included as-is); nothing is
  looked up or enriched.

Guardrails (hard): public API GETs only. NO HTML scraping, NO logins,
NO passwords, NO email/phone-to-account PII lanes (published
commit authorship is reported as-is, never resolved), NO breach data,
NO POSTs. DUMMY/example fixtures only in tests.
"""

import os
import re
import time
from urllib.parse import urlparse

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "github_lane"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied GitHub REST API docs only; API-only, no HTML scraping."
)

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; github-lane)"
API_HOST = "api.github.com"
API_BASE = "https://api.github.com"
PROFILE_URL = API_BASE + "/users/{handle}"
REPOS_URL = API_BASE + "/users/{handle}/repos"
ORGS_URL = API_BASE + "/users/{handle}/orgs"
EVENTS_URL = API_BASE + "/users/{handle}/events/public"
SEARCH_USERS_URL = API_BASE + "/search/users"
ENV_TOKEN = "SHERLOCK_GITHUB_TOKEN"
PACING_SEC = 1.0
MAX_TARGET_LEN = 256
MAX_REPOS = 5
MAX_ORGS = 10
MAX_EMAILS = 5
MAX_SEARCH = 5
EVENTS_SCAN = 30

_HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .'\-]*$")
_EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")
_PHONE_RE = re.compile(r"^\+?[\d][\d\s\-().]{6,}$")
_WS_RE = re.compile(r"\s+")


def get_token() -> str:
    """Return the operator's GitHub token, or '' when absent/placeholder.

    ``DUMMY_...`` placeholders (repo policy: no live keys committed) are
    treated as missing so tests and demos never authenticate.
    """
    try:
        token = os.environ.get(ENV_TOKEN, "") or ""
    except Exception:
        return ""
    token = token.strip()
    if not token or token.upper().startswith("DUMMY"):
        return ""
    return token


def is_handle(text) -> bool:
    """True when text is a GitHub-shaped username (1-39 chars, no '--')."""
    if not isinstance(text, str):
        return False
    t = text.strip()
    if not t or "--" in t:
        return False
    return bool(_HANDLE_RE.match(t))


def _sleep(seconds: float) -> None:
    """Sleeper (monkeypatchable; SHERLOCK_NO_PACING=1 skips in tests)."""
    if os.environ.get("SHERLOCK_NO_PACING") == "1":
        return
    try:
        time.sleep(seconds)
    except Exception:
        pass


def _auth_headers(token: str) -> dict:
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = "Bearer %s" % token
    return headers


def _api_get(url, params=None, token="", timeout=TIMEOUT):
    """Polite API GET returning (status:int|None, data, meta).

    Host-guarded to ``api.github.com`` (HTML scraping is forbidden: any
    other host yields ``(None, None, {})`` without touching the network).
    ``data`` is the decoded JSON body when it is a dict/list, else None
    (kept even on non-200 so callers can sniff quota messages). ``meta``
    carries ``remaining`` / ``retry_after`` header echoes. Never raises.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None, None, {}
    if host != API_HOST:
        return None, None, {}
    if requests is None:
        return None, None, {}
    try:
        resp = requests.get(
            url, params=params or {}, headers=_auth_headers(token),
            timeout=timeout,
        )
        try:
            status = resp.status_code
        except Exception:
            return None, None, {}
        meta = {"remaining": "", "retry_after": ""}
        try:
            if resp.headers:
                meta["remaining"] = str(
                    resp.headers.get("X-RateLimit-Remaining", "") or "")
                meta["retry_after"] = str(
                    resp.headers.get("Retry-After", "") or "").strip()
        except Exception:
            pass
        try:
            data = resp.json()
        except Exception:
            return status, None, meta
        if isinstance(data, (dict, list)):
            return status, data, meta
        return status, None, meta
    except Exception:
        return None, None, {}


def _is_exhausted(status, data, meta) -> bool:
    """True when a 403 means the API quota is spent (not just forbidden)."""
    if status != 403:
        return False
    try:
        if isinstance(meta, dict) and str(meta.get("remaining", "")) == "0":
            return True
    except Exception:
        pass
    try:
        if isinstance(data, dict):
            msg = str(data.get("message", "")).lower()
            if "rate limit" in msg or "exceeded" in msg:
                return True
    except Exception:
        pass
    return False


def _cache_hint() -> str:
    return "serve cached 24h (orchestrator serves cache; no hallucination)"


def _quota_reason() -> str:
    return ("rejected: GitHub quota exhausted (anon 60/hr; set %s with "
            "your own token for 5000/hr; back off, no retry; %s)"
            % (ENV_TOKEN, _cache_hint()))


def fetch_profile(handle, token="", timeout=TIMEOUT):
    """GET /users/{handle} (profile lane)."""
    return _api_get(PROFILE_URL.format(handle=handle), token=token,
                    timeout=timeout)


def fetch_repos(handle, token="", timeout=TIMEOUT):
    """GET /users/{handle}/repos (top-5 by recent update)."""
    return _api_get(REPOS_URL.format(handle=handle),
                    params={"per_page": MAX_REPOS, "sort": "updated",
                            "type": "owner"},
                    token=token, timeout=timeout)


def fetch_orgs(handle, token="", timeout=TIMEOUT):
    """GET /users/{handle}/orgs (public memberships)."""
    return _api_get(ORGS_URL.format(handle=handle),
                    params={"per_page": MAX_ORGS}, token=token,
                    timeout=timeout)


def fetch_events(handle, token="", timeout=TIMEOUT):
    """GET /users/{handle}/events/public (commit-email source lane)."""
    return _api_get(EVENTS_URL.format(handle=handle),
                    params={"per_page": EVENTS_SCAN}, token=token,
                    timeout=timeout)


def fetch_user_search(query, token="", timeout=TIMEOUT):
    """GET /search/users (name -> candidate handles, capped)."""
    return _api_get(SEARCH_USERS_URL,
                    params={"q": query, "per_page": MAX_SEARCH},
                    token=token, timeout=timeout)


def parse_profile(data):
    """Parse a user object -> finding dict, or None when unusable.

    Emits one ``github_profile`` finding (login + display name + URL,
    with company/location/blog folded in when published). Missing login
    or non-dict input yields None (never invented).
    """
    if not isinstance(data, dict):
        return None
    login = data.get("login")
    if not isinstance(login, str) or not login.strip():
        return None
    login = login.strip()
    bits = []
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        bits.append(name.strip()[:64])
    for key in ("company", "location", "blog"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            bits.append("%s: %s" % (key, val.strip()[:128]))
    url = data.get("html_url")
    url = url.strip()[:256] if isinstance(url, str) and url.strip() else ""
    value = "github_profile: %s" % login
    if bits:
        value += " (%s)" % "; ".join(bits)
    if url:
        value += " — %s" % url
    return {"type": "github_profile", "value": value[:512],
            "source": NAME, "confidence": "low"}


def parse_repos(data, limit=MAX_REPOS):
    """Parse a repos array -> ``github_repo`` findings (capped, low)."""
    out = []
    if not isinstance(data, list):
        return out
    try:
        limit = int(limit)
    except Exception:
        limit = MAX_REPOS
    for row in data:
        if len(out) >= limit:
            break
        if not isinstance(row, dict):
            continue
        full = row.get("full_name") or row.get("name")
        url = row.get("html_url")
        if not isinstance(full, str) or not full.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue
        if not (url.strip().startswith("http://")
                or url.strip().startswith("https://")):
            continue
        extra = ""
        try:
            stars = row.get("stargazers_count")
            if isinstance(stars, int) and stars >= 0:
                extra = " (stars %d%s)" % (
                    stars, ", fork" if row.get("fork") is True else "")
        except Exception:
            extra = ""
        out.append(
            {"type": "github_repo",
             "value": ("repo: %s — %s%s"
                       % (full.strip()[:128], url.strip()[:256],
                          extra))[:512],
             "source": NAME, "confidence": "low"})
    return out


def parse_orgs(data, limit=MAX_ORGS):
    """Parse an orgs array -> ``github_org`` findings (capped, low)."""
    out = []
    if not isinstance(data, list):
        return out
    try:
        limit = int(limit)
    except Exception:
        limit = MAX_ORGS
    for row in data:
        if len(out) >= limit:
            break
        if not isinstance(row, dict):
            continue
        login = row.get("login")
        if not isinstance(login, str) or not login.strip():
            continue
        url = row.get("html_url") or row.get("url") or ""
        url = url.strip() if isinstance(url, str) else ""
        value = "org: %s" % login.strip()[:128]
        if url and (url.startswith("http://")
                    or url.startswith("https://")):
            value += " — %s" % url[:256]
        out.append({"type": "github_org", "value": value[:512],
                    "source": NAME, "confidence": "low"})
    return out


def parse_commit_emails(data, limit=MAX_EMAILS, scan=EVENTS_SCAN):
    """Parse public events -> ``github_email`` findings (capped, low).

    Only ``PushEvent`` commit authorship already published by the user is
    read (``payload.commits[].author.email``); shield
    (``users.noreply``) addresses pass through as-is. Anything else —
    private emails, lookups, enrichment — is out of scope and never
    emitted.
    """
    out = []
    seen = set()
    if not isinstance(data, list):
        return out
    try:
        limit = int(limit)
    except Exception:
        limit = MAX_EMAILS
    try:
        scan = int(scan)
    except Exception:
        scan = EVENTS_SCAN
    for event in data[:scan]:
        if len(out) >= limit:
            break
        if not isinstance(event, dict) or event.get("type") != "PushEvent":
            continue
        repo = ""
        try:
            repo_obj = event.get("repo")
            if isinstance(repo_obj, dict) and \
                    isinstance(repo_obj.get("name"), str):
                repo = repo_obj["name"].strip()[:128]
        except Exception:
            repo = ""
        try:
            payload = event.get("payload")
            commits = payload.get("commits") if isinstance(payload,
                                                           dict) else None
        except Exception:
            commits = None
        if not isinstance(commits, list):
            continue
        for commit in commits:
            if len(out) >= limit:
                break
            if not isinstance(commit, dict):
                continue
            try:
                author = commit.get("author")
                email = author.get("email") if isinstance(author,
                                                           dict) else None
            except Exception:
                email = None
            if not isinstance(email, str) or "@" not in email:
                continue
            email = email.strip()[:254]
            if not email or email.lower() in seen:
                continue
            seen.add(email.lower())
            value = "commit-email: %s" % email
            if repo:
                value += " (public push to %s)" % repo
            out.append({"type": "github_email", "value": value[:512],
                        "source": NAME, "confidence": "low"})
    return out


def parse_user_search(data, limit=MAX_SEARCH):
    """Parse /search/users -> ``github_user`` candidate findings (low).

    Name matches are candidates only — a login similarity never asserts
    identity. Zero items yields [] (never invented handles).
    """
    out = []
    if not isinstance(data, dict):
        return out
    items = data.get("items")
    if not isinstance(items, list):
        return out
    try:
        limit = int(limit)
    except Exception:
        limit = MAX_SEARCH
    for row in items[:limit]:
        if not isinstance(row, dict):
            continue
        login = row.get("login")
        url = row.get("html_url")
        if not isinstance(login, str) or not login.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue
        if not (url.strip().startswith("http://")
                or url.strip().startswith("https://")):
            continue
        out.append(
            {"type": "github_user",
             "value": ("user-match: %s — %s (candidate only; confirm via "
                       "profile URL)" % (login.strip()[:128],
                                         url.strip()[:256]))[:512],
             "source": NAME, "confidence": "low"})
    return out


def _run_handle(handle, token):
    """Profile -> repos/orgs/events fan (sequential, paced)."""
    try:
        status, data, meta = fetch_profile(handle, token)
    except Exception:
        status, data, meta = None, None, {}
    if status is None:
        return {"status": "rejected",
                "reason": "rejected: GitHub upstream unavailable "
                          "(timeout/network; %s)" % _cache_hint(),
                "findings": []}
    if status == 429:
        note = ""
        try:
            if isinstance(meta, dict) and meta.get("retry_after"):
                note = "retry-after %s; " % meta["retry_after"]
        except Exception:
            note = ""
        return {"status": "rejected",
                "reason": "rejected: GitHub rate-limited (HTTP 429; %sback "
                          "off, no retry; %s)" % (note, _cache_hint()),
                "findings": []}
    if _is_exhausted(status, data, meta):
        return {"status": "rejected", "reason": _quota_reason(),
                "findings": []}
    if status == 404:
        return {"status": "ok",
                "reason": "no GitHub user %r (not found; no hallucination)"
                          % ("@" + handle),
                "findings": []}
    if status != 200 or not isinstance(data, dict):
        return {"status": "rejected",
                "reason": "rejected: GitHub upstream error (HTTP %s; %s)"
                          % (status, _cache_hint()),
                "findings": []}
    findings = []
    seen = set()

    def _add(items):
        for item in items or []:
            if not isinstance(item, dict):
                continue
            key = (item.get("type"), item.get("value"))
            if key in seen:
                continue
            seen.add(key)
            findings.append(item)

    try:
        profile = parse_profile(data)
    except Exception:
        profile = None
    if profile is not None:
        _add([profile])

    degraded = []
    for lane, fetch in (("repos", fetch_repos), ("orgs", fetch_orgs),
                        ("events", fetch_events)):
        _sleep(PACING_SEC)
        try:
            st, lane_data, lane_meta = fetch(handle, token)
        except Exception:
            st, lane_data, lane_meta = None, None, {}
        if st == 429 or _is_exhausted(st, lane_data, lane_meta):
            # Exhaustion mid-run: stop at once (no hammering), rejected-clean.
            if st == 429:
                note = ""
                try:
                    if isinstance(lane_meta, dict) and \
                            lane_meta.get("retry_after"):
                        note = "retry-after %s; " % lane_meta["retry_after"]
                except Exception:
                    note = ""
                reason = ("rejected: GitHub rate-limited mid-run "
                          "(HTTP 429 in %s lane; %sback off; %s)"
                          % (lane, note, _cache_hint()))
            else:
                reason = _quota_reason()
            return {"status": "rejected", "reason": reason, "findings": []}
        if st != 200:
            degraded.append(lane)
            continue
        try:
            if lane == "repos":
                _add(parse_repos(lane_data))
            elif lane == "orgs":
                _add(parse_orgs(lane_data))
            else:
                _add(parse_commit_emails(lane_data))
        except Exception:
            degraded.append(lane)
    for item in findings:  # single-source public metadata never goes high
        if item.get("confidence") not in ("low", "medium"):
            item["confidence"] = "low"
    n_repos = sum(1 for f in findings if f["type"] == "github_repo")
    n_orgs = sum(1 for f in findings if f["type"] == "github_org")
    n_emails = sum(1 for f in findings if f["type"] == "github_email")
    detail = "profile + %d repos + %d orgs + %d public emails" % (
        n_repos, n_orgs, n_emails)
    if degraded:
        detail += " (degraded lanes: %s)" % ", ".join(sorted(set(degraded)))
    if findings:
        reason = ("github intel for @%s: %d finding(s) (%s; single-source "
                  "public API metadata: low confidence; never high)"
                  % (handle, len(findings), detail))
    else:
        reason = ("no github data for @%s (%s; no hallucination)"
                  % (handle, detail))
    return {"status": "ok", "reason": reason, "findings": findings}


def _run_search(query, token):
    """Name -> candidate handles via /search/users (discovery only)."""
    _sleep(PACING_SEC)
    try:
        status, data, meta = fetch_user_search(query, token)
    except Exception:
        status, data, meta = None, None, {}
    if status is None:
        return {"status": "rejected",
                "reason": "rejected: GitHub upstream unavailable "
                          "(timeout/network; %s)" % _cache_hint(),
                "findings": []}
    if status == 429:
        return {"status": "rejected",
                "reason": "rejected: GitHub search rate-limited (HTTP 429; "
                          "search pool is 10/min; back off; %s)"
                          % _cache_hint(),
                "findings": []}
    if _is_exhausted(status, data, meta):
        return {"status": "rejected", "reason": _quota_reason(),
                "findings": []}
    if status != 200 or not isinstance(data, dict):
        return {"status": "rejected",
                "reason": "rejected: GitHub search upstream error "
                          "(HTTP %s; %s)" % (status, _cache_hint()),
                "findings": []}
    try:
        findings = parse_user_search(data)
    except Exception:
        findings = []
    if findings:
        reason = ("github user search for %r: %d candidate(s) (name "
                  "matches are candidates only: low; confirm via profile "
                  "URL)" % (query[:64], len(findings)))
    else:
        reason = ("no github user matches for %r (no hallucination)"
                  % query[:64])
    return {"status": "ok", "reason": reason, "findings": findings}


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    if target is None or (isinstance(target, str) and not target.strip()):
        return {"status": "rejected",
                "reason": "empty target: pass a GitHub handle (e.g. "
                          "@demo-sleuth) or a name to search",
                "findings": []}
    if not isinstance(target, str):
        return {"status": "rejected",
                "reason": "rejected: invalid github target",
                "findings": []}
    text = _WS_RE.sub(" ", target.strip()).strip()
    if len(text) > MAX_TARGET_LEN:
        return {"status": "rejected",
                "reason": "rejected: target over %d chars" % MAX_TARGET_LEN,
                "findings": []}
    if _EMAIL_RE.match(text):
        return {"status": "rejected",
                "reason": "rejected: email-to-account lookup is excluded "
                          "(PII tool)",
                "findings": []}
    if _PHONE_RE.match(text):
        return {"status": "rejected",
                "reason": "rejected: phone-to-account lookup is excluded "
                          "(PII tool)",
                "findings": []}
    token = get_token()
    bare = text[1:] if text.startswith("@") else text
    if is_handle(bare):
        return _run_handle(bare, token)
    if "://" in text or "/" in text:
        return {"status": "rejected",
                "reason": "rejected: pass a handle or a name, not a URL "
                          "(this lane never scrapes web pages; API only)",
                "findings": []}
    if len(text) <= MAX_TARGET_LEN and _NAME_RE.match(text) \
            and re.search(r"[A-Za-z]", text):
        return _run_search(text, token)
    return {"status": "rejected",
            "reason": "rejected: invalid handle; use 1-39 chars of letters, "
                      "digits or single hyphens (e.g. demo-sleuth)",
            "findings": []}
