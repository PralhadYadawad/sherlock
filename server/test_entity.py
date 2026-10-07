"""Entity module tests (>=18). Pure functions, stdlib only, no network.

DUMMY/example fixtures only. Covers the Kotabagi/Kotabaghi
transliteration lesson: variant spellings resolve together only when
affiliation/location agree, and never merge across affiliations.
"""

import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    path = os.path.join(HERE, "entity.py")
    spec = importlib.util.spec_from_file_location("entity_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["entity_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


entity = _load()


def _fic(name, affil="", loc="", source="demo-src-a", **kw):
    d = {"name": name, "affiliation": affil, "location": loc,
         "source": source, "confidence": "medium"}
    d.update(kw)
    return d


# ---------------- normalize ----------------

def test_normalize_trims_and_casefolds():
    assert entity.normalize("  Kotabagi  ") == "kotabagi"
    assert entity.normalize("ANIL KOTABAGI") == "anil kotabagi"


def test_normalize_strips_diacritics():
    assert entity.normalize("Kotabági") == "kotabagi"
    assert entity.normalize("Zoë Démo") == "zoe demo"
    assert entity.normalize("François") == "francois"


def test_normalize_collapses_spaces():
    assert entity.normalize("anil   r.\tkotabagi\nx") == "anil r. kotabagi x"
    assert entity.normalize("  a  b  ") == "a b"


def test_normalize_empty_and_nonstring():
    assert entity.normalize("") == ""
    assert entity.normalize("   ") == ""
    assert entity.normalize(None) == ""
    assert entity.normalize(123) == ""
    assert entity.normalize(["x"]) == ""


def test_normalize_casefold_unicode():
    assert entity.normalize("STRASSE") == "strasse"
    assert entity.normalize("  DéMO  SLEUTH ") == "demo sleuth"


def test_normalize_tabs_newlines_only():
    assert entity.normalize("\t\n ") == ""


# ---------------- variants ----------------

def test_variants_kotabagi_contains_kotabaghi():
    vs = entity.variants("Kotabagi")
    assert "kotabagi" in vs
    assert "kotabaghi" in vs


def test_variants_kotabaghi_contains_kotabagi():
    vs = entity.variants("Kotabaghi")
    assert "kotabaghi" in vs
    assert "kotabagi" in vs


def test_variants_ph_f_both_directions():
    assert "filip" in entity.variants("Philip")
    assert "philip" in entity.variants("Filip")


def test_variants_ee_i_both_directions():
    assert "nil" in entity.variants("Neel")
    assert "neel" in entity.variants("Nil")


def test_variants_single_double_both_directions():
    assert "sunil" in entity.variants("Sunnil")
    assert "sunnil" in entity.variants("Sunil")


def test_variants_middle_initial_removal():
    vs = entity.variants("Anil R Kotabagi")
    assert "anil kotabagi" in vs
    vs2 = entity.variants("Anil R. Kotabagi")
    assert "anil kotabagi" in vs2 or "anil r kotabagi" in vs2


def test_variants_surname_first():
    assert "kotabagi anil" in entity.variants("Anil Kotabagi")
    # symmetric for two tokens
    assert "anil kotabagi" in entity.variants("Kotabagi Anil")


def test_variants_capped_at_12():
    vs = entity.variants("Anil R Kotabaghi Philip")
    assert len(vs) <= 12
    assert len(vs) == len(set(vs))
    long_vs = entity.variants("Christopher Phillipe Anderson")
    assert len(long_vs) <= 12


def test_variants_deterministic_order():
    a = entity.variants("Kotabagi")
    b = entity.variants("Kotabagi")
    assert a == b
    assert a[0] == "kotabagi"  # base always first
    assert entity.variants("  KOTABAGI ") == entity.variants("kotabagi")


def test_variants_empty_returns_empty():
    assert entity.variants("") == []
    assert entity.variants("   ") == []
    assert entity.variants(None) == []


def test_variants_all_outputs_normalized():
    for base in ("Kotabagi", "Anil R. Kotabaghi", "Philip Neel"):
        for v in entity.variants(base):
            assert v == entity.normalize(v)


def test_variants_no_duplicates():
    vs = entity.variants("Fee Philip Kotabaghi")
    assert len(vs) == len(set(vs))


# ---------------- split_homonyms ----------------

def test_split_empty():
    assert entity.split_homonyms([]) == []
    assert entity.split_homonyms(None) == []
    assert entity.split_homonyms("junk") == []


def test_split_garbage_no_crash():
    out = entity.split_homonyms([None, 123, "x", {}, {"name": ""}])
    assert isinstance(out, list)


def test_split_same_spelling_same_affil_merges():
    fs = [_fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a"),
          _fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-b")]
    out = entity.split_homonyms(fs)
    assert len(out) == 1
    assert out[0]["member_count"] == 2
    assert out[0]["confidence"] == "high"
    assert sorted(out[0]["sources"]) == ["demo-src-a", "demo-src-b"]
    assert out[0]["supporting_sources"] == out[0]["sources"]


def test_split_variant_spelling_same_affil_merges():
    fs = [_fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a"),
          _fic("R Kotabaghi", "Example University", "Bengaluru",
               "demo-src-b")]
    out = entity.split_homonyms(fs)
    assert len(out) == 1
    assert set(out[0]["names"]) == {"R Kotabagi", "R Kotabaghi"}


def test_split_same_name_different_affil_splits():
    fs = [_fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a"),
          _fic("R Kotabagi", "Another Institute", "Bengaluru",
               "demo-src-b")]
    out = entity.split_homonyms(fs)
    assert len(out) == 2
    affils = sorted(c["affiliation"] for c in out)
    assert affils == ["Another Institute", "Example University"]
    # no member leaked across clusters
    for c in out:
        assert c["member_count"] == 1


def test_split_variant_spelling_different_affil_never_merges():
    fs = [_fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a"),
          _fic("R Kotabaghi", "Another Institute", "Bengaluru",
               "demo-src-b"),
          _fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-c")]
    out = entity.split_homonyms(fs)
    assert len(out) == 2
    by_affil = {c["affiliation"]: c for c in out}
    assert by_affil["Example University"]["member_count"] == 2
    assert by_affil["Another Institute"]["member_count"] == 1


def test_split_different_location_splits():
    fs = [_fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a"),
          _fic("R Kotabagi", "Example University", "Mumbai",
               "demo-src-b")]
    out = entity.split_homonyms(fs)
    assert len(out) == 2


def test_split_missing_affil_does_not_force_split():
    fs = [_fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a"),
          _fic("R Kotabagi", "", "Bengaluru", "demo-src-b")]
    out = entity.split_homonyms(fs)
    assert len(out) == 1


def test_split_confidence_and_sources_present():
    fs = [_fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a")]
    out = entity.split_homonyms(fs)
    assert len(out) == 1
    c = out[0]
    assert c["confidence"] in ("high", "medium", "low")
    assert c["sources"] == ["demo-src-a"]
    assert c["supporting_sources"] == ["demo-src-a"]
    assert c["member_count"] == 1
    assert c["key"]
    assert c["member_indices"] == [0]


def test_split_singleton_no_affil_is_low():
    out = entity.split_homonyms([_fic("Demo Person", "", "",
                                       "demo-src-a")])
    assert out[0]["confidence"] == "low"


def test_split_deterministic():
    fs = [_fic("R Kotabaghi", "Another Institute", "Mumbai",
               "demo-src-b"),
          _fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a"),
          _fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-c")]
    assert entity.split_homonyms(fs) == entity.split_homonyms(list(fs))


def test_split_orcid_mismatch_splits():
    fs = [_fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-a", orcid="DUMMY-ORCID-1"),
          _fic("R Kotabagi", "Example University", "Bengaluru",
               "demo-src-b", orcid="DUMMY-ORCID-2")]
    out = entity.split_homonyms(fs)
    assert len(out) == 2
