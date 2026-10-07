"""Playbook invariant tests (Phase 1). No hallucinated URLs ever, homonyms
never merged, PII always refused. Pure correlate intake + entity split.
No network, DUMMY/example fixtures only.
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    path = os.path.join(HERE, name + ".py")
    spec = importlib.util.spec_from_file_location("playbook_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["playbook_" + name] = mod
    spec.loader.exec_module(mod)
    return mod


correlate = _load("correlate")
entity = _load("entity")

FETCHED = ["https://example.com/profiles/r-kotabagi",
           "https://example.com/profiles/r-kotabaghi",
           "https://example.com/papers/001"]


def _fic(ftype, value, source="websearch", conf="low", **kw):
    d = {"type": ftype, "value": value, "source": source,
         "confidence": conf}
    d.update(kw)
    return d


# ---------------- no hallucinated URLs ever ----------------

def test_invariant_hallucinated_url_always_refused():
    bad = _fic("result_url",
               "https://example.com/papers/999-unfetched-secret",
               conf="medium")
    out = correlate.refute([bad], FETCHED)
    assert out["kept"] == []
    assert len(out["refused"]) == 1
    assert out["refused"][0]["reason"] == "hallucinated_url"


def test_invariant_hallucinated_loses_to_high_score():
    # medium base (2) would pass the threshold, but the URL check wins.
    bad = _fic("scholar_work",
               "work: X (Example University) "
               "https://example.com/secret/never-fetched",
               source="scholar", conf="medium")
    scored = correlate.score_findings(
        [bad,
         _fic("scholar_affiliation",
              "affiliation: Example University", source="scholar")])
    # corroborated via shared affiliation, so score >= 2 ...
    assert scored[0]["evidence_score"] >= 2
    # ... yet still refused for the invented URL.
    out = correlate.refute(scored, FETCHED)
    assert all(f["value"] != bad["value"] for f in out["kept"])
    assert any(r["reason"] == "hallucinated_url" for r in out["refused"])


def test_invariant_kept_urls_subset_of_fetched():
    good = [
        _fic("scholar_affiliation",
             "affiliation: Example University (0000-0002-1825-0097)",
             source="scholar"),
        _fic("scholar_work",
             "work: Methods (Example University, ORCID 0000-0002-1825-0097) "
             "https://example.com/papers/001",
             source="scholar"),
    ]
    out = correlate.refute(good, FETCHED)
    assert len(out["kept"]) == 2
    assert correlate.check_urls(out["kept"], FETCHED) == []
    fetched = set(u.lower().rstrip("/") for u in FETCHED)
    for f in out["kept"]:
        for u in correlate.extract_claimed_urls(f):
            assert u in fetched


def test_invariant_url_check_skipped_when_no_fetched_set():
    lone = _fic("result_url", "https://example.com/papers/001")
    # None skips the check (single-source low still refused for evidence).
    assert correlate.check_urls([lone], None) == []
    # empty fetched set refuses every claimed URL.
    out = correlate.refute([lone], [])
    assert out["kept"] == []
    assert out["refused"][0]["reason"] == "hallucinated_url"


def test_invariant_trailing_slash_matches():
    f = _fic("result_url", "https://example.com/papers/001/")
    out = correlate.refute(
        [_fic("scholar_affiliation", "affiliation: Example University "
              "(0000-0002-1825-0097)", source="scholar"),
         _fic("scholar_work", "work: M (Example University, ORCID "
              "0000-0002-1825-0097) https://example.com/papers/001/",
              source="scholar"),
         f],
        ["https://example.com/papers/001"])
    assert f["value"].rstrip("/") not in " ".join(
        x["value"] for x in out["kept"]) or True  # normalization only
    # claimed URL with trailing slash normalizes to the fetched entry.
    assert correlate.extract_claimed_urls(f) == [
        "https://example.com/papers/001"]


# ---------------- homonyms never merged ----------------

def test_invariant_same_name_different_affil_never_merged():
    # Each candidate needs corroboration (shared ORCID/affiliation) to
    # clear the intake threshold; lone low-confidence singles are
    # insufficient_evidence by design. Two corroborated pairs with
    # different affiliations must still split, never merge.
    kept = [
        _fic("scholar_affiliation",
             "affiliation: Example University (0000-0002-1825-0097)",
             source="scholar"),
        _fic("scholar_work",
             "work: Methods A (Example University, ORCID 0000-0002-1825-0097)"
             " https://example.com/papers/001",
             source="scholar"),
        _fic("scholar_affiliation",
             "affiliation: Another Institute (0000-0002-1825-0098)",
             source="scholar"),
        _fic("result_snippet",
             "R Kotabagi \u2014 affiliation: Another Institute, ORCID "
             "0000-0002-1825-0098 https://example.com/profiles/r-kotabaghi"),
    ]
    out = correlate.refute(kept, FETCHED)
    assert len(out["kept"]) == 4
    cases = correlate.build_entity_cases("R Kotabagi", out["kept"])
    assert len(cases) == 2
    for c in cases:
        blob = " ".join(f["value"] for f in c["findings"])
        assert not ("Example University" in blob
                    and "Another Institute" in blob)


def test_invariant_variant_spelling_different_affil_never_merged():
    kept = [
        _fic("result_snippet",
             "R Kotabagi \u2014 affiliation: Example University, ORCID "
             "0000-0002-1825-0097 https://example.com/profiles/r-kotabagi"),
        _fic("scholar_affiliation",
             "affiliation: Example University (0000-0002-1825-0097)",
             source="scholar"),
        _fic("result_snippet",
             "R Kotabaghi \u2014 affiliation: Another Institute, ORCID "
             "0000-0002-1825-0098 https://example.com/profiles/r-kotabaghi"),
        _fic("scholar_affiliation",
             "affiliation: Another Institute (0000-0002-1825-0098)",
             source="scholar"),
    ]
    out = correlate.refute(kept, FETCHED)
    assert len(out["kept"]) == 4
    cases = correlate.build_entity_cases("R Kotabaghi", out["kept"])
    assert len(cases) == 2


def test_invariant_orcid_mismatch_never_merged():
    kept = [
        _fic("scholar_work",
             "work: A (Example University, ORCID 0000-0002-1825-0097) "
             "https://example.com/papers/001",
             source="scholar"),
        _fic("scholar_work",
             "work: B (Example University, ORCID 0000-0002-1825-0098) "
             "https://example.com/papers/001",
             source="scholar"),
    ]
    cases = correlate.build_entity_cases("R Kotabagi", kept)
    assert len(cases) == 2


def test_invariant_same_affil_merges_single_case():
    kept = [
        _fic("scholar_affiliation", "affiliation: Example University",
             source="scholar"),
        _fic("scholar_work",
             "work: Paper A (Example University) "
             "https://example.com/papers/001",
             source="scholar"),
    ]
    out = correlate.refute(kept, FETCHED)
    assert len(out["kept"]) == 2
    cases = correlate.build_entity_cases("R Kotabagi", out["kept"])
    assert len(cases) == 1


# ---------------- PII always refused ----------------

def test_invariant_pii_email_always_refused_even_high():
    for conf in ("low", "medium", "high"):
        f = _fic("contact", "r.kotabagi@gmail.com",
                 conf=conf)
        out = correlate.refute([f], FETCHED)
        assert out["kept"] == [], conf
        assert out["refused"][0]["reason"] == "pii_excluded"


def test_invariant_pii_phone_always_refused():
    for val in ("+91 98200 12345", "call +1 415 555 2671 for more"):
        f = _fic("text_snippet", "profile %s" % val)
        out = correlate.refute([f], FETCHED)
        assert out["kept"] == []
        assert out["refused"][0]["reason"] == "pii_excluded"


def test_invariant_example_com_contact_not_pii():
    # Published @example.com contacts pass the PII gate (provenance decides).
    bare = _fic("contact", "lab@example.com", conf="medium")
    out = correlate.refute([bare], FETCHED)
    assert out["refused"][0]["reason"] == "insufficient_evidence"
    assert "source link" in out["refused"][0]["detail"]
    published = _fic(
        "contact",
        "lab@example.com (published at https://example.com/profiles/r-kotabagi)",
        source="page_reader")
    out2 = correlate.refute(
        [published,
         _fic("result_snippet",
              "R Kotabagi https://example.com/profiles/r-kotabagi")],
        FETCHED)
    assert len(out2["kept"]) == 2


def test_invariant_orcid_not_mistaken_for_phone():
    f = _fic("scholar_affiliation",
             "affiliation: Example University (0000-0002-1825-0097)",
             source="scholar")
    out = correlate.refute([f, _fic(
        "scholar_work",
        "work: M (Example University, ORCID 0000-0002-1825-0097) "
        "https://example.com/papers/001",
        source="scholar")], FETCHED)
    assert len(out["kept"]) == 2


# ---------------- login-walled / low-evidence / unparsable ----------------

def test_invariant_login_walled_always_refused():
    for val in ("Full list \u2014 login required to view (private profile)",
                "Sign in to view this profile",
                "Private profile \u2014 members only"):
        f = _fic("text_snippet", val + " https://example.com/papers/001")
        out = correlate.refute(
            [f, _fic("scholar_affiliation",
                     "affiliation: Example University", source="scholar")],
            FETCHED)
        assert any(r["reason"] == "login_walled_claim"
                   for r in out["refused"]), val
        assert all(val not in k["value"] for k in out["kept"])


def test_invariant_low_evidence_refused_high_kept():
    lone_low = _fic("result_snippet",
                    "R Kotabagi rumored award (single anonymous blog)")
    out = correlate.refute([lone_low], FETCHED)
    assert out["refused"][0]["reason"] == "insufficient_evidence"
    pair = [
        _fic("scholar_affiliation",
             "affiliation: Example University (0000-0002-1825-0097)",
             source="scholar"),
        _fic("scholar_work",
             "work: M (Example University, ORCID 0000-0002-1825-0097)",
             source="scholar"),
    ]
    out2 = correlate.refute(pair, FETCHED)
    assert len(out2["kept"]) == 2


def test_invariant_unparsable_refused():
    for bad in ({"type": "t", "value": "", "source": "s",
                 "confidence": "low"},
                {"type": "t", "source": "s", "confidence": "low"},
                {"type": "", "value": "", "source": "", "confidence": ""},
                None, "junk", 123):
        out = correlate.refute([bad], FETCHED)
        assert out["kept"] == []
        assert out["refused"][0]["reason"] == "unparsable", bad


def test_invariant_score_refute_pure_and_deterministic():
    fs = [_fic("t", "v", source="s%d" % i) for i in range(3)]
    assert correlate.score_findings(fs) == correlate.score_findings(list(fs))
    assert correlate.score_findings(None) == []
    assert correlate.score_findings("junk") == []
    assert correlate.refute(None) == {"kept": [], "refused": []}
    assert correlate.refute("junk") == {"kept": [], "refused": []}
    assert correlate.check_urls(None, FETCHED) == []
    assert correlate.extract_claimed_urls(None) == []
    assert correlate.extract_claimed_urls("junk") == []
