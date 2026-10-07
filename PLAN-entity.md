# Sherlock — Entity Pipeline Plan (PLAN-entity.md)

> Date: 2026-10-06. Status: Phase 0 DONE (224 tests green). This file is the build contract for Phases 1–5.
> Principles (non-negotiable): public sources only; no logins, no breach creds, no face-ID, no login/paywall bypass, no phone/address hunting; published contacts only (with source link); fake fixtures + DUMMY secrets; no network in tests (live smokes gated); verify 3x; honest logs; never hallucinate — refuse with reason.

## Journey summary

1. AskMe (Instagram saved-reel memory): share/paste + export backfill + transcript search. 173 tests green.
2. Sherlock v1: 30-site username probing + domain intel + correlation. Live-verified (octocat 9 hits). 102 tests.
3. The name problem: "Sanjay Kotabaghi" → zeros everywhere → real spelling KotabAGI (KLE Tech professor). Lesson baked into code as variant generation (ph/f, ee/i, doubling, order swap, ≤12 deterministic).
4. Entity pipeline: normalize → lane fan-out → homonym-split resolution. Dravya Shah live run: 6 ORCID IDs → 6 kept-separate clusters.
5. Scrapling review (85.9k★, BSD-3-Clause): adopt parser + polite spiders (`robots_txt_obey`); stealth/turnstile/proxy tiers EXCLUDED; pip dependency + attribution.
6. Architecture insight: plugin traffic exits OUR server, not user IPs. Hence **orchestrate, don't fetch** — model's search retrieves, our code judges. Server does polite known-URL reads; dashboard fetches client-side (reader.js, visitor IPs); local connector for power users.
7. Search without keys: DDG-polite default (paced, cached, per-user buckets); Brave BYOK for Google-quality; client-side search later. No keyless limitless Google exists — stated, not chased.
8. Enforcement: numbered playbook + refusing tools + invariant tests + golden runs.
9. Scope: all entities, all public pages, published contacts IN; breach/face-ID/login-bypass/phone-hunting OUT. Login-required, India (DPDP), free forever. Front doors: plugin + dashboard + local connector.

## Phase 1 — Skill-steered orchestration (CURRENT)

- Strict SKILL.md playbook: numbered steps (normalize → query set → fetch → correlate → present/refuse). Query sets literal (variants × `site:` operators).
- Findings-intake validation in correlate: score model-brought facts, refute low-evidence with reason codes, homonym-never-merge, anti-hallucination URL check.
- Golden-run fixtures: fixed input → full playbook → asserted case file. Invariant tests only (never exact live findings).
- Acceptance: scripted run completes on fixtures; full suite green 3x; verify.sh green; secrets clean.

## Phase 2 — Reader upgrade

- Scrapling parser in page_reader (pinned dep + attribution); contact-pattern extraction (published emails/phones/`mailto:`/`tel:` with source links); sitemap spider, robots-obey, polite throttle.
- Acceptance: KLE-Tech-shaped fixture yields title/role/email/links; politeness tests green.

## Phase 3 — Search lanes

- DDG-polite adapter (default, paced, cached, per-user buckets); Brave BYOK; GitHub lane upgrade (API-first users/repos/code).
- Acceptance: keyless entity queries return results; quota exhaustion degrades with reason.

## Phase 4 — Front doors

- Dashboard: wire reader.js live fetching + entity search UI. Plugin: skill + tools (live). Local connector localhost quickstart.
- Acceptance: same query works all three doors.

## Phase 5 — Launch hardening

- DPDP delete/export endpoints, per-user throttle proofs, load smoke, review packet, rename decision (Sherlock collision), video + lawyer flags.
- Acceptance: checklist all READY.

## Honest risks → mitigations

- Model nondeterminism → invariant tests + golden runs.
- SERP blocks at shared IP → DDG-polite + cache + client-side.
- Homonym merges → never-merge rule + split tests.
- Free-tier exhaustion → cache-first + BYOK + throttles.
