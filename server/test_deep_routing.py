"""Deep-routing tests (>=12): entity_search fast/deep streams.

Covers: depth param routing (default fast, explicit fast/deep, invalid
rejected), fast unchanged (never calls deep_probe), deep merges fast +
deep findings with lane tags preserved, deep passes sites_cap ~120, deep
failure/exception degrades to fast results + reason, demo fixture-pinning
+ determinism in both streams, PII/throttle unchanged per stream, honest
sync minutes-long note in deep reason, offline deep never sweeps.

Hermetic: no network (requests.get + socket stubbed; live lanes fully
mocked via registry.run_adapter; real deep_probe touched only on demo
handles, which fast-lane before any network). DUMMY/example fixtures only.
"""

import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, tag="rout_test_"):
    path = os.path.join(HERE, name + ".py")
    spec = importlib.util.spec_from_file_location(tag + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[tag + name] = mod
    spec.loader.exec_module(mod)
    return mod


registry = _load("registry")
correlate = _load("correlate")
tools = _load("tools")
entity = _load("entity")


class _Resp:
    def __init__(self, status=404):
        self.status_code = status
        self.text = ""
        self.headers = {}

    def json(self):
        return {}


def _fake_http_get(url, **kw):
    s = str(url)
    if "demo.sleuth" in s and "example.com" in s:
        if any(k in s for k in ("/users/", "/@", "/blog/")):
            return _Resp(200)
    return _Resp(404)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SHERLOCK_DB", str(tmp_path / "routing.db"))
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


FAST_FINDING = {"type": "presence",
                "value": "GitHub: https://github.com/demo-deep-person",
                "source": "username_probe", "confidence": "low"}
DEEP_FINDING = {"type": "presence",
                "value": "GitLab: https://gitlab.com/demo-deep-person",
                "source": "deep_probe", "confidence": "medium"}


def _live_mock(monkeypatch, deep_result="ok", record=None):
    """Mock all entity lanes for live mode. deep_result: ok|rejected|raise."""
    if record is None:
        record = []

    def fake_run(adapter, target, **kwargs):
        record.append((adapter, target, dict(kwargs)))
        if adapter == "username_probe":
            return {"status": "ok", "reason": "live hit",
                    "findings": [dict(FAST_FINDING)]}
        if adapter == "deep_probe":
            if deep_result == "raise":
                raise RuntimeError("sweep down")
            if deep_result == "rejected":
                return {"status": "rejected",
                        "reason": "engine site list unavailable",
                        "findings": []}
            return {"status": "ok",
                    "reason": "deep sweep: 1 of 120 sites hit",
                    "findings": [dict(DEEP_FINDING)]}
        return {"status": "ok", "reason": "live mock empty", "findings": []}

    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    monkeypatch.setattr(tools.registry, "run_adapter", fake_run)
    return record


# ---------------- routing param ----------------

def test_depth_default_is_fast():
    res = tools.entity_search("R Kotabagi", "rout-default-1")
    assert res["status"] == "ok"
    assert res["depth"] == "fast"
    assert "sites_cap" not in res


def test_depth_fast_explicit_matches_default():
    r_default = tools.entity_search("R Kotabagi", "rout-fast-1")
    r_fast = tools.entity_search("R Kotabagi", "rout-fast-1b",
                                 depth="fast")
    assert r_fast["depth"] == "fast"
    assert r_fast["findings"] == r_default["findings"]
    assert [c["case_id"] for c in r_fast["cases"]] == \
        [c["case_id"] for c in r_default["cases"]]


def test_depth_invalid_rejected():
    res = tools.entity_search("R Kotabagi", "rout-bad-1", depth="turbo")
    assert res["status"] == "rejected"
    assert res.get("field") == "depth"
    assert res["findings"] == []


def test_depth_invalid_types_rejected():
    for bad in (None, 123, "", "DEEP", "Deep", "fast "):
        res = tools.entity_search("R Kotabagi", "rout-bad-2", depth=bad)
        assert res["status"] == "rejected", bad
        assert res.get("field") == "depth", bad


# ---------------- fast unchanged ----------------

def test_fast_never_calls_deep_probe(monkeypatch):
    seen = []

    def fake_run(adapter, target, **kwargs):
        seen.append(adapter)
        return {"status": "ok", "reason": "mock empty", "findings": []}

    monkeypatch.setattr(tools.registry, "run_adapter", fake_run)
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    res = tools.entity_search("R Kotabagi", "rout-fast-2", depth="fast")
    assert "deep_probe" not in seen
    assert res["depth"] == "fast"


# ---------------- deep merges lanes ----------------

def test_deep_merges_lanes_lane_tags_preserved(monkeypatch):
    _live_mock(monkeypatch)
    res = tools.entity_search("Deep Demo Person", "rout-deep-1",
                              depth="deep")
    assert res["status"] == "ok"
    assert res["depth"] == "deep"
    assert res["live"] is True
    values = [f["value"] for f in res["findings"]]
    assert FAST_FINDING["value"] in values
    assert DEEP_FINDING["value"] in values
    sources = {f["source"] for f in res["findings"]}
    assert "username_probe" in sources and "deep_probe" in sources
    # Same case file: one cluster, both lane tags present in its lanes.
    assert len(res["cases"]) == 1
    assert "username_probe" in res["cases"][0]["lanes"]
    assert "deep_probe" in res["cases"][0]["lanes"]
    assert res["sites_cap"] == tools.DEEP_SITES_CAP


def test_deep_respects_sites_cap(monkeypatch):
    record = _live_mock(monkeypatch)
    tools.entity_search("Deep Demo Person", "rout-deep-2", depth="deep")
    deep_calls = [kw for ad, _, kw in record if ad == "deep_probe"]
    assert deep_calls, "deep stream must sweep deep_probe"
    for kw in deep_calls:
        assert kw.get("sites_cap") == tools.DEEP_SITES_CAP == 120


# ---------------- deep failure degrades ----------------

def test_deep_failure_degrades_to_fast_results(monkeypatch):
    _live_mock(monkeypatch, deep_result="rejected")
    res = tools.entity_search("Deep Demo Person", "rout-deep-3",
                              depth="deep")
    assert res["status"] == "ok"
    values = [f["value"] for f in res["findings"]]
    assert FAST_FINDING["value"] in values
    assert DEEP_FINDING["value"] not in values
    assert "degraded to fast results" in res["reason"]


def test_deep_exception_degrades_to_fast_results(monkeypatch):
    _live_mock(monkeypatch, deep_result="raise")
    res = tools.entity_search("Deep Demo Person", "rout-deep-4",
                              depth="deep")
    assert res["status"] == "ok"
    values = [f["value"] for f in res["findings"]]
    assert FAST_FINDING["value"] in values
    assert "degraded to fast results" in res["reason"]


# ---------------- demo pinning + determinism ----------------

def test_demo_determinism_both_streams_offline():
    r_fast = tools.entity_search("Demo Sleuth", "rout-demo-1",
                                 depth="fast")
    r_deep = tools.entity_search("Demo Sleuth", "rout-demo-2",
                                 depth="deep")
    assert r_fast["status"] == "ok" and r_deep["status"] == "ok"
    assert r_fast["findings"] == r_deep["findings"]
    assert r_fast["findings"], "demo fixtures must be non-empty"
    assert r_deep["depth"] == "deep" and r_deep["live"] is False
    low = r_deep["reason"].lower()
    assert "offline" in low and "minute" in low


def test_kotabagi_offline_deep_matches_fast():
    r_fast = tools.entity_search("R Kotabagi", "rout-kot-1", depth="fast")
    r_deep = tools.entity_search("R Kotabagi", "rout-kot-2", depth="deep")
    assert r_fast["status"] == "ok" and r_deep["status"] == "ok"
    assert r_deep["findings"] == r_fast["findings"]
    assert len(r_deep["cases"]) == 2 == len(r_fast["cases"])
    assert r_deep["homonym_clusters"] == 2


def test_demo_handle_deep_probe_pinned_via_registry():
    # Real adapter, demo handle: fast-lanes before any network/engine.
    res = registry.run_adapter("deep_probe", "@demo.sleuth", sites_cap=7)
    assert res["status"] == "ok" and res["findings"] == []
    assert "fast lane" in res["reason"]
    # Backward compat: single-arg adapters ignore the routed kwarg.
    res2 = registry.run_adapter("username_probe", "@demo.sleuth",
                                sites_cap=7)
    assert res2["status"] == "ok" and res2["findings"]


def test_deep_offline_never_calls_deep_probe(monkeypatch):
    seen = []
    orig = tools.registry.run_adapter

    def spy(adapter, target, **kwargs):
        seen.append(adapter)
        return orig(adapter, target, **kwargs)

    monkeypatch.setattr(tools.registry, "run_adapter", spy)
    res = tools.entity_search("R Kotabagi", "rout-off-1", depth="deep")
    assert "deep_probe" not in seen
    assert res["status"] == "ok" and res["depth"] == "deep"


# ---------------- PII / throttle unchanged ----------------

def test_pii_refused_both_depths():
    for bad in ("jane.doe@gmail.com", "+91 98200 12345"):
        for depth in ("fast", "deep"):
            res = tools.entity_search(bad, "rout-pii-1", depth=depth)
            assert res["status"] == "rejected", (bad, depth)
            assert res["findings"] == []


def test_throttle_blocks_both_depths():
    for _ in range(tools.THROTTLE_LIMIT_ANON):
        tools.throttle_check(None)
    for depth in ("fast", "deep"):
        res = tools.entity_search("R Kotabagi", None, depth=depth)
        assert res["status"] == "rejected", depth
        assert res.get("field") == "user_id"


# ---------------- honest sync note ----------------

def test_deep_sync_note_in_reason(monkeypatch):
    _live_mock(monkeypatch)
    res = tools.entity_search("Deep Demo Person", "rout-deep-5",
                              depth="deep")
    low = res["reason"].lower()
    assert "sync" in low
    assert "minute" in low
    assert "background" in low


def test_deep_unknown_empty_with_note():
    res = tools.entity_search("Zzqxjklwvm Unlikely Person 99999",
                              "rout-unk-1", depth="deep")
    assert res["status"] == "ok"
    assert res["findings"] == [] and res["cases"] == []
    assert res["case_id"] is None
    assert res["depth"] == "deep"
    assert res["sites_cap"] == tools.DEEP_SITES_CAP
    assert "no hallucination" in res["reason"]
