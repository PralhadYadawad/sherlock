# Sherlock LIVE.md (live lanes, 2026-10-05)

> Fixture-first. Live is opt-in via `SHERLOCK_LIVE=1`; default runs
> offline fixtures only (`example.com` / `@demo.*` / `DMYosint001`,
> `DUMMY_...` secrets). No logins, no PII lanes, no password flows —
> ever. See `AGENTS.md` §0, `SECURITY.md` §4.

## 1. What is live vs fixture

| lane | fixture mode (default) | live mode (`SHERLOCK_LIVE=1`) |
|---|---|---|
| `username_probe` | 5 `DEMO_SITES` (`example.com` subtree), no pacing. `@demo.sleuth` → 3 `presence` (medium); others → `ok` + `[]`. | Non-demo handles → 30 `LIVE_SITES` (curated `/{handle}` public-profile URL shapes: GitHub/Reddit/YouTube/X-style pages, reimplemented shapes, no copied lists). Demo handles stay on fixtures (deterministic `DEMO-CASE-001`). |
| `domain_intel` | `example.com` only → 2 `subdomain` + 1 `contact` (offline fixture when crt.sh + DNS both fail). Other domains → `rejected` (no live third-party lookups). | Any well-formed bare domain → crt.sh JSON API + `socket.getaddrinfo` A-records. `example.com` still resolves (fixture fallback when both sources fail). |
| `oembed_public` / `exif_local` | Unchanged (demo reel stub; local bytes only). | Unchanged — no live lane (no new network). |

Live never invents findings: unknown / private / deleted / rate-limited /
error targets return `ok` + `[]` (or `rejected` for malformed/PII input)
with a reason string. `search_memory("osint demo case")` still returns
`DEMO-CASE-001` top-1 with 10 findings in both modes (live findings use
separate `LIVE-<adapter>-<target>` case ids, never mixed into the demo).

Enable:

```bash
SHERLOCK_LIVE=1 SHERLOCK_DB=/tmp/opencode/sherlock.db \
  python3 -c "from server import tools; print(tools.probe_username('octocat'))"
# pacing 2s × 30 sites ≈ 60s worst case; SHERLOCK_NO_PACING=1 skips
# sleeps in smoke tests (still real GETs, see §5).
```

## 2. Measured network reality (2026-10-05, this box)

- `api.github.com` → HTTP 200 (reachable; GitHub live probes viable).
- `crt.sh` → HTTP 502 (flaky under load; treat as transient — DNS path
  still attempted, reason notes `crt.sh unavailable/flaky, DNS only`).
- No `nslookup` binary on this box → DNS uses stdlib `socket.getaddrinfo`
  (AF_INET A-records) with a `gethostbyname_ex` fallback for stubbed
  resolvers. No new dependency (`requests` + stdlib `socket` only).

## 3. Free caps

- `username_probe` live: 0 keys, public data + own compute. Cap: ≤30
  plain GETs per `run()`, 10s timeout each, Sherlock UA
  (`SherlockOSINT/0.1 (+https://example.com/osint; ...)`), concurrency 1.
- `domain_intel` live: 0 keys. crt.sh = free public log, no key, but
  burst callers get 429/502 → back off, use the 24h cache, do not retry
  hot. DNS = local resolver (OS-limited, no key).
- No breach-password data, no email/phone-to-account, no authenticated
  endpoints. Anything requiring a session/cookie/token is out of scope
  (rejected with reason, listed only to exclude).

## 4. Rate behavior / robots / ToS

- Pacing: 1 request per 2s (`PACING_SEC=2.0`) in the live username lane
  only; demo lane has no pacing (5 fast fixture GETs). `SHERLOCK_NO_PACING=1`
  disables sleeps (smoke tests / unit tests with mocked transport).
- Single GET per site per run; `allow_redirects=True` (final URL
  classified); `429` → `error` (not a hit), caller backs off; no retry
  storm (one shot per site).
- UA identifies the probe; honor `robots.txt` and each host's ToS by
  keeping volume at demo scale (one handle per invocation, cached 24h —
  §6). Bulk scanning / enumeration loops are out of scope.
- Guardrails (hard, enforced in code + tests): public GET only; NO
  logins, NO passwords, NO email/phone PII lanes, NO breach-password
  data, NO POSTing forms. Login-submit walls (`password` + `log in` form
  markers) classify as `error`, never as hits.

## 5. Failure taxonomy (never hallucinated)

`username_probe` per-site verdict (`classify_live_response`):

- `found`: HTTP 200 whose body carries no not-found phrase, no
  login wall (continue/required phrases, or any password form), AND
  names the handle in both body and `<title>` (generic `200` shells
  titled just `Reddit`/`Twitch`/`Bluesky` are soft-404s → `error`).
  Only verdict that creates a `presence` finding (single → `low`,
  corroborated multi-site → `medium`, never `high`).
- `not-found`: 404/410, or 200 whose body says `user not found` /
  `page not found` / `account suspended` / `does not exist` etc.
- `error`: timeout/connection failure (`None`), 403 (bot-gate), 429,
  5xx (incl. flaky upstreams), empty body, login wall
  (`log in to continue` / `login required` / password form), or any
  non-200 outside the above.

Run-level reasons: `live presence: X of 30 ...` (hits), `no live
presence found for @H (30 checked, E errored)` (clean miss),
`live probe unavailable for @H (30 sites, all errored; ...)` (network
down → `ok` + `[]`, registry fixture covers `@demo.sleuth`).

Measured 2026-10-05 (this box, `SHERLOCK_NO_PACING=1`): `octocat`
(well-known public handle) → 9/30 titled hits incl. GitHub; random
handle `zzqxjklwvm12345unlikely` → 0/30 (10 errored bot-gates, rest
clean misses). Before the title/handle gates the same random handle
drew 6 soft-404 false hits (Reddit/PyPI/Twitch-style HTTP-200 shells) —
the gates exist because of that measurement. Snippet window is 100 KiB:
large pages bury `<title>` under inlined assets (GitHub's title sits
past byte 8000).

`domain_intel` live: crt.sh non-200 (incl. 502) → `None` (tolerant
fallback); DNS NXDOMAIN/timeout → `None`. Both `None` + demo domain →
offline fixture (`demo fixture (offline) ...`); both `None` + live
domain → `ok` + `[]` (`live intel degraded ...`). crt `None` + DNS ok →
`live intel for D (crt.sh unavailable/flaky, DNS only)`. Findings:
`subdomain` (medium, crt.sh-scoped to the queried domain — siblings
excluded) + `a_record` (`D -> IP`, low, ≤8) + `contact` (low, fixture
only — live DNS has no contact).

## 6. Caching (sqlite fetch_log TTL 24h)

- Key: `(adapter, target)` exact match in `fetch_log`.
- TTL: `FETCH_CACHE_TTL_S = 86400` (`server/tools.py`). Fresh `ok` row →
  live findings served from the `findings` table under
  `LIVE-<adapter>-<target>` with reason `cached live hit (TTL 24h, no
  re-fetch)` — no network touched.
- Demo fixtures bypass the cache (always deterministic). Stale/missing
  rows → live fetch, then `log_fetch` + `persist_findings` (idempotent
  `INSERT OR IGNORE`).
- Helpers: `is_live_enabled()`, `live_case_id()`,
  `fetch_cache_lookup()`, `get_live_findings()` — all covered by mocked
  unit tests (`test_core.py`: fresh/stale/key-isolation/cache-avoids-refetch).

## 7. Tests

- Mocked unit tests (default, no network): `test_adapters.py` (30-site
  shape, classifier matrix, mocked live run, demo-stays-5, all-error
  degrade, crt 502 → None, getaddrinfo A-records, live-gating) and
  `test_core.py` (TTL fresh/stale, gating, cache-avoids-refetch).
  `SHERLOCK_NO_PACING=1` + monkeypatched `_fetch_live_detail` /
  `_fetch_crtsh` / `_resolve_dns` keep them hermetic and fast.
- Live smoke (gated, real network): `SHERLOCK_LIVE=1` only, else skipped.
  Targets are fixture-safe: `example.com` (IANA reserved) + `octocat`
  (well-known public demo handle). Shape-only assertions (keys, finding
  schema) — never content. Run:

```bash
SHERLOCK_LIVE=1 SHERLOCK_NO_PACING=1 \
  /tmp/opencode/sherlock-venv/bin/python -m pytest server/ -q -k live_smoke
```

4 smoke tests: 2 real-network (`test_adapters.py`: `octocat` + `example.com`,
shape-only) + 2 degraded-shape (`test_core.py` under its offline stubs —
proves fixture-mode-when-network-down). Real-network pair takes ~25s with
`SHERLOCK_NO_PACING=1` (~60s paced without it).

## 8. Secrets

Committed fixtures stay `DUMMY` / `example.com` / `@demo.*` only
(`demo-data/fixtures/*.json`, `server/.env.example`, `supabase/seed_fake.sql`).
Live runs write only to `/tmp/opencode/sherlock.db` (gitignored) and
never log credentials (there are none — public GET, no keys).
`verify.sh` secrets scan stays clean; see `LIVE_VERIFY.log`.
