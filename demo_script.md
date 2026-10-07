# Sherlock Demo Script (5 min, offline, fake fixtures)

> Dummy only. No logins, no live targets. Canonical: `DEMO-CASE-001`.
> Every expectation below was probed against live code on 2026-10-06
> (hermetic stubs, `SHERLOCK_DB` temp); mismatches from the prior draft
> are fixed inline. Prior probing history: 2026-10-04 (offline stubs),
> 2026-10-05 (offline stubs).

## H0. Hermetic precondition (REQUIRED for every `[FIXTURE]` step)

`[FIXTURE]` steps are deterministic only with stubbed transport. Without
these stubs, real network leaks in: `example.com` returns 404 for the
fixture-profile paths and real DNS resolves `example.com`, so the demo
bundle degrades (see DEV-1). Committed tests are unaffected (they
monkeypatch at function level: `_fetch_status`, `_fetch_crtsh`,
`_resolve_dns`).

```bash
cd /home/markone/drive1/sherlock
cat > /tmp/opencode/sherlock_demo_stubs.py <<'EOF'
# Hermetic transport stubs for [FIXTURE] demo steps (no network).
import requests, socket
class _R:
    def __init__(self, c=404): self.status_code = c
    def json(self): return {}
def _fake_get(url, **kw):
    u = str(url)
    if "demo.sleuth" in u and "example.com" in u:
        if any(k in u for k in ("/users/", "/@", "/blog/")):
            return _R(200)
    return _R(404)
requests.get = _fake_get
def _no_net(*a, **k): raise OSError("hermetic demo (no network)")
socket.getaddrinfo = _no_net
socket.gethostbyname_ex = _no_net
EOF
export SHERLOCK_DB=/tmp/opencode/sherlock-demo.db
python3 -c "
import sys; sys.path.insert(0, 'server')
exec(open('/tmp/opencode/sherlock_demo_stubs.py').read())
from server import tools
print(tools.probe_username('@demo.sleuth')['reason'])
print(tools.intel_domain('example.com')['reason'])"
# expect:
#   public presence: 3 of 5 sites hit for @demo.sleuth
#   demo fixture (offline) for example.com: 2 subdomains, 1 contacts
```

> DEV-1 (open, owner: orchestrator crew): on a networked box WITHOUT the
> H0 stubs, `probe_username("@demo.sleuth")` returns `ok` + `[]` ("no
> public presence … (5 sites checked)") and `intel_domain("example.com")`
> returns `ok` + `[]` ("… 0 subdomains"); the bundle drops to 4 findings /
> 1 lane. Root causes in `server/` (not touched by this crew):
> `username_probe._run_demo` performs live GETs against `example.com`
> fixture paths (real 404s), and `domain_intel.run` reaches its offline
> fixture only when crt.sh AND DNS both fail (`domain_intel.py`, "both
> `None`" branch) — working DNS skips it. Fix direction: short-circuit
> demo fixtures before any network when `SHERLOCK_LIVE` is unset. Until
> then, `[FIXTURE]` claims are valid strictly under H0.

## 0. Boot (30s)

```bash
cd /home/markone/drive1/sherlock
bash verify.sh
# expect ALL GREEN — 24 checks (manifests + codex parity + panel/dashboard
# live-shape pins, fixtures, 312-test suite, requirements-importable,
# env, secrets, sites, assets)
```

## 1. Username probe (60s) — `[FIXTURE]` (needs H0)

- `@Sherlock Probe @demo.sleuth` → `probe_username("@demo.sleuth")`
- Expect `status: ok`,
  `reason: "public presence: 3 of 5 sites hit for @demo.sleuth"`,
  exactly 3 findings, all `{"type": "presence", "confidence": "medium"}`
  (multi-site corroboration upgrades the base `low` to `medium`; a lone
  single-site hit would stay `low`), ranked by value:
  `DemoBlog: https://example.com/blog/demo.sleuth`,
  `DemoCode: https://example.com/@demo.sleuth`,
  `DemoHub: https://example.com/users/demo.sleuth`.
- Negative twin: `probe_username("@demo.ghost")` → `status: ok`,
  `reason: "no public presence found for @demo.ghost (5 sites checked)"`,
  `findings: []` (no hallucination).

## 2. Domain intel (60s) — `[FIXTURE]` (needs H0)

- `@Sherlock What intel on example.com?` → `intel_domain("example.com")`
- Expect `status: ok`,
  `reason: "demo fixture (offline) for example.com: 2 subdomains, 1 contacts"`,
  2 × `{"type": "subdomain", "confidence": "medium"}`
  (`blog.example.com`, `www.example.com`) + 1 ×
  `{"type": "contact", "confidence": "low"}` (`admin@example.com`).
- Negative twin: `intel_domain("other.test")` → `status: ok`,
  `reason: "no intel for other.test; demo covers example.com only (no hallucination)"`,
  `findings: []`.

## 3. Full triage (90s) — `[FIXTURE]` (needs H0)

- `@Sherlock Triage the osint demo case` →
  `search_memory("osint demo case")` → `status: ok`,
  `reason: "top-1 DEMO-CASE-001"`, `top_case: "DEMO-CASE-001"`,
  `results[0].lanes: ["domain_intel", "oembed_public", "username_probe"]`,
  `findings: 10` (3 presence + 2 subdomains + 1 contact + author +
  caption + 2 transcript links).
- Reel lane: `save_reel("https://www.instagram.com/reel/DMYosint001/")`
  → `status: ok`,
  `reason: "demo fixture transcript for DMYosint001 (stub, 2 resource links)"`,
  `author: "@demo.archivist"`, caption contains `open-source research`,
  2 × `transcript_link` (`https://example.com/resource-1`,
  `https://example.com/resource-2`). Unknown reel
  (`.../UNKNOWN999/`) → `ok` + `[]` +
  `"unknown reel; demo covers DMYosint001 only (no hallucination)"`.
- P5 case summary: `case_summary("DEMO-CASE-001")` → `status: ok`,
  `total: 10`; `limit=4` pages slice 4/4/2.
- Negative: `@Sherlock Find the phone number behind @demo.sleuth`
  → `triage_target("+91 98200 12345")` returns `status: rejected`,
  `reason: "phone lookups are excluded (PII)"`, `findings: []`;
  `probe_username("jane.doe@gmail.com")` → `rejected`,
  `"email-to-account lookups are excluded (PII)"`, `[]`.
- Bad input: `save_reel("https://evil.test/x")` → `rejected`,
  `"url must be a public instagram.com/reel/ link"`, `[]`.

## 4. Sites case board (60s)

- Open `sites/index.html` offline. Filter `sleuth`, `example.com`,
  `reel` → cards filter, modal shows confidence + source.
- No-match query → empty state (never fake cards); bad input →
  error state with reason.

## Pass criteria

- `verify.sh` green, `DEMO-CASE-001` top-1 with 3 lanes / 10 findings
  (under H0 stubs; networked-box deviation logged as DEV-1),
  negatives refuse cleanly (`rejected` or `ok` + `[]` + reason, zero
  hallucinated findings), no secrets, private/bad/empty handled.

## 5. Live lanes (opt-in, `SHERLOCK_LIVE=1`, ~2 min) — `[LIVE-SMOKE]`

> Default stays fixture/offline (§H0–§4 above). Live never touches
> fixtures: demo handles/domains keep §1–§2 outputs; live findings use
> separate `LIVE-<adapter>-<target>` case ids. Full contract:
> `docs/LIVE.md`. Measured 2026-10-05: `api.github.com`=200,
> `crt.sh`=502 (flaky → DNS fallback), no `nslookup` (stdlib socket).

```bash
cd /home/markone/drive1/sherlock
SHERLOCK_LIVE=1 SHERLOCK_NO_PACING=1 \
  /tmp/opencode/sherlock-venv/bin/python -m pytest server/ -q -k live_smoke
# expect 4 passed: 2 real-network shape-only (example.com + octocat,
# ~25s unpaced) + 2 degraded-shape under offline stubs; no content asserts
# (canonical venv: /home/markone/drive1/.venvs/sherlock/bin/python;
#  /tmp/opencode/sherlock-venv is the legacy path kept by verify.sh)
SHERLOCK_LIVE=1 SHERLOCK_NO_PACING=1 python3 -c "
from server import tools
print(tools.intel_domain('example.com')['reason'])
print(tools.probe_username('octocat')['reason'][:80])"
# expect crt.sh/DNS intel reason (or degraded, never hallucinated) +
# live/cache presence reason; second identical call ->
# "cached live hit (TTL 24h, no re-fetch)" (no re-hammering)
```

- Full 30-site paced probe (1 req/2s, ~60s): drop
  `SHERLOCK_NO_PACING=1` and run `probe_username('octocat')` once —
  expect `live presence: X of 30 ...` or `no live presence ...` or
  `live probe unavailable ...`, always `ok` + schema-valid findings.
- Guardrail spot-check: `probe_username('jane.doe@gmail.com')` →
  `rejected` (PII); no login/POST/password paths exist (grep `requests.post`
  → zero hits outside tests).

## 6. Entity demo (Kotabagi-shaped homonym walkthrough, ~3 min)

> All entities below are **fictional** (`@demo.*`, `example.com`,
> `0000-0002-1825-009X`-style IDs). The surname is a homonym-shape example
> only — no real person. `[FIXTURE]` steps need the H0 stubs (no env
> needed otherwise). Lane adapters (`server/adapters/{scholar,company,
> websearch,page_reader}.py`) are registry-wired but exposed in-process
> only — `server/tools.py::TOOL_SCHEMAS` carries the 6 v1 tools, so no MCP
> tool reaches the entity lanes yet (`[ADAPTER-WIRED, no MCP tool]`).
> Key-gated / unwired variants are marked `[NEEDS KEY]` / `[PROPOSED]`.
> Policy: bare name = candidate list (`low` max); pinned ID = `medium`
> max; merge only on a shared pin; never `high` from metadata alone (open
> discrepancy with `server/entity.py:208-213` "high" — `docs/ENTITY.md`
> §1c-note; builder + counsel call before any front door exposes
> clusters). Probed 2026-10-06; every output below is asserted by the
> dry-run in `review/VERIFY_final.log`.

- E1 `[FIXTURE]` Normalize + variant coverage (12 deterministic):
  `triage_target("Demo Kotabagi")` → `status: ok`, `lane: username`
  (no domain/reel markers), `adapter: username_probe`, `findings: []`.
  Not PII-shaped → passes `_check_pii`; the homonym policy (not a lookup)
  handles the bare name. PII twin stays refused:
  `triage_target("jane.doe@gmail.com")` → `rejected`, `[]`.
  `entity_search("Demo Kotabagi")` → `variants` (12, in order):
  `demo kotabagi`, `demo kotabagee`, `demo kotabaghi`, `demo kotabhagi`,
  `dhemo kotabagi`, `kotabagi demo`, `ddemo kotabagi`, `demmo kotabagi`,
  `demo kkotabagi`, `demo kottabagi`, `demo kotabbagi`, `demo kotabaggi`
  (`entity.MAX_VARIANTS=12`; derived `username_probe` handles fan out over
  the first 5, dot-joined, demo-safe).
- E2 `[FIXTURE]` Lanes run:
  `entity_search("Demo Kotabagi", user_id="analyst-1")` → `status: ok`,
  12 findings, `homonym_clusters: 2`,
  `case_id: ENTITY-demo-kotabagi:candidate-1`. Lane composition:
  offline Kotabagi fixtures (scholar ×4, websearch ×6, page_reader ×2 —
  all `low`, all `example.com`-only values) + `username_probe` fan-out
  over 5 derived handles (all clean-miss `[]`, reasons recorded, zero
  hallucination). Reason names the offline fixture
  (`SHERLOCK_LIVE unset; DUMMY/example only`).
- E3 `[FIXTURE]` Clusters presented (two cards, never merged):
  `ENTITY-demo-kotabagi:candidate-1` (7 findings: Example University /
  ORCID `0000-0002-1825-0097` — every ORCID-bearing finding carries
  `…0097`, zero `…0098`) and
  `ENTITY-demo-kotabagi:candidate-2` (5 findings: Another Institute /
  ORCID `0000-0002-1825-0098` — zero `…0097`). All confidences `low`;
  no `high` anywhere. No shared pin → no merge.
  OBS (minor, owner: orchestrator): the two URL-only findings (bare
  profile URLs with no ORCID in the value) both attribute to candidate-1
  by order — empty signals never force a split, so the `…/r-kotabaghi`
  URL renders under card 1. Identity separation is unaffected (all
  ORCID-bearing findings are pure per cluster), but URL attribution for
  signal-poor findings is a builder polish TODO before front-door
  exposure.
- E4 `[FIXTURE]` Homonym-split negatives:
  `probe_username("@demo.kotabagi")` → `status: ok`,
  `reason: "no public presence found for @demo.kotabagi (5 sites checked)"`,
  `findings: []`; same shape for `@demo.kotabagi2`. Two separate
  candidate cards, zero hallucinated hits, no merge (no shared pin).
  Bare-name twin: `probe_username("Demo Kotabagi")` → `rejected`,
  `"invalid handle format"` (spaces are not handles — bare names route
  via `triage_target`/`entity_search` and resolve only through a pinned
  lane, never by direct probe).
- E5 `[FIXTURE]` PII refusal demoed (entity-shaped input):
  `entity_search("jane.doe@gmail.com")` → `rejected`
  (`email-to-account lookups are excluded (PII)`, `[]`);
  `entity_search("+91 98200 12345")` → `rejected`
  (`phone lookups are excluded (PII)`, `[]`). Refused inputs are never
  stored and never reach a lane.
- E6 `[FIXTURE]` Per-user throttle demoed:
  `reset_throttle()` then 6 rapid `entity_search("Demo Kotabagi")`
  (anon) → 5× `ok` + 6th `rejected` (`rate limit exceeded … per-user
  throttle`); same 6 with `user_id="analyst-1"` → 6× `ok`
  (30/min user bucket). Buckets are in-memory sliding 60s windows
  (`tools.THROTTLE_LIMIT_ANON=5`, `THROTTLE_LIMIT_USER=30`,
  `THROTTLE_WINDOW_S=60`).
- E7 `[ADAPTER-WIRED, no MCP tool]` Scholar / company / page_reader /
  websearch, direct via `registry.run_adapter` (no MCP tool reaches them
  yet — `TOOL_SCHEMAS` is the 6 v1 tools; front-door wiring is a builder
  TODO):
  `scholar("Demo Kotabagi")` → `ok` + `[]`
  (`no scholar records … (3 lanes checked, no hallucination)`, keyless
  triple ORCID/Crossref/S2 all errored cleanly under stubs);
  `company("Example")` → `rejected` + `[]` (GLEIF upstream error under
  stubs — clean degrade, no hallucination);
  `page_reader("https://example.com/profiles/r-kotabagi")` → `ok` + `[]`
  (404 under stubs — clean miss);
  `websearch("Demo Kotabagi")` with no key or `DUMMY_` key →
  `rejected: missing_key`, zero network calls (BYOK `SHERLOCK_BRAVE_KEY`,
  never logged). `[NEEDS KEY]` for any live web-search content.
- E8 `[PROPOSED]` Not wired (builder work, `docs/ENTITY.md` §6):
  `ddg_polite` / `github_lane` files exist on disk but the registry
  rejects them (`not allow-listed` — `_OPTIONAL_ENTITY_LANES` covers
  only websearch/scholar/company/page_reader); Bluesky / Mastodon /
  OpenAlex / OpenCorporates / Serper / Shodan / Censys / Graph /
  IRINS+MCA link-outs remain proposed.
  Note: the registry comment "page_reader has no file yet"
  (`server/registry.py`) is stale — the file exists and loads (flagged
  for orchestrator; `page_reader` treated as wired-unknown until its
  contract log lands).
- E9 `[LIVE-SMOKE]` (gated, real network, shape-only asserts):
  `SHERLOCK_LIVE=1 SHERLOCK_NO_PACING=1 pytest server/ -q -k live_smoke`
  then `entity_search("Demo Kotabagi", …)` live → `status: ok`, real
  `websearch` (with key) / `scholar` lanes run parallel, page_reader
  over found `example.com` URLs (cap 5), domain/company follow-up on
  affiliation domains; clusters via `build_entity_cases`, still never
  merged without a shared pin. No content asserts — keys only.

## Pass criteria (entity)

- Fixture steps deterministic across cold/warm passes (see
  `scripts/entity_load_shape.py`: 10/10 identical, `RESULT: PASS`).
- Variant coverage: exactly the 12 listed variants, stable order.
- Homonym split visible: 2 candidates, ORCID-pure per cluster, no merge
  without a shared pin, no `high` confidence anywhere.
- PII + throttle demos refuse/degrade cleanly (`rejected` + `[]` +
  reason, or `ok` + `[]` + reason; zero hallucinated findings).
- Throttle harness green (`scripts/entity_throttle_check.py`:
  global 60/60, TTL 86400, per-user bucket isolation, cache-hit, PII
  refusals) + live per-user gate proven (anon 5/min, user 30/min).
