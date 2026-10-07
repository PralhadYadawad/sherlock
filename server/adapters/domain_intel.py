"""domain_intel adapter — crt.sh-shaped + DNS-shaped fixture parsing.

Studied source: laramies/theHarvester docs/README only (interface pattern:
enumerate subdomains via certificate-transparency logs such as crt.sh and
join with DNS records). Clean-room reimplementation — no code copied. MIT.

Two modes (same contract):

- Fixture/demo mode (default): only ``example.com`` (and its subdomains)
  resolves to the embedded DEMO fixture offline. Any other domain is
  rejected so tests and demos never touch live third-party targets.
- Live mode (SHERLOCK_LIVE=1): any well-formed bare domain is probed via
  the crt.sh JSON API (10s timeout, Sherlock UA, 502/429-tolerant
  fallback) plus stdlib ``socket.getaddrinfo`` A-records (no binary
  needed). Failures degrade to fixture (demo domain) or ok + [] with a
  reason — never fabricated records.

Pattern: fetch crt.sh-style JSON (``[{"name_value": ...}]``), split
multi-name entries on newlines, strip ``*.`` wildcards, dedupe; join with
DNS-shaped records (A via getaddrinfo) plus an abuse/contact address
(demo fixture only; live DNS has no contact).

Free cap / rate behavior: crt.sh is a free public log with no key but it
rate-limits burst callers (and 502s under load — treated as flaky, DNS
still attempted); cache results (tools fetch_log TTL 24h) and back off
on 429/5xx. DNS uses the local resolver (no key, OS-limited).

Failure taxonomy: private/deleted/nonexistent domains, crt.sh outages
(incl. 502), and DNS NXDOMAIN all yield clean results (``ok`` with fewer
findings, or ``rejected`` for malformed/out-of-scope input in fixture
mode) — never fabricated records.

Guardrails (hard): public GET only (crt.sh). NO logins, NO passwords, NO
email/phone PII lanes, NO breach-password data, NO POSTing forms.
robots/ToS respected, pacing via single-shot queries, failures degrade
to fixture/empty with reason.
"""

import os
import re
import socket
import threading

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "domain_intel"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied laramies/theHarvester docs only."
)

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; ct+DNS intel)"

# Guards the getdefaulttimeout/setdefaulttimeout dance in _resolve_dns:
# mutating the process-global default is not thread-safe, so concurrent
# adapter runs serialize here (each still restores the previous value).
_DNS_TIMEOUT_LOCK = threading.Lock()

# Embedded DEMO fixture (DEMO-CASE-001): example.com -> 2 subdomains,
# 1 contact. Documentation TEST-NET-1 address only; no live data.
DEMO_DOMAIN = "example.com"
DEMO_CT_ROWS = [
    {"name_value": "www.example.com"},
    {"name_value": "blog.example.com\nwww.example.com"},
]
DEMO_DNS = {
    "A": ["192.0.2.1"],
    "AAAA": [],
    "CNAME": {},
    "contact": "admin@example.com",
}

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def is_live_enabled() -> bool:
    """Live intel is opt-in via SHERLOCK_LIVE=1 (else fixture mode)."""
    return os.environ.get("SHERLOCK_LIVE") == "1"


def _is_demo_domain(domain: str) -> bool:
    return domain == DEMO_DOMAIN or domain.endswith("." + DEMO_DOMAIN)


def _normalize_domain(target, live: bool = False):
    """Return (domain, error). In fixture mode only example.com passes."""
    if target is None:
        return None, "empty target: pass a bare domain such as example.com"
    text = target.strip().lower() if isinstance(target, str) else ""
    if not text:
        return None, "empty target: pass a bare domain such as example.com"
    if "://" in text or "/" in text or "@" in text:
        return None, "rejected: pass a bare domain (example.com), not a URL or email"
    if not _DOMAIN_RE.match(text):
        return None, "rejected: malformed domain; expected a bare domain like example.com"
    if not live and not _is_demo_domain(text):
        return None, (
            "rejected: demo scope is example.com only "
            "(no live third-party lookups)"
        )
    return text, None


def _fetch_crtsh(domain, timeout=TIMEOUT):
    """Query crt.sh for a domain. Returns list of rows, or None on failure.

    502/429/5xx (crt.sh is flaky under load — observed 502 from this box
    2026-10-05) returns None so callers degrade to DNS/fixture gracefully.
    Public GET only, Sherlock UA.
    """
    if requests is None:
        return None
    try:
        resp = requests.get(
            "https://crt.sh/?q=%25." + domain + "&output=json",
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, list) else None
    except Exception:
        return None


def _resolve_dns(domain, timeout=TIMEOUT):
    """Local-resolver DNS lookup via getaddrinfo. Returns dict or None.

    Stdlib only (no nslookup binary). Returns {"A": [...], "AAAA": [],
    "CNAME": {}, "contact": ""}. NXDOMAIN / timeout / any failure -> None.
    """
    try:
        with _DNS_TIMEOUT_LOCK:
            old = socket.getdefaulttimeout()
            socket.setdefaulttimeout(timeout)
            try:
                infos = socket.getaddrinfo(
                    domain, 80, family=socket.AF_INET,
                    type=socket.SOCK_STREAM)
            finally:
                socket.setdefaulttimeout(old)
        addrs = sorted({info[4][0] for info in infos if info and len(info) >= 5})
        # Keep only literal IPv4 dots (defensive; getaddrinfo AF_INET
        # already constrains this, but never trust blindly).
        v4 = [a for a in addrs
              if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", a)]
        return {"A": sorted(set(v4)), "AAAA": [], "CNAME": {}, "contact": ""}
    except Exception:
        # Fallback for resolvers/mocks that only stub gethostbyname_ex
        # (hermetic tests): try the legacy call once before giving up.
        try:
            with _DNS_TIMEOUT_LOCK:
                old = socket.getdefaulttimeout()
                socket.setdefaulttimeout(timeout)
                try:
                    _, _, addrs = socket.gethostbyname_ex(domain)
                finally:
                    socket.setdefaulttimeout(old)
            return {"A": sorted(set(addrs)), "AAAA": [],
                    "CNAME": {}, "contact": ""}
        except Exception:
            return None


def parse_ct_rows(rows, domain):
    """Parse crt.sh-shaped rows into sorted unique in-scope subdomains."""
    subs = set()
    domain = domain.lower()
    for row in rows or []:
        raw = row.get("name_value", "") if isinstance(row, dict) else ""
        for line in str(raw).splitlines():
            name = line.strip().lower().rstrip(".")
            if name.startswith("*."):
                # Wildcard cert: covered names are unknown, so skip rather
                # than invent a subdomain finding (no hallucination).
                continue
            if not name or "@" in name or " " in name:
                continue
            if name == domain or name.endswith("." + domain):
                subs.add(name)
    return sorted(subs)


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    live = is_live_enabled()
    domain, error = _normalize_domain(target, live=live)
    if error:
        return {"status": "rejected", "reason": error, "findings": []}
    try:
        ct_rows = _fetch_crtsh(domain)
    except Exception:
        ct_rows = None
    try:
        dns = _resolve_dns(domain)
    except Exception:
        dns = None
    from_fixture = False
    crt_down = ct_rows is None
    if ct_rows is None and dns is None and _is_demo_domain(domain):
        # Offline demo path: documented DEMO-CASE-001 fixture only.
        ct_rows, dns, from_fixture = DEMO_CT_ROWS, DEMO_DNS, True
    subdomains = parse_ct_rows(ct_rows, domain)
    findings = [
        {
            "type": "subdomain",
            "value": sub,
            "source": NAME,
            "confidence": "medium",
        }
        for sub in subdomains
    ]
    contact = (dns or {}).get("contact", "") if isinstance(dns, dict) else ""
    if contact and "@" in contact:
        findings.append(
            {
                "type": "contact",
                "value": contact.strip(),
                "source": NAME,
                "confidence": "low",
            }
        )
    # Live A-records: surface resolved IPv4 as low-confidence findings
    # (shape, not content, is asserted by live smoke tests).
    if live and not from_fixture and isinstance(dns, dict):
        for ip in (dns.get("A") or [])[:8]:
            findings.append(
                {
                    "type": "a_record",
                    "value": "%s -> %s" % (domain, ip),
                    "source": NAME,
                    "confidence": "low",
                }
            )
    if from_fixture:
        reason = "demo fixture (offline) for %s: %d subdomains, %d contacts" % (
            domain, len(subdomains), 1 if contact else 0)
    elif live:
        if crt_down and dns is not None:
            reason = ("live intel for %s (crt.sh unavailable/flaky, DNS only): "
                      "%d subdomains" % (domain, len(subdomains)))
        elif crt_down:
            reason = ("live intel degraded for %s (crt.sh + DNS unavailable; "
                      "no hallucination)" % domain)
        else:
            reason = "certificate-transparency + DNS intel for %s: %d subdomains" % (
                domain, len(subdomains))
    else:
        reason = "certificate-transparency + DNS intel for %s: %d subdomains" % (
            domain, len(subdomains))
    return {"status": "ok", "reason": reason, "findings": findings}
