"""page_reader tests. No network: _fetch_page/requests faked via monkeypatch.

DUMMY fixtures only: example.com pages, example.org/example.net outbound
dummies (IANA reserved), never live third-party targets.
"""

import sys

import pytest

from adapters import page_reader

VALID_CONF = {"high", "medium", "low"}

# KLE-Tech-shaped faculty fixture (DUMMY identifiers only): profile title,
# academic role, and an address published on the page.
FACULTY_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Dr Demo Rao \\u2014 Assistant Professor, Computer Science | Demo Institute (KLE-Tech-shaped fixture)</title>
<meta name="description" content="Demo faculty profile: Assistant Professor of Computer Science. Research: open-source intelligence methods. All identifiers DUMMY.">
</head>
<body>
<header><p>Demo Institute of Technology \\u2014 KLE-Tech-shaped layout fixture (fictional)</p></header>
<main>
<h1>Dr Demo Rao</h1>
<h2>Assistant Professor, Department of Computer Science</h2>
<h3>Research Interests</h3>
<p>Open-source research methods for public web data. This demo profile
exists only to exercise the Sherlock page-reader lane; every identifier
on this page is DUMMY.</p>
<p>Contact (published on this page):
<a href="mailto:demo.rao@example.com">demo.rao@example.com</a></p>
<p>Lab: <a href="https://example.com/labs/demo-lab">Demo Lab (internal)</a></p>
<p>Project mirror:
<a href="https://www.example.org/demo-project">demo project (external dummy)</a></p>
<p>Dataset:
<a href="https://example.net/data/demo-set">demo dataset (external dummy)</a></p>
</main>
</body>
</html>"""

FACULTY_URL = "https://example.com/faculty/demo-rao"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Harden hermeticity: any stray requests.get explodes loudly."""
    if page_reader.requests is None:  # pragma: no cover - venv has requests
        return

    def _boom(*a, **k):
        raise AssertionError("network disabled in tests (mock _fetch_page)")

    monkeypatch.setattr(page_reader.requests, "get", _boom)


def _serve(monkeypatch, html=FACULTY_HTML, status=200,
           ctype="text/html; charset=utf-8"):
    monkeypatch.setattr(page_reader, "_fetch_page",
                        lambda url, timeout=10: (status, ctype, html))


def check_contract(result):
    assert set(result) == {"status", "reason", "findings"}, result
    assert result["status"] in ("ok", "rejected")
    assert isinstance(result["reason"], str) and result["reason"]
    assert isinstance(result["findings"], list)
    for f in result["findings"]:
        assert set(f) == {"type", "value", "source", "confidence"}, f
        assert f["source"] == page_reader.NAME
        assert f["confidence"] in VALID_CONF
        assert isinstance(f["value"], str) and f["value"]
        assert f["confidence"] != "high", "scrape alone is never high"


def by_type(findings):
    grouped = {}
    for f in findings:
        grouped.setdefault(f["type"], []).append(f["value"])
    return grouped


# ---------- contract ----------

def test_contract_signature():
    assert page_reader.NAME == "page_reader"
    assert "clean-room" in page_reader.LICENSE_NOTE
    assert "MIT" in page_reader.LICENSE_NOTE
    assert "Apache-2.0" in page_reader.LICENSE_NOTE
    assert callable(page_reader.run)
    out = page_reader.run("")
    check_contract(out)
    assert out["status"] == "rejected" and out["findings"] == []


def test_timeout_and_ua():
    assert page_reader.TIMEOUT == 10
    assert "Sherlock" in page_reader.USER_AGENT


# ---------- happy path (mocked faculty page) ----------

def test_run_faculty_ok_all_finding_types(monkeypatch):
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "ok"
    got = by_type(out["findings"])
    for want in ("title", "heading", "email", "outbound_link", "text_snippet"):
        assert want in got, got.keys()


def test_title_value_and_confidence(monkeypatch):
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    titles = by_type(out["findings"])["title"]
    assert len(titles) == 1 and "Demo Rao" in titles[0]
    assert out["findings"][0]["confidence"] == "medium"  # title + body


def test_headings_include_role(monkeypatch):
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    headings = by_type(out["findings"])["heading"]
    assert any("Assistant Professor" in h for h in headings)
    assert any("Research Interests" in h for h in headings)


def test_published_email_found(monkeypatch):
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    emails = by_type(out["findings"])["email"]
    assert emails == ["demo.rao@example.com"]  # mailto + visible deduped


def test_outbound_links_external_only(monkeypatch):
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    links = by_type(out["findings"])["outbound_link"]
    assert "https://www.example.org/demo-project" in links
    assert "https://example.net/data/demo-set" in links
    assert not any("example.com/labs" in link for link in links)


def test_snippet_bounded_and_textual(monkeypatch):
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    snippets = by_type(out["findings"])["text_snippet"]
    assert len(snippets) == 1
    assert 0 < len(snippets[0]) <= page_reader.SNIPPET_CHARS
    assert "Open-source research methods" in snippets[0]


def test_determinism(monkeypatch):
    _serve(monkeypatch)
    assert page_reader.run(FACULTY_URL) == page_reader.run(FACULTY_URL)


# ---------- input / scope rejections (no fetch) ----------

def test_empty_rejected():
    assert page_reader.run("   ")["status"] == "rejected"


def test_bare_host_rejected_without_fetch(monkeypatch):
    monkeypatch.setattr(page_reader, "_fetch_page",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not fetch")))
    out = page_reader.run("example.com/faculty/demo-rao")
    assert out["status"] == "rejected" and out["findings"] == []


def test_ftp_rejected():
    out = page_reader.run("ftp://example.com/file.txt")
    assert out["status"] == "rejected" and out["findings"] == []


def test_credentialed_url_rejected(monkeypatch):
    monkeypatch.setattr(page_reader, "_fetch_page",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not fetch")))
    out = page_reader.run("https://user:pass@example.com/page")
    assert out["status"] == "rejected" and out["findings"] == []


def test_out_of_scope_rejected_without_fetch(monkeypatch):
    monkeypatch.setattr(page_reader, "_fetch_page",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not fetch third parties")))
    out = page_reader.run("https://github.com/octocat")
    assert out["status"] == "rejected" and out["findings"] == []


# ---------- fetch taxonomy (mocked statuses) ----------

def test_429_rejected_clean(monkeypatch):
    _serve(monkeypatch, status=429)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "429" in out["reason"]


def test_404_ok_empty_no_hallucination(monkeypatch):
    _serve(monkeypatch, html="not found", status=404)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "ok" and out["findings"] == []


def test_403_ok_empty_bot_gate(monkeypatch):
    _serve(monkeypatch, html="forbidden", status=403)
    out = page_reader.run(FACULTY_URL)
    assert out["status"] == "ok" and out["findings"] == []
    assert "bot-gate" in out["reason"]


def test_500_ok_empty(monkeypatch):
    _serve(monkeypatch, html="error", status=500)
    out = page_reader.run(FACULTY_URL)
    assert out["status"] == "ok" and out["findings"] == []


def test_fetch_exception_ok_empty(monkeypatch):
    def _raise(*a, **k):
        raise TimeoutError("simulated outage")

    monkeypatch.setattr(page_reader.requests, "get", _raise)
    status, ctype, body = page_reader._fetch_page(FACULTY_URL)
    assert (status, ctype, body) == (None, "", "")
    monkeypatch.setattr(page_reader, "_fetch_page",
                        lambda url, timeout=10: (None, "", ""))
    out = page_reader.run(FACULTY_URL)
    assert out["status"] == "ok" and out["findings"] == []


def test_non_html_ok_empty(monkeypatch):
    _serve(monkeypatch, html="%PDF-1.4 binary", ctype="application/pdf")
    out = page_reader.run(FACULTY_URL)
    assert out["status"] == "ok" and out["findings"] == []


# ---------- walls: detect + reject, never bypass ----------

def test_login_wall_rejected(monkeypatch):
    wall = ('<html><head><title>x</title></head><body>'
            '<form action="/login"><input type="password">'
            'Log in to continue</form></body></html>')
    _serve(monkeypatch, html=wall)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "login-walled" in out["reason"]


def test_paywall_rejected(monkeypatch):
    wall = ('<html><head><title>Story</title></head><body>'
            '<article><p>Subscribe to continue reading this article.</p>'
            '</article></body></html>')
    _serve(monkeypatch, html=wall)
    out = page_reader.run(FACULTY_URL)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "paywalled" in out["reason"]


def test_js_shell_ok_empty(monkeypatch):
    shell = ('<html><head><title></title></head><body>'
             '<script>window.APP={};</script><div id="root"></div>'
             '</body></html>')
    _serve(monkeypatch, html=shell)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "ok" and out["findings"] == []
    assert "JS" in out["reason"]


# ---------- extraction branches ----------

def test_stdlib_fallback_title_and_meta(monkeypatch):
    monkeypatch.setattr(page_reader, "_lib_main_text",
                        lambda html: (None, None))
    html = ('<html><head><title>Demo Solo Title</title>'
            '<meta name="description" content="Standalone meta summary.">'
            '</head><body></body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "ok"
    got = by_type(out["findings"])
    assert got["title"] == ["Demo Solo Title"]
    assert got["text_snippet"] == ["Standalone meta summary."]


def test_lib_branch_preferred(monkeypatch):
    class _FakeTraf:
        @staticmethod
        def extract(html, **kw):
            return "LIB TEXT from optional extractor"

    monkeypatch.setitem(sys.modules, "trafilatura", _FakeTraf)
    html = ('<html><head><title>T</title></head>'
            '<body><p>short</p></body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    assert by_type(out["findings"])["text_snippet"] == [
        "LIB TEXT from optional extractor"]


def test_lib_api_drift_degrades_to_stdlib(monkeypatch):
    class _BrokenTraf:
        @staticmethod
        def extract(html, **kw):
            raise RuntimeError("API changed upstream")

    monkeypatch.setitem(sys.modules, "trafilatura", _BrokenTraf)
    monkeypatch.setitem(sys.modules, "readability", None)
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    assert out["status"] == "ok"
    assert "text_snippet" in by_type(out["findings"])


def test_email_cap(monkeypatch):
    addrs = " ".join("user%d@example.com" % i for i in range(8))
    html = ('<html><head><title>T</title></head><body><p>%s</p>'
            '<p>filler text for snippet</p></body></html>' % addrs)
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    assert len(by_type(out["findings"])["email"]) == page_reader.MAX_EMAILS


def test_heading_cap_parse_level():
    html = "<html><body>" + "".join(
        "<h1>Section %d</h1>" % i for i in range(40)) + "</body></html>"
    parsed = page_reader.parse_page(html, FACULTY_URL)
    assert len(parsed["headings"]) == page_reader.MAX_HEADINGS


# ---------- live scope (mocked, no network) ----------

def test_live_scope_rules(monkeypatch):
    monkeypatch.setenv("SHERLOCK_LIVE", "1")
    assert page_reader.is_live_enabled()
    # Literal private hosts are never fetched, even live.
    monkeypatch.setattr(page_reader, "_fetch_page",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not fetch private hosts")))
    out = page_reader.run("http://127.0.0.1/admin")
    assert out["status"] == "rejected" and out["findings"] == []
    # Public hosts pass validation (fetch still mocked).
    monkeypatch.setattr(page_reader, "_fetch_page",
                        lambda url, timeout=10: (200, "text/html",
                                                 FACULTY_HTML))
    out = page_reader.run("https://www.example.org/demo-project")
    check_contract(out)
    assert out["status"] == "ok" and out["findings"]


def test_demo_scope_when_not_live(monkeypatch):
    monkeypatch.delenv("SHERLOCK_LIVE", raising=False)
    assert not page_reader.is_live_enabled()
    monkeypatch.setattr(page_reader, "_fetch_page",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not fetch")))
    out = page_reader.run("https://www.example.org/demo-project")
    assert out["status"] == "rejected" and out["findings"] == []


# ---------- Phase 2: Scrapling-first extraction + fallback chain ----------

def test_scrapling_primary_engine_used():
    parsed, engine = page_reader._parse_structured(FACULTY_HTML, FACULTY_URL)
    # Scrapling installed in project venv: primary engine wins.
    assert engine == "scrapling", engine
    assert parsed.get("engine") == "scrapling"
    assert "Demo Rao" in parsed.get("title", "")
    assert any("Assistant Professor" in h for h in parsed["headings"])
    # Body-only text excludes <title> head metadata (matches stdlib).
    assert "Demo Rao" in parsed["text"]  # from h1/body, not just title


def test_scrapling_parse_returns_none_when_blocked(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)
    assert page_reader._scrapling_parse(FACULTY_HTML, FACULTY_URL) is None
    parsed, engine = page_reader._parse_structured(FACULTY_HTML, FACULTY_URL)
    assert engine == "stdlib", engine
    assert "Demo Rao" in parsed.get("title", "")


def test_fallback_stdlib_when_scrapling_blocked(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "ok"
    got = by_type(out["findings"])
    for want in ("title", "heading", "email", "outbound_link", "text_snippet"):
        assert want in got


def test_fallback_chain_trafilatura_when_scrapling_blocked(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)

    class _FakeTraf:
        @staticmethod
        def extract(html, **kw):
            return "FALLBACK LIB TEXT via trafilatura"

    monkeypatch.setitem(sys.modules, "trafilatura", _FakeTraf)
    html = ('<html><head><title>T</title></head>'
            '<body><p>short body</p></body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    assert by_type(out["findings"])["text_snippet"] == [
        "FALLBACK LIB TEXT via trafilatura"]


def test_fallback_chain_stdlib_when_all_libs_blocked(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)
    monkeypatch.setitem(sys.modules, "trafilatura", None)
    monkeypatch.setitem(sys.modules, "readability", None)
    _serve(monkeypatch)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "ok"
    assert "text_snippet" in by_type(out["findings"])


def test_scrapling_attribution_present():
    assert page_reader.SCRAPLING_PIN == "0.4.15"
    assert "BSD-3-Clause" in page_reader.LICENSE_NOTE
    assert "scrapling" in page_reader.LICENSE_NOTE.lower()
    # Stealth/turnstile/proxy tiers must never be imported or called by this
    # lane (the docstring names them only to document the exclusion).
    src = open(page_reader.__file__).read()
    assert "EXCLUDED" in src
    for banned_import in ("from scrapling.fetchers.stealth",
                          "from scrapling.fetchers.chrome",
                          "proxy_rotation import",
                          "StealthyFetcher(",
                          "DynamicFetcher(",
                          "ProxyRotator("):
        assert banned_import not in src, banned_import


# ---------- Phase 2: published-contact extraction ----------

def _contacts(monkeypatch, html):
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "ok"
    return out, by_type(out["findings"])


def test_published_contact_email_with_source_url(monkeypatch):
    out, got = _contacts(monkeypatch, FACULTY_HTML)
    assert "published_contact" in got
    emails = [v for v in got["published_contact"] if v.startswith("email:")]
    assert len(emails) == 1
    assert "demo.rao@example.com" in emails[0]
    assert FACULTY_URL in emails[0]  # source URL embedded in value
    assert out["findings"][0]["confidence"] != "high"


def test_published_contact_tel_link(monkeypatch):
    html = ('<html><head><title>Demo Contact</title></head><body>'
            '<p>Call us: <a href="tel:+1-555-010-1234">+1-555-010-1234</a></p>'
            '<p>Body text for snippet.</p></body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    got = by_type(out["findings"])
    phones = [v for v in got.get("published_contact", [])
              if v.startswith("phone:")]
    assert len(phones) == 1
    assert "+1-555-010-1234" in phones[0]
    assert FACULTY_URL in phones[0]


def test_published_contact_visible_phone_formats(monkeypatch):
    html = ('<html><head><title>Demo Phones</title></head><body>'
            '<p>US office +1-555-010-1234, alt (555) 010-1235.</p>'
            '<p>Snippet filler text here.</p></body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    got = by_type(out["findings"])
    phones = [v for v in got.get("published_contact", [])
              if v.startswith("phone:")]
    assert len(phones) == 2
    assert all(FACULTY_URL in v for v in phones)


def test_contact_negative_date_refused(monkeypatch):
    html = ('<html><head><title>Demo Dates</title></head><body>'
            '<p>Published 2026-10-06. No contacts here.</p>'
            '<p>Snippet filler text here.</p></body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    got = by_type(out["findings"])
    assert "published_contact" not in got, got.get("published_contact")


def test_contact_negative_version_ip_year_range_refused(monkeypatch):
    html = ('<html><head><title>Demo Versions</title></head><body>'
            '<p>Release 2.3.0 on host 192.168.1.1, years 2020-2024.</p>'
            '<p>Snippet filler text here.</p></body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    assert "published_contact" not in by_type(out["findings"])


def test_contact_negative_short_digits_refused(monkeypatch):
    html = ('<html><head><title>Demo Short</title></head><body>'
            '<p>Room 101, ticket 12345, code 5550123 without separators.</p>'
            '<p>Snippet filler text here.</p></body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    assert "published_contact" not in by_type(out["findings"])


def test_contact_never_infers_personal(monkeypatch):
    # Headings/title alone (a name + role) must never mint contacts.
    html = ('<html><head><title>Dr Demo Rao</title></head><body>'
            '<h1>Dr Demo Rao</h1><h2>Assistant Professor</h2>'
            '<p>Research methods page with no contact lines.</p>'
            '</body></html>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    assert "published_contact" not in by_type(out["findings"])
    # And a page-text-only promise: no mailto/tel hrefs, no regex hits.
    assert page_reader._extract_published_contacts(
        page_reader.parse_page(html, FACULTY_URL), FACULTY_URL) == []


def test_contact_caps(monkeypatch):
    emails = " ".join("user%d@example.com" % i for i in range(30))
    html = ('<html><head><title>T</title></head><body><p>%s</p>'
            '<p>filler text for snippet</p></body></html>' % emails)
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    got = by_type(out["findings"])
    assert len(got.get("published_contact", [])) <= page_reader.MAX_CONTACTS


# ---------- Phase 2: KLE-Tech-shaped page (title/role/email/links) ----------

def test_kle_tech_shaped_page_full(monkeypatch):
    html = FACULTY_HTML.replace(
        "</main>",
        '<p>Office phone (published): <a href="tel:+91-80-5550-1234">'
        '+91-80-5550-1234</a></p></main>')
    _serve(monkeypatch, html=html)
    out = page_reader.run(FACULTY_URL)
    check_contract(out)
    assert out["status"] == "ok"
    got = by_type(out["findings"])
    assert "Demo Rao" in got["title"][0]
    assert any("Assistant Professor" in h for h in got["heading"])
    assert got["email"] == ["demo.rao@example.com"]
    assert "https://www.example.org/demo-project" in got["outbound_link"]
    kinds = got.get("published_contact", [])
    assert any("demo.rao@example.com" in v and FACULTY_URL in v
               for v in kinds if v.startswith("email:"))
    assert any("+91-80-5550-1234" in v and FACULTY_URL in v
               for v in kinds if v.startswith("phone:"))


# ---------- Phase 2: sitemap spider helper (fixtures only, no network) ----------

URLSET_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/faculty/demo-rao</loc></url>
  <url><loc>https://example.com/labs/demo-lab</loc></url>
  <url><loc>https://example.com/about</loc></url>
</urlset>"""

INDEX_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-faculty.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-labs.xml</loc></sitemap>
</sitemapindex>"""


def test_spider_parse_urlset():
    parsed = page_reader.parse_sitemap_xml(URLSET_FIXTURE)
    assert parsed["urls"] == [
        "https://example.com/faculty/demo-rao",
        "https://example.com/labs/demo-lab",
        "https://example.com/about",
    ]
    assert parsed["sitemaps"] == []


def test_spider_parse_sitemapindex():
    parsed = page_reader.parse_sitemap_xml(INDEX_FIXTURE)
    assert parsed["urls"] == []
    assert parsed["sitemaps"] == [
        "https://example.com/sitemap-faculty.xml",
        "https://example.com/sitemap-labs.xml",
    ]


def test_spider_parse_malformed_never_raises():
    assert page_reader.parse_sitemap_xml("not xml <<<") == {
        "urls": [], "sitemaps": []}
    assert page_reader.parse_sitemap_xml("") == {"urls": [], "sitemaps": []}
    assert page_reader.parse_sitemap_xml(None) == {"urls": [], "sitemaps": []}


def test_spider_cap_enforced():
    many = ["https://example.com/page-%d" % i for i in range(50)]
    plan = page_reader.plan_sweep(many, max_pages=page_reader.SPIDER_MAX_PAGES)
    assert len(plan["pages"]) == page_reader.SPIDER_MAX_PAGES
    assert plan["capped"] is True
    assert plan["total_found"] == 50
    # sweep_domain enforces the same cap from a sitemap body (no network).
    big = ("<urlset>" + "".join(
        "<url><loc>https://example.com/p%d</loc></url>" % i
        for i in range(50)) + "</urlset>")
    out = page_reader.sweep_domain("example.com", max_pages=5,
                                   sitemap_body=big)
    assert out["status"] == "ok"
    assert len(out["pages"]) == 5
    assert "cap=5" in out["reason"]


def test_spider_politeness_attrs():
    spider = page_reader.SherlockSitemapSpider
    assert spider.robots_txt_obey is True
    assert spider.download_delay == page_reader.SPIDER_POLITE_DELAY >= 1.0
    assert spider.concurrent_requests == 1
    assert spider.concurrent_requests_per_domain == 1
    assert spider.autothrottle_enabled is True
    assert spider.max_pages == page_reader.SPIDER_MAX_PAGES
    assert spider.name == "sherlock-sitemap"


def test_sweep_domain_demo_scope_and_robots_note(monkeypatch):
    monkeypatch.delenv("SHERLOCK_LIVE", raising=False)
    out = page_reader.sweep_domain("example.com",
                                   sitemap_body=URLSET_FIXTURE)
    assert out["status"] == "ok"
    assert out["pages"] == [
        "https://example.com/faculty/demo-rao",
        "https://example.com/labs/demo-lab",
        "https://example.com/about",
    ]
    assert "robots_txt_obey=True" in out["reason"]
    # Out-of-scope domains are rejected without any fetch.
    bad = page_reader.sweep_domain(
        "https://github.com/octocat",
        fetch_fn=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not fetch out-of-scope")))
    assert bad["status"] == "rejected" and bad["pages"] == []

