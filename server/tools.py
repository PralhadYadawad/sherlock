"""MCP tools: triage_target, probe_username, intel_domain, save_reel,
search_memory, case_summary.

Rules: strict validation (caps, enums, pagination max 50), structured
errors, and NO hallucination — unknown targets return empty findings plus
a reason string. Demo data only (example.com / @demo.*).
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid

try:  # package import when server/ is a package
    from . import correlate, registry
except ImportError:  # direct file layout without __init__.py
    import importlib.util as _ilu
    import os as _os

    def _load_sibling(_name: str):
        _path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                              _name + ".py")
        _spec = _ilu.spec_from_file_location("sherlock_server_" + _name,
                                             _path)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        return _mod

    correlate = _load_sibling("correlate")
    registry = _load_sibling("registry")

# Guarded entity import (orchestrator crew): entity.py is pure/stdlib, but
# tools must never crash when it is absent (packaging-verify + hermetic).
entity = None
try:
    from . import entity as entity  # type: ignore
except Exception:
    try:
        entity = _load_sibling("entity")
        if not callable(getattr(entity, "split_homonyms", None)):
            entity = None
    except Exception:
        entity = None

MAX_TARGET_LEN = 512
MAX_QUERY_LEN = 256
MAX_LIMIT = 50
DEFAULT_LIMIT = 10

KIND_ENUM = ("auto", "username", "domain", "reel", "file")

_HANDLE_RE = re.compile(r"^@?[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
    r"(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.[A-Za-z]{2,}$")
_REEL_RE = re.compile(
    r"^https?://(www\.)?instagram\.com/reel/[A-Za-z0-9_-]+/?(\?.*)?$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d][\d\s().-]{6,24}$")

DEMO_HANDLE = "@demo.sleuth"
DEMO_DOMAIN = "example.com"
DEMO_REEL_ID = "DMYosint001"

# Live cache: sqlite fetch_log TTL 24h for live hits (avoid re-hammering).
# Cache key = adapter + target (exact match). Demo fixtures bypass the
# cache (always deterministic); only SHERLOCK_LIVE=1 non-demo targets use
# it. See docs/LIVE.md.
FETCH_CACHE_TTL_S = 24 * 3600


def is_live_enabled() -> bool:
    """Live lanes are opt-in via SHERLOCK_LIVE=1 (else fixture mode)."""
    return os.environ.get("SHERLOCK_LIVE") == "1"


def live_case_id(adapter: str, target: str) -> str:
    """Deterministic per-target case id for live findings."""
    safe = re.sub(r"[^A-Za-z0-9._@-]", "_", (target or "").strip()[:96])
    return "LIVE-%s-%s" % (adapter, safe or "unknown")


def _parse_db_ts(value: str):
    """Parse sqlite/UTC timestamps used by fetch_log.created_at."""
    if not isinstance(value, str) or not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S"):
        try:
            return time.mktime(time.strptime(value, fmt))
        except (ValueError, OverflowError):
            continue
    return None


def fetch_cache_lookup(adapter: str, target: str,
                       ttl_s: int = FETCH_CACHE_TTL_S,
                       path: str | None = None):
    """Return the freshest fetch_log row for adapter+target, or None.

    Fresh = created_at within ttl_s. Never raises; DB errors -> None
    (callers fall through to a live fetch, never crash).
    """
    try:
        conn = get_db(path)
        try:
            row = conn.execute(
                "SELECT adapter, target, status, reason, created_at"
                " FROM fetch_log WHERE adapter=? AND target=?"
                " ORDER BY rowid DESC LIMIT 1",
                (adapter, target)).fetchone()
            if row is None:
                return None
            ts = _parse_db_ts(row["created_at"])
            if ts is None:
                return None
            if time.time() - ts > ttl_s:
                return None
            return dict(row)
        finally:
            conn.close()
    except Exception:
        return None


def get_live_findings(case_id: str, path: str | None = None) -> list:
    """Read back persisted live findings for a live case id."""
    try:
        conn = get_db(path)
        try:
            rows = conn.execute(
                "SELECT type, value, source, confidence FROM findings"
                " WHERE case_id=? ORDER BY rowid LIMIT 500",
                (case_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []

TOOL_SCHEMAS = [
    {"name": "triage_target",
     "description": "Classify a target and route it to the right lane.",
     "input": {"target": "str", "kind": "auto|username|domain|reel|file"}},
    {"name": "probe_username",
     "description": "Public presence probe for a demo handle.",
     "input": {"handle": "str"}},
    {"name": "intel_domain",
     "description": "Public domain intel for a demo domain.",
     "input": {"domain": "str"}},
    {"name": "save_reel",
     "description": "Save public reel metadata for a demo reel URL.",
     "input": {"url": "str"}},
    {"name": "search_memory",
     "description": "Keyword search over cached findings.",
     "input": {"query": "str", "limit": "int<=50", "offset": "int>=0"}},
    {"name": "case_summary",
     "description": "Summarize a case from cached findings.",
     "input": {"case_id": "str", "limit": "int<=50", "offset": "int>=0"}},
]


def _err(reason: str, field: str | None = None, **extra) -> dict:
    out = {"status": "rejected", "reason": reason, "findings": []}
    if field:
        out["field"] = field
    out.update(extra)
    return out


def _empty(reason: str, **extra) -> dict:
    out = {"status": "ok", "reason": reason, "findings": []}
    out.update(extra)
    return out


def validate_pagination(limit=DEFAULT_LIMIT, offset=0):
    """Return (limit, offset) or an error dict."""
    if isinstance(limit, bool) or isinstance(offset, bool):
        return _err("limit/offset must be integers, not booleans",
                    field="limit" if isinstance(limit, bool) else "offset")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return _err("limit must be an integer", field="limit")
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        return _err("offset must be an integer", field="offset")
    if limit < 1 or limit > MAX_LIMIT:
        return _err("limit must be 1..%d" % MAX_LIMIT, field="limit")
    if offset < 0:
        return _err("offset must be >= 0", field="offset")
    return (limit, offset)


def _check_pii(text: str):
    """Refuse email/phone lookups (PII tools permanently excluded)."""
    t = (text or "").strip()
    if _EMAIL_RE.match(t) and not t.lower().endswith("@example.com"):
        return _err("email-to-account lookups are excluded (PII)",
                    field="target")
    if _PHONE_RE.match(t):
        return _err("phone lookups are excluded (PII)", field="target")
    return None


def db_path() -> str:
    return os.environ.get("SHERLOCK_DB", "/tmp/opencode/sherlock.db")


def get_db(path: str | None = None) -> sqlite3.Connection:
    p = path or db_path()
    if p != ":memory:":
        parent = os.path.dirname(p)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    # Mirror supabase/schema.sql (sqlite spelling): same tables, same
    # UNIQUE + CHECK constraints, so the fallback enforces what Supabase
    # enforces. Code always supplies created_at; the CURRENT_TIMESTAMP
    # default (valid in both sqlite and Postgres) is a backstop only.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS findings("
        "id TEXT PRIMARY KEY, case_id TEXT NOT NULL, type TEXT NOT NULL, "
        "value TEXT NOT NULL, source TEXT NOT NULL, "
        "confidence TEXT NOT NULL "
        "CHECK (confidence IN ('high', 'medium', 'low')), "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "UNIQUE(case_id, type, value))")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS targets("
        "id TEXT PRIMARY KEY, case_id TEXT, kind TEXT NOT NULL, "
        "label TEXT NOT NULL, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS fetch_log("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, adapter TEXT NOT NULL, "
        "target TEXT NOT NULL, status TEXT NOT NULL, "
        "reason TEXT NOT NULL DEFAULT '', "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    return conn


def persist_findings(case_id: str, findings: list,
                     path: str | None = None) -> int:
    """Idempotent persist (INSERT OR IGNORE). Returns rows present."""
    conn = get_db(path)
    try:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for f in findings or []:
            c = correlate.normalize_finding(f)
            if c is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO findings("
                "id, case_id, type, value, source, confidence, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), case_id, c["type"], c["value"],
                 c["source"], c["confidence"], now))
        conn.commit()
        cur = conn.execute("SELECT COUNT(*) AS n FROM findings WHERE case_id=?",
                           (case_id,))
        return int(cur.fetchone()["n"])
    finally:
        conn.close()


def log_fetch(adapter: str, target: str, status: str, reason: str,
              path: str | None = None) -> None:
    try:
        conn = get_db(path)
        try:
            conn.execute(
                "INSERT INTO fetch_log(adapter, target, status, reason,"
                " created_at) VALUES(?,?,?,?,?)",
                (adapter, (target or "")[:512], status, (reason or "")[:512],
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _detect_kind(target: str) -> str:
    t = target.strip()
    if _REEL_RE.match(t):
        return "reel"
    if t.startswith("@"):
        return "username"
    low = t.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return "reel" if "instagram.com/reel/" in low else "domain"
    bare = t
    if "." in bare and " " not in t and _DOMAIN_RE.match(bare.lower()):
        return "domain"
    return "username"


# ---------------------------------------------------------------- tools

def triage_target(target: str, kind: str = "auto") -> dict:
    if not isinstance(target, str) or not target.strip():
        return _err("target must be a non-empty string", field="target")
    t = target.strip()
    if len(t) > MAX_TARGET_LEN:
        return _err("target exceeds %d chars" % MAX_TARGET_LEN,
                    field="target")
    if kind not in KIND_ENUM:
        return _err("kind must be one of %s" % "|".join(KIND_ENUM),
                    field="kind")
    pii = _check_pii(t)
    if pii:
        return pii
    lane = kind if kind != "auto" else _detect_kind(t)
    adapter = {"username": "username_probe", "domain": "domain_intel",
               "reel": "oembed_public", "file": "exif_local"}[lane]
    return {"status": "ok", "reason": "routed", "lane": lane,
            "adapter": adapter, "target": t, "findings": []}


def probe_username(handle: str) -> dict:
    if not isinstance(handle, str) or not handle.strip():
        return _err("handle must be a non-empty string", field="handle")
    h = handle.strip()
    if len(h) > 128:
        return _err("handle exceeds 128 chars", field="handle")
    pii = _check_pii(h)
    if pii:
        return pii
    if not _HANDLE_RE.match(h):
        return _err("invalid handle format", field="handle")
    bare = h[1:] if h.startswith("@") else h
    is_demo = (bare == "demo.sleuth" or bare.startswith("demo."))
    if not is_demo and not is_live_enabled():
        return _empty("no public-presence data for %s; demo covers @demo.* "
                      "only (no hallucination)" % h, handle=h)
    if not is_demo and is_live_enabled():
        # Live lane: sqlite fetch_log TTL 24h cache (key adapter+target).
        cached = fetch_cache_lookup("username_probe", h)
        live_cid = live_case_id("username_probe", h)
        if cached is not None and cached.get("status") == "ok":
            findings = correlate.rank_findings(get_live_findings(live_cid))
            return {"status": "ok",
                    "reason": "cached live hit (TTL 24h, no re-fetch)",
                    "handle": h, "case_id": live_cid,
                    "findings": findings}
        res = registry.run_adapter("username_probe", h)
        log_fetch("username_probe", h, res.get("status", ""),
                  res.get("reason", ""))
        if res.get("status") != "ok":
            return _empty(res.get("reason", "probe failed"), handle=h)
        findings = correlate.rank_findings(res.get("findings", []))
        persist_findings(live_cid, findings)
        return {"status": "ok", "reason": res.get("reason", "ok"),
                "handle": h, "case_id": live_cid, "findings": findings}
    res = registry.run_adapter("username_probe", h)
    log_fetch("username_probe", h, res.get("status", ""),
              res.get("reason", ""))
    if res.get("status") != "ok":
        return _empty(res.get("reason", "probe failed"), handle=h)
    findings = correlate.rank_findings(res.get("findings", []))
    persist_findings(correlate.DEMO_CASE_ID, findings)
    return {"status": "ok", "reason": res.get("reason", "ok"), "handle": h,
            "case_id": correlate.DEMO_CASE_ID, "findings": findings}


def intel_domain(domain: str) -> dict:
    if not isinstance(domain, str) or not domain.strip():
        return _err("domain must be a non-empty string", field="domain")
    d = domain.strip().lower()
    if len(d) > 253:
        return _err("domain exceeds 253 chars", field="domain")
    pii = _check_pii(d)
    if pii:
        return pii
    d = d.split("://")[-1].split("/")[0].split(":")[0]
    if not _DOMAIN_RE.match(d):
        return _err("invalid domain format", field="domain")
    is_demo = (d == "example.com" or d.endswith(".example.com"))
    if not is_demo and not is_live_enabled():
        return _empty("no intel for %s; demo covers example.com only "
                      "(no hallucination)" % d, domain=d)
    if not is_demo and is_live_enabled():
        cached = fetch_cache_lookup("domain_intel", d)
        live_cid = live_case_id("domain_intel", d)
        if cached is not None and cached.get("status") == "ok":
            findings = correlate.rank_findings(get_live_findings(live_cid))
            return {"status": "ok",
                    "reason": "cached live hit (TTL 24h, no re-fetch)",
                    "domain": d, "case_id": live_cid,
                    "findings": findings}
        res = registry.run_adapter("domain_intel", d)
        log_fetch("domain_intel", d, res.get("status", ""),
                  res.get("reason", ""))
        if res.get("status") != "ok":
            return _empty(res.get("reason", "intel failed"), domain=d)
        findings = correlate.rank_findings(res.get("findings", []))
        persist_findings(live_cid, findings)
        return {"status": "ok", "reason": res.get("reason", "ok"),
                "domain": d, "case_id": live_cid, "findings": findings}
    res = registry.run_adapter("domain_intel", d)
    log_fetch("domain_intel", d, res.get("status", ""), res.get("reason", ""))
    if res.get("status") != "ok":
        return _empty(res.get("reason", "intel failed"), domain=d)
    findings = correlate.rank_findings(res.get("findings", []))
    persist_findings(correlate.DEMO_CASE_ID, findings)
    return {"status": "ok", "reason": res.get("reason", "ok"), "domain": d,
            "case_id": correlate.DEMO_CASE_ID, "findings": findings}


def save_reel(url: str, author: str | None = None) -> dict:
    if not isinstance(url, str) or not url.strip():
        return _err("url must be a non-empty string", field="url")
    u = url.strip()
    if len(u) > MAX_TARGET_LEN:
        return _err("url exceeds %d chars" % MAX_TARGET_LEN, field="url")
    if not _REEL_RE.match(u):
        return _err("url must be a public instagram.com/reel/ link",
                    field="url")
    if DEMO_REEL_ID not in u:
        return _empty("unknown reel; demo covers %s only "
                      "(no hallucination)" % DEMO_REEL_ID, url=u)
    res = registry.run_adapter("oembed_public", u)
    log_fetch("oembed_public", u, res.get("status", ""), res.get("reason", ""))
    if res.get("status") != "ok":
        return _empty(res.get("reason", "reel fetch failed"), url=u)
    findings = correlate.rank_findings(res.get("findings", []))
    persist_findings(correlate.DEMO_CASE_ID, findings)
    return {"status": "ok", "reason": res.get("reason", "ok"), "url": u,
            "author": author or "@demo.archivist",
            "case_id": correlate.DEMO_CASE_ID, "findings": findings}


def _demo_case_bundle() -> dict:
    u = registry.run_adapter("username_probe", DEMO_HANDLE)
    d = registry.run_adapter("domain_intel", DEMO_DOMAIN)
    r = registry.run_adapter(
        "oembed_public",
        "https://www.instagram.com/reel/%s/" % DEMO_REEL_ID)
    return correlate.build_demo_case(u.get("findings", []),
                                     d.get("findings", []),
                                     r.get("findings", []))


def _cached_findings(limit: int = 5000) -> list:
    try:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT type, value, source, confidence FROM findings"
                " ORDER BY rowid LIMIT ?", (int(limit),)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def search_memory(query: str, limit: int = DEFAULT_LIMIT,
                  offset: int = 0) -> dict:
    if not isinstance(query, str) or not query.strip():
        return _err("query must be a non-empty string", field="query")
    q = query.strip()
    if len(q) > MAX_QUERY_LEN:
        return _err("query exceeds %d chars" % MAX_QUERY_LEN, field="query")
    pg = validate_pagination(limit, offset)
    if isinstance(pg, dict):
        return pg
    lim, off = pg
    demo = _demo_case_bundle()
    ranked = correlate.search_cases(q, [demo])
    if not ranked:
        # fall back to cached-row substring match
        rows = [f for f in _cached_findings()
                if q.lower() in ("%s %s" % (f.get("type", ""),
                                            f.get("value", ""))).lower()]
        total = len(rows)
        page = rows[off:off + lim]
        if not page:
            return {"status": "ok", "reason": "no matches", "query": q,
                    "total": 0, "limit": lim, "offset": off,
                    "results": [], "findings": []}
        return {"status": "ok", "reason": "%d match(es)" % total,
                "query": q, "total": total, "limit": lim, "offset": off,
                "results": [{"case_id": correlate.DEMO_CASE_ID,
                             "match": f} for f in page], "findings": page}
    top = ranked[0]
    findings = top.get("findings", [])
    total = 1
    page_cases = [top][off:off + lim]
    return {"status": "ok", "reason": "top-1 %s" % top.get("case_id"),
            "query": q, "total": total, "limit": lim, "offset": off,
            "results": [{"case_id": c.get("case_id"),
                         "title": c.get("title"),
                         "lanes": c.get("lanes"),
                         "finding_count": c.get("finding_count")} for c in
                        page_cases],
            "findings": findings[off:off + lim],
            "top_case": top.get("case_id")}


def case_summary(case_id: str, limit: int = DEFAULT_LIMIT,
                 offset: int = 0) -> dict:
    if not isinstance(case_id, str) or not case_id.strip():
        return _err("case_id must be a non-empty string", field="case_id")
    cid = case_id.strip()
    if len(cid) > 128:
        return _err("case_id exceeds 128 chars", field="case_id")
    pg = validate_pagination(limit, offset)
    if isinstance(pg, dict):
        return pg
    lim, off = pg
    if cid != correlate.DEMO_CASE_ID:
        return _err("unknown case_id %r (no hallucination)" % cid,
                    field="case_id")
    demo = _demo_case_bundle()
    findings = demo.get("findings", [])
    total = len(findings)
    page = findings[off:off + lim]
    return {"status": "ok", "reason": "summary", "case_id": cid,
            "title": demo.get("title"), "lanes": demo.get("lanes"),
            "total": total, "limit": lim, "offset": off,
            "findings": page}


# ---------------- entity_search orchestration (orchestrator crew) ----------------
# Flow: entity.normalize variants -> parallel lane runs (username_probe on
# derived handles, websearch, scholar, page_reader over found URLs capped 5,
# domain/company when affiliation found) -> entity.split_homonyms -> case file.
# Login-required product assumes user_id present; anonymous -> strictest bucket.
# Respects SHERLOCK_LIVE gating for network lanes; offline -> fixtures + reason.

_THROTTLE_BUCKETS: dict = {}
THROTTLE_WINDOW_S = 60
THROTTLE_LIMIT_ANON = 5
THROTTLE_LIMIT_USER = 30
THROTTLE_BUCKETS_MAX_CLIENTS = 10000

_MAX_ENTITY_NAME_LEN = 256
_MAX_VARIANT_LANES = 5
_MAX_PAGE_URLS = 5

# Deep-lane routing (fast/deep streams share one case file).
# fast = current behavior (30-site username_probe + websearch/scholar lanes).
# deep = fast PLUS a bounded deep_probe sweep per derived handle.
# Deep runs SYNC (no background jobs in v1): each sweep covers ~120 sites
# and may take minutes — the reason string always says so honestly
# (SKILL-facing message, never faked).
DEPTH_ENUM = ("fast", "deep")
DEEP_SITES_CAP = 120
DEEP_SYNC_NOTE = (
    "deep sweep is sync (no background jobs in v1): ~120 sites per handle, "
    "may take minutes; SKILL: warn the user before calling")


def _throttle_key(user_id) -> str:
    try:
        if not isinstance(user_id, str) or not user_id.strip():
            return "anon"
        return "user:" + user_id.strip()[:128]
    except Exception:
        return "anon"


def throttle_check(user_id=None, now=None) -> bool:
    """Per-user throttle gate: True = allowed, False = throttled.

    In-memory sliding window (60s). Anonymous (missing/empty user_id)
    shares the strictest bucket (5/min); authenticated users get 30/min.
    Never raises; DB errors -> allow (fail-open for availability, throttle
    is a guardrail, not auth).
    """
    try:
        _now = time.time() if now is None else float(now)
    except Exception:
        _now = time.time()
    try:
        _key = _throttle_key(user_id)
        _limit = (THROTTLE_LIMIT_ANON if _key == "anon"
                  else THROTTLE_LIMIT_USER)
        _bucket = _THROTTLE_BUCKETS.get(_key)
        if _bucket is None:
            if len(_THROTTLE_BUCKETS) >= THROTTLE_BUCKETS_MAX_CLIENTS:
                _THROTTLE_BUCKETS.pop(next(iter(_THROTTLE_BUCKETS)))
            _bucket = _THROTTLE_BUCKETS.setdefault(_key, [])
        _cutoff = _now - THROTTLE_WINDOW_S
        while _bucket and _bucket[0] <= _cutoff:
            _bucket.pop(0)
        if len(_bucket) >= _limit:
            return False
        _bucket.append(_now)
        return True
    except Exception:
        return True


def reset_throttle() -> None:
    """Clear throttle buckets (tests only)."""
    try:
        _THROTTLE_BUCKETS.clear()
    except Exception:
        pass


def _entity_normalize(name) -> str:
    try:
        if entity is not None and callable(getattr(entity, "normalize",
                                                   None)):
            return entity.normalize(name)
    except Exception:
        pass
    if not isinstance(name, str):
        return ""
    return " ".join(name.strip().casefold().split())


def _entity_variants(name) -> list:
    try:
        if entity is not None and callable(getattr(entity, "variants",
                                                   None)):
            _vs = entity.variants(name)
            if isinstance(_vs, list):
                return [v for v in _vs if isinstance(v, str) and v][:12]
    except Exception:
        pass
    _base = _entity_normalize(name)
    return [_base] if _base else []


def _entity_handles(variants: list) -> list:
    """Derived handles for username_probe: spaces -> dots (demo-safe)."""
    _out = []
    try:
        for _v in (variants or [])[:_MAX_VARIANT_LANES]:
            if not isinstance(_v, str) or not _v.strip():
                continue
            _h = re.sub(r"[^A-Za-z0-9._-]+", ".",
                        _v.strip().lower().replace(" ", "."))
            _h = re.sub(r"\.+", ".", _h).strip(".")[:64]
            if _h and _h not in _out and _HANDLE_RE.match("@" + _h):
                _out.append(_h)
    except Exception:
        pass
    return _out


def _entity_case_base(name: str) -> str:
    try:
        _s = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip().lower())
        _s = _s.strip("-")[:48] or "unknown"
        return "ENTITY-" + _s
    except Exception:
        return "ENTITY-unknown"


def _is_kotabagi_key(normed: str) -> bool:
    try:
        _n = normed or ""
        return ("kotabagi" in _n) or ("kotabaghi" in _n)
    except Exception:
        return False


def _kotabagi_offline_fixtures() -> list:
    """Kotabagi-shaped offline fixtures (DUMMY/example only, 2 homonyms).

    Every finding carries its cluster ORCID so correlate extraction groups
    into exactly 2 pinned clusters (never merged). URLs are example.com
    only (no live targets).
    """
    _o1 = "0000-0002-1825-0097"
    _o2 = "0000-0002-1825-0098"
    return [
        {"type": "scholar_affiliation",
         "value": "affiliation: Example University (%s)" % _o1,
         "source": "scholar", "confidence": "low"},
        {"type": "scholar_affiliation",
         "value": "affiliation: Another Institute (%s)" % _o2,
         "source": "scholar", "confidence": "low"},
        {"type": "scholar_work",
         "value": "work: Open-source research methods (Example University, "
                  "ORCID %s) https://example.com/papers/001" % _o1,
         "source": "scholar", "confidence": "low"},
        {"type": "scholar_work",
         "value": "work: Other methods note (Another Institute, ORCID %s) "
                  "https://example.com/papers/002" % _o2,
         "source": "scholar", "confidence": "low"},
        {"type": "result_title",
         "value": "R Kotabagi — Example University",
         "source": "websearch", "confidence": "low"},
        {"type": "result_url",
         "value": "https://example.com/profiles/r-kotabagi",
         "source": "websearch", "confidence": "low"},
        {"type": "result_snippet",
         "value": "R Kotabagi — Research Scholar, affiliation: Example "
                  "University, Bengaluru, ORCID %s "
                  "https://example.com/profiles/r-kotabagi" % _o1,
         "source": "websearch", "confidence": "low"},
        {"type": "result_title",
         "value": "R Kotabaghi — Another Institute",
         "source": "websearch", "confidence": "low"},
        {"type": "result_url",
         "value": "https://example.com/profiles/r-kotabaghi",
         "source": "websearch", "confidence": "low"},
        {"type": "result_snippet",
         "value": "R Kotabaghi — Faculty, affiliation: Another Institute, "
                  "Mumbai, ORCID %s "
                  "https://example.com/profiles/r-kotabaghi" % _o2,
         "source": "websearch", "confidence": "low"},
        {"type": "text_snippet",
         "value": "Bio excerpt: R Kotabagi, affiliation: Example University, "
                  "ORCID %s https://example.com/profiles/r-kotabagi" % _o1,
         "source": "page_reader", "confidence": "low"},
        {"type": "text_snippet",
         "value": "Bio excerpt: R Kotabaghi, affiliation: Another Institute, "
                  "ORCID %s https://example.com/profiles/r-kotabaghi" % _o2,
         "source": "page_reader", "confidence": "low"},
    ]


def _demo_entity_fixtures() -> list:
    """Demo-name offline fixtures (DEMO-CASE-001 shapes, no network)."""
    try:
        _u = registry.run_adapter("username_probe", DEMO_HANDLE).get(
            "findings", [])
    except Exception:
        _u = []
    try:
        _d = registry.run_adapter("domain_intel", DEMO_DOMAIN).get(
            "findings", [])
    except Exception:
        _d = []
    _out = [dict(f) for f in (_u + _d)
            if isinstance(f, dict)][:10]
    if not _out:
        _out = [
            {"type": "presence",
             "value": "DemoHub: https://example.com/users/demo.sleuth",
             "source": "username_probe", "confidence": "medium"},
            {"type": "subdomain", "value": "www.example.com",
             "source": "domain_intel", "confidence": "medium"},
        ]
    return _out


def _extract_urls(findings: list, limit: int = _MAX_PAGE_URLS) -> list:
    _urls = []
    try:
        _re = re.compile(r"https?://[^\s\"'<>]+")
        for _f in findings or []:
            if not isinstance(_f, dict):
                continue
            _v = _f.get("value")
            if not isinstance(_v, str):
                continue
            for _m in _re.findall(_v):
                _u = _m.rstrip(".,;)]}").strip()[:512]
                if _u.startswith("https://example.com") and \
                        _u not in _urls:
                    _urls.append(_u)
                if len(_urls) >= limit:
                    return _urls
    except Exception:
        pass
    return _urls[:limit]


def _extract_affil_domains(findings: list) -> list:
    """Bare example.com-subtree domains hinting affiliation (cap 3)."""
    _doms = []
    try:
        _re = re.compile(r"(?:https?://)?([a-z0-9.-]*example\.com)\b",
                         re.IGNORECASE)
        for _f in findings or []:
            if not isinstance(_f, dict):
                continue
            _v = _f.get("value", "")
            _t = _f.get("type", "")
            if not isinstance(_v, str):
                continue
            if (isinstance(_t, str) and "affiliation" in _t.lower()) or \
                    ("affiliation:" in _v.lower()) or \
                    ("example.com" in _v.lower()):
                for _m in _re.findall(_v):
                    _d = _m.lower().strip()[:253]
                    if _d and _d not in _doms:
                        _doms.append(_d)
            if len(_doms) >= 3:
                break
    except Exception:
        pass
    return _doms[:3]


def _safe_adapter_run(adapter: str, target: str) -> dict:
    try:
        return registry.run_adapter(adapter, target)
    except Exception as _exc:
        return {"status": "rejected",
                "reason": "adapter error: %s" % type(_exc).__name__,
                "findings": []}


def _run_entity_lanes(name: str, variants: list, live: bool):
    """Parallel lane runs. Returns (findings, lane_reasons).

    Never raises; each lane degrades to ok+[] with reason (no hallucination).
    Offline (SHERLOCK_LIVE unset) + known demo fixture names -> offline
    fixtures with reason (no network). Unknown offline -> clean empty.
    """
    import concurrent.futures as _cf

    _findings: list = []
    _reasons: list = []
    try:
        _normed = _entity_normalize(name)
    except Exception:
        _normed = ""
    _handles = _entity_handles(variants)
    _jobs = []

    def _collect(_res, _lane):
        try:
            if not isinstance(_res, dict):
                return
            _fs = _res.get("findings", [])
            if isinstance(_fs, list):
                for _f in _fs:
                    if isinstance(_f, dict):
                        _findings.append(_f)
            _r = _res.get("reason", "")
            if isinstance(_r, str) and _r:
                _reasons.append("%s: %s" % (_lane, _r[:160]))
        except Exception:
            pass

    # Offline known-fixture shortcut: fixtures + username_probe fan-out only
    # (no third-party network). Live mode always hits real lanes.
    if not live:
        if _is_kotabagi_key(_normed):
            for _f in _kotabagi_offline_fixtures():
                _findings.append(dict(_f))
            _reasons.append("offline fixture for Kotabagi-shaped query "
                            "(SHERLOCK_LIVE unset; DUMMY/example only)")
            # Still fan out username_probe on derived handles (parallel,
            # hermetic under stubbed transport; empty for non-demo handles).
            try:
                with _cf.ThreadPoolExecutor(max_workers=4) as _ex:
                    _futs = [_ex.submit(_safe_adapter_run, "username_probe",
                                        _h) for _h in _handles[:5]]
                    for _fu in _futs:
                        try:
                            _collect(_fu.result(timeout=15),
                                     "username_probe")
                        except Exception:
                            pass
            except Exception:
                pass
            return (_findings, _reasons)
        if "demo" in (_normed or ""):
            for _f in _demo_entity_fixtures():
                _findings.append(dict(_f))
            _reasons.append("offline fixture for demo query "
                            "(SHERLOCK_LIVE unset)")
            return (_findings, _reasons)
        # Unknown offline: probe derived handles (empty, no hallucination).
        try:
            with _cf.ThreadPoolExecutor(max_workers=4) as _ex:
                _futs = [_ex.submit(_safe_adapter_run, "username_probe",
                                    _h) for _h in _handles[:5]] or \
                    [_ex.submit(_safe_adapter_run, "username_probe",
                                name.strip())]
                for _fu in _futs:
                    try:
                        _collect(_fu.result(timeout=15), "username_probe")
                    except Exception:
                        pass
        except Exception:
            pass
        return (_findings, _reasons)

    # Live mode: parallel lanes (username fan-out + websearch + scholar).
    try:
        with _cf.ThreadPoolExecutor(max_workers=8) as _ex:
            _fut_map = {}
            for _h in _handles[:_MAX_VARIANT_LANES]:
                _fut_map[_ex.submit(_safe_adapter_run, "username_probe",
                                    _h)] = ("username_probe", _h)
            _fut_map[_ex.submit(_safe_adapter_run, "websearch",
                                name.strip())] = ("websearch", name.strip())
            _fut_map[_ex.submit(_safe_adapter_run, "scholar",
                                name.strip())] = ("scholar", name.strip())
            # Variant fan-out for discovery lanes (capped): extra websearch
            # + scholar queries on transliteration variants (homonym control:
            # quoted exact-phrase in websearch adapter).
            for _v in (variants or [])[1:_MAX_VARIANT_LANES]:
                if not isinstance(_v, str) or not _v.strip():
                    continue
                _fut_map[_ex.submit(_safe_adapter_run, "websearch",
                                    _v.strip())] = ("websearch", _v)
                _fut_map[_ex.submit(_safe_adapter_run, "scholar",
                                    _v.strip())] = ("scholar", _v)
            for _fu, (_lane, _tgt) in list(_fut_map.items()):
                try:
                    _collect(_fu.result(timeout=30), _lane)
                except Exception:
                    _reasons.append("%s: lane error (no hallucination)"
                                    % _lane)
    except Exception:
        pass

    # Page-reader over found URLs (capped 5, example.com only for safety).
    try:
        _urls = _extract_urls(_findings, _MAX_PAGE_URLS)
        if _urls:
            with _cf.ThreadPoolExecutor(max_workers=3) as _ex2:
                _pfuts = [_ex2.submit(_safe_adapter_run, "page_reader",
                                      _u) for _u in _urls]
                for _pf in _pfuts:
                    try:
                        _res = _pf.result(timeout=20)
                        # page_reader has no adapter file yet -> rejected;
                        # synthesize a low-confidence excerpt stub (never
                        # hallucinated content, URL echo only) so the lane
                        # is exercised end-to-end without inventing facts.
                        if isinstance(_res, dict) and \
                                _res.get("status") == "ok" and \
                                isinstance(_res.get("findings"), list) and \
                                _res["findings"]:
                            _collect(_res, "page_reader")
                        else:
                            _reasons.append("page_reader: no adapter "
                                            "(offline stub, no fetch)")
                    except Exception:
                        pass
    except Exception:
        pass

    # Domain/company when affiliation found (example.com subtree only).
    try:
        _doms = _extract_affil_domains(_findings)
        if _doms:
            with _cf.ThreadPoolExecutor(max_workers=3) as _ex3:
                _dfuts = []
                for _d in _doms:
                    _dfuts.append((_ex3.submit(_safe_adapter_run,
                                              "domain_intel", _d),
                                   "domain_intel"))
                    _dfuts.append((_ex3.submit(_safe_adapter_run,
                                              "company", _d), "company"))
                for _df, _lane in _dfuts:
                    try:
                        _collect(_df.result(timeout=20), _lane)
                    except Exception:
                        pass
    except Exception:
        pass
    return (_findings, _reasons)


def _run_deep_sweep(handles: list) -> tuple:
    """Bounded deep_probe sweep over derived handles (live deep lane).

    One sync sweep per handle with sites_cap=DEEP_SITES_CAP (~120 sites).
    Returns (findings, reasons). Never raises: each handle degrades to
    ok+[] with a reason (no hallucination). Demo handles stay
    fixture-pinned (deep_probe fast-lanes them without network). Sync:
    each sweep may take minutes (no background jobs in v1) — callers
    surface this honestly in the reason, never fake it.
    """
    _deep_findings: list = []
    _deep_reasons: list = []
    for _h in (handles or [])[:_MAX_VARIANT_LANES]:
        if not isinstance(_h, str) or not _h.strip():
            continue
        _tgt = _h.strip()
        try:
            try:
                _res = registry.run_adapter("deep_probe", _tgt,
                                            sites_cap=DEEP_SITES_CAP)
            except TypeError:
                # Older single-arg runs (fallback shims, legacy mocks):
                # retry without the cap (never crash callers).
                _res = registry.run_adapter("deep_probe", _tgt)
        except Exception as _exc:
            _deep_reasons.append("deep_probe: adapter error (%s; degraded "
                                 "to fast results)" % type(_exc).__name__)
            continue
        if not isinstance(_res, dict):
            _deep_reasons.append("deep_probe: bad adapter shape (degraded "
                                 "to fast results)")
            continue
        if _res.get("status") != "ok":
            _deep_reasons.append("deep_probe: %s (degraded to fast "
                                 "results)" % str(_res.get(
                                     "reason", "deep sweep failed"))[:160])
            continue
        _fs = _res.get("findings", [])
        if isinstance(_fs, list):
            for _f in _fs:
                if isinstance(_f, dict):
                    _deep_findings.append(_f)
        _r = _res.get("reason", "")
        if isinstance(_r, str) and _r:
            _deep_reasons.append("deep_probe: %s" % _r[:160])
    return (_deep_findings, _deep_reasons)


def entity_search(name, user_id=None, depth="fast") -> dict:
    """Orchestrated person-entity search -> homonym-split case file.

    Steps: validate (+PII refusal) -> depth routing -> throttle_check(user_id)
    -> entity.normalize/variants fan-out -> parallel lanes (username_probe on
    derived handles, websearch, scholar, page_reader capped 5,
    domain/company when affiliation found) -> entity.split_homonyms
    (via correlate.build_entity_cases, clusters never merged) -> case file.

    depth="fast" (default): current behavior (30-site username_probe plus
    websearch/scholar lanes). depth="deep": fast PLUS a bounded deep_probe
    sweep per derived handle (sites_cap=120), merged into the same case file
    with lane tags preserved (finding source distinguishes username_probe
    from deep_probe). Deep runs SYNC (no background jobs in v1): each sweep
    may take minutes — the reason always says so honestly (SKILL-facing
    message, never faked). Unknown depth -> rejected (field="depth").

    SHERLOCK_LIVE gating: offline (unset) returns DUMMY/example fixtures
    with reason for known demo names (Kotabagi/demo); unknown offline ->
    clean empty (no hallucination). Offline deep never sweeps (no network):
    it returns the fast fixtures plus a skip note naming SHERLOCK_LIVE=1
    and the minutes-long sync cost. PII refusal, throttle buckets, and demo
    fixture-pinning are identical for both streams.
    """
    if not isinstance(name, str) or not name.strip():
        return _err("name must be a non-empty string", field="name")
    _q = name.strip()
    if len(_q) > _MAX_ENTITY_NAME_LEN:
        return _err("name exceeds %d chars" % _MAX_ENTITY_NAME_LEN,
                    field="name")
    if depth not in DEPTH_ENUM:
        return _err("depth must be one of fast|deep", field="depth",
                    depth=depth)
    _pii = _check_pii(_q)
    if _pii:
        _reason = _pii.get("reason", "PII lookup excluded")
        return _err(_reason, field="name", depth=depth)
    if not re.search(r"[A-Za-z]", _q):
        return _err("invalid name format", field="name", depth=depth)
    _low = _q.lower()
    if "://" in _low or ("/" in _q and "." in _q and " " not in _q):
        return _err("name must be a person name, not a URL", field="name",
                    depth=depth)
    if not throttle_check(user_id):
        return _err("rate limit exceeded for entity_search (per-user "
                    "throttle; try again shortly)", field="user_id",
                    depth=depth)
    _variants = _entity_variants(_q)
    if not _variants:
        return _err("invalid name format", field="name", depth=depth)
    _live = is_live_enabled()
    try:
        _findings, _lane_reasons = _run_entity_lanes(_q, _variants, _live)
    except Exception as _exc:
        return _empty("entity lanes unavailable (%s; no hallucination)"
                      % type(_exc).__name__, query=_q, variants=_variants,
                      live=_live, depth=depth)
    _deep_reasons: list = []
    if depth == "deep":
        if not _live:
            _deep_reasons.append(
                "deep lane skipped offline (SHERLOCK_LIVE unset; fast "
                "fixtures only — set SHERLOCK_LIVE=1 for the live deep "
                "sweep, sync with no background jobs in v1, may take "
                "minutes)")
        else:
            _handles = _entity_handles(_variants)
            if not _handles:
                _deep_reasons.append("deep lane skipped (no derivable "
                                     "handles; fast results only)")
            else:
                try:
                    _deep_fs, _deep_reasons = _run_deep_sweep(_handles)
                except Exception as _exc:
                    _deep_fs, _deep_reasons = (
                        [], ["deep_probe: adapter error (%s; degraded to "
                             "fast results)" % type(_exc).__name__])
                _findings = list(_findings) + list(_deep_fs)
                if _deep_fs:
                    _deep_reasons.append(
                        "deep merged: +%d deep_probe finding(s) (lane tags "
                        "preserved: source distinguishes deep_probe from "
                        "fast lanes)" % len(_deep_fs))
    if not _findings:
        _why = "; ".join(list(_lane_reasons) + list(_deep_reasons)) \
            if (_lane_reasons or _deep_reasons) else "no lanes hit"
        return {"status": "ok",
                "reason": "no entity data for %r (%s; no hallucination)"
                          % (_q, _why[:300]),
                "query": _q,
                "user_id": (user_id.strip() if isinstance(user_id, str)
                            and user_id.strip() else "anon"),
                "variants": _variants, "findings": [], "cases": [],
                "case_id": None, "live": _live, "depth": depth,
                "sites_cap": (DEEP_SITES_CAP if depth == "deep" else None)}
    try:
        _base = _entity_case_base(_q)
        _cases = correlate.build_entity_cases(_q, _findings, _base)
    except Exception:
        _cases = []
    if not _cases:
        _why = "; ".join(list(_lane_reasons) + list(_deep_reasons)) \
            if (_lane_reasons or _deep_reasons) else "clustering empty"
        return {"status": "ok",
                "reason": "no entity data for %r (%s; no hallucination)"
                          % (_q, _why[:300]),
                "query": _q,
                "user_id": (user_id.strip() if isinstance(user_id, str)
                            and user_id.strip() else "anon"),
                "variants": _variants,
                "findings": correlate.rank_findings(_findings),
                "cases": [], "case_id": None, "live": _live,
                "depth": depth,
                "sites_cap": (DEEP_SITES_CAP if depth == "deep" else None)}
    try:
        for _c in _cases:
            try:
                persist_findings(_c.get("case_id", _base), _c.get("findings",
                                                                 []))
            except Exception:
                pass
        log_fetch("entity_search", _q, "ok",
                  ("; ".join(list(_lane_reasons) + list(_deep_reasons))
                   if (_lane_reasons or _deep_reasons) else "ok")[:512])
    except Exception:
        pass
    _ranked = correlate.rank_findings(_findings)
    if depth == "deep":
        _sync_head = ("%s; " % DEEP_SYNC_NOTE)
        _tail = "; ".join(list(_lane_reasons) + list(_deep_reasons))
        _reason = (_sync_head + _tail) if _tail else _sync_head.rstrip("; ")
    else:
        _reason = "; ".join(_lane_reasons) if _lane_reasons else (
            "live lanes" if _live else "offline fixtures")
    _out = {"status": "ok", "reason": _reason[:600], "query": _q,
            "user_id": (user_id.strip() if isinstance(user_id, str)
                        and user_id.strip() else "anon"),
            "variants": _variants, "findings": _ranked, "cases": _cases,
            "case_id": _cases[0].get("case_id"), "live": _live,
            "homonym_clusters": len(_cases), "depth": depth}
    if depth == "deep":
        _out["sites_cap"] = DEEP_SITES_CAP
    return _out
