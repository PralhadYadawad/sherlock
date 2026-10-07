# Sherlock launch checklist (demo 0.1.0)

> DUMMY / `example.com` / `@demo.*` only. No real users, no live targets.

## 1. Manifest mapping

| surface | file | status |
|---|---|---|
| ChatGPT plugin manifest | `plugin.json` (name `sherlock`, v `0.1.0-demo`, displayName `Sherlock`, 5 positive + 3 negative `review.test_cases`, `demo_recording_url: https://example.com/review/sherlock-demo`, countries `IN, US`, no commerce) | READY (demo) |
| MCP manifest | `mcp.json` (`sherlock` → streamable-http `https://example.com/mcp`) | READY (demo URL placeholder) |
| Codex overlay | `.codex-plugin/plugin.json` + `.codex-plugin/.mcp.json` (mirrors name/version/interface/capabilities; full 5+3 review cases; `.mcp.json` carries `type: streamable-http` like `mcp.json`) | READY |
| Skill | `skills/osint-triage/SKILL.md` (frontmatter `name: osint-triage`, workflow triage→probe→correlate→case-summary, 5 positive in §P1–P5 + 3 negative N1–N3, refusal rules, TODOs) | READY |
| Panel | `skills/osint-triage/panel.json` (grid + modal, lane filter, empty/error states, `exampleResult` fixture rank note, markdown fallback, refusals; tool args mirror the real signatures; example findings use the frozen live shapes) | READY |
| Dashboard | `sites/index.html` (offline single-file, search + modal + empty/error + mobile/a11y) | READY (per UI crew log) |
| Server | `server/main.py` (`/health`, `/ready`, `/mcp`, CORS, 1 MB cap, 60/60s rate limit) | READY |
| Tools | `server/tools.py` (6 tools, caps 512/256/50, PII refusals, no hallucination) | READY |
| Adapters | `server/adapters/*.py` (4 × `NAME`/`LICENSE_NOTE`/`run`, fixtures only) | READY |
| DB | `supabase/schema.sql` + `seed_fake.sql` (10 findings, 3 targets, idempotent) | READY |
| Docs | `demo_script.md`, `SECURITY.md`, `LOAD.md`, `verify.sh` | READY (this packet) |
| Legal drafts | `review/privacy.md`, `review/terms.md`, `review/support.md` | TODO: lawyer review (flagged in each file) |

## 2. Test cases (5 positive + 3 negative)

Canonical fixtures: `@demo.sleuth`, `example.com`, reel
`https://www.instagram.com/reel/DMYosint001/` → `DEMO-CASE-001`
(10 findings, 3 lanes). Verified live outputs in `demo_script.md`.

Positive (must succeed):

1. P1 full triage — `search_memory("osint demo case")` → top-1
   `DEMO-CASE-001`, lanes `[domain_intel, oembed_public, username_probe]`,
   10 findings. (`plugin.json` P1, `SKILL.md` P1.)
2. P2 username probe — `probe_username("@demo.sleuth")` → ok, 3
   `presence` findings, all `medium` (corroborated).
3. P3 domain intel — `intel_domain("example.com")` → ok, 2 `subdomain`
   + 1 `contact` (`admin@example.com`).
4. P4 reel memory — `save_reel(<demo reel>)` → ok,
   author `@demo.archivist`, caption contains `open-source research`,
   2 `transcript_link` findings.
5. P5 case summary — `case_summary("DEMO-CASE-001")` → ok, total 10,
   `limit=4` pages slice 4/4/2.

Negative (must refuse or return empty + reason, zero findings):

1. N1 login-gated — "Pull my Instagram followers / Saved list" →
   `rejected`, no-findings, paste-link/Export-ZIP alternative offered.
2. N2 PII — email (`jane.doe@gmail.com`) / phone (`+91 98200 12345`)
   → `rejected` (`_check_pii`, `server/tools.py:200-208`, call sites
   `:317/:333/:379/:974`).
3. N3 bad/empty/unknown — `""`, `"not a domain!!"`,
   `https://evil.test/x`, `@demo.ghost`, `other.test`,
   `UNKNOWN999` reel, `CASE-9999` → `rejected` or `ok` + `[]` + reason.

Fixture-hermeticity note (DEV-1, owner: orchestrator — not a test
failure): P2/P3 counts above hold only with stubbed transport (see
`demo_script.md` H0). On a networked box without stubs,
`probe_username("@demo.sleuth")` → `ok` + `[]` and
`intel_domain("example.com")` → `ok` + `[]` (`… 0 subdomains`), because
`_run_demo` live-GETs fixture paths (real 404s) and `domain_intel`
reaches its offline fixture only when crt.sh AND DNS both fail. Committed
tests are unaffected (function-level monkeypatch). Builder fix: short-circuit
demo fixtures before any network when `SHERLOCK_LIVE` is unset.

Known drift — FIXED in audit-2 (2026-10-05): `panel.json`
`exampleResult` / `markdownFallback`, `sites/index.html` embedded DB, and
`SKILL.md` N3 wording previously used illustrative `profile-presence` /
`reel-meta` / `transcript-link` shapes that did not match the frozen
finding schema. All three surfaces now carry the live adapter output
(`presence` ×3 medium; `subdomain` ×2 medium + `contact` low
`admin@example.com`; `author` + `caption` medium + `transcript_link`
×2 low), pinned by `verify.sh` (`panel live shapes`, `dashboard live
shapes`) and an 86-test suite. `.codex-plugin` expanded 1+1 → 5+3 in the
same pass.

## 3. Video shot-list (≤5 min, dummy data only)

1. (30s) Boot: `bash verify.sh` → ALL GREEN (24 checks).
2. (60s) Probe `@demo.sleuth` → 3 presence hits, medium, sources shown.
3. (60s) Intel `example.com` → 2 subdomains + 1 contact.
4. (90s) `Triage the osint demo case` → DEMO-CASE-001, 3 lanes, reel
   with 2 resource links; then PII refusal
   ("Find the phone number behind @demo.sleuth" → rejected, []).
5. (60s) Offline `sites/index.html`: filter `sleuth` / `example.com` /
   `reel`, open modal (confidence + source), show empty state for a
   no-match query.
6. Outro card: DUMMY-only, public-sources-only, rename TODO
   (OpenLens / Lantern / TraceKit).

Recording URL placeholder: `https://example.com/review/sherlock-demo`
(not yet recorded) — TODO.

## 4. Test account

No login-gated flows exist, so no test account is needed or provided.
Reviewers exercise the demo with the public fixtures above; any
credential prompt is a bug. `server/.env.example` carries `DUMMY_`
placeholders only.

## 5. Attestations

- [READY] Public sources only; no login/session/cookie/password paths.
- [READY] No PII tools; email/phone lookups refused with reason.
- [READY] No hallucination: unknown targets → empty + reason
  (covered by V3 negatives, 75-test suite green 3x).
- [READY] Secrets scan clean (see `SECURITY.md` §1).
- [READY] Offline tests: no network in `server/test_*.py`
  (monkeypatched HTTP/DNS) or `scripts/load_smoke.py`.
- [TODO] Lawyer review of `review/privacy.md`, `review/terms.md`,
  `review/support.md` (drafts only, flagged inside each file).
- [TODO] Rename display name before public launch
  (`sherlock-project/sherlock` owns "sherlock" in OSINT).
- [TODO] Record demo video; replace `example.com/review` placeholder.
- [TODO] Supabase India-region project + RLS/backup review (sqlite
  fallback only in v1).
- [READY] `.codex-plugin/plugin.json` carries the full 5+3 (audit-2;
  mirrors `plugin.json`; `.mcp.json` carries `type: streamable-http`).
- [READY] `panel.json` exampleResult mirrors live finding shapes
  (audit-2; panel + dashboard + SKILL.md N3; pinned by verify.sh).

## 6. Live readiness (`SHERLOCK_LIVE=1`, 2026-10-05)
> Opt-in only; default stays fixture/offline. Measured reality this box:
> `api.github.com`=200 reachable; `crt.sh`=502 (flaky, DNS fallback);
> no `nslookup` binary (stdlib `socket.getaddrinfo` only). Details:
> `docs/LIVE.md`. Committed fixtures stay `DUMMY` / `example.com` /
> `@demo.*` only.

- [READY] `username_probe` LIVE: 30 curated `/{handle}` public-profile
  URL shapes (GitHub/Reddit/YouTube/X-style, reimplemented — no copied
  lists), public GET only, 10s timeout, Sherlock UA, 1 req/2s pacing,
  found/not-found/error classification (login-submit walls never hits).
  Demo handles stay on 5 fixture sites (deterministic `DEMO-CASE-001`).
  Fixture mode when network down (existing behavior preserved).
- [READY] `domain_intel` LIVE: crt.sh JSON API (10s, Sherlock UA,
  502-tolerant fallback) + `socket.getaddrinfo` A-records (no binary).
  Fixture fallback preserved (`example.com` offline → 2 subdomains +
  1 contact; live adds `a_record` findings, ≤8, low).
- [READY] Guardrails (hard): public GET only; NO logins, NO passwords,
  NO email/phone PII lanes, NO breach-password data, NO POSTing forms.
  robots/ToS respected (single GET/site, 2s pacing, 429 backoff),
  failures degrade to fixture/empty with reason — never hallucinated.
- [READY] Caching: sqlite `fetch_log` TTL 24h for live hits
  (`FETCH_CACHE_TTL_S=86400`, key `adapter+target`; demo bypasses;
  `cached live hit (TTL 24h, no re-fetch)` + `LIVE-<adapter>-<target>`
  findings; helpers `live_case_id` / `fetch_cache_lookup` /
  `get_live_findings`).
- [READY] Tests: mocked unit tests (classifier, pacing, 502, getaddrinfo,
  TTL, gating; `SHERLOCK_NO_PACING=1` hermetic) + live smoke gated
  behind `SHERLOCK_LIVE=1` (skipped otherwise; 2 real-network shape-only
  on `example.com` + `octocat`, 2 degraded-shape under offline stubs).
  Suite 102 passed / 4 skipped; `verify.sh` 24/24 ALL GREEN;
  secrets clean; see `LIVE_VERIFY.log`.
- [READY] Docs: `docs/LIVE.md` (live vs fixture, free caps, rate
  behavior, failure taxonomy) + `demo_script.md` §5 live section.

## 7. Entity launch (FINAL review, 2026-10-06)

> What landed since the 2026-10-05 docs packet (sibling crews; reviewed
> here read-only — no `server/`/`skills/`/`sites/` writes by this crew):
> `entity_search` orchestration + real per-user throttle in
> `server/tools.py`, Phase-1 entity playbook in `skills/osint-triage/
> SKILL.md`, `ddg_polite`/`github_lane` adapter files (present but NOT
> allow-listed). Registry loads 8 adapters; `TOOL_SCHEMAS` still carries
> only the 6 v1 tools. Proofs below were re-probed 2026-10-06 (hermetic
> stubs `H0`, canonical venv); full transcripts in
> `review/VERIFY_final.log` + `demo_script.md` §6 (E1–E9).

Variant coverage — [READY] (proof, not plan):

- `entity.MAX_VARIANTS = 12`; `entity_search("Demo Kotabagi")` returns
  exactly 12 variants in stable order: `demo kotabagi`, `demo kotabagee`,
  `demo kotabaghi`, `demo kotabhagi`, `dhemo kotabagi`, `kotabagi demo`,
  `ddemo kotabagi`, `demmo kotabagi`, `demo kkotabagi`, `demo kottabagi`,
  `demo kotabbagi`, `demo kotabaggi` (covers the Kotabagi/Kotabaghi
  ph/f + doubling + order-swap classes from the lesson).
- Derived-handle fan-out over the first 5 (`_MAX_VARIANT_LANES=5`,
  dot-joined, demo-safe); all 5 `username_probe` runs recorded clean-miss
  `[]` with reasons inside the entity reason string — recall expanded,
  zero hallucination.

Homonym-split proof — [READY with OBS-E1] (proof, not plan):

- [READY] `entity_search("Demo Kotabagi", user_id="analyst-1")` →
  `homonym_clusters: 2`, `case_id: ENTITY-demo-kotabagi:candidate-1`:
  card 1 = 7 findings (Example University, every ORCID-bearing finding
  carries `0000-0002-1825-0097`, zero `…0098`); card 2 = 5 findings
  (Another Institute, all `0000-0002-1825-0098`, zero `…0097`). Every
  confidence `low`; no `high` anywhere; no shared pin → no merge.
- [READY] Negatives: `@demo.kotabagi` / `@demo.kotabagi2` → each `ok` +
  `"no public presence found … (5 sites checked)"` + `[]` (two cards, no
  merge); bare `"Demo Kotabagi"` via `probe_username` → `rejected`
  (`invalid handle format`); via `triage_target` → `ok`, routed lane
  `username` (pin required before identity).
- [OBS-E1 — minor, owner: orchestrator] The two URL-only findings (bare
  profile URLs with no ORCID in the value) both attribute to candidate-1
  by order — empty signals never force a split, so the `…/r-kotabaghi`
  URL renders under card 1. Identity separation is unaffected (all
  ORCID-bearing findings are pure per cluster). Polish TODO before any
  front door exposes clusters; does not block the READY above.

Throttle proof — [READY (code gate) + TODO (BYOK budgets)]:

- [READY] Real per-user gate in `server/tools.py:543-595`
  (`THROTTLE_LIMIT_ANON=5`, `THROTTLE_LIMIT_USER=30`,
  `THROTTLE_WINDOW_S=60`, 10k-bucket cap): 6 rapid anon
  `entity_search` → 5× `ok` + 6th `rejected` (`rate limit exceeded …
  per-user throttle`); 6 rapid named-user → 6× `ok` (probed 2026-10-06).
  Global `main.py:20-21` 60 req/60s per-IP gate unchanged;
  `FETCH_CACHE_TTL_S=86400` (`tools.py:72`); `fetch_log` HIT on fresh
  row / MISS on negative TTL; PII email + phone refused with `[]`
  (`scripts/entity_throttle_check.py` re-run 2026-10-06: `RESULT: PASS`).
- [TODO — builders + counsel] Per-user *daily BYOK budgets* (50/50/100/
  10/5/5/20/20) remain plan-level simulation: no operator keys are wired
  (`websearch` with missing/`DUMMY_` key → `rejected: missing_key`, zero
  network — proven). Needs key store + `DUMMY_*` placeholders +
  401/402/429 degrade mapping.

Per-front-door status (entity surface) — no fake READY:

| front door | status | note |
|---|---|---|
| ChatGPT plugin (`plugin.json`) | TODO (builders) | 4 capabilities / 6 tools only; no entity tools exposed; file untouched |
| Offline dashboard (`sites/index.html`) | TODO (builders) | renders `DEMO-CASE-001` only; zero `candidate`/`entity_search` hits; file untouched |
| API (`server/main.py` `/mcp` + `server/tools.py`) | TODO (builders) | `entity_search` is in-process only — `TOOL_SCHEMAS` lists the 6 v1 tools, so no MCP tool reaches the entity lanes; files untouched |
| Skill panel (`skills/osint-triage/panel.json`) | TODO (builders) | no entity-candidate view; file untouched |
| Local connector | TODO (builders) | no local-connector surface exists; `entity_search` is importable in-process (Codex/local path works by direct import, as `SKILL.md` demonstrates) |
| Skill playbook (`skills/osint-triage/SKILL.md`) | READY (docs) | Phase-1 entity playbook present (normalize → query set → fetch → score/refute → `build_entity_cases`); E1–E6 dry-run follows it; file untouched |
| Registry lanes | READY (wired) | 8/8 load (`username_probe`, `domain_intel`, `exif_local`, `oembed_public`, `websearch`, `scholar`, `company`, `page_reader`); `ddg_polite`/`github_lane` files present but registry-`rejected` (`not allow-listed` — `_OPTIONAL_ENTITY_LANES` covers only the four above) |
| Docs + packet (this crew) | READY | ENTITY/DPDP/demo-§6/S6/L4/scripts/log; verified in `VERIFY_final.log` |

Rename decision — [BLOCKER-BEFORE-PUBLIC, owner: maintainer + counsel]:

- Fact: `sherlock-project/sherlock` (~93k stars) owns "Sherlock" in
  OSINT; shipping a public OSINT plugin under that display name invites
  confusion + trademark friction. Current tree defaults to "Sherlock"
  (`plugin.json` displayName, SKILL.md, panel TODO, SECURITY §5).
- Recommendation: **TraceKit** (first choice). Of the shortlisted
  candidates, OpenLens collides with a prominent K8s IDE and Lantern
  with a prominent VPN/proxy tool; TraceKit's live collision is weakest
  (a long-inactive JS error-reporting lib) — but this is a desk screen
  only, NOT a clearance search.
- Required before any public launch (hard gate, not a TODO-comment):
  counsel trademark screen of the shortlist, then rename displayName +
  onboarding copy + assets + review rows in one pass. Demo keeps
  "Sherlock" only behind the existing TODOs.

Blockers for builders (not fixed here): (1) DEV-1 fixture-hermeticity
fix (short-circuit demo fixtures pre-network when `SHERLOCK_LIVE`
unset — `username_probe._run_demo` + `domain_intel` both-fail branch);
(2) `tools.py` MCP exposure decision for entity lanes + front-door
entity views (plugin caps, dashboard candidates, skill panel, local
connector); (3) BYOK key-store + `.env.example` placeholders +
daily-budget buckets (core + counsel); (4) `high` discrepancy
`entity.py:208-213` vs research-§9/ENTITY-§4 — decide before exposure;
(5) `page_reader` contract doc + stale registry comment
("page_reader has no file yet" — file exists and loads) + OBS-E1 URL
attribution polish; (6) re-check vendor caps at build (Brave/OpenAlex/
Serper/OC/Censys moved in 2025–2026); (7) lawyer review (DPDP drafts),
rename gate above, video, Supabase India project (carried over from §5).
