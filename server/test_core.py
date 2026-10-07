"""Core orchestrator tests (>=25). Validation, pagination, idempotency,
unicode/injection, import perf, contract fallback, negatives.

Hermetic: an autouse fixture stubs the HTTP/DNS layer the sibling
adapters use, so no test touches the network. The stub mirrors the
DEMO-CASE-001 contract (AGENTS.md section 3): @demo.sleuth hits 3 demo
sites; example.com resolves offline; the demo reel needs no network.
"""

import importlib.util
import json
import os
import sqlite3
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXDIR = os.path.join(os.path.dirname(HERE), "demo-data", "fixtures")
SUPDIR = os.path.join(os.path.dirname(HERE), "supabase")


def _load(name):
    path = os.path.join(HERE, name + ".py")
    spec = importlib.util.spec_from_file_location("core_test_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["core_test_" + name] = mod
    spec.loader.exec_module(mod)
    return mod


registry = _load("registry")
correlate = _load("correlate")
tools = _load("tools")
main = _load("main")

DEMO_REEL_URL = "https://www.instagram.com/reel/DMYosint001/"


class _Resp:
    def __init__(self, status=404):
        self.status_code = status

    def json(self):
        return {}


def _fake_http_get(url, **kw):
    # Demo-handle profile URLs hit on 3 stubbed sites (mirrors the
    # username_probe fixture list); everything else misses. No network.
    if "demo.sleuth" in str(url) and "example.com" in str(url):
        if any(k in str(url) for k in ("/users/", "/@", "/blog/")):
            return _Resp(200)
    return _Resp(404)


@pytest.fixture(autouse=True)
def _offline_and_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SHERLOCK_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("SHERLOCK_FIXTURES", FIXDIR)
    try:
        import requests
        monkeypatch.setattr(requests, "get", _fake_http_get)
    except ImportError:
        pass
    import socket
    def _no_dns(*a, **k):
        raise OSError("offline test")
    monkeypatch.setattr(socket, "gethostbyname_ex", _no_dns)
    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    main.reset_rate_limits()
    yield


def _demo_bundles():
    u = registry.run_adapter("username_probe", "@demo.sleuth")["findings"]
    d = registry.run_adapter("domain_intel", "example.com")["findings"]
    r = registry.run_adapter("oembed_public", DEMO_REEL_URL)["findings"]
    return u, d, r


# ---------------- registry ----------------

def test_allow_list_exact():
    # Base lanes always present; optional entity lanes (websearch/scholar/
    # company/page_reader) join ONLY when their adapter files exist
    # (orchestrator crew, guarded import stays unbreakable).
    base = ("username_probe", "domain_intel",
            "exif_local", "oembed_public")
    assert tuple(registry.ALLOW_LIST[:4]) == base
    assert set(base) <= set(registry.ALLOW_LIST)
    for _opt in ("websearch", "scholar", "company", "page_reader"):
        import os as _os
        _p = _os.path.join(_os.path.dirname(
            _os.path.abspath(registry.__file__)),
            "adapters", _opt + ".py")
        if _os.path.isfile(_p):
            assert _opt in registry.ALLOW_LIST
        else:
            assert _opt not in registry.ALLOW_LIST


def test_load_allowlisted_never_crashes():
    for name in registry.ALLOW_LIST:
        ad = registry.load_adapter(name)
        assert ad.NAME == name
        res = ad.run("example-probe-target")
        assert set(("status", "reason", "findings")) <= set(res)


def test_rejected_non_allowlisted():
    for bad in ("osintgram", "../evil", "", "USERNAME_PROBE", "osintgram;rm"):
        res = registry.run_adapter(bad, "@demo.sleuth")
        assert res["status"] == "rejected" and res["findings"] == []


def test_run_adapter_demo_username_3_hits():
    res = registry.run_adapter("username_probe", "@demo.sleuth")
    assert res["status"] == "ok" and len(res["findings"]) == 3
    assert {f["type"] for f in res["findings"]} == {"presence"}


def test_run_adapter_unknown_target_empty():
    res = registry.run_adapter("username_probe", "@demo.ghost")
    assert res["status"] == "ok" and res["findings"] == []
    assert res["reason"]


def test_run_adapter_empty_target_safe():
    res = registry.run_adapter("domain_intel", "   ")
    assert res["findings"] == [] and res["status"] in ("ok", "rejected")


def test_run_adapter_never_raises_on_garbage():
    for name in registry.ALLOW_LIST:
        for target in ("", "   ", "\x00", "x" * 600):
            res = registry.run_adapter(name, target)
            assert set(("status", "reason", "findings")) <= set(res)


# ---------------- correlate ----------------

def test_dedupe_by_type_value():
    fs = [{"type": "subdomain", "value": "a.example.com",
           "source": "domain_intel", "confidence": "high"},
          {"type": "subdomain", "value": "a.example.com",
           "source": "domain_intel", "confidence": "low"},
          {"type": "contact", "value": "a.example.com",
           "source": "domain_intel", "confidence": "low"}]
    assert len(correlate.dedupe_findings(fs)) == 2


def test_dedupe_keeps_highest_confidence():
    fs = [{"type": "t", "value": "v", "source": "s", "confidence": "low"},
          {"type": "t", "value": "v", "source": "s2", "confidence": "high"}]
    out = correlate.dedupe_findings(fs)
    assert out[0]["confidence"] == "high"
    assert sorted(out[0]["sources"]) == ["s", "s2"]


def test_rank_confidence_order():
    fs = [{"type": "t", "value": "l", "source": "s", "confidence": "low"},
          {"type": "t", "value": "h", "source": "s", "confidence": "high"},
          {"type": "t", "value": "m", "source": "s", "confidence": "medium"}]
    assert [f["value"] for f in correlate.rank_findings(fs)] == ["h", "m", "l"]


def test_assemble_case_lanes():
    u, d, r = _demo_bundles()
    case = correlate.assemble_case("DEMO-CASE-001", u + d + r)
    assert case["finding_count"] == 10
    assert sorted(case["lanes"]) == ["domain_intel", "oembed_public",
                                     "username_probe"]


def test_demo_case_all_three_lanes():
    u, d, r = _demo_bundles()
    assert len(u) == 3 and len(d) == 3 and len(r) == 4
    case = correlate.build_demo_case(u, d, r)
    assert case["case_id"] == "DEMO-CASE-001"
    assert case["finding_count"] == 10


def test_search_demo_top1():
    u, d, r = _demo_bundles()
    demo = correlate.build_demo_case(u, d, r)
    hits = correlate.search_cases("osint demo case", [demo])
    assert hits and hits[0]["case_id"] == "DEMO-CASE-001"


# ---------------- tools: validation ----------------

def test_triage_routes_all_kinds():
    assert tools.triage_target("@demo.sleuth")["lane"] == "username"
    # bare dotted strings that parse as domains route to domain_intel;
    # the @-form is unambiguously a username.
    assert tools.triage_target("demo.sleuth")["lane"] == "domain"
    assert tools.triage_target("example.com")["lane"] == "domain"
    assert tools.triage_target(DEMO_REEL_URL)["lane"] == "reel"
    assert tools.triage_target("notes.bin",
                               kind="file")["adapter"] == "exif_local"
    assert tools.triage_target("@demo.sleuth")["adapter"] == "username_probe"


def test_triage_bad_kind_enum():
    res = tools.triage_target("@demo.sleuth", kind="phone")
    assert res["status"] == "rejected" and res["field"] == "kind"


def test_triage_target_cap():
    assert tools.triage_target("x" * 513)["status"] == "rejected"
    assert tools.triage_target("  ")["status"] == "rejected"


def test_probe_username_demo_ok():
    res = tools.probe_username("@demo.sleuth")
    assert res["status"] == "ok" and len(res["findings"]) == 3
    assert res["case_id"] == "DEMO-CASE-001"


def test_probe_username_unknown_empty_reason():
    res = tools.probe_username("@demo.stranger")
    assert res["status"] == "ok" and res["findings"] == [] and res["reason"]


def test_intel_domain_demo_ok():
    res = tools.intel_domain("example.com")
    subs = [f for f in res["findings"] if f["type"] == "subdomain"]
    cons = [f for f in res["findings"] if f["type"] == "contact"]
    assert res["status"] == "ok"
    assert len(subs) == 2 and len(cons) == 1
    assert all(v["value"].endswith("example.com")
               for v in subs + cons)


def test_save_reel_demo_ok():
    res = tools.save_reel(DEMO_REEL_URL)
    caps = [f for f in res["findings"] if f["type"] == "caption"]
    links = [f for f in res["findings"] if f["type"] == "transcript_link"]
    assert res["status"] == "ok"
    assert caps and "open-source research" in caps[0]["value"]
    assert len(links) == 2
    assert res["author"] == "@demo.archivist"


def test_pii_email_phone_rejected():
    assert tools.triage_target("jane.doe@gmail.com")["status"] == "rejected"
    assert tools.triage_target("+91 98200 12345")["status"] == "rejected"
    assert tools.probe_username("jane.doe@gmail.com")["status"] == "rejected"


# ---------------- pagination ----------------

def test_pagination_max_50_enforced():
    assert tools.search_memory(
        "osint demo case", limit=51)["status"] == "rejected"
    assert tools.case_summary(
        "DEMO-CASE-001", limit=51)["status"] == "rejected"
    assert tools.search_memory(
        "osint demo case", limit=50)["status"] == "ok"
    assert tools.case_summary("DEMO-CASE-001", limit=50)["total"] == 10


def test_pagination_offset_slicing():
    p1 = tools.case_summary("DEMO-CASE-001", limit=4, offset=0)
    p2 = tools.case_summary("DEMO-CASE-001", limit=4, offset=4)
    p3 = tools.case_summary("DEMO-CASE-001", limit=4, offset=8)
    assert (len(p1["findings"]), len(p2["findings"]),
            len(p3["findings"])) == (4, 4, 2)
    assert p1["total"] == 10


def test_pagination_bad_types():
    assert tools.search_memory("x", limit="many")["status"] == "rejected"
    assert tools.search_memory("x", offset=-1)["status"] == "rejected"
    assert tools.search_memory("   ")["status"] == "rejected"


# ---------------- idempotency ----------------

def test_persist_idempotent():
    d = registry.run_adapter("domain_intel", "example.com")["findings"]
    n1 = tools.persist_findings("DEMO-CASE-001", d)
    n2 = tools.persist_findings("DEMO-CASE-001", d)
    assert n1 == n2 == 3


def test_seed_idempotent():
    conn = sqlite3.connect(":memory:")
    with open(os.path.join(SUPDIR, "schema.sql")) as fh:
        conn.executescript("\n".join(
            l for l in fh.read().splitlines()
            if not l.startswith("CREATE EXTENSION")))
    with open(os.path.join(SUPDIR, "seed_fake.sql")) as fh:
        seed = fh.read()
    conn.executescript(seed)
    conn.executescript(seed)
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 10
    assert conn.execute(
        "SELECT COUNT(*) FROM targets").fetchone()[0] == 3


# ---------------- unicode / injection ----------------

def test_unicode_no_crash():
    r1 = tools.probe_username("d\u00e9mo.sleuth\u2603")
    r2 = tools.search_memory("osint d\u00e9mo \u2603 case")
    assert r1["findings"] == [] and isinstance(r2["status"], str)


def test_sql_injection_safe():
    tools.probe_username("@demo.sleuth")
    res = tools.search_memory("' OR '1'='1' --")
    assert res["status"] == "ok"
    assert res.get("top_case", None) is None or res["total"] <= 1
    r2 = tools.probe_username("'; DROP TABLE findings; --")
    assert r2["status"] in ("ok", "rejected")
    conn = sqlite3.connect(os.environ["SHERLOCK_DB"])
    assert conn.execute(
        "SELECT COUNT(*) FROM findings").fetchone()[0] >= 3


def test_empty_inputs_rejected():
    assert tools.probe_username("  ")["status"] == "rejected"
    assert tools.intel_domain("")["status"] == "rejected"
    assert tools.save_reel("")["status"] == "rejected"
    assert tools.case_summary("  ")["status"] == "rejected"


# ---------------- perf + contract fallback ----------------

def test_500_adapter_runs_fast():
    t0 = time.time()
    for _ in range(500):
        res = registry.run_adapter("username_probe", "@demo.sleuth")
        assert len(res["findings"]) == 3
    assert time.time() - t0 < 10


def test_contract_fallback_adapters_absent(tmp_path, monkeypatch):
    # Simulate the adapters directory being empty: registry must fall back
    # to builtin fixtures and never crash.
    monkeypatch.setattr(registry, "_load_from_file", lambda name: None)
    monkeypatch.setenv("SHERLOCK_FIXTURES", str(tmp_path / "missing"))
    assert registry.load_adapter("username_probe").fallback is True
    res = registry.run_adapter("username_probe", "@demo.sleuth")
    assert res["status"] == "ok" and len(res["findings"]) == 3
    res = registry.run_adapter("domain_intel", "example.com")
    subs = [f for f in res["findings"] if f["type"] == "subdomain"]
    assert res["status"] == "ok" and len(subs) == 2
    res = registry.run_adapter("exif_local", "notes.bin")
    assert res["status"] == "ok" and res["findings"] == []


def test_real_adapters_loaded_when_present():
    loaded = {a.NAME: a for a in registry.list_adapters()}
    assert set(loaded) == set(registry.ALLOW_LIST)
    assert all(a.fallback is False and a.rejected is False
               for a in loaded.values())


# ---------------- main ----------------

def test_health_ready_payloads():
    assert main.health_payload() == {"status": "ok", "service": "sherlock"}
    ready = main.ready_payload()
    assert ready["ready"] is True and set(
        ("username_probe", "domain_intel", "exif_local",
         "oembed_public")) <= set(ready["adapters"])


def test_cors_allows_localhost_blocks_evil():
    assert main.is_origin_allowed("http://localhost:3000")
    assert main.is_origin_allowed("http://127.0.0.1:8000")
    assert main.is_origin_allowed("https://example.com")
    assert not main.is_origin_allowed("https://evil.example.net")
    assert any("localhost" in o for o in main.ALLOWED_ORIGINS)
    assert any("example.com" in o for o in main.ALLOWED_ORIGINS)


def test_rate_limit_blocks_after_60():
    for _ in range(60):
        assert main.check_rate_limit("c1")
    assert not main.check_rate_limit("c1")
    assert main.check_rate_limit("other-client")


def test_size_cap_1mb():
    assert main.enforce_size(b"x" * (1024 * 1024))
    assert not main.enforce_size(b"x" * (1024 * 1024 + 1))


def test_mcp_tools_list_has_six():
    res = main.handle_mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in res["result"]["tools"]]
    assert names == ["triage_target", "probe_username", "intel_domain",
                     "save_reel", "search_memory", "case_summary"]


def test_mcp_call_probe_and_unknown():
    ok = main.handle_mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": "probe_username",
                                     "arguments": {"handle": "@demo.sleuth"}}})
    assert len(ok["result"]["findings"]) == 3
    bad = main.handle_mcp({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "pwn", "arguments": {}}})
    assert "error" in bad
    assert "error" in main.handle_mcp({"jsonrpc": "2.0", "id": 4,
                                       "method": "nope"})
    assert "error" in main.handle_mcp("not-a-dict")


# ---------------- negatives ----------------

def test_negative_unknown_user_domain_reel():
    assert tools.probe_username("@demo.ghost")["findings"] == []
    assert tools.intel_domain("other.test")["findings"] == []
    assert tools.save_reel(
        "https://www.instagram.com/reel/UNKNOWN999/")["findings"] == []


def test_negative_bad_inputs_rejected():
    assert tools.save_reel("https://evil.test/x")["status"] == "rejected"
    assert tools.intel_domain("not a domain!!")["status"] == "rejected"
    assert tools.probe_username("!!!")["status"] == "rejected"
    assert tools.case_summary("CASE-9999")["status"] == "rejected"


def test_negative_unknown_case_no_hallucination():
    res = tools.case_summary("CASE-9999")
    assert res["status"] == "rejected"
    assert res.get("findings", []) == []


def test_search_memory_demo_top1_three_lanes():
    res = tools.search_memory("osint demo case")
    assert res["top_case"] == "DEMO-CASE-001"
    assert sorted(res["results"][0]["lanes"]) == ["domain_intel",
                                                 "oembed_public",
                                                 "username_probe"]
    assert len(res["findings"]) == 10


# ---------------- schema + fixtures contract ----------------

def test_schema_sqlite_compatible():
    conn = sqlite3.connect(":memory:")
    with open(os.path.join(SUPDIR, "schema.sql")) as fh:
        sql = "\n".join(l for l in fh.read().splitlines()
                         if not l.startswith("CREATE EXTENSION"))
    conn.executescript(sql)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"findings", "targets", "fetch_log"} <= tables


def test_fixtures_match_contract():
    with open(os.path.join(FIXDIR, "username.json")) as fh:
        u = json.load(fh)
    with open(os.path.join(FIXDIR, "domain.json")) as fh:
        d = json.load(fh)
    with open(os.path.join(FIXDIR, "reel.json")) as fh:
        r = json.load(fh)
    assert u["handle"] == "@demo.sleuth" and len(u["findings"]) == 3
    subs = [f for f in d["findings"] if f["type"] == "subdomain"]
    cons = [f for f in d["findings"] if f["type"] == "contact"]
    assert d["domain"] == "example.com" and len(subs) == 2 and len(cons) == 1
    assert r["url"] == "https://www.instagram.com/reel/DMYosint001/"
    assert r["author"] == "@demo.archivist"
    assert "open-source research" in r["caption"]
    assert len(r["resource_links"]) == 2


# ---------------- audit-2 regressions ----------------

def test_requirements_importable():
    """Every server/requirements.txt entry must import in this venv.

    Regression for the missing-requests incident: `requests` was imported
    by all 3 network adapters but absent from requirements AND the venv,
    which silently zeroed username_probe (11 integration failures).
    This test fails loudly instead of skipping.
    """
    import importlib
    req = os.path.join(os.path.dirname(HERE), "server", "requirements.txt")
    names = []
    with open(req) as fh:
        for line in fh:
            line = line.split("#")[0].strip()
            if line:
                names.append(line)
    assert "requests" in " ".join(names), "requests must be a declared dep"
    mapping = {"pytest": "pytest", "fastapi": "fastapi",
               "uvicorn": "uvicorn", "pydantic": "pydantic",
               "httpx": "httpx", "requests": "requests",
               "readability-lxml": "readability",
               "trafilatura": "trafilatura",
               "scrapling": "scrapling",
               "sherlock-project": "sherlock_project",
               "psycopg": "psycopg"}
    for entry in names:
        base = "".join(c for c in entry.split(">")[0].split("=")[0]
                       .strip().lower())
        modname = mapping.get(base)
        assert modname is not None, "unmapped requirement: %r" % entry
        importlib.import_module(modname)


def test_validate_pagination_rejects_bool():
    # bool is a subclass of int: True must not parse as limit=1.
    assert tools.validate_pagination(limit=True)["status"] == "rejected"
    assert tools.validate_pagination(offset=False)["status"] == "rejected"


def test_search_memory_offset_pages_findings():
    full = tools.search_memory("osint demo case", limit=10, offset=0)
    assert len(full["findings"]) == 10
    page = tools.search_memory("osint demo case", limit=4, offset=8)
    assert len(page["findings"]) == 2
    assert page["findings"] == full["findings"][8:12]
    past = tools.search_memory("osint demo case", limit=10, offset=1)
    assert past["results"] == [] and past["total"] == 1


def test_rank_preserves_sources_with_invalid_neighbors():
    good = {"type": "t", "value": "v", "source": "s",
            "confidence": "high", "sources": ["s", "s2"]}
    out = correlate.rank_findings([{"type": "t"}, "junk", 123, good])
    assert len(out) == 1 and out[0]["sources"] == ["s", "s2"]


def test_exif_fallback_has_no_fixture_file():
    # exif_local parses user bytes only: no fixture file, never findings
    # from fixtures (missing file -> clean rejected, never hallucinated).
    assert "exif_local" not in registry._FIXTURE_FILES
    res = registry.run_adapter("exif_local", "notes.bin")
    assert res["findings"] == []
    assert res["status"] in ("ok", "rejected")


def test_rate_buckets_bounded():
    main.reset_rate_limits()
    for i in range(main.RATE_BUCKETS_MAX_CLIENTS + 500):
        assert main.check_rate_limit("audit-client-%d" % i)
    assert len(main._rate_buckets) <= main.RATE_BUCKETS_MAX_CLIENTS


def test_handle_mcp_internal_error_shape(monkeypatch):
    cached = main._load_tools()
    monkeypatch.setattr(cached, "triage_target", lambda *a, **k: 1 / 0)
    res = main.handle_mcp({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                           "params": {"name": "triage_target",
                                      "arguments": {"target": "x"}}})
    assert res["error"]["code"] == -32603
    assert "error" not in res.get("result", {}) if "result" in res else True
    main._clear_caches()


def test_tools_db_enforces_confidence_check(tmp_path):
    conn = tools.get_db(str(tmp_path / "c.db"))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO findings(id, case_id, type, value, source,"
                " confidence, created_at) VALUES(?,?,?,?,?,?,?)",
                ("x", "C", "t", "v", "s", "bogus", "now"))
    finally:
        conn.close()


def test_http_guards_via_testclient():
    tc = pytest.importorskip("fastapi.testclient")
    Client = tc.TestClient
    assert main.app is not None
    main.reset_rate_limits()
    c = Client(main.app)
    assert c.get("/health").json() == {"status": "ok",
                                       "service": "sherlock"}
    assert c.get("/ready").json()["ready"] is True
    assert c.get("/health",
                 headers={"origin": "https://evil.example.net"}).status_code == 403
    big = b"x" * (main.MAX_BODY_BYTES + 1)
    r = c.post("/mcp", content=big,
               headers={"content-type": "application/json"})
    assert r.status_code == 413
    main.reset_rate_limits()
    for _ in range(60):
        assert c.get("/health").status_code == 200
    assert c.get("/health").status_code == 429


# ---------------- live cache (TTL 24h, key adapter+target) ----------------

def test_live_cache_ttl_fresh_and_stale(tmp_path, monkeypatch):
    db = str(tmp_path / "cache.db")
    monkeypatch.setenv("SHERLOCK_DB", db)
    assert tools.FETCH_CACHE_TTL_S == 24 * 3600
    assert tools.fetch_cache_lookup("username_probe", "octocat",
                                    path=db) is None
    tools.log_fetch("username_probe", "octocat", "ok", "live", path=db)
    fresh = tools.fetch_cache_lookup("username_probe", "octocat", path=db)
    assert fresh is not None and fresh["status"] == "ok"
    # Wrong adapter/target is a different cache key.
    assert tools.fetch_cache_lookup("domain_intel", "octocat",
                                    path=db) is None
    # Stale entries (TTL exceeded) miss.
    assert tools.fetch_cache_lookup("username_probe", "octocat",
                                    ttl_s=-1, path=db) is None
    # Case id is deterministic per adapter+target.
    assert tools.live_case_id("username_probe", "octocat") == \
        tools.live_case_id("username_probe", "octocat")
    assert tools.live_case_id("username_probe", "a") != \
        tools.live_case_id("domain_intel", "a")


def test_tools_live_gating_username(monkeypatch):
    monkeypatch.delenv("SHERLOCK_LIVE", raising=False)
    res = tools.probe_username("octocat")
    assert res["status"] == "ok" and res["findings"] == []
    assert "demo covers" in res["reason"]


def test_tools_live_username_uses_cache(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    calls = {"n": 0}

    def fake_run(name, target):
        calls["n"] += 1
        return {"status": "ok", "reason": "live",
                "findings": [{"type": "presence", "value": "GitHub: x",
                              "source": "username_probe",
                              "confidence": "low"}]}

    monkeypatch.setattr(tools.registry, "run_adapter", fake_run)
    r1 = tools.probe_username("octocat")
    assert r1["status"] == "ok" and len(r1["findings"]) == 1
    assert r1["case_id"].startswith("LIVE-")
    assert calls["n"] == 1
    r2 = tools.probe_username("octocat")
    assert r2["status"] == "ok"
    assert "cached" in r2["reason"]
    assert calls["n"] == 1  # second call served from fetch_log, no refetch


def test_tools_live_gating_domain(monkeypatch):
    monkeypatch.delenv("SHERLOCK_LIVE", raising=False)
    res = tools.intel_domain("github.com")
    assert res["status"] == "ok" and res["findings"] == []
    assert "demo covers" in res["reason"]


def test_tools_live_domain_uses_cache(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    calls = {"n": 0}

    def fake_run(name, target):
        calls["n"] += 1
        return {"status": "ok", "reason": "live",
                "findings": [{"type": "subdomain",
                              "value": "www.github.com",
                              "source": "domain_intel",
                              "confidence": "medium"}]}

    monkeypatch.setattr(tools.registry, "run_adapter", fake_run)
    r1 = tools.intel_domain("github.com")
    assert r1["status"] == "ok" and len(r1["findings"]) == 1
    assert calls["n"] == 1
    r2 = tools.intel_domain("github.com")
    assert "cached" in r2["reason"] and calls["n"] == 1


# ---------------- live smoke (gated: SHERLOCK_LIVE=1, real network) ----------------
# Shape-only assertions (never content): status/reason/findings keys,
# finding schema, zero exceptions. Targets are fixture-safe only:
# example.com (IANA reserved) + octocat (well-known public demo handle).

def _assert_shape(result, source):
    assert set(("status", "reason", "findings")) <= set(result)
    assert result["status"] in ("ok", "rejected")
    assert isinstance(result["reason"], str) and result["reason"]
    assert isinstance(result["findings"], list)
    for f in result["findings"]:
        assert set(f) == {"type", "value", "source", "confidence"}, f
        assert f["source"] == source
        assert f["confidence"] in ("high", "medium", "low")
        assert isinstance(f["value"], str) and f["value"]


@pytest.mark.skipif(os.environ.get("SHERLOCK_LIVE") != "1",
                    reason="live smoke needs SHERLOCK_LIVE=1")
def test_live_smoke_domain_example_shape():
    res = registry.run_adapter("domain_intel", "example.com")
    _assert_shape(res, "domain_intel")


@pytest.mark.skipif(os.environ.get("SHERLOCK_LIVE") != "1",
                    reason="live smoke needs SHERLOCK_LIVE=1")
def test_live_smoke_username_octocat_shape(monkeypatch):
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    res = registry.run_adapter("username_probe", "octocat")
    _assert_shape(res, "username_probe")
