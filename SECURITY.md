# Sherlock SECURITY.md (demo build 0.1.0)

> Demo-only. Public sources, fake fixtures (`example.com`, `@demo.*`,
> `DMYosint001`). No live keys in repo (`DUMMY_...` only). Lawyer review
> required before any public launch (see `review/launch_checklist.md`).

## 1. Secrets scan (2026-10-04, run at packaging)

Command (repo root — same pattern `verify.sh` enforces):

```bash
grep -rEn "ghp_[A-Za-z0-9]{8,}|sk-live|bearer [A-Za-z0-9._-]{8,}|api[-_]key\s*[:=]\s*['\"][^'\"]{8,}|password\s*=\s*['\"][^'\"]+|sessionid|cookies\.txt" \
  --include="*.py" --include="*.md" --include="*.json" --include="*.sql" --include="*.example" --include="*.sh" .
# then drop the scanner's own command-text lines (grep -rEn / SECRET_PAT=):
# any remaining hit is a real finding.
grep -rEn "DUMMY" --include="*.py" --include="*.example" --include="*.sql" --include="*.md" .
```

Result: **clean — no live secrets found.**

- First pattern: zero matches (no tokens, session IDs, or cookie files).
- `DUMMY` hits are only placeholder keys and their documentation:
  `server/.env.example` (`DUMMY.supabase.co`, `DUMMY_ANON_KEY`,
  `DUMMY_SERVICE_KEY`), `AGENTS.md` / `supabase/README.md` policy lines
  ("No live keys in repo (`DUMMY_...` only)"), and `research-osint*.md`
  interface notes that explicitly say "use `DUMMY_...` only, no live
  targets". No real credentials anywhere.
- False-positive note (from core crew): the word `tokens` as a variable
  name in search scoring tripped a naive scan once; not a secret.

Policy: real keys never enter the repo or logs. `server/.env.example`
is the only env template and contains `DUMMY_` values. `.gitignore`
excludes `.env`, `.env.local`, `*.pem`, `*.key`, and local `*.db` files.

## 2. Dependency pins

`server/requirements.txt`:

```text
fastapi>=0.110       # MCP server (server/main.py; pulls in pydantic/starlette)
uvicorn>=0.29        # ASGI server (Dockerfile CMD; local `uvicorn server.main:app`)
pydantic>=2.0        # fastapi dependency; direct import guard for future schemas
httpx>=0.27          # FastAPI TestClient transport (server/test_core.py HTTP-guard tests)
requests>=2.31       # adapter HTTP transport (all 3 network adapters import it)
pytest>=8            # test runner (AGENTS.md §7 flow installs this file, then runs pytest)
```

Every entry is asserted importable in the project venv by
`server/test_core.py::test_requirements_importable`, and `verify.sh`
re-checks the six imports — the missing-requests class of incident
(entry declared but absent from the venv, silently zeroing results)
now fails loudly in two places instead of being skipped.

Pinned at audit-2 (2026-10-05, `/tmp/opencode/sherlock-venv`):

```text
fastapi==0.142.2
httpx==0.28.1
pydantic==2.13.5
requests==2.34.2
pytest==9.1.1
uvicorn==0.37.0
```

Frozen at entity review (2026-10-06, canonical
`/home/markone/drive1/.venvs/sherlock`, `pip freeze`):

```text
fastapi==0.142.2
httpx==0.28.1
pydantic==2.13.5 (+ pydantic_core==2.46.5)
requests==2.34.2
pytest==9.1.1
uvicorn==0.54.0          # bumped since audit-2; re-pin before prod image cut
scrapling==0.4.15        # BSD-3-Clause (see §S6). Page-reader primary parser.
trafilatura==2.3.0       # Apache-2.0. Page-reader fallback extractor.
readability-lxml==0.9    # Apache-2.0 (+ lxml==6.1.3). Page-reader fallback.
```

Scrapling license note (verified 2026-10-06: `pip show scrapling` →
`License: BSD 3-Clause License`; PyPI BSD classifier; see
`server/adapters/page_reader.py:12-28` header): only the plain parser
(`scrapling.Selector`, lxml-backed) plus polite-spider patterns
(`SitemapSpider` shape, `robots_txt_obey`) are adopted. The
stealth/turnstile/proxy tiers (`scrapling.fetchers.stealth_chrome`,
`chrome`, `engines.toolbelt.proxy_rotation`, `_browsers._stealth`) are
EXCLUDED by policy — grep-asserted out of the adapter. All three reader
deps are optional at runtime with stdlib fallback (adapter imports
guarded `try/except`; no-reader-deps venv still passes the suite —
page_reader degrades to `rejected`/empty, never crash).

Note (audit-2 venv gap, same class as the requests incident):
`uvicorn` was declared in `requirements.txt` but missing from the venv,
so `uvicorn server.main:app` could not run locally. Fixed by installing
`uvicorn==0.37.0` in the venv; the new import test covers all six entries
going forward. `pytest` was likewise needed by the AGENTS.md §7 flow
(install-then-pytest on a fresh venv) but undeclared — now declared.

Note (integration fix, same date): `requests` was **missing** from
`requirements.txt` while all three adapters import it (guarded
`try/except` with offline fallback). The integration venv lacked the
package, so `username_probe` returned 0 hits and
`test_oembed_fetch_always_dict` hit `None.get`. Fix: added
`requests>=2.31` to `requirements.txt` (one line, no adapter rewrite);
installed `requests==2.34.2` in the venv. Full suite 75 passed 3x after.
`Dockerfile` installs from `requirements.txt`, so prod images now get it
too. No `beautifulsoup` / `dnspython` dependency: adapters use stdlib +
`requests` + `socket` only (verified by import grep).

## 3. Network guards (refs to `server/main.py`)

- CORS allow-list — `ALLOWED_ORIGINS` (`server/main.py:26-33`),
  `is_origin_allowed` (`server/main.py:47-59`), enforced in the HTTP
  middleware (`server/main.py:188-206`) via `CORSMiddleware`
  (`server/main.py:181-186`). Non-listed origins get HTTP 403.
  Allowed: `http://localhost`, `http://localhost:3000`,
  `http://localhost:8000`, `http://127.0.0.1:8000`,
  `https://example.com` (demo placeholder) plus any
  `http://localhost:*` / `http://127.0.0.1:*` port.
- Body cap — `MAX_BODY_BYTES = 1 MB` (`server/main.py:19`),
  `enforce_size` (`server/main.py:61-65`) plus a declared
  `content-length` pre-check so oversize bodies are rejected with
  HTTP 413 before being buffered (`server/main.py:193-202`).
- Rate limit — `RATE_LIMIT_MAX = 60` per `RATE_LIMIT_WINDOW_S = 60`
  (`server/main.py:20-21`), sliding-window `check_rate_limit`
  (`server/main.py:68-83`, `reset_rate_limits` at `:86-87`),
  middleware returns HTTP 429 when exceeded (`server/main.py:203-205`).
  Client table is bounded (`RATE_BUCKETS_MAX_CLIENTS = 10000`,
  `server/main.py:24`, oldest evicted past the cap).
  Covered by `test_rate_limit_blocks_after_60`,
  `test_rate_buckets_bounded`, `test_size_cap_1mb`,
  `test_cors_allows_localhost_blocks_evil`, and the TestClient
  guard test (`test_http_guards_via_testclient`: 403/413/429 live).
- MCP surface — `handle_mcp` (`server/main.py:116-154`) speaks
  JSON-RPC only (`tools/list`, `tools/call` for the 6 allow-listed
  tools); unknown tools/methods return `-32602`/`-32601`, tool
  crashes return `-32603` (never a stack trace;
  `test_handle_mcp_internal_error_shape`). Validation caps live in
  `server/tools.py:35-37`
  (`MAX_TARGET_LEN=512`, `MAX_QUERY_LEN=256`, `MAX_LIMIT=50`).

## 4. PII policy + delete flow

Permanently excluded (AGENTS.md §0.2): login/session/cookie tools,
password flows, and email/phone-to-account (PII) tools. Enforcement in
`server/tools.py:111-119` (`_check_pii`): non-`@example.com` emails and
phone-shaped inputs return `status: rejected` with reason, zero findings.
Adapter-level guards mirror this (`username_probe`, `domain_intel`,
`oembed_public` reject PII-shaped input; `exif_local` refuses URLs).

Stored data in v1 is **public demo fixtures only**
(`DEMO-CASE-001`: 3 presence + 2 subdomains + 1 contact + author +
caption + 2 transcript links; sqlite `findings`/`targets`/`fetch_log`
or the same Supabase tables). Per-user storage, 90-day retention, and
delete-on-request terms are drafted in `review/privacy.md` (TODO: lawyer
review before launch).

Delete flow (per-user, on request):

```sql
DELETE FROM findings  WHERE case_id = '<USER-CASE-ID>';
DELETE FROM targets   WHERE case_id = '<USER-CASE-ID>';
DELETE FROM fetch_log WHERE target LIKE '%<user-handle>%';
-- Supabase: same statements; finding_embeddings rows cascade
-- (REFERENCES findings ON DELETE CASCADE) where the optional table exists.
```

Verify with `SELECT COUNT(*) FROM findings WHERE case_id='<USER-CASE-ID>';`
→ expect 0. 超过 90 days: purge rows with
`created_at < datetime('now','-90 days')` (sqlite) / `now() - interval
'90 days'` (Supabase). No backups retain PII beyond the window in v1
(TODO: confirm Supabase PITR/backup retention with lawyer/ops before
launch).

## 5. Residual risks (TODO, not shipped)

- Display name "Sherlock" collides with `sherlock-project/sherlock`
  (~93k stars). Rename before public launch (candidates: OpenLens,
  Lantern, TraceKit).
- Live adapter paths (crt.sh, public probes, noembed) need free-tier
  caps + 429 backoff + ToS review before any prod claim; v1 runs on
  fixtures.
- Supabase project region TODO: create in India (`ap-south-1`/Mumbai);
  confirm backup retention + row-level security before storing any
  user data.

## 6. Appendix S6 — entity-pipeline guardrails (AS-BUILT, 2026-10-06)

> What changed since the 2026-10-05 plan: the per-user throttle for the
> entity path is now REAL code (`server/tools.py:543-595`), not a
> simulation. The BYOK daily budgets below remain plan-level (no operator
> keys are wired yet — `websearch` is the only keyed lane and it has no
> key to spend). Harness: `scripts/entity_throttle_check.py` (offline,
> temp DB). Run 2026-10-06, canonical venv: `RESULT: PASS`.

### S6.1 Enforcement layers (as built)

| layer | where | config | scope |
|---|---|---|---|
| global HTTP gate | `server/main.py:20-21` (`RATE_LIMIT_MAX=60`, `RATE_LIMIT_WINDOW_S=60`; sliding-window `check_rate_limit`, buckets capped 10k clients) | 60 req / 60 s | per client IP, all `/mcp` traffic |
| per-user entity gate | `server/tools.py:543-595` (`THROTTLE_LIMIT_ANON=5`, `THROTTLE_LIMIT_USER=30`, `THROTTLE_WINDOW_S=60`, `_THROTTLE_BUCKETS` cap 10k, `reset_throttle()` tests-only) | anon 5/min, named user 30/min | `entity_search` only; missing/empty `user_id` → strictest bucket; over-budget → `rejected` + `rate limit exceeded … per-user throttle` (never hallucinated) |
| live/BYOK cache | `server/tools.py:72` (`FETCH_CACHE_TTL_S = 24*3600`), `fetch_cache_lookup` / `get_live_findings` / `live_case_id` | TTL 24 h, key `(adapter, target)` | live lanes only; demo fixtures bypass by design (`docs/LIVE.md` §6) |
| transport caps | adapters (`username_probe`: 10 s timeout, 1 req/2s, ≤30 GETs; `domain_intel`: 10 s, 502-tolerant; `websearch`: zero calls without key) | per-lane | each `run()` |

Proven 2026-10-06 (in-process, hermetic): 6 rapid anon
`entity_search` → 5× `ok` + 6th `rejected`; 6 rapid named-user →
6× `ok`. `entity_throttle_check.py` re-run: global 60/60 present, TTL
86400 present, plan-bucket isolation (A 50/55 throttled, B 3/3 isolated),
`fetch_log` HIT on fresh row / MISS on negative TTL, PII email + phone
refused with `[]` → `RESULT: PASS`.

### S6.2 Plan-level BYOK daily budgets (still plan — no keys wired)

| BYOK lane | budget/user/day | rationale |
|---|---|---|
| `brave_search` | 50 | well inside ~1k/mo credit |
| `serper_search` | 50 | well inside 2.5k free |
| `openalex` | 100 | well inside $1/day free |
| `opencorporates` | 10 | 200/mo + 50/d free is demo-tiny |
| `shodan` / `censys` | 5 / 5 | limited credits, never shared |
| `github_search` / `graph` | 20 / 20 | 30/min search; 200/hr/token |

These budgets live only in the harness simulation (`_buckets`) and
`docs/ENTITY.md` — no server code spends operator keys today
(`websearch` without/`DUMMY_` key → `rejected: missing_key`, zero
network; key name `SHERLOCK_BRAVE_KEY`, never logged). Builder TODOs:
per-user key store + `DUMMY_*` placeholders in `server/.env.example`;
daily-budget buckets keyed by operator key / Data Principal (not IP);
401/402/429 → clean-degrade mapping per lane.

### S6.3 PII refusal points (entity path)

1. `server/tools.py:200-208` (`_check_pii`): non-`@example.com` emails
   and phone-shaped input → `rejected` + `[]`. Called by
   `triage_target` (`:317`), `probe_username` (`:333`),
   `intel_domain` (`:379`), and `entity_search` (`:974`) — each returns
   the refusal before any `persist_findings`/`log_fetch` call, so refused
   inputs never reach a lane and are never stored (same posture as
   `docs/DPDP.md` §3).
2. Adapter-level mirrors: `username_probe` (`_PII_HINTS` + explicit
   email/phone branches, `:107/:164-174`), `domain_intel` (URL/email
   rejection, `:97`), `websearch` (`_is_pii_shaped`, `:120-125`,
   enforced `:222-224` before any key use). `scholar`/`company` refuse
   PII-shaped input the same way; `exif_local` refuses URLs.
3. Bare person names are NOT PII-shaped — they pass the gate and are
   handled by the homonym policy (`docs/ENTITY.md` §4), never by lookup.

### S6.4 Throttled/over-budget degradation contract

Throttled/over-budget/missing-key/quota-exhausted calls degrade to
cached-or-empty with reason — never hallucinated findings, never a key
leak (`DUMMY_...` only in repo). Throttle state is in-memory
(fail-open on DB error by design — throttle is a guardrail, not auth);
a restart clears buckets (documented, not a finding: the global IP gate
in `main.py` survives per-process the same way).
