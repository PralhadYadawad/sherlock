# Sherlock — AGENTS.md

> Working directory: `/home/markone/drive1/sherlock` ONLY. Do not read/write outside this folder except `/tmp/opencode` for temp. Do NOT import from `/home/markone/drive1/askme` — reimplement small shared patterns cleanly instead.
> Product: Sherlock — clean-room OSINT orchestrator as a ChatGPT plugin. Public sources only. No login-gated fetching, no PII tools, no password flows. Fake fixtures + free tiers only. Demo-first, prod-shaped.
> DB: Supabase (India region preferred) with sqlite fallback. No live keys in repo (`DUMMY_...` only).
> Name flag (honest): `sherlock-project/sherlock` (93k stars) owns this name in OSINT. Folder stays `sherlock` per instruction; plugin display name defaults to "Sherlock" with a TODO to rename before public launch (candidates: OpenLens, Lantern, TraceKit).

## 0. Honest constraints (do not assume otherwise)

1. Instagram Saved/Liked history has NO endpoint (even Creator/Business). IG lane = share/paste link + Export-ZIP backfill + own-catalog via official Graph API only. Same rule as AskMe.
2. Login/session/cookie tools (Osintgram, Toutatis, instagrapi login mode, gallery-dl cookie mode, password MCPs) and PII tools (email/phone-to-account) are PERMANENTLY EXCLUDED. Listed only to exclude, with reason. No bypass instructions anywhere, ever.
3. GPL-2.0/3.0 code (theHarvester, Recon-ng, Photon, gallery-dl, Osintgram) is NEVER copied into core. Interface patterns only (flags, JSON shapes, tool schemas). Any GPL adapter ships only as separate optional subprocess module with license intact — none for v1.
4. "Free" = public data + own compute + free-tier keys. Every adapter declares its free cap + rate behavior + failure taxonomy (private/deleted/rate-limit → clean FAIL, no hallucination).
5. No contradiction to `research-osint.md` (seed, 2026-10-04) found at write time; extend it, don't redo it.

## 1. What we ship (prod-shaped demo)

- Core orchestrator: adapter registry (allow-list), uniform finding schema, correlate/dedupe/score, sqlite cache, MCP server (FastAPI streamable HTTP) + CLI. Tools: `triage_target`, `probe_username`, `intel_domain`, `save_reel`, `search_memory`, `case_summary`.
- Clean adapters (reimplemented, ours, MIT): `username_probe` (public HTTP presence checks vs fixture list), `domain_intel` (crt.sh-shaped + DNS fixtures), `exif_local` (user-uploaded files only), `oembed_public` (no-auth public metadata + stub transcript).
- Caching DB: `supabase/schema.sql` (findings, targets, fetch_log), sqlite fallback, `seed_fake.sql`.
- Skill `osint-triage/SKILL.md` (5 positive + 3 negative), panel UI, offline `sites/index.html` case-file dashboard, branding assets.
- `review/` launch packet, `SECURITY.md`, `LOAD.md`, `verify.sh`, `demo_script.md`.

## 2. Adapter contract (frozen — parallel crews must not clash)

```python
# server/adapters/<name>.py
NAME = "<name>"            # registry key
LICENSE_NOTE = "clean-room reimplementation, MIT (ours). Studied <repo> docs only."
def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [finding...]}"""
    # finding = {"type": str, "value": str, "source": NAME, "confidence": "high|medium|low"}
```
Registry (`server/registry.py`) loads ONLY allow-listed names. Core imports adapters via `try/except` with builtin fixture fallback. Nobody edits another crew's files (§5).

## 3. Fake fixture contract (do not invent IDs at call time)

- Case `DEMO-CASE-001`: handle `@demo.sleuth` (3 public-presence hits), domain `example.com` (2 subdomains, 1 contact), reel `https://www.instagram.com/reel/DMYosint001/` by `@demo.archivist` (caption has `open-source research`, transcript stub with 2 resource links).
- Files: `demo-data/fixtures/{username,domain,reel}.json`. Search `osint demo case` must return DEMO-CASE-001 top-1 with all three lanes linked.

## 4. Folder layout

```
sherlock/
  AGENTS.md  research-osint.md (seed)  research-osint-2.md (expand)
  plugin.json  mcp.json  .codex-plugin/plugin.json + .mcp.json
  skills/osint-triage/{SKILL.md,panel.json}
  server/{main.py,registry.py,correlate.py,tools.py,requirements.txt,test_*.py,VERIFY*.log}
  server/adapters/{username_probe,domain_intel,exif_local,oembed_public}.py
  supabase/{schema.sql,seed_fake.sql,README.md}
  assets/  demo-data/fixtures/  sites/index.html  review/  docs/  scripts/
  verify.sh  demo_script.md  SECURITY.md  LOAD.md
```

## 5. Domain crews (parallel, file-scoped — never touch another crew's files)

1. `research-expand` — owns `research-osint-2.md` only: new repos beyond seed (WhatsMyName, Holehe/HIBP, Amass/subfinder chain, ExifTool, OpenOSINT, UseOSINT skills + more), include/exclude table with license+activity+ToS reason each. 2x verify + log.
2. `core-orchestrator` — owns `server/{main,registry,correlate,tools,requirements,Dockerfile,.env.example}`, `supabase/*`, `server/test_core.py`. Validation, pagination, rate limits, CORS, /health+/ready, JSON logs, contracts with fallback. ≥25 tests, 3x green + log.
3. `adapters-clean` — owns `server/adapters/*.py` (4 files) + `server/test_adapters.py`. Explore docs first, reimplement, no network in tests (fixtures/monkeypatch). ≥20 tests, 3x green + log.
4. `plugin-site` — owns `skills/osint-triage/*`, `sites/index.html`, `assets/*` (generate 256px PNG placeholders via script). 5+3 cases, offline single-file dashboard (search, modal, empty/error, mobile+a11y). 3x verify + log.
5. `packaging-verify` (spawns after 1-4 land) — manifests, `verify.sh`, `demo_script.md`, `SECURITY.md`, `LOAD.md`, final 4th run.

## 6. Verification protocol (mandatory, same as AskMe)

V1 unit → V2 integration on fixtures (DEMO-CASE-001 top-1) → V3 negatives (private/bad/empty/PII-request → safe refusal, zero hallucinated findings) → V4 packaging end-to-end + load smoke + secrets scan. Log every run; FAIL + cause + fix + re-run. No green-washing. No real creds, no live targets (example.com / @demo.* only).

## 7. Commands

```
python3 -m venv .venv; source .venv/bin/activate
pip install -r server/requirements.txt
grep -v '^CREATE EXTENSION' supabase/schema.sql | sqlite3 /tmp/opencode/sherlock.db
python -m pytest server/ -q
bash verify.sh
```

## 8. Out of scope

Live keys, Meta App Review submit, public Directory submit video, lawyer review, bulk scraping, any login-gated or PII adapter. TODOs, not half-builds.

## 8b. LIVE lanes (in scope since 2026-10-05 — guardrails are hard rules)

Public-GET-only live adapters: username presence (top-30 public profile URL shapes, 10s timeout, 1 req/2s, found/not-found/error classification), domain intel (crt.sh JSON + socket DNS, 502-tolerant). Fixture fallback preserved when network down. PERMANENTLY OUT: logins, passwords, email/phone PII lanes, breach-password data, form POSTs. Live smoke tests gated behind SHERLOCK_LIVE=1. See docs/LIVE.md.

## 9. Done = all suites green + verify.sh ALL GREEN + demo click-path works + review packet complete + secrets clean.
