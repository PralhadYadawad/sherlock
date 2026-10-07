#!/usr/bin/env bash
# Sherlock verify.sh — end-to-end (venv-aware). Offline, fake fixtures only.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
set -o pipefail
if [ -x "/home/markone/drive1/.venvs/sherlock/bin/python" ]; then
  PY="/home/markone/drive1/.venvs/sherlock/bin/python"
elif [ -x "/tmp/opencode/sherlock-venv/bin/python" ]; then
  PY="/tmp/opencode/sherlock-venv/bin/python"
else
  PY="python3"
fi
PASS=0; FAIL=0
ok(){ echo "PASS: $1"; PASS=$((PASS+1)); }
bad(){ echo "FAIL: $1"; FAIL=$((FAIL+1)); }

echo "== Sherlock verify =="

for f in plugin.json mcp.json .codex-plugin/plugin.json .codex-plugin/.mcp.json skills/osint-triage/panel.json; do
  if [ -f "$ROOT/$f" ] && python3 -m json.tool "$ROOT/$f" >/dev/null 2>&1; then ok "$f json"; else bad "$f json"; fi
done

# Codex overlay parity: must mirror the 5+3 review cases of plugin.json.
for key in '"capabilities": \["Triage target", "Username probe", "Domain intel", "Reel memory"\]'; do
  if grep -q "$key" "$ROOT/.codex-plugin/plugin.json" 2>/dev/null; then ok "codex overlay parity"; else bad "codex overlay parity"; fi
done
if python3 -c "import json;d=json.load(open('$ROOT/.codex-plugin/plugin.json'));e=d['extensions']['com.openai']['review']['test_cases'];assert len(e['positive'])==5 and len(e['negative'])==3" 2>/dev/null; then ok "codex 5+3 cases"; else bad "codex 5+3 cases"; fi
if python3 -c "import json;d=json.load(open('$ROOT/.codex-plugin/.mcp.json'));s=d['mcpServers']['sherlock'];assert s['type']=='streamable-http' and s['url']" 2>/dev/null; then ok "codex mcp type+url"; else bad "codex mcp type+url"; fi

# Panel exampleResult must use the frozen live finding shapes (audit-2 drift fix).
if python3 -c "
import json
d=json.load(open('$ROOT/skills/osint-triage/panel.json'))
lanes=d['exampleResult']['case']['lanes']
u={f['type'] for f in lanes['username']['findings']}
assert u=={'presence'}, u
assert {f['confidence'] for f in lanes['username']['findings']}=={'medium'}
dd={f['type'] for f in lanes['domain']['findings']}
assert dd=={'subdomain','contact'}, dd
r={f['type'] for f in lanes['reel']['findings']}
assert r=={'author','caption','transcript_link'}, r
assert 'transcript-link' not in json.dumps(d) and 'profile-presence' not in json.dumps(d) and 'reel-meta' not in json.dumps(d)
" 2>/dev/null; then ok "panel live shapes"; else bad "panel live shapes"; fi

# Dashboard embedded DB must mirror the same live shapes (10 findings).
if python3 -c "
import re
h=open('$ROOT/sites/index.html').read()
assert h.count('transcript_link')>=2, 'transcript_link findings'
assert 'profile-presence' not in h and 'reel-meta' not in h, 'drift shapes'
assert 'admin@example.com' in h, 'contact value'
assert len(re.findall(r'\{id:\"[udr]\d\"', h))==10, 'finding count'
assert 'card-title' in h and '\"<h2>\"' not in h, 'no heading-in-button'
" 2>/dev/null; then ok "dashboard live shapes"; else bad "dashboard live shapes"; fi

if [ -f "$ROOT/skills/osint-triage/SKILL.md" ] && head -n 5 "$ROOT/skills/osint-triage/SKILL.md" | grep -q "name: osint-triage"; then ok "SKILL frontmatter"; else bad "SKILL frontmatter"; fi

DB="/tmp/opencode/sherlock.db"
rm -f "$DB"
if [ -f "$ROOT/supabase/schema.sql" ]; then
  grep -v '^CREATE EXTENSION' "$ROOT/supabase/schema.sql" | sqlite3 "$DB" 2>/tmp/opencode/sherlock_sqlite.log || bad "schema load"
  sqlite3 "$DB" < "$ROOT/supabase/seed_fake.sql" 2>>/tmp/opencode/sherlock_sqlite.log || bad "seed load"
  CNT=$(sqlite3 "$DB" "SELECT count(*) FROM findings;" 2>/dev/null || echo 0)
  [ "$CNT" -ge 5 ] && ok "findings>=$CNT" || bad "findings count $CNT"
  TOP=$(sqlite3 "$DB" "SELECT case_id FROM findings WHERE value LIKE '%demo.sleuth%' OR value LIKE '%example.com%' LIMIT 1;" 2>/dev/null)
  [ "$TOP" = "DEMO-CASE-001" ] && ok "case top-1 DEMO-CASE-001" || bad "case top-1 (got $TOP)"
else
  echo "SKIP: supabase schema not yet landed (core crew)"
fi

for f in demo-data/fixtures/username.json demo-data/fixtures/domain.json demo-data/fixtures/reel.json; do
  [ -f "$ROOT/$f" ] && ok "$f exists" || bad "$f exists"
done

[ -f "$ROOT/server/requirements.txt" ] && ok "server requirements" || bad "server requirements"
# Requirements must equal venv reality (missing-requests incident): every
# entry imports in the project venv. Never silently skip.
if "$PY" -c "import fastapi, uvicorn, pydantic, httpx, requests, pytest" >/dev/null 2>&1; then ok "requirements importable"; else bad "requirements importable"; fi

# Env template must exist and carry DUMMY placeholders only.
if [ -f "$ROOT/server/.env.example" ] && grep -q "DUMMY" "$ROOT/server/.env.example"; then ok ".env.example DUMMY-only"; else bad ".env.example DUMMY-only"; fi

# Secrets scan: no live tokens/keys/sessions. Lines containing the scanner
# invocation itself (`grep -rEn ...`, in this file and SECURITY.md §1 docs)
# are self-referential command text, not secrets, and are excluded.
SECRET_PAT="ghp_[A-Za-z0-9]{8,}|sk-live|bearer [A-Za-z0-9._-]{8,}|api[-_]key\s*[:=]\s*['\"][^'\"]{8,}|password\s*=\s*['\"][^'\"]+|sessionid|cookies\.txt"
if grep -rEn "$SECRET_PAT" \
  --include="*.py" --include="*.md" --include="*.json" --include="*.sql" --include="*.example" --include="*.sh" "$ROOT" 2>/dev/null | grep -v "grep -rEn" | grep -v "SECRET_PAT=" | grep -q .; then
  bad "secrets scan"
else
  ok "secrets scan clean"
fi
if [ -f "$ROOT/server/test_core.py" ] || [ -f "$ROOT/server/test_adapters.py" ]; then
  (cd "$ROOT" && "$PY" -m pytest server/ -q 2>&1 | tail -n 3) || bad "pytest"
else
  echo "SKIP: server tests not yet landed"
fi

[ -f "$ROOT/sites/index.html" ] && ok "sites page" || bad "sites page"
for f in assets/logo.png assets/icon.png assets/screenshot.png; do
  [ -f "$ROOT/$f" ] && ok "$f" || bad "$f"
done

echo "== RESULT pass=$PASS fail=$FAIL =="
[ "$FAIL" -eq 0 ] && echo "ALL GREEN" || echo "FIX FAILs above"
exit $FAIL
