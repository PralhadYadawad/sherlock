"""websearch adapter — Brave Search API shape, per-user-key (BYOK) only.

Studied source: Brave Search API docs + pricing pages only (interface
pattern: ``q, count, country`` -> ``web.results[{title,url,description}]``;
auth header ``X-Subscription-Token``). Clean-room reimplementation — no
code copied. MIT (ours).

Key model: BYOK via the ``SHERLOCK_BRAVE_KEY`` environment variable (each
operator pastes their own free-tier key; ``DUMMY_...`` placeholders never
authenticate). No key (or a ``DUMMY_`` placeholder) -> ``rejected`` with a
``missing_key`` reason and ZERO network calls. The key is never logged.

Query builder: the person/company name is double-quoted (homonym control)
with optional affiliation and ``site:`` hints appended, e.g.
``"Demo Person" "Example University" site:example.com``.

Response parsing: Brave-shaped JSON ``{"web": {"results": [...]}}`` is
parsed into per-result findings of type ``result_title`` / ``result_url`` /
``result_snippet`` (all ``low`` confidence — a single snippet never
identifies a person; see research-entity-apis.md grade notes: require >=2
corroborating signals before ``medium``).

Free cap / rate behavior: vendor free tier is ~$5 credit/mo (~1,000 Search
queries at $5.00/1,000; old no-card free plan removed ~Feb 2026 — verify at
signup). One search call per ``run()`` (``count`` <= 5), 10s timeout,
Sherlock UA, server-called + 24h ``fetch_log`` cache (tools layer). Clean
FAIL on 401 (bad key) / 402 (quota exhausted) / 429 / 5xx.

Failure taxonomy: missing key, empty/PII-shaped input, bad-key, quota,
rate-limit, flaky upstream, and zero-result searches all return clean
results — ``rejected`` (errors) or ``ok`` + ``[]`` (valid empty) — never
fabricated results.

Guardrails (hard): public GET only (api.search.brave.com). NO logins, NO
passwords, NO email/phone PII lanes, NO breach-password data, NO POSTing
forms, NO SERP scraping.
"""

import os
import re

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "websearch"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied Brave Search API docs only."
)

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; web-search)"
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
ENV_KEY = "SHERLOCK_BRAVE_KEY"
MAX_RESULTS = 5
DEFAULT_COUNTRY = "IN"

_EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")
_PHONE_RE = re.compile(r"^\+?[\d][\d\s\-().]{6,}$")


def get_api_key():
    """Return the operator's Brave key, or '' when absent/placeholder.

    ``DUMMY_...`` placeholders (repo policy: no live keys committed) are
    treated as missing so tests and demos never authenticate.
    """
    try:
        key = os.environ.get(ENV_KEY, "") or ""
    except Exception:
        return ""
    key = key.strip()
    if not key or key.upper().startswith("DUMMY"):
        return ""
    return key


def build_query(name, affiliation="", site=""):
    """Build a Brave ``q`` string: quoted name + hints.

    - ``name`` is always double-quoted (homonym control; exact-phrase).
    - ``affiliation`` (employer/university) is appended quoted when given.
    - ``site`` appends a ``site:<host>`` operator when given (bare host).
    Internal quotes are stripped so the query cannot break quoting.
    """
    base = (name or "").strip().replace('"', "").strip()
    if not base:
        return ""
    parts = ['"%s"' % base]
    aff = (affiliation or "").strip().replace('"', "").strip()
    if aff:
        parts.append('"%s"' % aff)
    host = (site or "").strip().lower().replace('"', "").strip()
    host = re.sub(r"^https?://", "", host).split("/")[0].strip()
    if host:
        parts.append("site:%s" % host)
    return " ".join(parts)


def _split_target(target):
    """Split ``Name | Affiliation`` / ``Name @ Affiliation`` forms.

    Returns (name, affiliation). Plain names yield ("<name>", "").
    """
    text = (target or "").strip()
    for sep in (" | ", " @ "):
        if sep in text:
            name, aff = text.split(sep, 1)
            return name.strip(), aff.strip()
    lowered = text.lower()
    for sep in (" at ", " with "):
        if sep in lowered:
            idx = lowered.index(sep)
            return text[:idx].strip(), text[idx + len(sep):].strip()
    return text, ""


def _is_pii_shaped(text):
    lowered = text.strip().lower()
    if _EMAIL_RE.match(text.strip()):
        return "rejected: email-to-account lookup is excluded (PII tool)"
    if _PHONE_RE.match(text.strip()):
        return "rejected: phone-to-account lookup is excluded (PII tool)"
    return None


def _fetch_brave(query, api_key, count=MAX_RESULTS, country=DEFAULT_COUNTRY,
                 timeout=TIMEOUT):
    """GET the Brave Search API. Returns (status:int|None, data:dict|None).

    Public GET only, 10s timeout, Sherlock UA. Never raises. ``status`` is
    None on timeout/connection failure; ``data`` is a dict only on
    JSON-object responses (else None) so callers never parse garbage.
    """
    if requests is None:
        return None, None
    try:
        resp = requests.get(
            BRAVE_ENDPOINT,
            params={"q": query, "count": count, "country": country},
            headers={"X-Subscription-Token": api_key,
                     "Accept": "application/json",
                     "User-Agent": USER_AGENT},
            timeout=timeout,
        )
        status = resp.status_code
        if status != 200:
            return status, None
        try:
            data = resp.json()
        except Exception:
            return status, None
        return status, data if isinstance(data, dict) else None
    except Exception:
        return None, None


def parse_brave_results(data, limit=MAX_RESULTS):
    """Parse Brave-shaped JSON into findings (never hallucinates).

    Accepts ``{"web": {"results": [{title, url, description}]}}``. Each
    well-formed result yields up to three findings (``result_title``,
    ``result_url``, ``result_snippet``), all ``low`` confidence. Rows with
    no usable title+url are skipped (never invented). Caps at ``limit``.
    """
    findings = []
    if not isinstance(data, dict):
        return findings
    web = data.get("web")
    if not isinstance(web, dict):
        return findings
    results = web.get("results")
    if not isinstance(results, list):
        return findings
    for row in results[:limit]:
        if not isinstance(row, dict):
            continue
        title = row.get("title")
        url = row.get("url")
        desc = row.get("description", "")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue
        if not (url.strip().startswith("http://")
                or url.strip().startswith("https://")):
            continue
        findings.append(
            {"type": "result_title", "value": title.strip()[:256],
             "source": NAME, "confidence": "low"}
        )
        findings.append(
            {"type": "result_url", "value": url.strip()[:512],
             "source": NAME, "confidence": "low"}
        )
        if isinstance(desc, str) and desc.strip():
            findings.append(
                {"type": "result_snippet", "value": desc.strip()[:512],
                 "source": NAME, "confidence": "low"}
            )
    return findings


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    if target is None or (isinstance(target, str) and not target.strip()):
        return {"status": "rejected",
                "reason": "empty target: pass a person or company name "
                          'in quotes, e.g. "Demo Person"',
                "findings": []}
    if not isinstance(target, str):
        return {"status": "rejected",
                "reason": "rejected: invalid search target",
                "findings": []}
    text = target.strip()
    if len(text) > 256:
        return {"status": "rejected",
                "reason": "rejected: target over 256 chars",
                "findings": []}
    pii_reason = _is_pii_shaped(text)
    if pii_reason:
        return {"status": "rejected", "reason": pii_reason, "findings": []}
    api_key = get_api_key()
    if not api_key:
        # BYOK gate: never touch the network without an operator key.
        return {"status": "rejected",
                "reason": "missing_key: set %s with your own Brave Search "
                          "API key (BYOK free tier); no key, no call"
                          % ENV_KEY,
                "findings": []}
    name, affiliation = _split_target(text)
    if not name:
        return {"status": "rejected",
                "reason": "empty target: pass a person or company name",
                "findings": []}
    query = build_query(name, affiliation)
    if not query:
        return {"status": "rejected",
                "reason": "empty target: pass a person or company name",
                "findings": []}
    try:
        status, data = _fetch_brave(query, api_key)
    except Exception:
        status, data = None, None
    if status is None:
        return {"status": "rejected",
                "reason": "rejected: search upstream unavailable "
                          "(timeout/network; no hallucination)",
                "findings": []}
    if status in (401, 403):
        return {"status": "rejected",
                "reason": "rejected: invalid Brave key (HTTP %d; check %s)"
                          % (status, ENV_KEY),
                "findings": []}
    if status == 402:
        return {"status": "rejected",
                "reason": "rejected: Brave quota exhausted (HTTP 402; "
                          "free $5 credit/mo — retry next cycle)",
                "findings": []}
    if status == 429:
        return {"status": "rejected",
                "reason": "rejected: Brave rate-limited (HTTP 429; "
                          "back off, cached 24h)",
                "findings": []}
    if status == 422:
        return {"status": "rejected",
                "reason": "rejected: bad search query (HTTP 422)",
                "findings": []}
    if status != 200 or not isinstance(data, dict):
        return {"status": "rejected",
                "reason": "rejected: search upstream error (HTTP %s; "
                          "no hallucination)" % status,
                "findings": []}
    try:
        findings = parse_brave_results(data)
    except Exception:
        findings = []
    if findings:
        n_results = len([f for f in findings if f["type"] == "result_url"])
        reason = ("web search for %s: %d result(s), %d finding(s) "
                  "(single-snippet hits are low confidence; corroborate "
                  "before asserting identity)" % (query, n_results,
                                                  len(findings)))
    else:
        reason = "no web results for %s (no hallucination)" % query
    return {"status": "ok", "reason": reason, "findings": findings}
