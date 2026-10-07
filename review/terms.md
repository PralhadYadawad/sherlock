# Terms of service — DEMO DRAFT (not legal advice)

> **TODO: lawyer review required before any public launch or store
> submission.** Demo build 0.1.0; fixtures only. Contact:
> `demo@example.com`.

## 1. The service

Sherlock (working title — rename pending, see AGENTS.md §9) is a
clean-room OSINT triage demo over **public sources only**: username
presence checks, domain intel, and public reel metadata. Instagram
Saved/Liked history has no endpoint and is not offered; login-gated,
session/cookie, password, and email/phone-to-account (PII) flows are
permanently excluded and refused.

## 2. Acceptable use

- Submit only public targets you have a right to research, or the demo
  fixtures (`@demo.sleuth`, `example.com`,
  `https://www.instagram.com/reel/DMYosint001/`).
- Do not submit credentials, sessions, cookies, private exports of
  others, or third-party personal data. Such inputs are refused, never
  stored.
- Do not scrape aggressively, circumvent rate limits, or violate
  source ToS/robots. Demo caps: 60 requests / 60 s, 1 MB bodies
  (`server/main.py`).

## 3. Demo data

All findings in v1 are fake fixtures for `DEMO-CASE-001` (10 findings,
3 lanes). Transcript content is a stub, honestly marked low
confidence. Do not rely on demo output for real investigations.

## 4. Storage, retention, deletion

Per-user cache as described in `review/privacy.md`: **90-day
retention**, **delete on request** via `demo@example.com`. No
guarantee demo data persists across resets.

## 5. No warranty; liability

Provided "as is", without warranty of any kind. To the maximum extent
permitted by law, liability is limited to the fees paid (demo: none).
(TODO: counsel to add governing law, venue, age, and IP/license terms
before launch.)
