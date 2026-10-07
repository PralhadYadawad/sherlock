# Sherlock LOAD.md (demo build 0.1.0)

> Offline smoke only. Fake fixtures (`@demo.sleuth`, `example.com`,
> `DMYosint001`). No network in the harness: `requests.get` and DNS are
> stubbed exactly like `server/test_core.py`. Not a prod load test.

## Harness

`scripts/load_smoke.py` — 100 `triage_target` calls (round-robin over
`@demo.sleuth` / `example.com` / demo reel URL) + 100 `search_memory`
calls (round-robin over `osint demo case` / `demo.sleuth` /
`example.com`), hermetic temp `SHERLOCK_DB`, prints p50/p95/max.

```bash
/tmp/opencode/sherlock-venv/bin/python scripts/load_smoke.py
/tmp/opencode/sherlock-venv/bin/python scripts/load_smoke.py --triages 100 --searches 100
```

## Results (2026-10-05 audit-2 re-run, 3 consecutive runs, same machine)

| run | triages (100) p50 / p95 / max | searches (100) p50 / p95 / max | ok |
|-----|-------------------------------|--------------------------------|----|
| 1 | 0.002 ms / 0.003 ms / 0.011 ms | 0.352 ms / 0.416 ms / 1.387 ms | 100/100, 100/100 |
| 2 | 0.002 ms / 0.003 ms / 0.011 ms | 0.356 ms / 0.440 ms / 1.462 ms | 100/100, 100/100 |
| 3 | 0.002 ms / 0.003 ms / 0.012 ms | 0.352 ms / 0.426 ms / 1.390 ms | 100/100, 100/100 |

Summary: **triage p95 ≈ 0.003 ms, search p95 ≈ 0.42–0.44 ms** across 3
runs; 200/200 ok each run; worst single search 1.5 ms. Unchanged from
packaging (module caching in `server/main.py` keeps the in-process path
at the same floor; triage is pure routing, search rebuilds the
`DEMO-CASE-001` bundle from stubbed adapters each call).

Bounds: well under the 10 s budget used for the 500-probe perf tests
(`test_500_adapter_runs_fast`, `test_perf_500_username_probes`). No
persistence growth issue: smoke uses a temp DB, deleted after the run.

## TODO before any prod claim

- Real-network budgets (crt.sh, public probes, oEmbed) with 429 backoff.
- Concurrent-client test through `uvicorn` + `/mcp` (this smoke calls
  `tools.*` in-process, single-threaded).
- Supabase latency numbers once a project exists (India region).

## Entity-pipeline load shape (appendix L4, re-run 2026-10-06)

Harness: `scripts/entity_load_shape.py` — 10 fictional entities
(`@demo.*` handles incl. Kotabagi-shaped homonym pair, `example.com`
domains, demo reel, 1 search query) × 4 tool calls each
(`triage_target` + lane tool + `search_memory`/`case_summary`), cold pass
then identical warm pass, temp DB. Targets: 20/20 ok
(10+10); warm p95 within max(2× cold p95, cold + 5ms) — no growth;
repeat-stability 10/10 identical (fixtures deterministic).

Measured 2026-10-06 (this box, canonical venv
`/home/markone/drive1/.venvs/sherlock`, 1 run):

| pass | n / ok | p50 | p95 | max |
|---|---|---|---|---|
| cold | 10 / 10 | 6.247 ms | 25.240 ms | 25.240 ms |
| warm | 10 / 10 | 5.294 ms | 9.415 ms | 9.415 ms |

Repeat-stability: 10/10 identical. `RESULT: PASS`.

Prior (2026-10-05, system `python3`): cold p50 4.199/p95 8.643,
warm p50 4.141/p95 7.081, `RESULT: PASS`. The cold-p95 spread across
runs is first-call/DB-init noise; the warm pass is the stable comparator
and stays ≤10 ms p95 on both dates.

Hermeticity caveat (open, owner: orchestrator): the harness stubs
`requests.get` + `socket.gethostbyname_ex` only — `socket.getaddrinfo`
is NOT stubbed, so on a networked box `domain_intel` resolves
`example.com` via real DNS and skips its both-fail offline fixture
(same DEV-1 root cause as `demo_script.md` H0). The shape targets above
(ok-count, no-growth bound, repeat-stability) are DNS-independent, so
`RESULT: PASS` holds either way — but the per-entity finding counts
differ (fixture-full under H0 stubs vs domain-lane-empty on a networked
box). Re-run with `SHERLOCK_LIVE=1` + BYOK keys for the true live
cache-hit ratio (builder TODO, unchanged).

Cache-hit ratio target (live/BYOK path only): ≥50% of repeat identical
entity lookups served from `fetch_log` TTL-24h cache (`cached live hit
(TTL 24h, no re-fetch)`, no re-fetch) once entity adapters land. NOT
measured here — demo fixtures bypass the cache by design
(`docs/LIVE.md` §6), so the fixture proxy above reports
repeat-stability instead of cache hits. Builder TODO: re-run this shape
with `SHERLOCK_LIVE=1` + BYOK keys and report the true cache-hit ratio.
