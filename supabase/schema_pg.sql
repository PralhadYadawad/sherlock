-- Sherlock cache schema — Postgres/Supabase native (see schema.sql for sqlite).
-- Idempotent: IF NOT EXISTS + ON CONFLICT in seed_pg.sql. Run twice safely.
-- Requires: pgvector extension (run CREATE EXTENSION first or via dashboard).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  type TEXT NOT NULL,
  value TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (case_id, type, value)
);

CREATE TABLE IF NOT EXISTS targets (
  id TEXT PRIMARY KEY,
  case_id TEXT,
  kind TEXT NOT NULL,
  label TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fetch_log (
  id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  adapter TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_findings_case ON findings (case_id);
CREATE INDEX IF NOT EXISTS idx_findings_type ON findings (type);
CREATE INDEX IF NOT EXISTS idx_targets_case ON targets (case_id);

CREATE TABLE IF NOT EXISTS finding_embeddings (
  finding_id TEXT PRIMARY KEY REFERENCES findings (id) ON DELETE CASCADE,
  embedding vector(1536),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
