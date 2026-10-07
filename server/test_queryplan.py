"""Tests for server/queryplan.py (GPT-search loop support, no network).

DUMMY/example fixtures only. Covers: variant fan-out incl.
Kotabagi/Kotabaghi, query cap, purpose/lane tags, determinism, junk
handling, URL extraction/cleaning (duplicates, non-http, non-public,
cap), and intake provenance.
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    path = os.path.join(HERE, "queryplan.py")
    spec = importlib.util.spec_from_file_location("queryplan_under_test",
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["queryplan_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


qp = _load()

DUMMY_URLS = [
    "https://example.com/sanjay-kotabagi",
    "https://linkedin.com/in/demo-sleuth",
    "https://github.com/demo-sleuth",
]


# ---------------- build_queries: fan-out ----------------

def test_baseline_is_quoted_full_name():
    qs = qp.build_queries("Sanjay Kotabaghi")
    assert qs, "expected non-empty query set"
    assert qs[0]["query"] == '"sanjay kotabaghi"'
    assert qs[0]["purpose"] == "baseline"
    assert qs[0]["lane"] == "web"


def test_variant_fanout_kotabaghi_includes_kotabagi():
    qs = qp.build_queries("Sanjay Kotabaghi")
    texts = [q["query"] for q in qs]
    assert any("kotabagi" in t and "kotabaghi" not in t for t in texts), \
        "aspirated-h variant sanjay kotabagi missing: %r" % (texts,)


def test_variant_fanout_kotabagi_includes_kotabaghi():
    qs = qp.build_queries("Sanjay Kotabagi")
    texts = [q["query"] for q in qs]
    assert any("kotabaghi" in t for t in texts), \
        "reverse aspirated-h variant missing: %r" % (texts,)


def test_ph_f_variant_present():
    qs = qp.build_queries("Stephan Demo")
    texts = [q["query"] for q in qs]
    assert any("stefan demo" in t for t in texts), texts


def test_site_operators_cover_four_lanes():
    qs = qp.build_queries("Demo Sleuth")
    lanes = {q["lane"] for q in qs}
    for lane in ("linkedin", "github", "scholar", "news"):
        assert lane in lanes, "lane %s missing: %r" % (lane, qs)
    texts = " ".join(q["query"] for q in qs)
    assert "site:linkedin.com" in texts
    assert "site:github.com" in texts
    assert "site:scholar.google.com" in texts


def test_cap_respected_at_twelve():
    qs = qp.build_queries("Sanjay Kotabaghi")
    assert 1 <= len(qs) <= qp.MAX_QUERIES == 12
    # long multi-token name must also respect the cap
    qs2 = qp.build_queries("Anna Bee See Dee Eeff Geetha Henry")
    assert len(qs2) <= 12


def test_every_query_tagged_purpose_and_lane():
    for qs in (qp.build_queries("Demo Sleuth"),
               qp.build_queries("Sanjay Kotabaghi", "KLE Tech")):
        for q in qs:
            assert set(q) >= {"query", "purpose", "lane"}
            assert q["purpose"] in ("baseline", "variant", "site",
                                    "affiliation")
            assert q["lane"] in ("web", "linkedin", "github", "scholar",
                                 "news")
            assert q["query"].strip()


def test_affiliation_param_adds_affiliation_guess():
    qs = qp.build_queries("Sanjay Kotabagi", "KLE Tech")
    texts = [q["query"].lower() for q in qs]
    assert any("kle tech" in t for t in texts), texts
    assert any(q["purpose"] == "affiliation" for q in qs)


def test_no_affiliation_still_covers_affiliation_lane_generically():
    qs = qp.build_queries("Sanjay Kotabagi")
    aff = [q for q in qs if q["purpose"] == "affiliation"]
    assert aff, "affiliation guess missing without org"
    joined = " ".join(q["query"] for q in aff)
    assert "professor" in joined or "university" in joined
    # must NOT invent a real org
    assert "kle" not in joined


def test_determinism_same_input_same_output():
    a = qp.build_queries("Sanjay Kotabaghi", "KLE Tech")
    b = qp.build_queries("Sanjay Kotabaghi", "KLE Tech")
    assert a == b
    # case/whitespace-insensitive determinism
    c = qp.build_queries("  SANJAY   kotabaghi ")
    assert c == qp.build_queries("sanjay kotabaghi")


def test_junk_name_returns_empty():
    for bad in ("", "   ", None, 123, ["x"], {}, "!!!   ", "---"):
        assert qp.build_queries(bad) == [], repr(bad)


def test_no_duplicate_queries():
    qs = qp.build_queries("Sanjay Kotabaghi")
    texts = [q["query"] for q in qs]
    assert len(texts) == len(set(texts))


# ---------------- parse_found_urls ----------------

def test_parse_extracts_urls_from_prose():
    text = ("I found https://example.com/sanjay-kotabagi and also "
            "http://example.com/news-demo.")
    urls = qp.parse_found_urls(text)
    assert "https://example.com/sanjay-kotabagi" in urls
    assert "http://example.com/news-demo" in urls


def test_parse_accepts_list_input():
    urls = qp.parse_found_urls(DUMMY_URLS)
    assert len(urls) == 3
    assert urls[0] == "https://example.com/sanjay-kotabagi"


def test_parse_junk_input_returns_empty():
    for bad in (None, 123, {}, "no urls here at all", "", ["", None, 5]):
        assert qp.parse_found_urls(bad) == [], bad


def test_parse_drops_duplicates_case_and_slash_insensitive():
    urls = qp.parse_found_urls(
        "see https://EXAMPLE.com/X/ and https://example.com/x plus "
        "https://example.com/x/")
    assert len(urls) == 1
    assert urls[0].lower().rstrip("/") == "https://example.com/x"


def test_parse_drops_non_http_schemes():
    text = ("ftp://example.com/f plus javascript:alert(1) plus "
            "mailto:demo@example.com plus bare example.com plus "
            "https://example.com/ok")
    urls = qp.parse_found_urls(text)
    assert urls == ["https://example.com/ok"]


def test_parse_drops_nonpublic_shapes():
    text = ("http://localhost:8000/x http://127.0.0.1/y "
            "http://10.0.0.5/z http://192.168.1.9/w "
            "https://example.com/keep")
    urls = qp.parse_found_urls(text)
    assert urls == ["https://example.com/keep"]


def test_parse_strips_trailing_prose_punctuation():
    urls = qp.parse_found_urls(
        "(see https://example.com/demo-case.), next: "
        "https://example.com/second;")
    assert "https://example.com/demo-case" in urls
    assert "https://example.com/second" in urls


def test_parse_cap_at_ten():
    blobs = ["https://example.com/page%d" % i for i in range(30)]
    urls = qp.parse_found_urls(" ".join(blobs))
    assert len(urls) == qp.MAX_URLS == 10
    assert urls[0] == "https://example.com/page0"


# ---------------- intake_package ----------------

def test_intake_provenance_note_marks_unverified():
    pkg = qp.intake_package(DUMMY_URLS, "sanjay kotabagi")
    assert pkg["provenance"] == "model-retrieved, unverified"
    assert "unverified" in pkg["note"].lower()
    assert "correlate" in pkg["note"].lower() or "hallucination" in \
        pkg["note"].lower()


def test_intake_cleans_urls_and_keeps_query():
    pkg = qp.intake_package(
        "junk ftp://x plus https://example.com/a "
        "https://example.com/a duplicate", " demo query ")
    assert pkg["query"] == "demo query"
    assert pkg["urls"] == ["https://example.com/a"]
    assert pkg["url_count"] == 1


def test_intake_garbage_never_raises():
    for bad_urls, bad_q in ((None, None), (123, 456), ("", None),
                            ([None, 5], ["x"])):
        pkg = qp.intake_package(bad_urls, bad_q)
        assert isinstance(pkg, dict)
        assert pkg["provenance"] == "model-retrieved, unverified"
        assert isinstance(pkg["urls"], list)
        assert pkg["url_count"] == len(pkg["urls"])
