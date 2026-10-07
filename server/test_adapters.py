"""Adapter contract + behavior tests. No network: all HTTP/DNS faked via
monkeypatch. Demo handles/domains only (@demo.*, example.com)."""

import os
import time

import pytest

from adapters import domain_intel, exif_local, oembed_public, username_probe

ADAPTERS = (username_probe, domain_intel, exif_local, oembed_public)

VALID_CONF = {"high", "medium", "low"}


def check_contract(result, name):
    assert set(result) == {"status", "reason", "findings"}, result
    assert result["status"] in ("ok", "rejected")
    assert isinstance(result["reason"], str) and result["reason"]
    assert isinstance(result["findings"], list)
    for f in result["findings"]:
        assert set(f) == {"type", "value", "source", "confidence"}, f
        assert f["source"] == name
        assert f["confidence"] in VALID_CONF
        assert isinstance(f["value"], str) and f["value"]


# ---------- contract: every adapter exposes NAME / LICENSE_NOTE / run ----------

@pytest.mark.parametrize("mod,name", [
    (username_probe, "username_probe"),
    (domain_intel, "domain_intel"),
    (exif_local, "exif_local"),
    (oembed_public, "oembed_public"),
])
def test_contract_signature(mod, name):
    assert mod.NAME == name
    assert "clean-room" in mod.LICENSE_NOTE and "MIT" in mod.LICENSE_NOTE
    assert callable(mod.run)
    out = mod.run("")
    check_contract(out, name)
    assert out["status"] == "rejected" and out["findings"] == []


# ---------- username_probe ----------

def _three_hit(monkeypatch):
    # Deterministic fake: first three site URLs hit.
    seen = {"n": 0}

    def fake2(url, timeout=5):
        seen["n"] += 1
        return 200 if seen["n"] <= 3 else 404

    monkeypatch.setattr(username_probe, "_fetch_status", fake2)


def test_username_ok_three_hits(monkeypatch):
    _three_hit(monkeypatch)
    out = username_probe.run("@demo.sleuth")
    check_contract(out, username_probe.NAME)
    assert out["status"] == "ok"
    assert len(out["findings"]) == 3
    assert all(f["type"] == "presence" for f in out["findings"])


def test_username_empty_rejected():
    out = username_probe.run("   ")
    assert out["status"] == "rejected" and out["findings"] == []


def test_username_email_rejected():
    out = username_probe.run("someone@example.com")
    assert out["status"] == "rejected" and out["findings"] == []


def test_username_phone_rejected():
    out = username_probe.run("+91 98765 43210")
    assert out["status"] == "rejected" and out["findings"] == []


def test_username_bad_chars_rejected():
    out = username_probe.run("not a target!!!")
    assert out["status"] == "rejected" and out["findings"] == []


def test_username_single_hit_stays_low(monkeypatch):
    calls = {"n": 0}

    def fake(url, timeout=5):
        calls["n"] += 1
        return 200 if calls["n"] == 1 else 404

    monkeypatch.setattr(username_probe, "_fetch_status", fake)
    out = username_probe.run("@demo.single")
    assert out["status"] == "ok" and len(out["findings"]) == 1
    assert out["findings"][0]["confidence"] == "low"


def test_username_determinism(monkeypatch):
    _three_hit(monkeypatch)
    a = username_probe.run("@demo.sleuth")
    _three_hit(monkeypatch)
    b = username_probe.run("@demo.sleuth")
    assert a == b


# ---------- domain_intel ----------

def _demo_dns(monkeypatch):
    monkeypatch.setattr(
        domain_intel, "_fetch_crtsh",
        lambda domain, timeout=5: [
            {"name_value": "*.example.com"},
            {"name_value": "www.example.com\nblog.example.com"},
            {"name_value": "other.org"},  # out of scope, must be dropped
        ])
    monkeypatch.setattr(
        domain_intel, "_resolve_dns",
        lambda domain, timeout=5: {"A": ["192.0.2.1"], "AAAA": [],
                                   "CNAME": {}, "contact": "admin@example.com"})


def test_domain_ok_two_subs_one_contact(monkeypatch):
    _demo_dns(monkeypatch)
    out = domain_intel.run("example.com")
    check_contract(out, domain_intel.NAME)
    subs = [f for f in out["findings"] if f["type"] == "subdomain"]
    contacts = [f for f in out["findings"] if f["type"] == "contact"]
    assert len(subs) == 2
    assert {f["value"] for f in subs} == {"www.example.com", "blog.example.com"}
    assert len(contacts) == 1 and "@" in contacts[0]["value"]


def test_domain_empty_rejected():
    assert domain_intel.run("")["status"] == "rejected"


def test_domain_url_rejected():
    out = domain_intel.run("https://example.com/page")
    assert out["status"] == "rejected" and out["findings"] == []


def test_domain_out_of_scope_rejected():
    out = domain_intel.run("google.com")
    assert out["status"] == "rejected" and out["findings"] == []


def test_domain_ct_parse_wildcards_dupes():
    rows = [{"name_value": "*.example.com"},
            {"name_value": "WWW.example.com.\nwww.example.com"},
            {"name_value": "evil-other.org"},
            {"not_a_name": 1},
            "junk"]
    assert domain_intel.parse_ct_rows(rows, "example.com") == ["www.example.com"]


def test_domain_determinism(monkeypatch):
    _demo_dns(monkeypatch)
    assert domain_intel.run("example.com") == domain_intel.run("example.com")


# ---------- exif_local ----------

def _write(tmp_path, name, data: bytes):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_exif_ok_all_fields(tmp_path):
    p = _write(tmp_path, "demo.jpg",
               b"\xff\xd8\xff\xe0MODEL: DemoCam 1000\nGPS: 12.9716,77.5946\n"
               b"TIMESTAMP: 2026-01-02 03:04:05\n" + b"\x00" * 64)
    out = exif_local.run(p)
    check_contract(out, exif_local.NAME)
    assert out["status"] == "ok"
    by_type = {f["type"]: f["value"] for f in out["findings"]}
    assert by_type["exif_model"] == "DemoCam 1000"
    assert by_type["exif_gps"] == "12.9716,77.5946"
    assert "2026-01-02" in by_type["exif_timestamp"]


def test_exif_url_refused():
    out = exif_local.run("https://example.com/pic.jpg")
    assert out["status"] == "rejected" and out["findings"] == []


def test_exif_missing_rejected(tmp_path):
    out = exif_local.run(str(tmp_path / "nope.jpg"))
    assert out["status"] == "rejected" and out["findings"] == []


def test_exif_empty_rejected():
    assert exif_local.run("   ")["status"] == "rejected"


def test_exif_no_fields_ok_empty(tmp_path):
    p = _write(tmp_path, "plain.bin", b"\x00\x01\x02" * 100)
    out = exif_local.run(p)
    assert out["status"] == "ok" and out["findings"] == []


def test_exif_determinism(tmp_path):
    p = _write(tmp_path, "d.jpg", b"MODEL: DemoCam 1000\nGPS: 1.0,2.0\n")
    assert exif_local.run(p) == exif_local.run(p)


# ---------- oembed_public ----------

def test_oembed_ok_demo_reel():
    out = oembed_public.run("https://www.instagram.com/reel/DMYosint001/")
    check_contract(out, oembed_public.NAME)
    assert out["status"] == "ok"
    by_type = {}
    for f in out["findings"]:
        by_type.setdefault(f["type"], []).append(f["value"])
    assert by_type["author"] == ["@demo.archivist"]
    assert any("open-source research" in c for c in by_type["caption"])
    assert len(by_type["transcript_link"]) == 2


def test_oembed_private_rejected():
    out = oembed_public.run("https://www.instagram.com/reel/DMYosint001/?private=1")
    assert out["status"] == "rejected" and out["findings"] == []


def test_oembed_deleted_rejected():
    out = oembed_public.run("https://www.instagram.com/reel/deleted-post-xyz/")
    assert out["status"] == "rejected" and out["findings"] == []


def test_oembed_bad_url_rejected():
    out = oembed_public.run("not-a-url")
    assert out["status"] == "rejected" and out["findings"] == []


def test_oembed_unknown_id_never_hallucinates(monkeypatch):
    monkeypatch.setattr(oembed_public, "fetch_oembed", lambda url, timeout=5: {})
    out = oembed_public.run("https://www.instagram.com/reel/UNKNOWN999/")
    assert out["status"] == "rejected" and out["findings"] == []


def test_oembed_fetch_always_dict(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(oembed_public.requests, "get", boom)
    assert oembed_public.fetch_oembed("https://example.com/x") == {}


def test_oembed_determinism():
    a = oembed_public.run("https://www.instagram.com/reel/DMYosint001/")
    b = oembed_public.run("https://www.instagram.com/reel/DMYosint001/")
    assert a == b


# ---------- perf: 500 records ----------

def test_perf_500_username_probes(monkeypatch):
    monkeypatch.setattr(username_probe, "_fetch_status", lambda url, timeout=5: 200)
    start = time.monotonic()
    total = 0
    for _ in range(500):
        out = username_probe.run("@demo.perf")
        total += len(out["findings"])
    elapsed = time.monotonic() - start
    assert total == 500 * len(username_probe.SITES)
    assert elapsed < 10, "500 probes took %.2fs" % elapsed


# ---------- audit-2 regressions ----------

def test_domain_subdomain_scope_excludes_siblings(monkeypatch):
    """parse/run must scope to the QUERIED domain, not the demo apex."""
    monkeypatch.setattr(
        domain_intel, "_fetch_crtsh",
        lambda d, timeout=5: [
            {"name_value": "www.example.com"},
            {"name_value": "blog.example.com"},
            {"name_value": "mail.blog.example.com"},
        ])
    monkeypatch.setattr(
        domain_intel, "_resolve_dns",
        lambda d, timeout=5: {"A": [], "AAAA": [], "CNAME": {},
                              "contact": ""})
    out = domain_intel.run("blog.example.com")
    vals = {f["value"] for f in out["findings"]
            if f["type"] == "subdomain"}
    assert vals == {"blog.example.com", "mail.blog.example.com"}
    assert "www.example.com" not in vals


def test_exif_marker_past_64k_found(tmp_path):
    """Text markers past the old 64 KiB window must still be found."""
    pad = b"\x00" * (70 * 1024)
    p = tmp_path / "late.jpg"
    p.write_bytes(pad + b"MODEL: LateCam 9\nGPS: 1.5,2.5\n")
    out = exif_local.run(str(p))
    assert out["status"] == "ok"
    by_type = {f["type"]: f["value"] for f in out["findings"]}
    assert by_type["exif_model"] == "LateCam 9"
    assert by_type["exif_gps"] == "1.5,2.5"


# ---------- LIVE: username_probe (mocked, no network) ----------

def test_username_live_sites_curated_30():
    assert len(username_probe.LIVE_SITES) == 30
    assert len(username_probe.DEMO_SITES) == 5
    assert len(username_probe.SITES) == 5  # fixture alias preserved
    for site in username_probe.LIVE_SITES:
        assert "{handle}" in site["url_template"]
        assert site["url_template"].startswith("https://")
        low = site["url_template"].lower()
        assert "password" not in low and "login" not in low


def test_username_classify_taxonomy():
    c = username_probe.classify_live_response
    good = ("<html><head><title>octocat (The Octocat) · GitHub</title></head>"
            "<body><h1>octocat</h1><p>public profile</p></body></html>")
    assert c(200, good, "octocat") == "found"
    assert c(404, "not found", "x") == "not-found"
    assert c(410, "gone", "x") == "not-found"
    assert c(200, "<html><title>x</title>User not found</html>", "x") == "not-found"
    assert c(200, "<html><title>x</title>Could not find user</html>",
             "x") == "not-found"
    assert c(429, "slow down", "x") == "error"
    assert c(502, "bad gateway", "x") == "error"
    assert c(403, "forbidden", "x") == "error"
    assert c(None, "", "x") == "error"
    assert c(200, "", "x") == "error"
    # Login-submit wall is never a hit.
    wall = ('<html><head><title>x</title></head><body>'
            '<form action="/login"><input type="password">'
            'Log in to continue</form></body></html>')
    assert c(200, wall, "x") == "error"
    # Soft-404: generic shell titled without the handle is never a hit.
    shell = ('<html><head><title>Reddit</title></head><body>'
             'user zzqxjklwvm12345unlikely app shell</body></html>')
    assert c(200, shell, "zzqxjklwvm12345unlikely") == "error"
    nohandle = ('<html><head><title>Twitch</title></head><body>'
                'video platform for gamers</body></html>')
    assert c(200, nohandle, "zzqxjklwvm12345unlikely") == "error"


def test_username_live_run_mocked(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")

    def fake_detail(url, timeout=10):
        if "github.com/octocat" in url or "gitlab.com/octocat" in url:
            return 200, ("<html><head><title>octocat profile</title></head>"
                         "<body><h1>octocat</h1> public profile</body></html>")
        if "reddit.com" in url:
            return 404, "not found"
        return 429, "rate limited"

    monkeypatch.setattr(username_probe, "_fetch_live_detail", fake_detail)
    out = username_probe.run("octocat")
    check_contract(out, username_probe.NAME)
    assert out["status"] == "ok"
    assert len(out["findings"]) == 2
    assert all(f["confidence"] == "medium" for f in out["findings"])
    assert "live presence" in out["reason"]


def test_username_demo_still_5_when_live(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    _three_hit(monkeypatch)
    out = username_probe.run("@demo.sleuth")
    assert out["status"] == "ok" and len(out["findings"]) == 3
    assert "3 of 5 sites" in out["reason"]


def test_username_live_all_error_degrades(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    monkeypatch.setattr(username_probe, "_fetch_live_detail",
                        lambda url, timeout=10: (None, ""))
    out = username_probe.run("octocat")
    check_contract(out, username_probe.NAME)
    assert out["status"] == "ok" and out["findings"] == []
    assert "unavailable" in out["reason"]


def test_username_live_uses_10s_timeout_and_ua(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    assert username_probe.TIMEOUT == 10
    assert "Sherlock" in username_probe.USER_AGENT
    seen = {}

    def fake_detail(url, timeout=10):
        seen["timeout"] = timeout
        return 404, "nope"

    monkeypatch.setattr(username_probe, "_fetch_live_detail", fake_detail)
    username_probe.run("octocat")
    assert seen.get("timeout") == 10


# ---------- LIVE: domain_intel (mocked, no network) ----------

def test_domain_crt_502_returns_none(monkeypatch):
    class _R:
        status_code = 502

        def json(self):
            return {}

    monkeypatch.setattr(domain_intel.requests, "get", lambda *a, **k: _R())
    assert domain_intel._fetch_crtsh("example.com") is None


def test_domain_resolve_via_getaddrinfo(monkeypatch):
    import socket as _sock
    fake_infos = [(2, 1, 6, "", ("93.184.215.14", 80)),
                  (2, 1, 6, "", ("93.184.215.14", 80))]
    monkeypatch.setattr(_sock, "getaddrinfo", lambda *a, **k: fake_infos)
    out = domain_intel._resolve_dns("example.com")
    assert out is not None and out["A"] == ["93.184.215.14"]


def test_domain_live_allows_non_demo(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    monkeypatch.setattr(
        domain_intel, "_fetch_crtsh",
        lambda d, timeout=10: [{"name_value": "www.github.com"}])
    monkeypatch.setattr(
        domain_intel, "_resolve_dns",
        lambda d, timeout=10: {"A": ["140.82.121.4"], "AAAA": [],
                               "CNAME": {}, "contact": ""})
    out = domain_intel.run("github.com")
    check_contract(out, domain_intel.NAME)
    assert out["status"] == "ok"
    vals = {f["value"] for f in out["findings"] if f["type"] == "subdomain"}
    assert vals == {"www.github.com"}


def test_domain_live_502_fallback_dns_only(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    monkeypatch.setattr(domain_intel, "_fetch_crtsh",
                        lambda d, timeout=10: None)
    monkeypatch.setattr(domain_intel, "_resolve_dns",
                        lambda d, timeout=10: {"A": ["93.184.215.14"],
                                              "AAAA": [], "CNAME": {},
                                              "contact": ""})
    out = domain_intel.run("example.com")
    assert out["status"] == "ok"
    assert "crt.sh unavailable" in out["reason"]


def test_domain_fixture_rejects_when_not_live(monkeypatch):
    monkeypatch.delenv("SHERLOCK_LIVE", raising=False)
    out = domain_intel.run("github.com")
    assert out["status"] == "rejected" and out["findings"] == []


# ---------- live smoke: REAL network (gated SHERLOCK_LIVE=1) ----------
# No stubs here (this module has no autouse network fixture), so these
# hit the live web when enabled. Targets are fixture-safe:
# example.com (IANA reserved) + octocat (well-known public demo handle).
# Shape-only assertions, never content. Honors SHERLOCK_NO_PACING=1.

def _assert_live_shape(result, name):
    assert set(result) == {"status", "reason", "findings"}, result
    assert result["status"] in ("ok", "rejected")
    assert isinstance(result["reason"], str) and result["reason"]
    assert isinstance(result["findings"], list)
    for f in result["findings"]:
        assert set(f) == {"type", "value", "source", "confidence"}, f
        assert f["source"] == name
        assert f["confidence"] in ("high", "medium", "low")


@pytest.mark.skipif(os.environ.get("SHERLOCK_LIVE") != "1",
                    reason="live smoke needs SHERLOCK_LIVE=1")
def test_live_smoke_username_octocat_real():
    out = username_probe.run("octocat")
    _assert_live_shape(out, username_probe.NAME)


@pytest.mark.skipif(os.environ.get("SHERLOCK_LIVE") != "1",
                    reason="live smoke needs SHERLOCK_LIVE=1")
def test_live_smoke_domain_example_real():
    out = domain_intel.run("example.com")
    _assert_live_shape(out, domain_intel.NAME)


def test_username_canonical_demo_pinned_offline(monkeypatch):
    """DEV-1 regression: @demo.sleuth returns the pinned 3-hit shape with
    zero network, live mode or not, stubs or not."""

    def _boom(url, timeout=5):
        raise RuntimeError("network down")

    monkeypatch.setattr(username_probe, "_fetch_status", _boom)
    for env_live in ("0", "1"):
        monkeypatch.setenv("SHERLOCK_LIVE", env_live)
        out = username_probe.run("@demo.sleuth")
        assert out["status"] == "ok" and len(out["findings"]) == 3
        assert "3 of 5 sites" in out["reason"]
        assert {f["type"] for f in out["findings"]} == {"presence"}
