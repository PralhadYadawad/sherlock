# Sherlock cache DB (Supabase + sqlite fallback)

## Region note (India)

Production Supabase project should be created in the India region
(**ap-south-1 / Mumbai**) for data-residency and latency. Set
`SUPABASE_REGION=ap-south-1` (see `server/.env.example`). All keys in
this repo are `DUMMY_...` placeholders — never commit real keys.

## Schema

- `findings(id, case_id, type, value, source, confidence)` — uniform
  finding rows, unique on `(case_id, type, value)` for idempotent writes.
- `targets(id, case_id, kind, label)` — triaged targets per case.
- `fetch_log(adapter, target, status, reason)` — adapter run ledger.
- `finding_embeddings` (commented, pgvector `vector(1536)`) — optional
  Supabase-only semantic memory; sqlite fallback ignores it.

## sqlite fallback

```bash
grep -v '^CREATE EXTENSION' supabase/schema.sql | sqlite3 /tmp/opencode/sherlock.db
sqlite3 /tmp/opencode/sherlock.db < supabase/seed_fake.sql
sqlite3 /tmp/opencode/sherlock.db "SELECT count(*) FROM findings;"
# expect 10
```

Seed is idempotent (`INSERT OR IGNORE`); running it twice keeps 10 rows.
