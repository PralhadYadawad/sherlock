# Privacy policy — DEMO DRAFT (not legal advice)

> **TODO: lawyer review required before any public launch or store
> submission.** This draft covers the v1 demo only (fake fixtures +
> user-pasted public links). Dummy contact: `demo@example.com`.

## 1. What we store (per-user)

- Triaged targets the user explicitly submits (`@demo.*` handles,
  `example.com`-scoped domains, user-pasted public reel URLs).
- Derived public findings (presence, subdomain, contact, author,
  caption, transcript links) with `source` + `confidence`, cached per
  case (`DEMO-CASE-001` in the demo).
- Operational `fetch_log` rows (adapter, target, status, reason,
  timestamp) for debugging and rate-limit accounting.
- No passwords, sessions, cookies, DMs, follower lists, Saved/Liked
  history, or email/phone-to-account data — those flows do not exist
  and are refused.

## 2. Where it lives

- Demo default: local sqlite fallback (`SHERLOCK_DB`, git-ignored).
- Optional Supabase cache (India region preferred,
  `SUPABASE_REGION=ap-south-1`): same `findings` / `targets` /
  `fetch_log` tables (`supabase/schema.sql`). No live keys in the repo
  (`DUMMY_...` only).

## 3. Retention

- **90-day retention:** cached findings and logs older than 90 days are
  purged (`created_at < now() - 90 days`). Demo fixtures may be
  re-seeded from `supabase/seed_fake.sql` on demand.
- Supabase point-in-time backups: confirm retention window with ops /
  counsel before storing any user data (TODO).

## 4. Delete on request

Email `demo@example.com` with the handle/case to erase. We run:

```sql
DELETE FROM findings  WHERE case_id = '<USER-CASE-ID>';
DELETE FROM targets   WHERE case_id = '<USER-CASE-ID>';
DELETE FROM fetch_log WHERE target LIKE '%<user-handle>%';
```

and confirm `SELECT COUNT(*) ...` returns 0. Target: completed within
30 days, confirmed by reply. (TODO: counsel to set SLA + identity
verification + backup-purge language.)

## 5. Sharing

No sale, no ads, no third-party enrichment. Live adapter fetches (if
ever enabled) go only to the public endpoints documented per adapter
(crt.sh-style logs, public profile pages, no-auth metadata) and honor
their ToS/rate limits.
