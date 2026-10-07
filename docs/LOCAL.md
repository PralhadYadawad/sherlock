# Sherlock LOCAL.md — localhost quickstart (local connector)

> Status: Phase 4 front door (2026-10-06). Fake fixtures + `DUMMY_...` secrets only.
> Public sources only — no logins, no PII lanes, no breach creds, no bypass.
> Three doors, same query: **plugin** (skill + tools) · **dashboard** (`sites/index.html`,
> visitor-browser fetch) · **local connector** (this file — localhost MCP server).

## 0. Which door does what (egress note — read first)

| Door | Where traffic exits | When to use |
|---|---|---|
| Plugin / MCP server (`server/main.py`) | **Our server IP** (shared). SERP lanes rate-limit here — hence DDG-polite + 24h cache + BYOK. | Orchestrated triage (`triage_target`, `probe_username`, `intel_domain`, …). |
| Dashboard (`sites/index.html` + `sites/reader.js`) | **Visitor browser IP** (yours). `fetchAndExtract` runs one `fetch()` from your browser only when you press **Fetch + extract** — zero network until then. | Paste a public URL you already trust; failures show error state, never fake data. |
| Local connector (this file) | **Your machine IP** (localhost). Full lane set without sharing a server key. | Power users / demo day overflow / live entity lanes. |

Architecture insight (PLAN-entity.md journey §6): plugin traffic exits our
server, not user IPs — hence **orchestrate, don't fetch**. The model retrieves,
our code judges. Server does polite known-URL reads; dashboard fetches
client-side; local connector gives power users their own egress.

## 1. Quickstart (localhost, ~3 min)

```bash
cd /home/markone/drive1/sherlock

# 1. venv + deps (pinned; scrapling/trafilatura/readability optional at runtime)
python3 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt

# 2. local cache DB (sqlite fallback; git-ignored — never commit)
grep -v '^CREATE EXTENSION' supabase/schema.sql | sqlite3 /tmp/opencode/sherlock.db
sqlite3 /tmp/opencode/sherlock.db < supabase/seed_fake.sql
export SHERLOCK_DB=/tmp/opencode/sherlock.db

# 3. run the MCP server (streamable HTTP) on localhost
uvicorn server.main:app --host 127.0.0.1 --port 8000
# expect: Uvicorn running on http://127.0.0.1:8000

# 4. smoke it (second terminal, same venv)
curl -s http://127.0.0.1:8000/health
# {"status":"ok","service":"sherlock"}
curl -s http://127.0.0.1:8000/ready
# {"ready":true,"adapters":[...]}
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 400
```

Docker equivalent:

```bash
docker build -f server/Dockerfile -t sherlock:local .
docker run --rm -p 8000:8000 -e SHERLOCK_DB=/tmp/opencode/sherlock.db sherlock:local
```

## 2. Point ChatGPT Developer Mode at it

ChatGPT Developer Mode talks to a **streamable-HTTP MCP endpoint**.
Localhost works for development (tunnel it for shared demos).

1. Keep `uvicorn server.main:app --host 127.0.0.1 --port 8000` running (§1).
2. In ChatGPT → Developer Mode → MCP servers → Add:
   - Transport: **streamable-http**
   - URL: `http://127.0.0.1:8000/mcp`
   - (Local reference shape: `mcp.json` / `.codex-plugin/.mcp.json`
     point at `https://example.com/mcp` — replace with the localhost URL
     for local runs; never commit the replacement.)
3. Verify from ChatGPT:
   - `tools/list` shows `triage_target`, `probe_username`, `intel_domain`,
     `save_reel`, `search_memory`, `case_summary`.
   - `Triage @demo.sleuth` → 3 presence hits (medium).
   - `What intel on example.com?` → 2 subdomains + 1 contact.
   - `osint demo case` → `DEMO-CASE-001` top-1 (10 findings).
4. Same query works all three doors: plugin (here) · dashboard
   (`sites/index.html` entity box offline, reader Fetch for URLs) ·
   local connector (this server).

Live lanes are opt-in only: `SHERLOCK_LIVE=1` (+ `SHERLOCK_NO_PACING=1`
for smokes). Default is offline fixtures. See `docs/LIVE.md`.

## 3. Keys: DUMMY only in repo, BYOK at runtime

```bash
cp server/.env.example .env   # never commit .env
cat server/.env.example
# SUPABASE_URL=https://DUMMY.supabase.co
# SUPABASE_ANON_KEY=DUMMY_ANON_KEY
# SUPABASE_SERVICE_KEY=DUMMY_SERVICE_KEY
# SUPABASE_REGION=ap-south-1
# SHERLOCK_DB=/tmp/opencode/sherlock.db
```

Rules:

- Committed fixtures stay `DUMMY_...` / `example.com` / `@demo.*` only
  (`demo-data/fixtures/*.json`, `server/.env.example`, `supabase/seed_fake.sql`).
- `websearch` (Brave shape) with missing/`DUMMY_` key → `rejected: missing_key`,
  zero network calls. Real keys go in **per-user runtime env**
  (`SHERLOCK_BRAVE_KEY=... uvicorn ...`) — never in the repo, never logged.
- Live runs write only to `/tmp/opencode/sherlock.db` (gitignored).
- `verify.sh` secrets scan stays clean; see `LIVE_VERIFY.log`.

## 4. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: fastapi` | You skipped the venv: `source .venv/bin/activate && pip install -r server/requirements.txt`. Every entry must import (regression test guards this). |
| `curl: Failed to connect` | `uvicorn` not running or wrong port — rerun §1 step 3, check `8000` free. |
| `403 origin not allowed` | Origin not in `ALLOWED_ORIGINS` (`server/main.py`) — use `http://localhost:*` / `http://127.0.0.1:*` for local dev. |
| `429 rate limit` | Global 60/60s per IP (`server/main.py`) — wait a minute; per-user buckets are a builder TODO (`docs/ENTITY.md` §6). |
| `rejected: missing_key` (websearch) | Expected without a key — set `SHERLOCK_BRAVE_KEY` per-user or stay on fixtures. |
| Reader `fetch blocked (CORS/network)` | The target site blocks cross-origin browser reads — honest miss, 0 findings. Try the local connector (`SHERLOCK_LIVE=1` server read) or paste a CORS-open `example.com` fixture URL. |
| `reader.js did not load` | Open `sites/index.html` via a local server (`python3 -m http.server`) so `./reader.js` resolves; fixtures still work without it. |

## 5. Verify (fake fixtures only)

```bash
source .venv/bin/activate
python -m pytest server/ -q        # untouched-still-green (368 passed, 5 skipped on 2026-10-07)
bash verify.sh                     # ALL GREEN + secrets clean
python3 -m http.server 8080       # then open http://localhost:8080/sites/
# dashboard: search `osint demo case` → DEMO-CASE-001 top-1 (existing cards);
# entity box: `R Kotabagi` → 2 kept-separate clusters (Kotabagi-shaped static
# demo), `dravya demo` → 6 kept-separate clusters (Dravya-shaped static demo);
# depth toggle is labels-only (fast seconds / deep minutes, no backend call);
# per-finding `Fetch this URL` reuses the visitor-browser reader (your IP,
# click only); reader: paste https://example.com/… → Fetch
```

No live targets (`example.com` / `@demo.*` only), no network in tests
(live smokes gated behind `SHERLOCK_LIVE=1`).
