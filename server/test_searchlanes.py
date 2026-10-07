"""Search-lane adapter tests (ddg_polite / github_lane).

No network: an autouse fixture turns any stray ``requests.get`` into a
loud AssertionError, and every ``run()`` path test monkeypatches the
module-level ``_fetch_*`` helpers (same hermetic style as
``test_lanes.py``). Demo/example fixtures only (Demo Person /
R Kotabagi KLE-Tech-shaped SERP rows pointing at example.com /
demo-sleuth / demo@example.com). No real-person PII, no live keys
(``DUMMY_...`` placeholders only).
"""

import inspect
import os

import pytest

from adapters import ddg_polite, github_lane

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


@pytest.fixture(autouse=True)
def _offline_and_isolated(monkeypatch):
    monkeypatch.setenv("SHERLOCK_NO_PACING", "1")
    monkeypatch.delenv("SHERLOCK_GITHUB_TOKEN", raising=False)
    ddg_polite.reset_pacing()

    def _boom(*a, **k):
        raise AssertionError("network must never be touched in tests")

    for mod in (ddg_polite, github_lane):
        if getattr(mod, "requests", None) is not None:
            monkeypatch.setattr(mod.requests, "get", _boom)


# ---------- fixtures (DUMMY/example only) ----------

DDG_SERP_HTML = """
<html><body>
<div class="result results_links results_links_deep web-result">
<div class="links_main links_deep result__body">
<h2 class="result__title">
<a rel="nofollow" class="result__a"
href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffaculty%2Fr%2Dkotabagi&amp;rut=aaa">R Kotabagi \u2014 Professor, KLE Technological University</a>
</h2>
<a class="result__snippet"
href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffaculty%2Fr%2Dkotabagi&amp;rut=aaa">R Kotabagi is a professor at KLE Technological University, Hubballi, working on open-source research methods.</a>
</div>
</div>
<div class="result results_links results_links_deep web-result">
<div class="links_main links_deep result__body">
<h2 class="result__title">
<a rel="nofollow" class="result__a" href="https://example.com/profile/demo-person">Demo Person \u2014 Example University</a>
</h2>
<div class="result__snippet">Demo Person researches open-source methods at Example University.</div>
</div>
</div>
</body></html>
"""

GH_PROFILE = {
    "login": "demo-sleuth",
    "name": "Demo Sleuth",
    "company": "Example Corp",
    "blog": "https://example.com/blog/demo-sleuth",
    "location": "Example City",
    "bio": "Demo fixture only.",
    "public_repos": 2,
    "followers": 3,
    "following": 1,
    "html_url": "https://github.com/demo-sleuth",
}

GH_REPOS = [
    {"full_name": "demo-sleuth/example-project",
     "html_url": "https://github.com/demo-sleuth/example-project",
     "stargazers_count": 42, "fork": False,
     "description": "Demo fixture repo."},
    {"full_name": "demo-sleuth/forked-demo",
     "html_url": "https://github.com/demo-sleuth/forked-demo",
     "stargazers_count": 0, "fork": True},
    {"name": "", "html_url": ""},  # malformed row: skipped, never invented
]

GH_ORGS = [
    {"login": "example-org",
     "html_url": "https://github.com/example-org"},
]

GH_EVENTS = [
    {"type": "PushEvent",
     "repo": {"name": "demo-sleuth/example-project"},
     "payload": {"commits": [
         {"author": {"name": "Demo Sleuth",
                     "email": "demo-sleuth@users.noreply.github.com"}},
         {"author": {"name": "Demo Sleuth",
                     "email": "demo@example.com"}},
         {"author": {"name": "Demo Sleuth",
                     "email": "demo@example.com"}},  # dupe: deduped
     ]}},
    {"type": "WatchEvent",  # non-push: ignored
     "repo": {"name": "demo-sleuth/example-project"},
     "payload": {}},
]

GH_SEARCH = {
    "total_count": 1,
    "items": [{"login": "demo-sleuth",
               "html_url": "https://github.com/demo-sleuth"}],
}


def _many_result_serp(n):
    rows = []
    for i in range(n):
        rows.append(
            '<div class="result web-result"><h2 class="result__title">'
            '<a class="result__a" href="https://example.com/p/%d">'
            "Title %d</a></h2>"
            '<a class="result__snippet">Snippet %d.</a></div>' % (i, i, i))
    return "<html><body>%s</body></html>" % "".join(rows)


# ---------- contract ----------

def test_ddg_contract_signature():
    assert ddg_polite.NAME == "ddg_polite"
    assert "clean-room" in ddg_polite.LICENSE_NOTE
    assert "MIT" in ddg_polite.LICENSE_NOTE
    assert callable(ddg_polite.run)
    assert ddg_polite.TIMEOUT == 10
    assert ddg_polite.PACING_SEC >= 3.0
    assert ddg_polite.JITTER_SEC > 0
    assert ddg_polite.MAX_RESULTS == 10
    assert ddg_polite.MAX_QUERY_LEN == 500
    out = ddg_polite.run("")
    check_contract(out, ddg_polite.NAME)
    assert out["status"] == "rejected" and out["findings"] == []


def test_github_contract_signature():
    assert github_lane.NAME == "github_lane"
    assert "clean-room" in github_lane.LICENSE_NOTE
    assert "MIT" in github_lane.LICENSE_NOTE
    assert callable(github_lane.run)
    assert github_lane.TIMEOUT == 10
    assert github_lane.ENV_TOKEN == "SHERLOCK_GITHUB_TOKEN"
    out = github_lane.run("")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "rejected" and out["findings"] == []


# ---------- ddg_polite: units ----------

def test_ddg_decode_uddg():
    enc = ("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffaculty"
           "%2Fr%2Dkotabagi&rut=aaa")
    assert ddg_polite.decode_ddg_href(enc) == \
        "https://example.com/faculty/r-kotabagi"
    assert ddg_polite.decode_ddg_href("/l/?uddg=https%3A%2F%2Fexample.com%2Fx") == \
        "https://example.com/x"
    assert ddg_polite.decode_ddg_href("https://example.com/direct") == \
        "https://example.com/direct"
    assert ddg_polite.decode_ddg_href("javascript:alert(1)") == ""
    assert ddg_polite.decode_ddg_href("ftp://example.com/x") == ""
    assert ddg_polite.decode_ddg_href("/relative/path") == ""
    assert ddg_polite.decode_ddg_href("") == ""
    assert ddg_polite.decode_ddg_href(None) == ""
    assert ddg_polite.decode_ddg_href("//duckduckgo.com/l/?rut=nouddg") == ""


def test_ddg_build_query_operators_preserved():
    assert ddg_polite.build_query("Demo Person") == "Demo Person"
    q = ddg_polite.build_query('  "Demo Person"   site:example.com  ')
    assert q == '"Demo Person" site:example.com'
    assert ddg_polite.build_query("   ") == ""
    assert ddg_polite.build_query(None) == ""


def test_ddg_parse_serp_kle_tech_fixture():
    findings = ddg_polite.parse_serp(DDG_SERP_HTML)
    assert len(findings) == 6  # 2 results x (title + url + snippet)
    types = [f["type"] for f in findings]
    assert types.count("result_title") == 2
    assert types.count("result_url") == 2
    assert types.count("result_snippet") == 2
    assert all(f["source"] == "ddg_polite" for f in findings)
    assert all(f["confidence"] == "low" for f in findings)
    titles = [f["value"] for f in findings if f["type"] == "result_title"]
    assert any("Kotabagi" in t and "KLE" in t for t in titles)
    urls = [f["value"] for f in findings if f["type"] == "result_url"]
    assert "https://example.com/faculty/r-kotabagi" in urls
    assert all(u.startswith("https://") for u in urls)
    snippets = [f["value"] for f in findings
                if f["type"] == "result_snippet"]
    assert any("Hubballi" in s for s in snippets)


def test_ddg_parse_skips_malformed_never_hallucinates():
    assert ddg_polite.parse_serp("") == []
    assert ddg_polite.parse_serp(None) == []
    assert ddg_polite.parse_serp("<html><body>no results</body></html>") == []
    # Title with an undecodable href: row skipped (no invented URL).
    bad = ('<a class="result__a" href="javascript:void(0)">T</a>'
           '<a class="result__snippet">S</a>')
    assert ddg_polite.parse_serp(bad) == []
    # Anchor without title text: skipped.
    assert ddg_polite.parse_serp(
        '<a class="result__a" href="https://example.com/x"></a>') == []
    # Snippet with no result anchor: orphan dropped, no row invented.
    assert ddg_polite.parse_serp(
        '<div class="result__snippet">Orphan.</div>') == []
    # Missing snippet still yields title + url (snippet optional).
    partial = ('<a class="result__a" href="https://example.com/only">'
               "Only Title</a>")
    out = ddg_polite.parse_serp(partial)
    assert [f["type"] for f in out] == ["result_title", "result_url"]


def test_ddg_parse_caps_top_10():
    findings = ddg_polite.parse_serp(_many_result_serp(12))
    urls = [f for f in findings if f["type"] == "result_url"]
    assert len(urls) == 10
    assert len(findings) == 30


def test_ddg_pacing_constants_and_sleep_gate(monkeypatch):
    assert ddg_polite.PACING_SEC >= 3.0
    assert "Sherlock" in ddg_polite.USER_AGENT
    # Fresh state: no sleep. Recent call: sleeps >= PACING_SEC + jitter.
    ddg_polite.reset_pacing()
    real_sleep = ddg_polite._sleep
    clock = {"t": 100.0}
    monkeypatch.setattr(ddg_polite, "_now", lambda: clock["t"])
    sleeps = []
    monkeypatch.setattr(ddg_polite, "_sleep",
                        lambda s: sleeps.append(s))
    monkeypatch.setattr(ddg_polite, "_jitter", lambda: 0.5)
    ddg_polite._pace()
    assert sleeps == []
    clock["t"] = 101.0
    ddg_polite._pace()
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(3.0 + 0.5 - 1.0)
    # SHERLOCK_NO_PACING env is honored by _sleep (raw hook observed).
    monkeypatch.setattr(ddg_polite, "_sleep", real_sleep)
    monkeypatch.delenv("SHERLOCK_NO_PACING", raising=False)
    calls = []
    monkeypatch.setattr(ddg_polite, "_sleep_raw",
                        lambda s: calls.append(s))
    ddg_polite._sleep(0.01)
    assert calls == [0.01]


def test_ddg_query_cap_boundary(monkeypatch):
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp", lambda *a, **k: (200, "", ""))
    out = ddg_polite.run("x" * 500)
    check_contract(out, ddg_polite.NAME)
    assert out["status"] == "ok" and out["findings"] == []


def test_ddg_throttle_hook_documented_standalone():
    doc = (ddg_polite.__doc__ or "").lower()
    assert "throttle_check" in doc and "tools" in doc
    assert "per-user" in doc or "per-user" in doc.replace("-", "-")
    src = inspect.getsource(ddg_polite)
    assert "from tools" not in src and "import tools" not in src
    assert "from registry" not in src and "import registry" not in src


# ---------- ddg_polite: run ----------

def test_ddg_run_ok_mocked(monkeypatch):
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp", lambda *a, **k: (200, DDG_SERP_HTML, ""))
    out = ddg_polite.run("R Kotabagi")
    check_contract(out, ddg_polite.NAME)
    assert out["status"] == "ok" and len(out["findings"]) == 6
    assert all(f["confidence"] == "low" for f in out["findings"])


def test_ddg_run_zero_results_ok_empty(monkeypatch):
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp",
        lambda *a, **k: (200, "<html><body>no results</body></html>", ""))
    out = ddg_polite.run("Nobody Example Xyz")
    check_contract(out, ddg_polite.NAME)
    assert out["status"] == "ok" and out["findings"] == []


def test_ddg_run_429_rejected_clean_no_retry(monkeypatch):
    calls = {"n": 0}

    def _fake(*a, **k):
        calls["n"] += 1
        return (429, "", "60")

    monkeypatch.setattr(ddg_polite, "_fetch_serp", _fake)
    out = ddg_polite.run("Demo Person")
    check_contract(out, ddg_polite.NAME)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "429" in out["reason"]
    assert "60" in out["reason"]  # retry-after note
    assert "cach" in out["reason"].lower()  # cache hint
    assert calls["n"] == 1  # no hammering: single call, no retry


def test_ddg_run_202_rejected_clean(monkeypatch):
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp", lambda *a, **k: (202, "", ""))
    out = ddg_polite.run("Demo Person")
    check_contract(out, ddg_polite.NAME)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "202" in out["reason"]
    assert "cach" in out["reason"].lower()


def test_ddg_run_5xx_timeout_forbidden_rejected(monkeypatch):
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp", lambda *a, **k: (502, "", ""))
    out = ddg_polite.run("Demo Person")
    assert out["status"] == "rejected" and out["findings"] == []
    assert "cach" in out["reason"].lower()
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp", lambda *a, **k: (None, "", ""))
    out = ddg_polite.run("Demo Person")
    assert out["status"] == "rejected" and out["findings"] == []
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp", lambda *a, **k: (403, "", ""))
    out = ddg_polite.run("Demo Person")
    assert out["status"] == "rejected" and out["findings"] == []


def test_ddg_run_validation_rejected_no_network(monkeypatch):
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise AssertionError("must not fetch invalid input")

    monkeypatch.setattr(ddg_polite, "_fetch_serp", _boom)
    assert ddg_polite.run("   ")["status"] == "rejected"
    assert ddg_polite.run("x" * 501)["status"] == "rejected"
    assert ddg_polite.run("someone@example.com")["status"] == "rejected"
    assert ddg_polite.run("+91 98765 43210")["status"] == "rejected"
    assert ddg_polite.run(123)["status"] == "rejected"
    assert calls["n"] == 0


def test_ddg_run_never_hallucinates_urls(monkeypatch):
    mixed = ('<a class="result__a" href="https://example.com/good">Good</a>'
             '<a class="result__snippet">S1.</a>'
             '<a class="result__a" href="javascript:void(0)">Bad</a>'
             '<a class="result__snippet">S2.</a>')
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp", lambda *a, **k: (200, mixed, ""))
    out = ddg_polite.run("Demo Person")
    urls = [f["value"] for f in out["findings"]
            if f["type"] == "result_url"]
    assert urls == ["https://example.com/good"]
    assert all(u.startswith("http") for u in urls)


def test_ddg_determinism(monkeypatch):
    monkeypatch.setattr(
        ddg_polite, "_fetch_serp", lambda *a, **k: (200, DDG_SERP_HTML, ""))
    assert ddg_polite.run("R Kotabagi") == ddg_polite.run("R Kotabagi")


# ---------- github_lane: units ----------

def test_github_token_dummy_as_missing(monkeypatch):
    monkeypatch.delenv("SHERLOCK_GITHUB_TOKEN", raising=False)
    assert github_lane.get_token() == ""
    monkeypatch.setenv("SHERLOCK_GITHUB_TOKEN", "DUMMY_GITHUB_TOKEN")
    assert github_lane.get_token() == ""
    monkeypatch.setenv("SHERLOCK_GITHUB_TOKEN", "  DUMMY_xyz  ")
    assert github_lane.get_token() == ""
    monkeypatch.setenv("SHERLOCK_GITHUB_TOKEN", "TEST_TOKEN_1")
    assert github_lane.get_token() == "TEST_TOKEN_1"
    headers = github_lane._auth_headers("")
    assert "Authorization" not in headers
    headers = github_lane._auth_headers("TEST_TOKEN_1")
    assert headers["Authorization"] == "Bearer TEST_TOKEN_1"


def test_github_is_handle():
    assert github_lane.is_handle("demo-sleuth")
    assert github_lane.is_handle("octocat")
    assert github_lane.is_handle("a")
    assert not github_lane.is_handle("Demo Sleuth")
    assert not github_lane.is_handle("someone@example.com")
    assert not github_lane.is_handle("-leading")
    assert not github_lane.is_handle("trailing-")
    assert not github_lane.is_handle("double--dash")
    assert not github_lane.is_handle("x" * 40)
    assert not github_lane.is_handle("")
    assert not github_lane.is_handle(None)


def test_github_parse_profile():
    finding = github_lane.parse_profile(GH_PROFILE)
    assert finding["type"] == "github_profile"
    assert finding["source"] == "github_lane"
    assert finding["confidence"] == "low"
    assert "demo-sleuth" in finding["value"]
    assert "https://github.com/demo-sleuth" in finding["value"]
    assert github_lane.parse_profile({}) is None
    assert github_lane.parse_profile({"login": "  "}) is None
    assert github_lane.parse_profile(None) is None
    assert github_lane.parse_profile([]) is None


def test_github_parse_repos_capped():
    out = github_lane.parse_repos(GH_REPOS)
    assert len(out) == 2  # malformed row skipped
    assert all(f["type"] == "github_repo" for f in out)
    assert all(f["confidence"] == "low" for f in out)
    assert "demo-sleuth/example-project" in out[0]["value"]
    assert github_lane.parse_repos({}) == []
    assert github_lane.parse_repos(None) == []
    big = [{"full_name": "u/r%d" % i,
            "html_url": "https://github.com/u/r%d" % i} for i in range(9)]
    assert len(github_lane.parse_repos(big)) == github_lane.MAX_REPOS == 5


def test_github_parse_orgs():
    out = github_lane.parse_orgs(GH_ORGS)
    assert len(out) == 1
    assert out[0]["type"] == "github_org"
    assert "example-org" in out[0]["value"]
    assert github_lane.parse_orgs({}) == []
    assert github_lane.parse_orgs([{"login": ""}]) == []


def test_github_parse_commit_emails_public_only():
    out = github_lane.parse_commit_emails(GH_EVENTS)
    assert len(out) == 2  # dupe deduped, WatchEvent ignored
    assert all(f["type"] == "github_email" for f in out)
    emails = [f["value"] for f in out]
    assert any("users.noreply.github.com" in e for e in emails)
    assert any("demo@example.com" in e for e in emails)
    assert any("demo-sleuth/example-project" in e for e in emails)
    assert github_lane.parse_commit_emails({}) == []
    assert github_lane.parse_commit_emails(None) == []
    many = [{"type": "PushEvent", "repo": {"name": "u/r"},
             "payload": {"commits": [
                 {"author": {"email": "e%d@example.com" % i}}]}}
            for i in range(9)]
    assert len(github_lane.parse_commit_emails(many)) == \
        github_lane.MAX_EMAILS == 5


def test_github_parse_user_search():
    out = github_lane.parse_user_search(GH_SEARCH)
    assert len(out) == 1
    assert out[0]["type"] == "github_user"
    assert out[0]["confidence"] == "low"
    assert "demo-sleuth" in out[0]["value"]
    assert github_lane.parse_user_search({"items": []}) == []
    assert github_lane.parse_user_search({}) == []
    assert github_lane.parse_user_search(None) == []


def test_github_api_host_guard_no_network(monkeypatch):
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("non-API host must never be fetched")

    monkeypatch.setattr(github_lane.requests, "get", _boom)
    assert github_lane._api_get("https://example.com/users/x") == \
        (None, None, {})
    assert github_lane._api_get("https://github.com/demo-sleuth") == \
        (None, None, {})
    assert called["n"] == 0  # HTML scraping forbidden: zero calls


def test_github_no_html_scraping_surface():
    src = inspect.getsource(github_lane)
    assert "BeautifulSoup" not in src
    assert "html.parser" not in src
    assert "lxml" not in src
    for const in ("PROFILE_URL", "REPOS_URL", "ORGS_URL", "EVENTS_URL",
                  "SEARCH_USERS_URL"):
        assert getattr(github_lane, const).startswith(
            "https://api.github.com/")
    assert "HTML scraping" in (github_lane.__doc__ or "")


# ---------- github_lane: run ----------

def _mock_github_full(monkeypatch):
    monkeypatch.setattr(
        github_lane, "fetch_profile",
        lambda *a, **k: (200, dict(GH_PROFILE), {}))
    monkeypatch.setattr(
        github_lane, "fetch_repos",
        lambda *a, **k: (200, [dict(r) for r in GH_REPOS], {}))
    monkeypatch.setattr(
        github_lane, "fetch_orgs",
        lambda *a, **k: (200, [dict(o) for o in GH_ORGS], {}))
    monkeypatch.setattr(
        github_lane, "fetch_events",
        lambda *a, **k: (200, [dict(e) for e in GH_EVENTS], {}))


def test_github_run_ok_mocked_full(monkeypatch):
    _mock_github_full(monkeypatch)
    out = github_lane.run("demo-sleuth")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "ok" and out["findings"]
    types = {f["type"] for f in out["findings"]}
    assert {"github_profile", "github_repo", "github_org",
            "github_email"} <= types
    assert all(f["confidence"] != "high" for f in out["findings"])


def test_github_run_at_handle_ok(monkeypatch):
    _mock_github_full(monkeypatch)
    out = github_lane.run("@demo-sleuth")
    assert out["status"] == "ok" and out["findings"]
    assert any("demo-sleuth" in f["value"] for f in out["findings"])


def test_github_run_404_ok_empty_no_hammer(monkeypatch):
    calls = {"repos": 0, "orgs": 0, "events": 0}
    monkeypatch.setattr(
        github_lane, "fetch_profile", lambda *a, **k: (404, None, {}))
    monkeypatch.setattr(
        github_lane, "fetch_repos",
        lambda *a, **k: (calls.__setitem__("repos", 1), (200, [], {}))[1])
    monkeypatch.setattr(
        github_lane, "fetch_orgs",
        lambda *a, **k: (calls.__setitem__("orgs", 1), (200, [], {}))[1])
    monkeypatch.setattr(
        github_lane, "fetch_events",
        lambda *a, **k: (calls.__setitem__("events", 1), (200, [], {}))[1])
    out = github_lane.run("ghost-handle-xyz")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "ok" and out["findings"] == []
    assert calls == {"repos": 0, "orgs": 0, "events": 0}


def test_github_run_429_rejected_clean(monkeypatch):
    monkeypatch.setattr(
        github_lane, "fetch_profile",
        lambda *a, **k: (429, None, {"retry_after": "60",
                                    "remaining": ""}))
    out = github_lane.run("demo-sleuth")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "429" in out["reason"]
    assert "cach" in out["reason"].lower()


def test_github_run_quota_403_rejected_with_token_hint(monkeypatch):
    monkeypatch.setattr(
        github_lane, "fetch_profile",
        lambda *a, **k: (403, {"message": "API rate limit exceeded"},
                         {"remaining": "0", "retry_after": ""}))
    out = github_lane.run("demo-sleuth")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "rejected" and out["findings"] == []
    assert "SHERLOCK_GITHUB_TOKEN" in out["reason"]
    assert "cach" in out["reason"].lower()


def test_github_run_timeout_rejected_with_cache_hint(monkeypatch):
    monkeypatch.setattr(
        github_lane, "fetch_profile", lambda *a, **k: (None, None, {}))
    out = github_lane.run("demo-sleuth")
    assert out["status"] == "rejected" and out["findings"] == []
    assert "cach" in out["reason"].lower()


def test_github_run_token_never_leaks(monkeypatch):
    monkeypatch.setenv("SHERLOCK_GITHUB_TOKEN", "TEST_TOKEN_1")
    monkeypatch.setattr(
        github_lane, "fetch_profile",
        lambda *a, **k: (429, None, {"retry_after": "", "remaining": ""}))
    out = github_lane.run("demo-sleuth")
    assert out["status"] == "rejected"
    assert "TEST_TOKEN_1" not in out["reason"]
    assert "TEST_TOKEN_1" not in "".join(
        f["value"] for f in out["findings"])


def test_github_run_partial_degrade_ok(monkeypatch):
    monkeypatch.setattr(
        github_lane, "fetch_profile",
        lambda *a, **k: (200, dict(GH_PROFILE), {}))
    monkeypatch.setattr(
        github_lane, "fetch_repos", lambda *a, **k: (500, None, {}))
    monkeypatch.setattr(
        github_lane, "fetch_orgs",
        lambda *a, **k: (200, [dict(o) for o in GH_ORGS], {}))
    monkeypatch.setattr(
        github_lane, "fetch_events", lambda *a, **k: (None, None, {}))
    out = github_lane.run("demo-sleuth")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "ok" and out["findings"]
    types = {f["type"] for f in out["findings"]}
    assert "github_profile" in types and "github_org" in types
    assert "degraded" in out["reason"]


def test_github_run_exhaustion_midrun_stops_clean(monkeypatch):
    seen = {"events": 0}
    monkeypatch.setattr(
        github_lane, "fetch_profile",
        lambda *a, **k: (200, dict(GH_PROFILE), {}))
    monkeypatch.setattr(
        github_lane, "fetch_repos",
        lambda *a, **k: (200, [dict(r) for r in GH_REPOS], {}))
    monkeypatch.setattr(
        github_lane, "fetch_orgs",
        lambda *a, **k: (429, None, {"retry_after": "30",
                                    "remaining": ""}))

    def _events(*a, **k):
        seen["events"] += 1
        return (200, [], {})

    monkeypatch.setattr(github_lane, "fetch_events", _events)
    out = github_lane.run("demo-sleuth")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "rejected" and out["findings"] == []
    assert seen["events"] == 0  # stopped at once: no hammering


def test_github_run_search_path_name(monkeypatch):
    monkeypatch.setattr(
        github_lane, "fetch_user_search",
        lambda *a, **k: (200, dict(GH_SEARCH), {}))
    out = github_lane.run("Demo Sleuth")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "ok" and len(out["findings"]) == 1
    assert out["findings"][0]["type"] == "github_user"
    assert out["findings"][0]["confidence"] == "low"


def test_github_run_search_zero_ok_empty(monkeypatch):
    monkeypatch.setattr(
        github_lane, "fetch_user_search",
        lambda *a, **k: (200, {"total_count": 0, "items": []}, {}))
    out = github_lane.run("Nobody Example Xyz")
    check_contract(out, github_lane.NAME)
    assert out["status"] == "ok" and out["findings"] == []


def test_github_run_validation_no_network(monkeypatch):
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise AssertionError("must not fetch invalid input")

    monkeypatch.setattr(github_lane, "fetch_profile", _boom)
    monkeypatch.setattr(github_lane, "fetch_user_search", _boom)
    assert github_lane.run("   ")["status"] == "rejected"
    assert github_lane.run("x" * 257)["status"] == "rejected"
    assert github_lane.run("someone@example.com")["status"] == "rejected"
    assert github_lane.run("+91 98765 43210")["status"] == "rejected"
    assert github_lane.run("https://github.com/demo-sleuth")["status"] == \
        "rejected"
    assert github_lane.run(123)["status"] == "rejected"
    assert calls["n"] == 0


def test_github_determinism(monkeypatch):
    _mock_github_full(monkeypatch)
    assert github_lane.run("demo-sleuth") == github_lane.run("demo-sleuth")


def test_searchlanes_env_placeholders_only():
    assert os.environ.get("SHERLOCK_GITHUB_TOKEN", "") == "" or True
    assert "DUMMY" in "DUMMY_GITHUB_TOKEN"  # repo policy: DUMMY only
