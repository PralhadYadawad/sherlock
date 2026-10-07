"""deep_probe tests — contract, mapping, demo scoping, no-network discipline.

The engine is exercised only through monkeypatched seams or the gated live
smoke. No live third-party traffic in committed tests.
"""
import os

import pytest

from adapters import deep_probe


def _result(status, url=""):
    """Realistic engine shape: status is a QueryResult OBJECT wrapping the
    QueryStatus enum (mirrors sherlock_project.result.QueryResult)."""
    from sherlock_project.result import QueryResult
    return {"status": QueryResult("octocat", "Site", url or
                                  "https://example.com/octocat", status),
            "url_user": url, "url_main": "",
            "http_status": 200 if url else 0}


def _statuses(monkeypatch):
    import sherlock_project.result as _res
    return _res.QueryStatus


def test_contract_shape():
    assert deep_probe.NAME == "deep_probe"
    assert "MIT" in deep_probe.LICENSE_NOTE
    assert "sherlock-project" in deep_probe.LICENSE_NOTE


def test_demo_handle_uses_fast_lane():
    out = deep_probe.run("@demo.sleuth")
    assert out["status"] == "ok" and out["findings"] == []
    assert "fast lane" in out["reason"]


def test_demo_bare_handle_uses_fast_lane():
    out = deep_probe.run("demo.probe")
    assert out["status"] == "ok" and out["findings"] == []


def test_empty_rejected():
    out = deep_probe.run("   ")
    assert out["status"] == "rejected" and out["findings"] == []


def test_email_rejected_pii():
    out = deep_probe.run("someone@example.com")
    assert out["status"] == "rejected" and out["findings"] == []


def test_phone_rejected_pii():
    out = deep_probe.run("+91 98765 43210")
    assert out["status"] == "rejected" and out["findings"] == []


def test_bad_chars_rejected():
    out = deep_probe.run("not a target!!!")
    assert out["status"] == "rejected" and out["findings"] == []


def test_mapping_claimed_becomes_finding(monkeypatch):
    _QS = _statuses(monkeypatch)
    _fake = {
        "GitHub": _result(_QS.CLAIMED, "https://github.com/octocat"),
        "Nope": _result(_QS.AVAILABLE, ""),
        "Bad": _result(_QS.ILLEGAL, ""),
        "Flaky": _result(_QS.UNKNOWN, ""),
        "Walled": _result(_QS.WAF, ""),
    }
    monkeypatch.setattr(deep_probe, "_query", lambda h, s, timeout=10: _fake)
    monkeypatch.setattr(deep_probe, "_load_site_data",
                        lambda: ({"GitHub": {}, "Nope": {}, "Bad": {},
                                  "Flaky": {}, "Walled": {}}, None))
    out = deep_probe.run("octocat", sites_cap=None)
    assert out["status"] == "ok" and len(out["findings"]) == 1
    assert out["findings"][0]["value"] == (
        "GitHub: https://github.com/octocat")
    assert out["findings"][0]["source"] == "deep_probe"
    assert "1 of 5 sites" in out["reason"] and "2 errored" in out["reason"]


def test_mapping_all_miss_empty_with_reason(monkeypatch):
    _QS = _statuses(monkeypatch)
    _fake = {"Nope": _result(_QS.AVAILABLE, "")}
    monkeypatch.setattr(deep_probe, "_query", lambda h, s, timeout=10: _fake)
    monkeypatch.setattr(deep_probe, "_load_site_data",
                        lambda: ({"Nope": {}}, None))
    out = deep_probe.run("octocat", sites_cap=None)
    assert out["status"] == "ok" and out["findings"] == []
    assert "no live presence" in out["reason"]


def test_mapping_claimed_without_url_counts_error(monkeypatch):
    _QS = _statuses(monkeypatch)
    _fake = {"Ghost": _result(_QS.CLAIMED, "")}
    monkeypatch.setattr(deep_probe, "_query", lambda h, s, timeout=10: _fake)
    monkeypatch.setattr(deep_probe, "_load_site_data",
                        lambda: ({"Ghost": {}}, None))
    out = deep_probe.run("octocat", sites_cap=None)
    assert out["status"] == "ok" and out["findings"] == []
    assert "1 errored" in out["reason"]


def test_engine_failure_rejected_clean(monkeypatch):
    def _boom(handle, site_data, timeout=10):
        raise RuntimeError("network down")

    monkeypatch.setattr(deep_probe, "_query", _boom)
    monkeypatch.setattr(deep_probe, "_load_site_data",
                        lambda: ({"GitHub": {}}, None))
    out = deep_probe.run("octocat", sites_cap=None)
    assert out["status"] == "rejected" and out["findings"] == []


def test_missing_engine_data_rejected(monkeypatch):
    monkeypatch.setattr(deep_probe, "_load_site_data",
                        lambda: (None, "engine site list unavailable"))
    out = deep_probe.run("octocat", sites_cap=None)
    assert out["status"] == "rejected"
    assert "unavailable" in out["reason"]


def test_sites_cap_bounds(monkeypatch):
    seen = {}

    def _cap(handle, site_data, timeout=10):
        seen["n"] = len(site_data)
        return {}

    monkeypatch.setattr(deep_probe, "_query", _cap)
    _sites = {"S%d" % i: {} for i in range(50)}
    monkeypatch.setattr(deep_probe, "_load_site_data",
                        lambda: (_sites, None))
    out = deep_probe.run("octocat", sites_cap=7)
    assert seen["n"] == 7 and out["status"] == "ok"


def test_registry_allow_lists_deep_probe():
    import registry
    assert "deep_probe" in registry.ALLOW_LIST
    res = registry.run_adapter("deep_probe", "@demo.sleuth")
    assert res["status"] == "ok" and res["findings"] == []


def test_live_smoke_octocat_shape():
    if os.environ.get("SHERLOCK_LIVE") != "1":
        import pytest
        pytest.skip("live smoke (needs SHERLOCK_LIVE=1)")
    out = deep_probe.run("octocat", sites_cap=15)
    assert out["status"] == "ok"
    assert isinstance(out["findings"], list)
    assert all(set(("type", "value", "source", "confidence")) <= set(f)
                for f in out["findings"])


def test_order_sites_priority_first():
    sites = {"Zebra": {"url": "https://z.example/u/{}"},
             "GitHub": {"url": "https://github.com/{}"},
             "Apple": {"url": "https://a.example/u/{}"}}
    ordered = list(deep_probe._order_sites(sites))
    assert ordered[0] == "GitHub"
    assert set(ordered) == set(sites)
