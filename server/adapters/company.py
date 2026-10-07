"""company adapter — GLEIF LEI search + RDAP domain shape.

Studied sources: GLEIF API docs (60 req/min/user, free, keyless) + IANA
RDAP bootstrap / about.rdap.org / RFC 9224 (RDAP preferred over WHOIS:
structured, GDPR-redacted) only. Clean-room reimplementation — no code
copied. MIT (ours).

Key model: keyless. GLEIF is free with no key (60 req/min/user — paced at
~1 req/s, single-shot queries, 24h ``fetch_log`` cache at the tools
layer). RDAP is free/keyless via the public bootstrap (servers 429 on
abuse — degrade cleanly, never retry hot).

Input routing:
- 20-char LEI (``^[0-9A-Z]{20}$``) -> GLEIF LEI-record lookup.
- bare domain (``example.com``) -> RDAP (registrar + creation/expiry).
- anything else (legal name, e.g. ``"Example Corp"``) -> GLEIF legal-name
  search.

Output finding types: ``company_lei`` (the LEI itself), ``company_name``
(legal name), ``company_status`` (ACTIVE/INACTIVE/...), ``company_address``
(registered address), ``registrar`` (RDAP registrar), ``domain_date``
(RDAP creation/expiry events).

Entity-resolution rule (research-entity-apis.md §9): bare company names
collide across jurisdictions — name-only candidates are ``low``;
LEI-pinned records (jurisdiction + number identity) corroborate to
``medium``; NEVER ``high`` from metadata alone.

Free cap / rate behavior: <=2 plain GETs per ``run()`` (one lane only per
target shape), 10s timeout each, Sherlock UA, ``PACING_SEC = 1.0`` between
calls (honors the 60/min GLEIF note; ``SHERLOCK_NO_PACING=1`` skips sleeps
in tests).

Failure taxonomy: empty/PII-shaped input -> ``rejected``; 429/5xx/timeout
-> ``rejected`` with reason and ZERO findings (rejected-clean); valid
misses (GLEIF empty ``data[]``, RDAP 404) -> ``ok`` + ``[]`` with reason
— never fabricated companies, officers, or dates. Officer/director names
are personal data: this lane surfaces entity/registry fields only (no bulk
officer harvesting; DPDP purpose-limitation note in research doc §8).

Guardrails (hard): public GET only. NO logins, NO passwords, NO
email/phone PII lanes, NO breach-password data, NO POSTing forms, NO
CAPTCHA scraping (MCA India stays a human link-out — never automated
here). DUMMY/example fixtures only (``Example Corp`` /
``DUMMYLEI000000000000`` / ``example.com``).
"""

import os
import re
import time

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "company"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied GLEIF API + RDAP docs only."
)

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; company-intel)"
GLEIF_ENDPOINT = "https://api.gleif.org/api/v1/lei-records"
RDAP_ENDPOINT_TMPL = "https://rdap.org/domain/{domain}"
PACING_SEC = 1.0
MAX_RECORDS = 5

_LEI_RE = re.compile(r"^[0-9A-Z]{20}$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")
_PHONE_RE = re.compile(r"^\+?[\d][\d\s\-().]{6,}$")


def is_lei(text):
    """True when text is a 20-char LEI (digits + uppercase A-Z)."""
    return bool(_LEI_RE.match((text or "").strip().upper()))


def is_domain(text):
    """True when text is a bare domain (no URL/email parts)."""
    t = (text or "").strip().lower()
    if "://" in t or "/" in t or "@" in t or " " in t:
        return False
    return bool(_DOMAIN_RE.match(t))


def _sleep(seconds):
    """Sleeper (monkeypatchable; SHERLOCK_NO_PACING=1 skips in tests)."""
    if os.environ.get("SHERLOCK_NO_PACING") == "1":
        return
    try:
        time.sleep(seconds)
    except Exception:
        pass


def _fetch_json(url, params=None, timeout=TIMEOUT):
    """Plain no-auth GET returning (status:int|None, data:dict|None).

    Never raises. ``status`` None = timeout/connection failure. Non-200 or
    non-JSON-object bodies yield (status, None).
    """
    if requests is None:
        return None, None
    try:
        resp = requests.get(
            url, params=params or {},
            headers={"Accept": "application/json",
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


def fetch_gleif(name_or_lei, page_size=MAX_RECORDS, timeout=TIMEOUT):
    """GLEIF LEI-records query (keyless, paced at ~1 req/s upstream).

    LEI input -> ``filter[lei]`` exact lookup; name input ->
    ``filter[entity.legalName]`` search. Returns (status, data).
    """
    text = (name_or_lei or "").strip()
    if is_lei(text):
        params = {"filter[lei]": text.upper()}
    else:
        params = {"filter[entity.legalName]": text,
                  "page[size]": page_size}
    return _fetch_json(GLEIF_ENDPOINT, params=params, timeout=timeout)


def parse_gleif(data, limit=MAX_RECORDS):
    """Parse GLEIF JSON:API -> [{"lei", "legal_name", "status", "address",
    "pinned"}]. ``pinned`` is True when the record carries its own LEI id
    (medium confidence) vs name-only rows (low). Unknown shapes -> [].
    """
    out = []
    if not isinstance(data, dict):
        return out
    rows = data.get("data")
    if not isinstance(rows, list):
        return out
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        lei = row.get("id")
        attrs = row.get("attributes")
        if not isinstance(attrs, dict):
            continue
        entity = attrs.get("entity")
        if not isinstance(entity, dict):
            continue
        legal = entity.get("legalName") or {}
        lname = legal.get("name") if isinstance(legal, dict) else None
        if not isinstance(lname, str) or not lname.strip():
            continue
        status = entity.get("status")
        status = status.strip()[:64] if isinstance(status, str) \
            and status.strip() else ""
        address = ""
        addrs = entity.get("addresses") or []
        if isinstance(addrs, list):
            for a in addrs:
                if not isinstance(a, dict):
                    continue
                bits = [a.get("city"), a.get("region"), a.get("country")]
                bits = [b.strip() for b in bits
                        if isinstance(b, str) and b.strip()]
                if bits:
                    address = ", ".join(bits)[:256]
                    break
                first = a.get("addressLines") or []
                if isinstance(first, list) and first \
                        and isinstance(first[0], str):
                    address = first[0].strip()[:256]
                    break
        pinned = isinstance(lei, str) and is_lei(lei)
        out.append({"lei": lei.strip().upper() if pinned else "",
                    "legal_name": lname.strip()[:256],
                    "status": status,
                    "address": address,
                    "pinned": pinned})
    return out


def fetch_rdap(domain, timeout=TIMEOUT):
    """RDAP lookup for a bare domain (keyless, redacted-by-default)."""
    return _fetch_json(
        RDAP_ENDPOINT_TMPL.format(domain=domain.strip().lower()),
        timeout=timeout,
    )


def parse_rdap(data):
    """Parse RDAP JSON -> {"registrar": str, "dates": [(action, date)]}.

    Reads ``entities`` (registrar role / vCard fn) + ``events`` (creation /
    expiration / last changed). Missing/redacted sections yield "" / [] —
    never invented. Unknown shapes yield the empty mapping.
    """
    empty = {"registrar": "", "dates": []}
    if not isinstance(data, dict):
        return empty
    registrar = ""
    for ent in (data.get("entities") or []):
        if not isinstance(ent, dict):
            continue
        roles = ent.get("roles") or []
        vcard = ent.get("vcardArray") or []
        fn = ""
        if isinstance(vcard, list) and len(vcard) == 2 \
                and isinstance(vcard[1], list):
            for item in vcard[1]:
                if isinstance(item, list) and len(item) >= 4 \
                        and item[0] == "fn":
                    fn = item[3] if isinstance(item[3], str) else ""
                    break
        if "registrar" in [str(r).lower() for r in roles
                           if isinstance(r, str)]:
            if fn.strip():
                registrar = fn.strip()[:256]
                break
            handle = ent.get("handle")
            if isinstance(handle, str) and handle.strip():
                registrar = handle.strip()[:256]
                break
    if not registrar:
        for key in ("registrar", "registrarName"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                registrar = val.strip()[:256]
                break
    dates = []
    for ev in (data.get("events") or []):
        if not isinstance(ev, dict):
            continue
        action = ev.get("eventAction")
        date = ev.get("eventDate")
        if isinstance(action, str) and isinstance(date, str) \
                and action.strip() and date.strip():
            a = action.strip().lower()
            if a in ("registration", "creation", "expiration",
                     "last changed", "last update of rdap database"):
                dates.append((action.strip()[:32], date.strip()[:32]))
        if len(dates) >= 4:
            break
    return {"registrar": registrar, "dates": dates}


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    if target is None or (isinstance(target, str) and not target.strip()):
        return {"status": "rejected",
                "reason": "empty target: pass a legal name "
                          '(e.g. "Example Corp"), an LEI, or a bare domain '
                          "(e.g. example.com)",
                "findings": []}
    if not isinstance(target, str):
        return {"status": "rejected",
                "reason": "rejected: invalid company target",
                "findings": []}
    text = target.strip()
    if len(text) > 256:
        return {"status": "rejected",
                "reason": "rejected: target over 256 chars",
                "findings": []}
    if _EMAIL_RE.match(text):
        return {"status": "rejected",
                "reason": "rejected: email-to-company lookup is excluded "
                          "(PII tool)",
                "findings": []}
    if _PHONE_RE.match(text):
        return {"status": "rejected",
                "reason": "rejected: phone-to-company lookup is excluded "
                          "(PII tool)",
                "findings": []}

    # Route: domain -> RDAP lane; LEI / legal name -> GLEIF lane.
    if is_domain(text):
        try:
            status, data = fetch_rdap(text.lower())
        except Exception:
            status, data = None, None
        if status is None:
            return {"status": "rejected",
                    "reason": "rejected: RDAP upstream unavailable "
                              "(timeout/network; no hallucination)",
                    "findings": []}
        if status == 429:
            return {"status": "rejected",
                    "reason": "rejected: RDAP rate-limited (HTTP 429; "
                              "back off, cached 24h)",
                    "findings": []}
        if status == 404:
            return {"status": "ok",
                    "reason": "no RDAP record for %s (not found; "
                              "no hallucination)" % text.lower(),
                    "findings": []}
        if status != 200 or not isinstance(data, dict):
            return {"status": "rejected",
                    "reason": "rejected: RDAP upstream error (HTTP %s; "
                              "no hallucination)" % status,
                    "findings": []}
        try:
            parsed = parse_rdap(data)
        except Exception:
            parsed = {"registrar": "", "dates": []}
        findings = []
        if parsed["registrar"]:
            findings.append(
                {"type": "registrar",
                 "value": "registrar: %s (%s)" % (parsed["registrar"],
                                                  text.lower()),
                 "source": NAME, "confidence": "medium"})
        for action, date in parsed["dates"]:
            findings.append(
                {"type": "domain_date",
                 "value": "%s: %s -> %s" % (text.lower(), action, date),
                 "source": NAME, "confidence": "medium"})
        if findings:
            reason = ("RDAP intel for %s: %d finding(s) (redacted registry "
                      "data; registrar + event dates only)"
                      % (text.lower(), len(findings)))
        else:
            reason = ("RDAP record for %s has no registrar/date fields "
                      "(redacted; no hallucination)" % text.lower())
        return {"status": "ok", "reason": reason, "findings": findings}

    # GLEIF lane (legal name or LEI).
    lei_lookup = is_lei(text)
    query = text.upper() if lei_lookup else text
    try:
        status, data = fetch_gleif(query)
    except Exception:
        status, data = None, None
    _sleep(PACING_SEC)  # honor the 60/min GLEIF note (skipped in tests)
    if status is None:
        return {"status": "rejected",
                "reason": "rejected: GLEIF upstream unavailable "
                          "(timeout/network; no hallucination)",
                "findings": []}
    if status == 429:
        return {"status": "rejected",
                "reason": "rejected: GLEIF rate-limited (HTTP 429, 60/min "
                          "note; back off, cached 24h)",
                "findings": []}
    if status != 200 or not isinstance(data, dict):
        return {"status": "rejected",
                "reason": "rejected: GLEIF upstream error (HTTP %s; "
                          "no hallucination)" % status,
                "findings": []}
    try:
        records = parse_gleif(data)
    except Exception:
        records = []
    if not records:
        return {"status": "ok",
                "reason": "no LEI records for %s (no hallucination)"
                          % query[:64],
                "findings": []}
    findings = []
    for rec in records:
        conf = "medium" if rec["pinned"] else "low"
        if rec["pinned"]:
            findings.append(
                {"type": "company_lei", "value": rec["lei"],
                 "source": NAME, "confidence": conf})
        findings.append(
            {"type": "company_name",
             "value": rec["legal_name"]
             + (" [%s]" % rec["lei"] if rec["pinned"] else ""),
             "source": NAME, "confidence": conf})
        if rec["status"]:
            findings.append(
                {"type": "company_status",
                 "value": "%s: %s" % (rec["legal_name"][:64], rec["status"]),
                 "source": NAME, "confidence": "low"})
        if rec["address"]:
            findings.append(
                {"type": "company_address",
                 "value": "%s: %s" % (rec["legal_name"][:64], rec["address"]),
                 "source": NAME, "confidence": "low"})
    for f in findings:  # metadata alone never reaches high
        if f["confidence"] not in ("low", "medium"):
            f["confidence"] = "low"
    n_pinned = sum(1 for r in records if r["pinned"])
    reason = ("GLEIF intel for %s: %d record(s) (%d LEI-pinned), %d "
              "finding(s) (name-only candidates low; LEI-pinned medium; "
              "never high from metadata alone)"
              % (query[:64], len(records), n_pinned, len(findings)))
    return {"status": "ok", "reason": reason, "findings": findings}
