"""Orchestrator tests (>=20): entity_search end-to-end.

Covers: variant fan-out (entity.normalize/variants), per-user throttle
buckets (anon strictest), offline fixture path (SHERLOCK_LIVE gating),
homonym split end-to-end on Kotabagi-shaped fixtures (clusters never merged),
PII-request refusal preserved, unknown entity -> clean empty.

Hermetic: HTTP/DNS stubbed (no network), tmp DB, throttle reset.
DUMMY/example fixtures only (R Kotabagi / Example University /
Another Institute / example.com / DUMMY ORCIDs). No real-person PII.
"""

import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    path = os.path.join(HERE, name + ".py")
    spec = importlib.util.spec_from_file_location("orch_test_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["orch_test_" + name] = mod
    spec.loader.exec_module(mod)
    return mod


registry = _load("registry")
correlate = _load("correlate")
tools = _load("tools")
entity = _load("entity")


class _Resp:
    def __init__(self, status=404):
        self.status_code = status

    def json(self):
        return {}


def _fake_http_get(url, **kw):
    s = str(url)
    # Demo-handle presence hits (mirrors core hermetic stub).
    if "demo.sleuth" in s and "example.com" in s:
        if any(k in s for k in ("/users/", "/@", "/blog/")):
            return _Resp(200)
    return _Resp(404)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SHERLOCK_DB", str(tmp_path / "orch.db"))
    monkeypatch.setenv("SHERLOCK_FIXTURES",
                       os.path.join(os.path.dirname(HERE),
                                    "demo-data", "fixtures"))
    monkeypatch.delenv("SHERLOCK_LIVE", raising=False)
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    monkeypatch.delenv("SHERLOCK_BRAVE_KEY", raising=False)
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
    tools.reset_throttle()
    yield
    tools.reset_throttle()


# ---------------- variants / fan-out ----------------

def test_variants_kotabagi_fanout():
    vs = entity.variants("Kotabagi")
    assert "kotabagi" in vs and "kotabaghi" in vs
    assert vs[0] == "kotabagi"
    assert len(vs) <= 12 and len(vs) == len(set(vs))


def test_variants_used_by_entity_search():
    vs = tools._entity_variants("R Kotabagi")
    assert "r kotabagi" in vs
    res = tools.entity_search("R Kotabagi", "fanout-user-1")
    assert res["status"] == "ok"
    assert set(vs) <= set(res["variants"]) or set(res["variants"]) >= set(vs[:3])
    assert len(res["variants"]) >= 3


def test_handles_derived_valid():
    vs = tools._entity_variants("Anil Kotabagi")
    hs = tools._entity_handles(vs)
    assert hs, "must derive at least one handle"
    assert all(" " not in h for h in hs)
    for h in hs:
        assert tools._HANDLE_RE.match("@" + h)


def test_variant_fanout_calls_multiple_lanes(monkeypatch):
    seen = []

    def fake_run(adapter, target):
        seen.append((adapter, target))
        return {"status": "ok", "reason": "mock empty", "findings": []}

    monkeypatch.setattr(tools.registry, "run_adapter", fake_run)
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    tools.entity_search("R Kotabagi", "fanout-user-2")
    adapters = {a for a, _ in seen}
    assert "username_probe" in adapters
    assert "websearch" in adapters and "scholar" in adapters
    # username fan-out: >1 derived handle probed
    up_targets = [t for a, t in seen if a == "username_probe"]
    assert len(up_targets) >= 2


# ---------------- throttle ----------------

def test_throttle_anon_strictest():
    for _ in range(tools.THROTTLE_LIMIT_ANON):
        assert tools.throttle_check(None) is True
    assert tools.throttle_check(None) is False
    assert tools.throttle_check("") is False


def test_throttle_user_generous_and_isolated():
    for _ in range(tools.THROTTLE_LIMIT_ANON):
        assert tools.throttle_check("alice") is True
    # anon exhausted does not exhaust authenticated user, and vice versa
    assert tools.throttle_check("alice") is True
    for _ in range(tools.THROTTLE_LIMIT_USER - tools.THROTTLE_LIMIT_ANON - 1):
        assert tools.throttle_check("alice") is True
    assert tools.throttle_check("alice") is False
    assert tools.throttle_check("bob") is True


def test_throttle_window_expiry():
    assert tools.throttle_check("carol", now=1000.0) is True
    for _ in range(tools.THROTTLE_LIMIT_USER - 1):
        assert tools.throttle_check("carol", now=1000.0) is True
    assert tools.throttle_check("carol", now=1000.0) is False
    assert tools.throttle_check("carol", now=1000.0 + 61.0) is True


def test_throttle_buckets_bounded(monkeypatch):
    monkeypatch.setattr(tools, "THROTTLE_BUCKETS_MAX_CLIENTS", 5)
    for i in range(10):
        assert tools.throttle_check("u-%d" % i) is True
    assert len(tools._THROTTLE_BUCKETS) <= 5


def test_throttle_blocks_entity_search():
    for _ in range(tools.THROTTLE_LIMIT_ANON):
        tools.throttle_check(None)
    res = tools.entity_search("R Kotabagi", None)
    assert res["status"] == "rejected"
    assert res.get("field") == "user_id"


# ---------------- offline fixture path + LIVE gating ----------------

def test_offline_kotabagi_fixtures():
    res = tools.entity_search("R Kotabagi", "offline-1")
    assert res["status"] == "ok"
    assert res["live"] is False
    assert len(res["findings"]) >= 6
    assert len(res["cases"]) >= 2
    assert "offline" in res["reason"].lower() or "fixture" in res["reason"].lower()


def test_offline_reason_mentions_gating():
    res = tools.entity_search("Demo Kotabagi", "offline-2")
    assert res["status"] == "ok"
    assert "SHERLOCK_LIVE" in res["reason"] or "offline" in res["reason"].lower()


def test_offline_demo_fixture():
    res = tools.entity_search("Demo Sleuth", "offline-3")
    assert res["status"] == "ok" and res["findings"]
    assert res["live"] is False


def test_live_gating_no_offline_fixture(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")

    def fake_empty(adapter, target):
        return {"status": "ok", "reason": "live mock empty", "findings": []}

    monkeypatch.setattr(tools.registry, "run_adapter", fake_empty)
    res = tools.entity_search("R Kotabagi", "live-user-1")
    assert res["live"] is True
    assert "offline fixture" not in res["reason"]
    assert res["findings"] == [] and res["cases"] == []


def test_live_username_lane_used(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    calls = []

    def fake_run(adapter, target):
        calls.append(adapter)
        if adapter == "username_probe":
            return {"status": "ok", "reason": "live hit",
                    "findings": [{"type": "presence",
                                  "value": "GitHub: https://github.com/rkotabagi",
                                  "source": "username_probe",
                                  "confidence": "low"}]}
        return {"status": "ok", "reason": "empty", "findings": []}

    monkeypatch.setattr(tools.registry, "run_adapter", fake_run)
    res = tools.entity_search("R Kotabagi", "live-user-2")
    assert "username_probe" in calls
    assert res["live"] is True


# ---------------- homonym split end-to-end ----------------

def _kotabagi_adapter_findings():
    return [
        {"type": "scholar_affiliation",
         "value": "affiliation: Example University (0000-0002-1825-0097)",
         "source": "scholar", "confidence": "low"},
        {"type": "scholar_affiliation",
         "value": "affiliation: Another Institute (0000-0002-1825-0098)",
         "source": "scholar", "confidence": "low"},
        {"type": "scholar_work",
         "value": "work: Open methods (ORCID 0000-0002-1825-0097)",
         "source": "scholar", "confidence": "low"},
        {"type": "result_snippet",
         "value": "R Kotabaghi — Another Institute, ORCID 0000-0002-1825-0098",
         "source": "websearch", "confidence": "low"},
    ]


def test_correlate_two_clusters_never_merged():
    cases = correlate.build_entity_cases("R Kotabagi",
                                         _kotabagi_adapter_findings(),
                                         "ENTITY-test")
    assert len(cases) == 2
    affils = sorted(c.get("affiliation", "") for c in cases)
    assert affils == ["Another Institute", "Example University"]
    # no case contains findings from both affiliations
    for c in cases:
        blob = " ".join(f.get("value", "") for f in c["findings"])
        assert not ("Example University" in blob
                    and "Another Institute" in blob)


def test_correlate_orcid_pins_stay_separate():
    cases = correlate.build_entity_cases("R Kotabagi",
                                         _kotabagi_adapter_findings())
    by_aff = {c["affiliation"]: c for c in cases}
    ex_blob = " ".join(f["value"] for f in by_aff["Example University"]["findings"])
    an_blob = " ".join(f["value"] for f in by_aff["Another Institute"]["findings"])
    assert "0000-0002-1825-0097" in ex_blob
    assert "0000-0002-1825-0098" not in ex_blob
    assert "0000-0002-1825-0098" in an_blob
    assert "0000-0002-1825-0097" not in an_blob


def test_end_to_end_kotabagi_two_cases():
    res = tools.entity_search("R Kotabagi", "e2e-1")
    assert len(res["cases"]) == 2
    assert res["homonym_clusters"] == 2
    affils = sorted(c.get("affiliation", "") for c in res["cases"])
    assert "Example University" in affils[0] or "Example University" in affils[1]
    assert "Another Institute" in affils[0] or "Another Institute" in affils[1]


def test_end_to_end_variant_spelling_same_clusters():
    r1 = tools.entity_search("R Kotabagi", "e2e-2")
    r2 = tools.entity_search("R Kotabaghi", "e2e-3")
    assert len(r1["cases"]) == 2 and len(r2["cases"]) == 2
    a1 = sorted(c.get("affiliation", "") for c in r1["cases"])
    a2 = sorted(c.get("affiliation", "") for c in r2["cases"])
    assert a1 == a2


def test_correlate_same_affil_single_case():
    fs = [
        {"type": "scholar_affiliation", "value": "affiliation: Example University",
         "source": "scholar", "confidence": "low"},
        {"type": "scholar_work", "value": "work: Paper A (Example University)",
         "source": "scholar", "confidence": "low"},
    ]
    cases = correlate.build_entity_cases("R Kotabagi", fs)
    assert len(cases) == 1


def test_correlate_empty():
    assert correlate.build_entity_cases("R Kotabagi", []) == []
    assert correlate.build_entity_cases("", [{"type": "t", "value": "v",
                                              "source": "s",
                                              "confidence": "low"}]) == []
    assert correlate.build_entity_cases("R Kotabagi", None) == []


# ---------------- PII + unknown + validation ----------------

def test_pii_email_refused():
    res = tools.entity_search("jane.doe@gmail.com", "pii-1")
    assert res["status"] == "rejected" and res["findings"] == []


def test_pii_phone_refused():
    for bad in ("+91 98200 12345", "+1 415 555 2671"):
        res = tools.entity_search(bad, "pii-2")
        assert res["status"] == "rejected" and res["findings"] == []


def test_unknown_clean_empty():
    res = tools.entity_search("Zzqxjklwvm Unlikely Person 99999", "unk-1")
    assert res["status"] == "ok"
    assert res["findings"] == [] and res["cases"] == []
    assert "no hallucination" in res["reason"]
    assert res["case_id"] is None


def test_empty_and_bad_inputs():
    assert tools.entity_search("", "u")["status"] == "rejected"
    assert tools.entity_search("   ", "u")["status"] == "rejected"
    assert tools.entity_search("x" * 257, "u")["status"] == "rejected"
    assert tools.entity_search("https://example.com/x", "u")["status"] == "rejected"
    assert tools.entity_search("12345 !!!", "u")["status"] == "rejected"


# ---------------- registry + helpers ----------------

def test_registry_conditional_allowlist():
    import os as _os
    for name in ("websearch", "scholar", "company", "page_reader"):
        p = _os.path.join(HERE, "adapters", name + ".py")
        if _os.path.isfile(p):
            assert name in registry.ALLOW_LIST
        else:
            assert name not in registry.ALLOW_LIST
    # guarded import never crashes
    for name in registry.ALLOW_LIST:
        ad = registry.load_adapter(name)
        assert ad.NAME == name
        assert set(("status", "reason", "findings")) <= set(
            ad.run("example-probe-target"))


def test_registry_rejected_unknown_never_raises():
    for bad in ("osintgram", "../evil", "", "PAGE_READER"):
        res = registry.run_adapter(bad, "R Kotabagi")
        assert res["status"] == "rejected" and res["findings"] == []


def test_page_urls_capped_5():
    fs = [{"type": "result_url",
           "value": "https://example.com/p/%d" % i,
           "source": "websearch", "confidence": "low"} for i in range(10)]
    fs.append({"type": "result_url", "value": "https://evil.test/x",
               "source": "websearch", "confidence": "low"})
    urls = tools._extract_urls(fs)
    assert len(urls) == 5
    assert all("example.com" in u for u in urls)


def test_affil_domain_trigger():
    fs = [{"type": "scholar_affiliation",
           "value": "affiliation: Example University https://example.com/u",
           "source": "scholar", "confidence": "low"}]
    assert "example.com" in tools._extract_affil_domains(fs)
    assert tools._extract_affil_domains(
        [{"type": "t", "value": "plain", "source": "s",
          "confidence": "low"}]) == []
