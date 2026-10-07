"""Golden-run tests (Phase 1). Fixed input -> full playbook -> asserted case file.

Loads demo-data/fixtures/golden_case.json (Kotabagi-shaped, DUMMY/example
only): 2 same-name candidates, mixed lanes, 1 PII trap, 1 login-walled
claim, 1 invented URL. Asserts exact expected case file + exact refusal
reasons. No network, no real PII.
"""

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(os.path.dirname(HERE), "demo-data", "fixtures",
                   "golden_case.json")


def _load(name):
    path = os.path.join(HERE, name + ".py")
    spec = importlib.util.spec_from_file_location("golden_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["golden_" + name] = mod
    spec.loader.exec_module(mod)
    return mod


correlate = _load("correlate")
entity = _load("entity")


def _golden():
    with open(FIX, encoding="utf-8") as fh:
        return json.load(fh)


def test_golden_file_shape():
    g = _golden()
    assert g["query"] == "R Kotabagi"
    assert g["base_case_id"] == "ENTITY-r-kotabagi"
    assert len(g["findings"]) == 14
    assert len(g["fetched_urls"]) == 4
    assert all("example.com" in u for u in g["fetched_urls"])
    assert g["expected"]["kept_count"] == 9
    assert len(g["expected"]["refused"]) == 5
    assert len(g["expected"]["cases"]) == 2


def test_golden_variants_contain_pair():
    g = _golden()
    vs = entity.variants(g["query"])
    assert "r kotabagi" in vs
    assert "r kotabaghi" in vs
    assert vs[0] == "r kotabagi"
    for hint in g["variants_hint"]:
        assert hint in vs


def test_golden_evidence_scores_exact():
    g = _golden()
    scored = correlate.score_findings(g["findings"])
    assert len(scored) == len(g["findings"])
    expect = {e["index"]: e["evidence_score"]
              for e in g["expected"]["evidence_scores"]}
    for s in scored:
        assert s["evidence_score"] == expect[s["index"]], s
    # valid lanes score >= threshold; lone rumor scores 1; garbage scores 0
    by_idx = {s["index"]: s for s in scored}
    for i in range(9):
        assert by_idx[i]["evidence_score"] >= 2, i
    assert by_idx[12]["evidence_score"] == 1
    assert by_idx[13]["evidence_score"] == 0


def test_golden_refusal_reasons_exact():
    g = _golden()
    scored = correlate.score_findings(g["findings"])
    out = correlate.refute(scored, g["fetched_urls"])
    assert len(out["kept"]) == g["expected"]["kept_count"]
    assert out["refused"] == g["expected"]["refused"]
    by_reason = {r["index"]: r["reason"] for r in out["refused"]}
    assert by_reason == {9: "pii_excluded",
                         10: "login_walled_claim",
                         11: "hallucinated_url",
                         12: "insufficient_evidence",
                         13: "unparsable"}
    # required Phase-1 codes are all present
    reasons = set(by_reason.values())
    assert {"insufficient_evidence", "unparsable",
            "login_walled_claim"} <= reasons


def test_golden_refute_accepts_raw_findings():
    g = _golden()
    from_scored = correlate.refute(
        correlate.score_findings(g["findings"]), g["fetched_urls"])
    from_raw = correlate.refute(g["findings"], g["fetched_urls"])
    assert from_raw == from_scored


def test_golden_case_file_exact():
    g = _golden()
    out = correlate.refute(
        correlate.score_findings(g["findings"]), g["fetched_urls"])
    cases = correlate.build_entity_cases(
        g["query"], out["kept"], g["base_case_id"])
    assert cases == g["expected"]["cases"]
    summary = [{"case_id": c["case_id"],
                "cluster_id": c.get("cluster_id"),
                "affiliation": c.get("affiliation"),
                "finding_count": c.get("finding_count"),
                "lanes": c.get("lanes")} for c in cases]
    assert summary == g["expected"]["case_summary"]
    assert [c["case_id"] for c in cases] == [
        "ENTITY-r-kotabagi:candidate-1",
        "ENTITY-r-kotabagi:candidate-2"]


def test_golden_homonyms_never_merged():
    g = _golden()
    out = correlate.refute(
        correlate.score_findings(g["findings"]), g["fetched_urls"])
    cases = correlate.build_entity_cases(
        g["query"], out["kept"], g["base_case_id"])
    assert len(cases) == 2
    affils = sorted(c.get("affiliation", "") for c in cases)
    assert affils == ["Another Institute", "Example University"]
    for c in cases:
        blob = " ".join(f.get("value", "") for f in c["findings"])
        assert not ("Example University" in blob
                    and "Another Institute" in blob), c["case_id"]
    # ORCID pins stay separate
    by_aff = {c["affiliation"]: c for c in cases}
    ex = " ".join(f["value"] for f in by_aff["Example University"]["findings"])
    an = " ".join(f["value"] for f in by_aff["Another Institute"]["findings"])
    assert "0000-0002-1825-0097" in ex
    assert "0000-0002-1825-0098" not in ex
    assert "0000-0002-1825-0098" in an
    assert "0000-0002-1825-0097" not in an


def test_golden_no_hallucinated_urls():
    g = _golden()
    fetched = set(u.lower().rstrip("/") for u in g["fetched_urls"])
    out = correlate.refute(
        correlate.score_findings(g["findings"]), g["fetched_urls"])
    assert correlate.check_urls(out["kept"], g["fetched_urls"]) == []
    for f in out["kept"]:
        for u in correlate.extract_claimed_urls(f):
            assert u in fetched, u
    # invented URL is refused, never kept
    assert correlate.check_urls(
        correlate.score_findings(g["findings"]),
        g["fetched_urls"]) == [
        {"index": 11,
         "claimed": ["https://example.com/papers/999-unfetched-secret"],
         "hallucinated": ["https://example.com/papers/999-unfetched-secret"]}]
    kept_vals = " ".join(f["value"] for f in out["kept"])
    assert "999-unfetched-secret" not in kept_vals


def test_golden_pii_login_never_kept():
    g = _golden()
    out = correlate.refute(
        correlate.score_findings(g["findings"]), g["fetched_urls"])
    kept_blob = " ".join(f.get("value", "") for f in out["kept"])
    assert "r.kotabagi@gmail.com" not in kept_blob
    assert "login required to view" not in kept_blob
    # high-confidence PII is still refused (score 3 but pii_excluded wins)
    scored = correlate.score_findings(g["findings"])
    by_idx = {s["index"]: s for s in scored}
    assert by_idx[9]["evidence_score"] == 3
    assert by_idx[10]["evidence_score"] == 3
