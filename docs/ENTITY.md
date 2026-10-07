# Sherlock ENTITY.md — entity-search pipeline (docs-only, no server code changed)

> Status: **launch packet** (2026-10-05). This crew changed no `server/`
> code; sibling crews landed `server/entity.py` (normalize/variants/
> split_homonyms), `server/adapters/{websearch,scholar,company,
> page_reader}.py`, and registry wiring *during* this packet — §0, §1a,
> §1c, §2, §4-note, and §6 were reconciled against those landings by
> read-only inspection. Still-unwired lanes (Bluesky, Mastodon,
> OpenAlex-key, OpenCorporates, Shodan/Censys, Graph, Serper) are
> **PROPOSED** (builder work, §6 blockers).
> Caps/key-models sourced from `research-entity-apis.md` (checked 2026-10-05).
> Example entities are fictional (`@demo.*`, `example.com`,
> `0000-0000-0000-0000`-style IDs). No real-person PII.

## 0. Adapter names claimed here (import-checked 2026-10-05)

Base allow-list + optional entity lanes (`server/registry.py:15-38` —
orchestrator crew changed the frozen 4-tuple to `_BASE_ALLOW +
_optional_present()` while this packet was being written; the quote below
is the new shape, re-verified by import, not by the old text):

```text
_BASE_ALLOW = ("username_probe", "domain_intel", "exif_local", "oembed_public")
_OPTIONAL_ENTITY_LANES = ("websearch", "scholar", "company", "page_reader")
ALLOW_LIST = _BASE_ALLOW + _optional_present()  # file-present lanes only
```

On this box all 8 load (`load_adapter(...).rejected is False`,
`fallback is False` for each; `grep ^NAME` matches in all 8 files).
`KNOWN-WIRED` in the matrix below means: file on disk + `NAME` match +
registry loads. `page_reader` loads too, but no sibling log describes its
contract yet — treated as wired-unknown (builders: document it). The
registry comment "page_reader has no file yet" is stale (file landed
after the comment) — harmless, flagged for the orchestrator crew.
`review/VERIFY_entity_launch.log` re-runs this check.

## 1. Pipeline: normalize → lanes → resolve

### 1a. Normalize (exists today — `server/tools.py` + `server/entity.py`)

1. Length/enum caps: `MAX_TARGET_LEN=512`, `MAX_QUERY_LEN=256`, `MAX_LIMIT=50`
   (`server/tools.py:35-37`). Pagination via `validate_pagination`.
2. PII gate first: `_check_pii` (`server/tools.py:187-195`) rejects
   non-`@example.com` emails and phone-shaped input → `rejected` + `[]`.
   Bare **person names are NOT PII-shaped** — they pass the gate and are
   handled by the homonym policy (§4), never by lookup.
3. Name normalize/variants (sibling entity crew, `server/entity.py`):
   `normalize` = trim + casefold + NFKD diacritic strip + whitespace
   collapse (non-string/empty → `""`); `variants` = ≤12 (`MAX_VARIANTS`)
   deterministic spellings (aspirated-h, ph/f, ee/i, single/double,
   middle-initial drop, surname-first). Variants expand recall; they never
   invent identity (§4 still gates every merge).
4. Kind detect: `_detect_kind` (`server/tools.py:277-289`) routes
   `@handle` → username, bare domain → domain, `instagram.com/reel/` →
   reel, else username. Entity kinds map as: person-handle → `username`,
   company/domain → `domain`, reel URL → `reel`, uploaded file → `file`.
5. Canonicalize: strip, lowercase domains, strip URL to bare host
   (`tools.intel_domain`); handles keep `@` prefix. Non-demo + live-off →
   `ok` + `[]` + `no hallucination` reason (never invent).

### 1b. Lanes (fan-out; keyless defaults today, BYOK proposed)

- Each lane runs one allow-listed adapter via `registry.run_adapter`
  (never raises; bad shape → `rejected: bad adapter shape`).
- Every lane call is logged: `log_fetch(adapter, target, status, reason)`
  → `fetch_log` (`server/tools.py:260-274`).
- Live/BYOK lanes (proposed) additionally check
  `fetch_cache_lookup(adapter, target)` first (`TTL 24h =
  FETCH_CACHE_TTL_S`, `server/tools.py:59`); fresh `ok` row → serve
  `get_live_findings(LIVE-<adapter>-<target>)` with reason
  `cached live hit (TTL 24h, no re-fetch)` — no network touched.
- Demo fixtures bypass the cache (always deterministic).

### 1c. Resolve (exists today — `server/correlate.py`)

1. `normalize_finding`: drop rows missing type/value/source or with
   confidence outside `{high, medium, low}`; trim + length-cap.
2. `dedupe_findings`: key `(type, value)`; keep highest confidence,
   merge `sources` list.
3. `rank_findings`: confidence desc → type → value (stable).
4. `assemble_case` / `build_demo_case`: group by `source` → `lanes`
   (sorted), `finding_count`, `DEMO-CASE-001` title + aliases.
5. Entity merge rule (§4) is applied **before** persist: findings from
   different lanes merge into one case only on a shared pin; otherwise
   they stay per-source / per-candidate. Sibling implementation:
   `server/entity.py:split_homonyms` clusters findings into person
   candidates (hard split on different affiliation / location / ORCID /
   incompatible name; empty signals never force split; deterministic
   order; per-cluster confidence + sources). NOTE — open discrepancy
   (flagged, not papered over): its `_cluster_confidence` returns
   `"high"` for ≥2 sources + affiliation (`server/entity.py:208-213`),
   which is looser than the §4 / research-§9 rule ("never `high` from
   metadata alone — human verification required"). Builder + counsel call
   which rule wins before any front door exposes entity clusters.

## 2. Lane matrix with caps + key models (checked 2026-10-05)

Legend: ✅ wired today (registry loads, §0) · 🔑 WIRED-BUT-BYOK-GATED
(`websearch`: no/`DUMMY_` key → `rejected: missing_key`, zero network calls;
key via `SHERLOCK_BRAVE_KEY`, never logged) · 👤 human link-out ·
❌ excluded. Full prose + URLs: `research-entity-apis.md`.
Registered entity-lane modules (lanes crew, `server/VERIFY_lanes.log`):
`websearch` (Brave-search shape, BYOK), `scholar` (ORCID-anon + Crossref
polite + S2-shape, keyless triple), `company` (GLEIF + RDAP-shape,
keyless), `page_reader` (loads; contract undocumented — builders: doc it).

| Lane (proposed adapter) | Entity fit | Free cap (2026-10-05) | Key model |
|---|---|---|---|
| ✅ `username_probe` presence (30 public-profile GETs) | person / brand handle | own compute; ≤30 GETs/run, 10s timeout, 1 req/2s, 24h cache | keyless |
| ✅ `domain_intel` crt.sh + socket DNS | company / domain | crt.sh free keyless (~1 req/5s norm, 502-tolerant); DNS OS-limited | keyless |
| ✅ `oembed_public` public metadata | reel / post URL | fair-use; token-or-keyless (verify at build) | keyless-or-BYOK |
| ✅ `exif_local` user bytes only | uploaded file | own compute | keyless |
| ✅ `scholar` (ORCID-anon + Crossref-polite + S2-shape) | person (papers/affiliation) | ORCID anon 12/s + burst 40 + 25k/d; Crossref keyless + mailto ~1/s, 50/s hard; S2 keyless 100/5min | keyless triple (all-3-error → `rejected`; any-ok → `ok`) |
| 🔑 OpenAlex (proposed `scholar` follow-up) | person (affiliation/ROR) | key REQUIRED since Feb 2026; $1/day free per key | per-user key (not wired) |
| 👤 IRINS profile pages (IN) | person (IN faculty) | no API; public pages only | human link-out + paste-back |
| ✅ `company` (GLEIF + RDAP-shape) | company + domain contacts | GLEIF keyless 60/min (`PACING_SEC=1.0`); RDAP redacted-by-default | keyless |
| 🔑 OpenCorporates (proposed `company` follow-up) | company | key required; free 200 req/mo + 50 req/day | per-user key (`api_token`), BYOK only (not wired) |
| 👤 MCA master data (IN) | company (IN) | no API; CAPTCHA-gated portal | human link-out + paste CIN |
| 🔑 RDAP-full / WHOIS-43 beyond `company` shape | domain contacts | free keyless; 429 on abuse; RDAP redacted | keyless (partially wired) |
| 🔑 Bluesky AppView reads | person/org social | keyless ~3,000 req/5min/IP; 5k pts/hr + 35k/day | keyless (not wired) |
| 🔑 Mastodon `/api/v2/search` | person/org social | keyless 300 req/5min per IP+account | keyless (not wired) |
| ✅ `websearch` (Brave-search shape) | discovery (all) | $5 credit/mo ≈ ~1k queries; old free plan removed Feb 2026 | 🔑 per-user key (`SHERLOCK_BRAVE_KEY`; missing/`DUMMY_` → `rejected: missing_key`, zero network) |
| 🔑 Serper.dev | discovery (all) | 2,500 free queries, no card; then ~$1/1k | per-user key (`X-API-KEY`) |
| 🔑 GitHub code/REST search | leak-string / domain | 60/hr anon, 5k/hr authed; search 30/min; code 10/min | keyless → per-user PAT |
| 🔑 Shodan / Censys | infra enrichment | limited free credits / ~250 queries/mo | per-user key, never shared |
| 🔑 Meta Graph incl. Business Discovery | IG official | ~200 req/hr/token; App Review for prod | per-user token |
| ❌ Bing Search API | — | RETIRED 2025-08-11 | do not adopt |
| ❌ X / Nitter / XCancel | — | dead + legally tainted; X API no free tier | excluded |
| ❌ Clearbit standalone | — | paid-only via HubSpot credits | excluded |
| ❌ breach-password / face-ID / login-bypass / phone-address hunting / bulk SERP scraping | — | permanently out (AGENTS.md §0) | excluded, reasons only |

Key-model rule: one shared server key burns out on demo day (Brave ~1k/mo,
OC 200/mo). BYOK lanes activate only with an operator-supplied key, are
server-called (not client-side, so queries stay server-IP), and are always
24h-`fetch_log`-cached with clean FAIL on 401/402/429. `DUMMY_...` in repo,
never real keys.

## 3. Failure taxonomy (never hallucinated)

Run-level contract per lane (`run(target) -> status/reason/findings`):

| Situation | Status | Findings | Reason pattern |
|---|---|---|---|
| hit(s) | `ok` | schema-valid list | `live presence: X of 30 …`, `demo fixture …` |
| clean miss (not-found / 404 / unknown fixture) | `ok` | `[]` | `no … found … (no hallucination)` |
| degraded (all-errored / 5xx / 502 / timeouts) | `ok` | `[]` | `live probe unavailable …`, `live intel degraded …` |
| malformed / empty input | `rejected` | `[]` | `invalid … format`, `empty target` |
| PII-shaped input | `rejected` | `[]` | `… lookups are excluded (PII)` |
| non-allow-listed lane | `rejected` | `[]` | `not allow-listed: …` |
| BYOK lane, no/invalid key, 401/402/429 | `ok` or `rejected` | `[]` | `key missing/invalid/quota exhausted for <lane>; degraded` |

Per-site (username live): `found` (200 + no not-found phrase + no login wall
+ handle named in body AND `<title>`) → only verdict that creates a finding;
`not-found` (404/410 / user-not-found / suspended); `error` (timeout, 403,
429, 5xx, empty, login wall). Single-site hit → `low`; corroborated
multi-site → `medium`; never `high` from presence alone (`docs/LIVE.md` §5).

Domain live: crt.sh non-200 → `None` (tolerant); DNS fail → `None`; both
`None` + demo domain → offline fixture; both `None` + live domain → `ok` +
`[]`; crt `None` + DNS ok → DNS-only reason. Findings: `subdomain` medium
(queried-domain-scoped, siblings excluded) + `a_record` low (≤8) + `contact`
low (fixture only).

## 4. Homonym policy (entity-resolution rule, all lanes)

From `research-entity-apis.md` §9 — binding for every entity lane:

1. **Bare name/handle = candidate, never identity** (`low` max). One
   snippet / one site hit never identifies a person.
2. **Pinned ID = `medium` max:** ORCID iD, LEI, CIN (`jurisdiction_code +
   number`), DID, domain + RDAP `creationDate`. No lane emits `high` from
   metadata/probe aggregation alone — `high` requires human verification
   outside the pipeline.
3. **Merge across lanes only on a shared pin** (same ORCID on paper +
   IRINS profile; same LEI on GLEIF + registry filing; same domain in
   cert + RDAP + DNS). Otherwise display candidates separately.
4. Web search is the worst homonym lane: require ≥2 corroborating signals
   (ORCID + employer domain, or LEI + registry address) before `medium`;
   single-snippet stays `low`.
5. Handles are per-instance unique, not cross-platform identity
   (`@demo.x` on bsky ≠ same human on mastodon) — corroborate via linked
   website / ORCID / GitHub profile URL before merging. Company names
   collide across jurisdictions — `jurisdiction_code + number` (or LEI)
   is the identity, never the bare name.
6. Display per-source findings separately (finding schema `source` +
   dedupe-merged `sources` already do this; `panel.json` lane filter
   keeps candidates visually split).

## 5. Worked shape (fictional — see `demo_script.md` §6)

Fictional query `Demo Kotabagi` (no real person; surname used as a
homonym-shape example only):

- normalize → not PII-shaped → kind `username` (no domain/reel markers).
- lanes (fixture walkthrough): username presence for `@demo.kotabagi` /
  `@demo.kotabagi2` (2 candidate handles, `low` each); scholar-shape
  candidate A carries ORCID pin `0000-0000-0000-0001` (fictional) +
  employer-domain corroboration → `medium`; candidate B has no pin → stays
  `low`. No merge (no shared pin) → two candidate cards.
- resolve → dedupe/rank/assemble; `case_summary` pages with `limit ≤ 50`.

## 6. Builder blockers (not fixed here — sibling crews own `server/`)

1. Tools-layer exposure: `websearch` / `scholar` / `company` /
   `page_reader` load in the registry but `server/tools.py` has NO
   entity-lane functions yet (grep `def .*entity|websearch|scholar|company`
   → zero hits), so no MCP tool / plugin capability reaches them.
   Needs orchestrator crew (functions + tests) + plugin-site crew
   (capabilities, panel, dashboard views).
2. BYOK key storage: `websearch` reads `SHERLOCK_BRAVE_KEY` (missing /
   `DUMMY_` → `rejected: missing_key`, zero network — good); but
   `server/.env.example` has no `DUMMY_BRAVE_KEY`-style placeholder and no
   per-user key store exists. Needs core crew + counsel.
3. Per-user throttle buckets: `server/main.py` enforces global 60/60s per
   IP only; the §S6 per-user budgets are plan-level (this packet's
   harness). Needs core crew.
4. `high`-confidence discrepancy: `entity.py:208-213` vs §4/research-§9.
   Decide before front-door exposure (builder + counsel).
5. `page_reader` contract undocumented (loads, no sibling log found) +
   stale registry comment ("page_reader has no file yet" —
   `server/registry.py:21-23`). Flagged for orchestrator crew.
6. Caps re-check at build: Brave / OpenAlex / Serper / OC / Censys changed
   terms in 2025–2026 — re-fetch pricing before wiring, treat stale caps
   as build signals, not Sherlock failures.
