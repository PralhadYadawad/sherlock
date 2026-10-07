"""ddg_polite adapter — keyless entity search over the DDG HTML endpoint.

Clean-room reimplementation, MIT (ours). Studied the public
``html.duckduckgo.com/html/`` response shape only (``result__a`` anchors
with ``uddg=`` redirect hrefs + ``result__snippet`` blocks). No code
copied from any scraper project.

Policy note (honest): ``research-entity-apis.md`` (2026-10-05) flags
HTML SERP scraping as excluded. This lane exists because the newer
build contract ``PLAN-entity.md`` Phase 3 (2026-10-06) explicitly orders
a paced keyless DDG lane as the default, and proceeds ONLY under strict
politeness: exactly one plain GET per ``run()``, >=3s inter-call pacing
plus jitter, identifiable Sherlock UA, no retry on 429/202 (back off),
and a 24h ``fetch_log`` cache at the tools layer so repeat queries never
re-hit DDG. If DDG starts refusing this shape, the lane degrades to
``rejected``-clean (never hallucinated results) and callers fall back to
Brave BYOK / client-side search.

Key model: keyless. No key, no env, no quota number from a vendor —
the practical cap is DDG's shared-IP throttling, which is why pacing +
cache exist. One search call per ``run()`` (``q`` only), 10s timeout,
Sherlock UA, ``Accept: text/html``.

Per-user bucket coordination: enforced in ``server/tools.py``
``throttle_check(user_id)`` (anonymous 5/min, authenticated 30/min,
60s sliding window). The orchestrator MUST gate entity searches there
before calling this lane. This module stays standalone on purpose — it
does NOT import ``tools`` or ``registry`` (the orchestrator wires this
lane next phase) — and enforces only its own inter-call pacing
(``PACING_SEC`` + jitter). Documented here, not implemented here.

Free cap / rate behavior: keyless; ``PACING_SEC = 3.0`` + up to
``JITTER_SEC = 1.0`` uniform jitter between calls (``SHERLOCK_NO_PACING=1``
skips sleeps in tests); top-10 results per query; queries capped at 500
chars (longer -> ``rejected``); 24h ``fetch_log`` cache at the tools
layer (orchestrator serves cache on exhaustion).

Failure taxonomy (never hallucinated findings):
- ``rejected`` + []: empty/non-string/over-500-char/PII-shaped input;
  429 (rate-limited) or 202 (anomaly/bot-check) with the Retry-After note
  when the upstream sends one — no retry, no hammering; other 4xx/5xx;
  timeout/network (status None).
- ``ok`` + []: HTTP 200 with zero parseable results (valid miss).
- ``ok`` + findings: parsed results. Every URL comes from a decoded
  ``uddg=`` (or direct http(s)) href — unparseable/non-http hrefs are
  skipped, never invented. Confidence is always ``low`` (a single
  snippet never identifies a person; corroborate before asserting).

Guardrails (hard): public GET only (``html.duckduckgo.com``). NO logins,
NO passwords, NO email/phone PII lanes, NO breach data, NO POSTing
forms. DUMMY/example fixtures only in tests.
"""

import os
import random
import re
import time
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urlsplit

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "ddg_polite"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied the public DDG HTML response shape only."
)

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; polite-search)"
DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
PACING_SEC = 3.0
JITTER_SEC = 1.0
MAX_RESULTS = 10
MAX_QUERY_LEN = 500

_LAST_CALL_TS = None  # monotonic timestamp of the last fetch (pacing state)

_EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")
_PHONE_RE = re.compile(r"^\+?[\d][\d\s\-().]{6,}$")
_WS_RE = re.compile(r"\s+")


def reset_pacing() -> None:
    """Clear inter-call pacing state (tests only)."""
    global _LAST_CALL_TS
    _LAST_CALL_TS = None


def _sleep(seconds: float) -> None:
    """Sleeper (monkeypatchable; SHERLOCK_NO_PACING=1 skips in tests)."""
    if os.environ.get("SHERLOCK_NO_PACING") == "1":
        return
    try:
        _sleep_raw(seconds)
    except Exception:
        pass


def _sleep_raw(seconds: float) -> None:
    """Raw sleeper (separate hook so tests never patch the time module)."""
    time.sleep(seconds)


def _now() -> float:
    """Monotonic clock (separate hook so tests never patch the time module)."""
    return time.monotonic()


def _jitter() -> float:
    """Uniform 0..JITTER_SEC extra pause (monkeypatchable in tests)."""
    try:
        return random.uniform(0, JITTER_SEC)
    except Exception:
        return 0.0


def _pace() -> None:
    """Enforce >=PACING_SEC + jitter between upstream calls. Never raises."""
    global _LAST_CALL_TS
    try:
        now = _now()
    except Exception:
        return
    try:
        last = _LAST_CALL_TS
        if last is not None:
            wait = PACING_SEC + _jitter() - (now - last)
            if wait > 0:
                _sleep(wait)
                try:
                    now = _now()
                except Exception:
                    pass
        _LAST_CALL_TS = now
    except Exception:
        try:
            _LAST_CALL_TS = _now()
        except Exception:
            pass


def build_query(target: str) -> str:
    """Normalize an entity query for the DDG ``q`` param (pass-through).

    Operator-preserving: ``site:`` / quotes assembled by the orchestrator
    playbook pass through untouched; only surrounding/duplicate whitespace
    is collapsed. Returns "" for blank input.
    """
    if not isinstance(target, str):
        return ""
    return _WS_RE.sub(" ", target.strip()).strip()


def decode_ddg_href(href) -> str:
    """Decode a DDG ``result__a`` href into a real URL, or "" when unusable.

    Accepts direct ``http(s)`` hrefs as-is. Redirect hrefs
    (``//duckduckgo.com/l/?uddg=<pct-encoded>&...`` or ``/l/?uddg=...``)
    decode via the ``uddg`` param. Anything else (relative, javascript:,
    ftp:, empty) yields "" — callers skip such rows, never invent URLs.
    """
    if not isinstance(href, str):
        return ""
    h = href.strip()
    if h.startswith("http://") or h.startswith("https://"):
        return h
    if h.startswith("//"):
        candidate = "https:" + h
    elif h.startswith("/"):
        candidate = "https://duckduckgo.com" + h
    else:
        return ""
    try:
        query = urlsplit(candidate).query
    except Exception:
        return ""
    try:
        for key, value in parse_qsl(query):
            if key == "uddg" and isinstance(value, str) and value.strip():
                try:
                    decoded = unquote(value).strip()
                except Exception:
                    continue
                if decoded.startswith("http://") \
                        or decoded.startswith("https://"):
                    return decoded
                return ""
    except Exception:
        return ""
    return ""


class _SerpParser(HTMLParser):
    """Minimal DDG-SERP parse: ``result__a`` titles + ``result__snippet``.

    Title anchors and snippet blocks are zipped by document order: each
    snippet attaches to the most recent result still missing one, so a
    result without a snippet never shifts later snippets onto the wrong
    title. Pure parse, no I/O.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []  # [{"title", "href", "snippet"}]
        self._cap = None  # (kind, tag, href, buf)

    def handle_starttag(self, tag, attrs):
        try:
            classes = ""
            href = ""
            for key, value in (attrs or []):
                if (key or "").lower() == "class" and isinstance(value, str):
                    classes = value
                elif (key or "").lower() == "href" and isinstance(value, str):
                    href = value
            names = classes.split()
            if "result__a" in names:
                self._cap = ("title", (tag or "").lower(), href, [])
            elif "result__snippet" in names:
                self._cap = ("snip", (tag or "").lower(), "", [])
        except Exception:
            pass

    def handle_endtag(self, tag):
        try:
            if not self._cap or (tag or "").lower() != self._cap[1]:
                return
            kind, _, href, buf = self._cap
            self._cap = None
            text = _WS_RE.sub(" ", "".join(buf)).strip()
            if kind == "title":
                if text and isinstance(href, str) and href.strip():
                    self.results.append(
                        {"title": text, "href": href.strip(),
                         "snippet": ""})
            else:
                if not text:
                    return
                for row in reversed(self.results):
                    if not row["snippet"]:
                        row["snippet"] = text
                        return
                # Orphan snippet (no result yet): drop, never invent a row.
        except Exception:
            pass

    def handle_data(self, data):
        try:
            if self._cap and isinstance(data, str) and data:
                self._cap[3].append(data)
        except Exception:
            pass


def parse_serp(html, limit=MAX_RESULTS):
    """Parse DDG HTML into findings (never hallucinates URLs).

    Each well-formed result yields ``result_title`` + ``result_url`` and,
    when the SERP carried one, ``result_snippet`` — all ``low``
    confidence. Rows whose href does not decode to http(s) are skipped.
    Caps at ``limit`` results. Non-string/empty input yields [].
    """
    findings = []
    if not isinstance(html, str) or not html.strip():
        return findings
    parser = _SerpParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    try:
        limit = int(limit)
    except Exception:
        limit = MAX_RESULTS
    if limit < 1:
        return findings
    for row in parser.results[:limit]:
        try:
            url = decode_ddg_href(row.get("href", ""))
        except Exception:
            url = ""
        if not url:
            continue
        title = row.get("title", "")
        if not isinstance(title, str) or not title.strip():
            continue
        findings.append(
            {"type": "result_title", "value": title.strip()[:256],
             "source": NAME, "confidence": "low"})
        findings.append(
            {"type": "result_url", "value": url.strip()[:512],
             "source": NAME, "confidence": "low"})
        snippet = row.get("snippet", "")
        if isinstance(snippet, str) and snippet.strip():
            findings.append(
                {"type": "result_snippet", "value": snippet.strip()[:512],
                 "source": NAME, "confidence": "low"})
    return findings


def _fetch_serp(query, timeout=TIMEOUT):
    """Single polite GET of the DDG HTML endpoint. Never raises.

    Returns (status:int|None, body:str, retry_after:str). ``status`` None
    means timeout/connection failure; ``retry_after`` echoes the upstream
    ``Retry-After`` header ("" when absent) so ``run()`` can note it.
    """
    if requests is None:
        return None, "", ""
    try:
        resp = requests.get(
            DDG_ENDPOINT,
            params={"q": query},
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=timeout,
        )
        try:
            status = resp.status_code
        except Exception:
            return None, "", ""
        try:
            retry_after = ""
            if resp.headers:
                retry_after = str(resp.headers.get("Retry-After", "") or "")
        except Exception:
            retry_after = ""
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        return status, body, retry_after.strip()
    except Exception:
        return None, "", ""


def _cache_hint() -> str:
    return ("serve cached 24h (orchestrator serves cache; "
            "no hallucination)")


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    if target is None or (isinstance(target, str) and not target.strip()):
        return {"status": "rejected",
                "reason": "empty target: pass a person/entity query, e.g. "
                          '"Demo Person"',
                "findings": []}
    if not isinstance(target, str):
        return {"status": "rejected",
                "reason": "rejected: invalid search target",
                "findings": []}
    text = target.strip()
    if len(text) > MAX_QUERY_LEN:
        return {"status": "rejected",
                "reason": "rejected: target over %d chars" % MAX_QUERY_LEN,
                "findings": []}
    if _EMAIL_RE.match(text):
        return {"status": "rejected",
                "reason": "rejected: email lookup is excluded (PII tool)",
                "findings": []}
    if _PHONE_RE.match(text):
        return {"status": "rejected",
                "reason": "rejected: phone lookup is excluded (PII tool)",
                "findings": []}
    query = build_query(text)
    if not query:
        return {"status": "rejected",
                "reason": "empty target: pass a person/entity query",
                "findings": []}
    _pace()  # >=3s + jitter between upstream calls (skipped in tests)
    try:
        status, body, retry_after = _fetch_serp(query)
    except Exception:
        status, body, retry_after = None, "", ""
    if status is None:
        return {"status": "rejected",
                "reason": "rejected: DDG upstream unavailable "
                          "(timeout/network; %s)" % _cache_hint(),
                "findings": []}
    if status == 429:
        note = ("retry-after %s; " % retry_after) if retry_after else ""
        return {"status": "rejected",
                "reason": "rejected: DDG rate-limited (HTTP 429; %sback "
                          "off, no retry, no hammering; %s)"
                          % (note, _cache_hint()),
                "findings": []}
    if status == 202:
        note = ("retry-after %s; " % retry_after) if retry_after else ""
        return {"status": "rejected",
                "reason": "rejected: DDG anomaly/bot-check (HTTP 202; %s"
                          "back off, no retry; %s)" % (note, _cache_hint()),
                "findings": []}
    if status == 403:
        return {"status": "rejected",
                "reason": "rejected: DDG forbidden/bot-gate (HTTP 403; "
                          "back off; %s)" % _cache_hint(),
                "findings": []}
    if status != 200:
        return {"status": "rejected",
                "reason": "rejected: DDG upstream error (HTTP %s; %s)"
                          % (status, _cache_hint()),
                "findings": []}
    try:
        findings = parse_serp(body)
    except Exception:
        findings = []
    if findings:
        n_results = len([f for f in findings if f["type"] == "result_url"])
        reason = ("ddg polite search for %s: %d result(s), %d finding(s) "
                  "(single-snippet hits are low confidence; corroborate "
                  "before asserting identity)" % (query[:64], n_results,
                                                  len(findings)))
    else:
        reason = "no ddg results for %s (no hallucination)" % query[:64]
    return {"status": "ok", "reason": reason, "findings": findings}
