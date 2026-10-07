# Sherlock DPDP.md — India DPDP Act 2023 posture (demo 0.1.0)

> **Not legal advice. TODO: lawyer review before public launch**
> (same gate as `review/privacy.md`, `review/terms.md`, `review/support.md`).
> Act: Digital Personal Data Protection Act, 2023 (in force 2023-08-11;
> Rules 2025). Applies to digital personal data in India + extraterritorial
> processing for Indian principals (Data Principals).
> This file states the demo's posture only: public data, stated purpose,
> per-user storage, delete-on-request, 90-day retention, grievance contact.

## 1. Basis we rely on (and its limits)

- We process **only publicly available personal data**: self-published
  profiles, public-record registry data (GLEIF / OpenCorporates /
  MCA-pattern), researcher showcase pages (ORCID / IRINS-pattern),
  public social posts via first-party open APIs (Bluesky / Mastodon),
  and infra facts (crt.sh / DNS / redacted RDAP).
- Use is for a **stated, limited purpose**: an open-source research brief
  over sources the user names or the demo fixtures. No repurposing, no
  bulk harvesting, no enumeration loops (one target per invocation,
  cached 24h — itself a safeguard).
- What this does **not** cover: non-public figures get a consent gate
  before any beyond-fixture lookup (builder TODO — no such gate exists in
  code today); login-gated, breach-credential, biometric, and
  phone/address-to-account lanes are permanently excluded and can never
  gain a DPDP basis in this product.
- Highest-care fields even when public: officer/director names (company
  lane), registrant contacts (prefer redacted RDAP; legacy WHOIS emails
  redacted by default), non-public-figure social content.

## 2. Purpose limitation (per lane)

| Data class | Purpose | Not used for |
|---|---|---|
| handle presence (`username_probe`) | answer "is this handle publicly present here" | cross-site identity proof (caps at `medium`, §ENTITY-4) |
| domain infra (crt.sh / DNS / RDAP) | answer "what infra belongs to this domain" | registrant identity (redacted) |
| scholar attribution (ORCID / Crossref / S2 / OpenAlex) | answer "which works affiliate to this pinned ID" | bare-name identity (name-only = `low`) |
| company registry (GLEIF / OC / MCA-pattern) | answer "what entity holds this LEI/CIN" | officer harvesting (no bulk officer pulls) |
| social-public (Bluesky / Mastodon; Graph BYOK) | answer "what did this account publicly post" | private/deleted/suspended content (clean miss) |
| web-search snippets (Brave / Serper BYOK) | discovery pointers only, ≥2-signal corroboration | standalone identity (single-snippet = `low` max) |

Cache (`fetch_log` TTL 24h) serves the same purpose only — never a
secondary use. Logs carry adapter/target/status/reason, no content beyond
persisted findings.

## 3. Per-user data (what is stored, where)

- Stored per submitting user only: triaged targets they explicitly submit
  + derived public findings (`type/value/source/confidence`) + operational
  `fetch_log` rows. v1 demo content is fixtures only (`DEMO-CASE-001`).
- Demo default: local sqlite (`SHERLOCK_DB`, git-ignored). Optional
  Supabase cache (India region preferred, `SUPABASE_REGION=ap-south-1`):
  same `findings` / `targets` / `fetch_log` tables (`supabase/schema.sql`).
- No passwords, sessions, cookies, DMs, follower/Saved/Liked data, or
  email/phone-to-account data — those flows do not exist and refused
  inputs are never stored (`server/tools.py:187-195`).
- Per-user keys (BYOK, proposed): operator keys are per-user secrets,
  never committed (`DUMMY_...` in repo), never logged; key storage design
  is a builder + counsel TODO.

## 4. Delete-on-request flow (Data Principal rights: correction + erasure)

Request: email the grievance contact (§6) with the handle / case ID /
URLs to erase (or correct). Target: completed within 30 days, confirmed by
reply (TODO: counsel to set SLA + identity verification + backup-purge
language).

```sql
-- 1. Erase findings + targets for the case:
DELETE FROM findings  WHERE case_id = '<USER-CASE-ID>';
DELETE FROM targets   WHERE case_id = '<USER-CASE-ID>';
-- 2. Drop cached fetch rows that could re-serve it:
DELETE FROM fetch_log WHERE target LIKE '%<user-handle>%';
-- Supabase: same statements; finding_embeddings rows cascade
-- (REFERENCES findings ON DELETE CASCADE) where the optional table exists.
-- 3. Verify (expect 0):
SELECT COUNT(*) FROM findings WHERE case_id = '<USER-CASE-ID>';
```

Correction path: same request channel; we correct the stored finding or
delete + refetch from the public source. The 24h cache TTL bounds
re-serving stale data by default; a deletion also suppresses re-fetch of
the erased target (operator blocklist — builder TODO in code).

## 5. 90-day retention (and purge)

```sql
-- sqlite:
DELETE FROM findings  WHERE created_at < datetime('now','-90 days');
DELETE FROM targets   WHERE created_at < datetime('now','-90 days');
DELETE FROM fetch_log WHERE created_at < datetime('now','-90 days');
-- Supabase (Postgres):
DELETE FROM findings  WHERE created_at < now() - interval '90 days';
DELETE FROM targets   WHERE created_at < now() - interval '90 days';
DELETE FROM fetch_log WHERE created_at < now() - interval '90 days';
```

- Demo fixtures may be re-seeded from `supabase/seed_fake.sql` on demand.
- TODO (ops + counsel before storing any user data): confirm Supabase
  point-in-time-recovery / backup retention window ≤ 90 days, RLS policy
  review, India-region (`ap-south-1`) project creation.

## 6. Grievance contact (placeholder)

- Demo: `demo@example.com` (same as `review/privacy.md`, `review/terms.md`,
  `review/support.md`). Security reports: same address, subject
  `[security]`; no public issues for suspected leaks.
- TODO before launch: name a Data Protection Officer / grievance officer
  with published response SLA, per the Act + Rules (counsel to draft).

## 7. What is NOT claimed

- No consent-management UI, no age-gating, no breach-notification
  playbook, no cross-border transfer memo, no governing-law/venue terms —
  all counsel TODOs, not half-builds (see `review/launch_checklist.md`).
- Entity lanes beyond the 4 registered adapters are proposed only
  (`docs/ENTITY.md` §6 blockers); this posture binds them when built,
  but no code enforces it yet.
