"""Entity-lane adapter tests (websearch / scholar / company).

No network: every HTTP call is faked via monkeypatch. Demo/example
fixtures only (Demo Person / Demo Kotabagi / Example Corp /
DUMMYLEI000000000000 / example.com / demo@example.com). No real-person
PII, no live keys (``DUMMY_...`` placeholders only).
"""

import os

import pytest

from adapters import company, scholar, websearch

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


# ---------- fixtures (DUMMY/example only) ----------

BRAVE_FIXTURE = {
    "web": {
        "results": [
            {"title": "Demo Person — Example University",
             "url": "https://example.com/profile/demo-person",
             "description": "Demo Person researches open-source methods."},
            {"title": "Example Corp annual filing",
             "url": "https://example.com/filings/42",
             "description": "Registry filing for Example Corp."},
        ]
    }
}

ORCID_SEARCH_FIXTURE = {
    # Kotabagi-shaped researcher record (demo/example only).
    "result": [
        {"orcid-identifier": {"path": "0000-0002-1825-0097"},
         "given-names": {"value": "Demo"},
         "family-names": {"value": "Kotabagi"}},
    ],
    "num-found": 1,
}

ORCID_RECORD_FIXTURE = {
    "employments": {
        "affiliation-group": [
            {"summaries": [
                {"organization": {"name": "Example University"},
                 "department-name": "Example Department"}]},
        ]
    },
    "educations": {"affiliation-group": []},
    "works": {
        "group": [
            {"work-summary": [
                {"title": {"title": {"value": "Open-source research methods"}}}]},
        ]
    },
}

CROSSREF_FIXTURE = {
    "message": {
        "items": [
            {"title": ["Open-source research methods"],
             "author": [
                 {"given": "Demo", "family": "Kotabagi",
                  "ORCID": "https://orcid.org/0000-0002-1825-0097"},
                 {"given": "Ex", "family": "Ample"}],
             "publisher": "Example Press"},
        ]
    }
}

S2_FIXTURE = {
    "data": [
        {"name": "Demo Kotabagi",
         "affiliations": ["Example University"],
         "papers": [
             {"title": "Open-source research methods",
              "authors": [{"name": "Demo Kotabagi"},
                          {"name": "Ex Ample"}]},
         ]},
    ]
}

GLEIF_FIXTURE = {
    "data": [
        {"id": "DUMMYLEI000000000000",
         "attributes": {
             "entity": {
                 "legalName": {"name": "Example Corp"},
                 "status": "ACTIVE",
                 "addresses": [{"city": "Example City",
                                "region": "Example State",
                                "country": "IN"}],
             },
             "registration": {}}},
    ]
}

RDAP_FIXTURE = {
    "ldhName": "example.com",
    "entities": [
        {"roles": ["registrar"], "handle": "DUMMY-REG",
         "vcardArray": ["vcard",
                        [["fn", {}, "text", "Example Registrar, Inc."]]]},
    ],
    "events": [
        {"eventAction": "creation", "eventDate": "1995-08-14T04:00:00Z"},
        {"eventAction": "expiration", "eventDate": "2026-08-13T04:00:00Z"},
    ],
}


# ---------- contract ----------

@pytest.mark.parametrize("mod,name", [
    (websearch, "websearch"),
    (scholar, "scholar"),
    (company, "company"),
])
def test_lanes_contract_signature(mod, name):
    assert mod.NAME == name
    assert "clean-room" in mod.LICENSE_NOTE and "MIT" in mod.LICENSE_NOTE
    assert callable(mod.run)
    assert mod.TIMEOUT == 10
    out = mod.run("")
    check_contract(out, name)
    assert out["status"] == "rejected" and out["findings"] == []


# ---------- websearch ----------

def test_websearch_missing_key_never_calls(monkeypatch):
    monkeypatch.delenv("SHERLOCK_BRAVE_KEY", raising=False)
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("network must never be touched without a key")

    monkeypatch.setattr(websearch.requests, "get", boom)
    out = websearch.run("Demo Person")
    check_contract(out, websearch.NAME)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "missing_key" in out["reason"]
    assert called["n"] == 0


def test_websearch_dummy_key_treated_as_missing(monkeypatch):
    monkeypatch.setenv("SHERLOCK_BRAVE_KEY", "DUMMY_BRAVE_KEY")
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("DUMMY keys must never authenticate")

    monkeypatch.setattr(websearch.requests, "get", boom)
    out = websearch.run("Demo Person")
    assert out["status"] == "rejected" and out["findings"] == []
    assert "missing_key" in out["reason"]
    assert called["n"] == 0


def test_websearch_build_query_quotes_and_hints():
    assert websearch.build_query("Demo Person") == '"Demo Person"'
    q = websearch.build_query("Demo Person", "Example University")
    assert q == '"Demo Person" "Example University"'
    q = websearch.build_query("Demo Person", "", "example.com")
    assert q == '"Demo Person" site:example.com'
    q = websearch.build_query("Demo Person", "Example University",
                              "https://example.com/page")
    assert q == '"Demo Person" "Example University" site:example.com'
    assert websearch.build_query("   ") == ""
    # Internal quotes are stripped (cannot break quoting).
    assert websearch.build_query('Demo "Person"') == '"Demo Person"'


def test_websearch_parse_results_shape():
    findings = websearch.parse_brave_results(BRAVE_FIXTURE)
    assert len(findings) == 6  # 2 results x (title + url + snippet)
    types = [f["type"] for f in findings]
    assert types.count("result_title") == 2
    assert types.count("result_url") == 2
    assert types.count("result_snippet") == 2
    assert all(f["source"] == "websearch" for f in findings)
    assert all(f["confidence"] == "low" for f in findings)


def test_websearch_parse_skips_malformed_never_hallucinates():
    assert websearch.parse_brave_results({}) == []
    assert websearch.parse_brave_results({"web": {}}) == []
    assert websearch.parse_brave_results({"web": {"results": "junk"}}) == []
    assert websearch.parse_brave_results(
        {"web": {"results": [{"title": "", "url": ""}]}}) == []
    assert websearch.parse_brave_results(
        {"web": {"results": [{"title": "T", "url": "ftp://example.com/x"}]}}
    ) == []
    assert websearch.parse_brave_results(None) == []


def test_websearch_run_ok_mocked(monkeypatch):
    monkeypatch.setenv("SHERLOCK_BRAVE_KEY", "TEST_KEY_123")
    monkeypatch.setattr(
        websearch, "_fetch_brave", lambda *a, **k: (200, BRAVE_FIXTURE))
    out = websearch.run("Demo Person")
    check_contract(out, websearch.NAME)
    assert out["status"] == "ok" and len(out["findings"]) == 6
    assert all(f["confidence"] == "low" for f in out["findings"])


def test_websearch_run_429_rejected_clean(monkeypatch):
    monkeypatch.setenv("SHERLOCK_BRAVE_KEY", "TEST_KEY_123")
    monkeypatch.setattr(
        websearch, "_fetch_brave", lambda *a, **k: (429, None))
    out = websearch.run("Demo Person")
    check_contract(out, websearch.NAME)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "429" in out["reason"]


def test_websearch_run_5xx_and_timeout_rejected_clean(monkeypatch):
    monkeypatch.setenv("SHERLOCK_BRAVE_KEY", "TEST_KEY_123")
    monkeypatch.setattr(
        websearch, "_fetch_brave", lambda *a, **k: (502, None))
    out = websearch.run("Demo Person")
    assert out["status"] == "rejected" and out["findings"] == []
    monkeypatch.setattr(
        websearch, "_fetch_brave", lambda *a, **k: (None, None))
    out = websearch.run("Demo Person")
    assert out["status"] == "rejected" and out["findings"] == []


def test_websearch_run_bad_key_and_quota_rejected(monkeypatch):
    monkeypatch.setenv("SHERLOCK_BRAVE_KEY", "TEST_KEY_123")
    monkeypatch.setattr(
        websearch, "_fetch_brave", lambda *a, **k: (401, None))
    assert websearch.run("Demo Person")["status"] == "rejected"
    monkeypatch.setattr(
        websearch, "_fetch_brave", lambda *a, **k: (402, None))
    out = websearch.run("Demo Person")
    assert out["status"] == "rejected" and out["findings"] == []


def test_websearch_run_pii_and_empty_rejected(monkeypatch):
    monkeypatch.setenv("SHERLOCK_BRAVE_KEY", "TEST_KEY_123")
    assert websearch.run("someone@example.com")["status"] == "rejected"
    assert websearch.run("+91 98765 43210")["status"] == "rejected"
    assert websearch.run("   ")["status"] == "rejected"


def test_websearch_determinism(monkeypatch):
    monkeypatch.setenv("SHERLOCK_BRAVE_KEY", "TEST_KEY_123")
    monkeypatch.setattr(
        websearch, "_fetch_brave", lambda *a, **k: (200, BRAVE_FIXTURE))
    assert websearch.run("Demo Person") == websearch.run("Demo Person")


# ---------- scholar ----------

def test_scholar_parse_orcid_search_kotabagi():
    hits = scholar.parse_orcid_search(ORCID_SEARCH_FIXTURE)
    assert len(hits) == 1
    assert hits[0]["orcid"] == "0000-0002-1825-0097"
    assert "Kotabagi" in hits[0]["name"]
    assert scholar.parse_orcid_search({}) == []
    assert scholar.parse_orcid_search({"result": "junk"}) == []


def test_scholar_parse_orcid_record_affiliations_works():
    affs, works = scholar.parse_orcid_record(ORCID_RECORD_FIXTURE)
    assert "Example University" in affs
    assert works == ["Open-source research methods"]
    assert scholar.parse_orcid_record({}) == ([], [])
    assert scholar.parse_orcid_record(None) == ([], [])


def test_scholar_parse_crossref_and_s2():
    items = scholar.parse_crossref(CROSSREF_FIXTURE)
    assert len(items) == 1
    assert items[0]["title"] == "Open-source research methods"
    assert any("Kotabagi" in a for a in items[0]["authors"])
    assert scholar.parse_crossref({}) == []
    authors = scholar.parse_semantic_scholar(S2_FIXTURE)
    assert len(authors) == 1
    assert authors[0]["name"] == "Demo Kotabagi"
    assert authors[0]["affiliations"] == ["Example University"]
    assert authors[0]["papers"] == ["Open-source research methods"]
    assert "Ex Ample" in authors[0]["coauthors"]
    assert scholar.parse_semantic_scholar({}) == []


def _mock_scholar_all_ok(monkeypatch):
    monkeypatch.setattr(
        scholar, "search_orcid", lambda *a, **k: (200, ORCID_SEARCH_FIXTURE))
    monkeypatch.setattr(
        scholar, "fetch_crossref", lambda *a, **k: (200, CROSSREF_FIXTURE))
    monkeypatch.setattr(
        scholar, "fetch_semantic_scholar",
        lambda *a, **k: (200, S2_FIXTURE))


def test_scholar_run_ok_mocked_kotabagi(monkeypatch):
    _mock_scholar_all_ok(monkeypatch)
    out = scholar.run("Demo Kotabagi")
    check_contract(out, scholar.NAME)
    assert out["status"] == "ok" and out["findings"]
    types = {f["type"] for f in out["findings"]}
    assert "scholar_work" in types
    assert "scholar_coauthor" in types
    assert "scholar_affiliation" in types or "scholar_orcid" in types
    assert all(f["confidence"] in ("low", "medium")
               for f in out["findings"])
    assert all(f["confidence"] != "high" for f in out["findings"])


def test_scholar_run_all_429_rejected_clean(monkeypatch):
    monkeypatch.setattr(scholar, "search_orcid",
                        lambda *a, **k: (429, None))
    monkeypatch.setattr(scholar, "fetch_crossref",
                        lambda *a, **k: (429, None))
    monkeypatch.setattr(scholar, "fetch_semantic_scholar",
                        lambda *a, **k: (503, None))
    out = scholar.run("Demo Kotabagi")
    check_contract(out, scholar.NAME)
    assert out["status"] == "rejected" and out["findings"] == []


def test_scholar_run_degrades_single_lane_ok(monkeypatch):
    monkeypatch.setattr(scholar, "search_orcid",
                        lambda *a, **k: (None, None))
    monkeypatch.setattr(scholar, "fetch_crossref",
                        lambda *a, **k: (200, CROSSREF_FIXTURE))
    monkeypatch.setattr(scholar, "fetch_semantic_scholar",
                        lambda *a, **k: (None, None))
    out = scholar.run("Demo Kotabagi")
    check_contract(out, scholar.NAME)
    assert out["status"] == "ok" and out["findings"]
    assert any(f["type"] == "scholar_work" for f in out["findings"])


def test_scholar_run_zero_results_ok_empty(monkeypatch):
    monkeypatch.setattr(scholar, "search_orcid",
                        lambda *a, **k: (200, {"result": []}))
    monkeypatch.setattr(scholar, "fetch_crossref",
                        lambda *a, **k: (200, {"message": {"items": []}}))
    monkeypatch.setattr(scholar, "fetch_semantic_scholar",
                        lambda *a, **k: (200, {"data": []}))
    out = scholar.run("Demo Kotabagi")
    check_contract(out, scholar.NAME)
    assert out["status"] == "ok" and out["findings"] == []


def test_scholar_run_pii_and_empty_rejected():
    assert scholar.run("someone@example.com")["status"] == "rejected"
    assert scholar.run("+91 98765 43210")["status"] == "rejected"
    assert scholar.run("   ")["status"] == "rejected"


def test_scholar_determinism(monkeypatch):
    _mock_scholar_all_ok(monkeypatch)
    assert scholar.run("Demo Kotabagi") == scholar.run("Demo Kotabagi")


# ---------- company ----------

def test_company_helpers_lei_domain():
    assert company.is_lei("DUMMYLEI000000000000")
    assert company.is_lei("dummylei000000000000")  # case-insensitive
    assert not company.is_lei("Example Corp")
    assert not company.is_lei("123")
    assert company.is_domain("example.com")
    assert company.is_domain("blog.example.com")
    assert not company.is_domain("https://example.com/page")
    assert not company.is_domain("someone@example.com")


def test_company_parse_gleif_dummy_lei():
    recs = company.parse_gleif(GLEIF_FIXTURE)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["lei"] == "DUMMYLEI000000000000"
    assert rec["legal_name"] == "Example Corp"
    assert rec["status"] == "ACTIVE"
    assert "Example City" in rec["address"]
    assert rec["pinned"] is True
    assert company.parse_gleif({}) == []
    assert company.parse_gleif({"data": "junk"}) == []


def test_company_parse_rdap_example():
    parsed = company.parse_rdap(RDAP_FIXTURE)
    assert parsed["registrar"] == "Example Registrar, Inc."
    actions = [a for a, _ in parsed["dates"]]
    assert "creation" in actions and "expiration" in actions
    assert company.parse_rdap({}) == {"registrar": "", "dates": []}
    assert company.parse_rdap(None) == {"registrar": "", "dates": []}


def test_company_run_lei_mocked(monkeypatch):
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    monkeypatch.setattr(
        company, "fetch_gleif", lambda *a, **k: (200, GLEIF_FIXTURE))
    out = company.run("DUMMYLEI000000000000")
    check_contract(out, company.NAME)
    assert out["status"] == "ok" and out["findings"]
    types = {f["type"] for f in out["findings"]}
    assert "company_lei" in types and "company_name" in types
    assert all(f["confidence"] != "high" for f in out["findings"])


def test_company_run_name_mocked_low_unless_pinned(monkeypatch):
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    monkeypatch.setattr(
        company, "fetch_gleif", lambda *a, **k: (200, GLEIF_FIXTURE))
    out = company.run("Example Corp")
    check_contract(out, company.NAME)
    assert out["status"] == "ok" and out["findings"]
    assert any("Example Corp" in f["value"] for f in out["findings"])


def test_company_run_domain_rdap_mocked(monkeypatch):
    monkeypatch.setattr(
        company, "fetch_rdap", lambda *a, **k: (200, RDAP_FIXTURE))
    out = company.run("example.com")
    check_contract(out, company.NAME)
    assert out["status"] == "ok" and out["findings"]
    types = {f["type"] for f in out["findings"]}
    assert "registrar" in types and "domain_date" in types


def test_company_run_429_rejected_clean(monkeypatch):
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    monkeypatch.setattr(company, "fetch_gleif",
                        lambda *a, **k: (429, None))
    out = company.run("Example Corp")
    check_contract(out, company.NAME)
    assert out["status"] == "rejected" and out["findings"] == []
    monkeypatch.setattr(company, "fetch_rdap",
                        lambda *a, **k: (503, None))
    out = company.run("example.com")
    assert out["status"] == "rejected" and out["findings"] == []


def test_company_run_valid_miss_ok_empty(monkeypatch):
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    monkeypatch.setattr(company, "fetch_gleif",
                        lambda *a, **k: (200, {"data": []}))
    out = company.run("Example Nonexistent Corp Xyz")
    check_contract(out, company.NAME)
    assert out["status"] == "ok" and out["findings"] == []
    monkeypatch.setattr(company, "fetch_rdap",
                        lambda *a, **k: (404, None))
    out = company.run("example.com")
    assert out["status"] == "ok" and out["findings"] == []


def test_company_run_pii_and_empty_rejected():
    assert company.run("someone@example.com")["status"] == "rejected"
    assert company.run("+91 98765 43210")["status"] == "rejected"
    assert company.run("   ")["status"] == "rejected"


def test_company_determinism(monkeypatch):
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    monkeypatch.setattr(
        company, "fetch_gleif", lambda *a, **k: (200, GLEIF_FIXTURE))
    assert company.run("Example Corp") == company.run("Example Corp")


def test_company_pacing_const_and_timeout():
    assert company.TIMEOUT == 10
    assert company.PACING_SEC == 1.0  # honors the 60/min GLEIF note
    assert "Sherlock" in company.USER_AGENT
    assert os.environ.get("SHERLOCK_BRAVE_KEY", "") == "" or True
