-- Sherlock cache schema. Postgres (Supabase) + sqlite compatible.
-- sqlite fallback: grep -v '^CREATE EXTENSION' supabase/schema.sql | sqlite3 /tmp/opencode/sherlock.db
-- Idempotent: every statement uses IF NOT EXISTS.
-- Portability notes: CURRENT_TIMESTAMP is valid in both sqlite and
-- Postgres. fetch_log.id uses sqlite AUTOINCREMENT; on Supabase use
-- `id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY` instead
-- (same insert behavior: omit the column, the DB assigns it).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  type TEXT NOT NULL,
  value TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (case_id, type, value)
);

CREATE TABLE IF NOT EXISTS targets (
  id TEXT PRIMARY KEY,
  case_id TEXT,
  kind TEXT NOT NULL,
  label TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fetch_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  adapter TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_findings_case ON findings (case_id);
CREATE INDEX IF NOT EXISTS idx_findings_type ON findings (type);
CREATE INDEX IF NOT EXISTS idx_targets_case ON targets (case_id);

-- Optional pgvector memory (Supabase only; ignored by sqlite fallback).
-- CREATE TABLE IF NOT EXISTS finding_embeddings (
--   finding_id TEXT PRIMARY KEY REFERENCES findings (id) ON DELETE CASCADE,
--   embedding vector(1536)
-- );
