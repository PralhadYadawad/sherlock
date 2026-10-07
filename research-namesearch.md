# Sherlock — Name Search Mapping (person by REAL NAME)

> Date: 2026-10-05 (UTC). Scope: `/home/markone/drive1/sherlock` only. RESEARCH grading memo — NOT a product spec.
> Constraints: AGENTS.md §0 + §8b apply. Public info only. Interface patterns only — no code copying.
> Never include session cookies, tokens, passwords, or bypass instructions. No PII of any real person anywhere in this file — all example identities are placeholders (`johndoe`, `Jane Q. Public`, `person@example.com`).
> Star/license/pushed_at numbers from `api.github.com` fetched 2026-10-05 unless noted. Stars are point-in-time; "activity" = `pushed_at`. Stale rule (per research-osint-2.md): `pushed_at` older than ~18mo → list but EXCLUDE.
> No contradiction to `research-osint.md` (seed, 2026-10-04) or `research-osint-2.md` (2026-10-04): username-presence pattern INCLUDE, email/phone/breach/biometric/login lanes EXCLUDE. This memo extends that line to name-anchored tools.
> Key finding up front: **almost nothing works from a bare real name alone.** Every tool below either needs a handle/email/photo as the true input (name is at best a hint), or is a commercial aggregator with homonym/accuracy limits. The honest product answer is: bare-name input → refuse or redirect to user-supplied handle/email/photo, never hallucinate an identity match.

## Method + freshness

- `websearch` for discovery (2026-10-05) + `curl api.github.com/repos/{o}/{repo}` for stars/license/pushed_at (2026-10-05).
- Commercial services (Webmii, Dehashed, IntelX, PimEyes, Epieos, HIBP) have no tool repo — numbers come from official pricing/docs pages + reputable press, fetched 2026-10-05.
- Legal/ToS risk grades used: **LOW** (public GET presence checks, own compute) / **MEDIUM** (scraping aggregators, password-reset differentials, stale-ToS services) / **HIGH** (breach-credential resale, biometric databases, login-gated session use).

---

## (a) Name→profile aggregators (search-engine scraping, social directory search)

| Tool / repo | Input it needs | Output it gives | Works from BARE NAME alone? | Stars / License / Activity (2026-10-05) | Price | Legal/ToS risk | Product-lane fit |
|---|---|---|---|---|---|---|---|
| `qeeqbox/social-analyzer` — https://github.com/qeeqbox/social-analyzer | **Username handle** (`--username johndoe`); optional Google/DuckDuckGo API keys for custom queries | Per-site profile hits (1000+ sites) with 0–100 rating, metadata/patterns, screenshots, name-origin/similarity analysis | **NO.** Name analysis = permutations/similarity of a *handle*; it does not resolve "Jane Q. Public" → profiles. | 24,197 ★ / **AGPL-3.0** / pushed 2026-01-12 — ACTIVE | Free (open source) | MEDIUM (1000-site sweeps = rate-limit/abuse surface; AGPL network-copyleft) | **EXCLUDE from core.** AGPL-3.0 → NEVER copy/combine (AGENTS.md §0.3 spirit). Interface note only. |
| `antoniaci/blackbird` (moved from `p1ngul1n0/blackbird`; old URL 301-redirects) — https://github.com/antoniaci/blackbird | **Username handle(s)** (`--username`) and/or **email** (`--email`); optional AI profiling (`--ai`, site-names-only) | Account presence across 600+ platforms (WMN data), PDF/CSV export, behavioral profile | **NO (username mode). Email mode needs the email, not a name.** No real-name resolution path. | 8,909 ★ / **NO LICENSE FILE (null)** / pushed 2025-07-13 — BORDERLINE (~15mo, maintenance-only, no releases) | Free (open source, no license file → all rights reserved by default) | LOW (username probes) / MEDIUM (email mode = PII) | **Username mode = interface-only study; email mode = EXCLUDE** (email-to-account PII, AGENTS.md §0.2). Copy NOTHING (no license). |
| Webmii (webmii.com — commercial people-search mashup) | **First + last name** (+ optional keywords to filter homonyms). One of the few that *accepts* a bare name. | Aggregated public web mentions, social-profile links, images, "visibility score" per person | **PARTIALLY — accepts bare name, but homonym-limited.** App reviews report unrelated people / missing target; score is visibility, not identity proof. | n/a (proprietary service + paid iOS app; co. founded 2009 per corp listings) / proprietary | Paid app (~$2.99–$3.99 one-time, App Store; price varies by region) + free web search | MEDIUM (scrapes/repacks third-party sites; shows sources per query; accuracy/homonym risk) | **EXCLUDE as adapter** (external commercial service, no free-tier public API, scraping-ToS surface). Pattern note only: name→candidate-links + per-source attribution + visibility-score shape. |

---

## (b) Email-anchored (email in, public profile bits out)

All tools in this lane need an **email address**, not a name. A bare real name is useless here unless already bridged to an email by other means. **Entire lane EXCLUDED from product** per AGENTS.md §0.2 (email-to-account PII) + §8b (email/phone PII lanes PERMANENTLY OUT). Listed to exclude, with reason. No flow details reproduced.

| Tool / repo | Input | Output | Bare name? | Stars / License / Activity (2026-10-05) | Price | Legal/ToS risk | Fit |
|---|---|---|---|---|---|---|---|
| `mxrch/GHunt` — https://github.com/mxrch/GHunt | **Email address** (or Gaia ID / Drive link); requires operator Google cookies via Companion extension (`ghunt login`) | Google-side dossier: display name, Gaia ID, profile photo, Workspace-vs-consumer, active services, public Maps reviews, public Calendar, YouTube channel | **NO — and login-gated.** Needs the email AND the operator's own Google session. | 19,659 ★ / NOASSERTION (non-standard) / pushed 2026-04-10 — ACTIVE | Free (open source) | HIGH (session/cookie-gated + Google-account PII; Google ToS surface) | **EXCLUDE** (login-gated + PII, AGENTS.md §0.2). |
| `megadose/holehe` — https://github.com/megadose/holehe | **Email address** (`holehe person@example.com`) | Registered-or-not across 120+ sites via signup/forgot-password differentials (+ occasional obfuscated recovery hints); alert-free by design | **NO.** | 15,086 ★ / **GPL-3.0** / pushed 2024-09-10 — **STALE (>12mo, ~25mo)** | Free (open source) | MEDIUM-HIGH (password-reset-flow probing + email-to-account PII; most modules reportedly broken — stale) | **EXCLUDE (triple reason)**: GPL-3.0 + PII lane + stale. |
| Epieos (epieos.com — commercial SaaS; GitHub org holds no tool repo) | **Email or phone number** | Linked social accounts, Google profile data, carrier info, HIBP-linked breach hints; watermarked free results | **NO.** | n/a (private co., Paris; active 2026; Maltego hub listing, LE/law-enforcement clientele claimed) / proprietary, account-gated | Freemium: free Member tier (Google + Email Checker + Skype only, heavy watermark) → Osinter **€29.99/mo (30 full-access req/mo)** → Custom/LEA-Private (API, 560+ platforms) | MEDIUM (proprietary PII aggregation; phone/email-to-account) | **EXCLUDE** (login-gated SaaS + PII, AGENTS.md §0.2). |
| HIBP API v3 (haveibeenpwned.com — service, not a repo) | **Email address** (or owned-domain) + `hibp-api-key` header | Breach names/dates/data-classes per account; domain search (ownership-verified); stealer-log endpoints (Pro); free public catalog (`/breaches`, `/dataClasses`); free k-anonymity Pwned-Passwords range API | **NO.** | n/a (service) / docs CC BY; API commercial | Core from **~$4.39/mo annual** (Core 1, 1 domain) → Pro/High-RPM tiers (stealer logs, up to 24k RPM); Pwned-Passwords range API free, no key | LOW *if* own verified domain + paid key; third-party email lookup = PII | **EXCLUDE live breach lookup from v1** (key requirement + breach-password data OUT per §8b); adopt k-anonymity range-query shape + failure taxonomy as interface pattern only. |

---

## (c) Breached-data name search (commercial, credential-data handling)

| Service | Input | Output | Bare name? | Activity / license | Price (2026-10-05 pages) | Legal/ToS risk | Fit |
|---|---|---|---|---|---|---|---|
| Dehashed (dehashed.com) | Email / username / IP / **name** / phone / VIN / domain via single search bar + regex operators; API key for programmatic | Raw breach rows (incl. credential material), monitoring, WHOIS/history | **EFFECTIVELY NO.** A `name` operator exists, but breach rows are keyed by email/username — a bare common name returns homonym soup or nothing; it is not identity resolution. | Active service 2026 (v4.x changelog; claims ~13–24B records, 24k data wells — vendor figures, unverified) / proprietary, account-gated | **Paid only, no free tier.** Tiers shown as Enthusiast/Monthly/Annual (prices N/A on current page — quote/rotating) + Search API pay-per-query (homepage claims "from $0.02"; third-party trackers describe credit-based paid). Verify on product page before citing a number. | **HIGH.** Resells/handles stolen credential data; operator AUP + regional computer-abuse / data-protection exposure; breach-password data is OUT per §8b regardless. | **EXCLUDE.** |
| Intelligence X / IntelX (intelx.io) | Email / domain / IP / Bitcoin / **Person tab** (meta-search that fans out to third-party people-search links incl. Spokeo-type vendors) + Phonebook (domains/emails/URLs) | Indexed leaks/pastes/darknet records, tree-view relations, export (CSV/ZIP caps); Identity portal (Leaks API) for stealer-log reverse lookup | **EFFECTIVELY NO.** No indexed real-name identity; Person tab = outbound links to other vendors, not a dossier. | Active service 2026 (Search API + Leaks API docs live; free vs paid instances `free.intelx.io` / `2.intelx.io`; third-party API license required for product integration) / proprietary | Freemium (capped results/timeouts) → paid Researcher/API/Identity/Enterprise licenses (tiered; exact current list price not captured in this fetch — check product page; 2023-era promos are stale, do not cite). | **HIGH** for leak/stealer content (same credential-data rule as Dehashed); MEDIUM for plain web-archive search | **EXCLUDE.** (Breach/leak content OUT per §8b; commercial key requirement.) |

---

## (d) Image-anchored (face search — commercial/biometric)

| Service | Input | Output | Bare name? | Price | Legal/ToS risk | Fit |
|---|---|---|---|---|---|---|
| PimEyes (pimeyes.com) | **Face photo upload** (not a name, not a handle) | Grid of web photos judged same-face + source URLs; Alerts/monitoring; takedown/DMCA-GDPR workflow; opt-out form | **NO — needs a face, and a name alone can never start a search.** | Commercial tiers: Open Plus / PROtect / Advanced (paid; NYT 2022 cited $29.99/mo historically — current list price not captured in this fetch, check pricing page; free search shows blurred/limited results). | **HIGH RISK — likely unlawful in many regions.** Biometric identification on a ~900M-image private database: EU Parliament written question E-002586/2022 (GDPR/fundamental-rights challenge), GDPR + Illinois BIPA exposure, documented stalker/harassment misuse surface (incl. porn-site false matches reported by NYT testing 2022-05-26). Vendor claims GDPR compliance + opt-out + monitoring; regulators and press remain adversarial. | **EXCLUDE — permanently.** Biometric PII + prohibited-data-category risk; no product lane ever (AGENTS.md §0.2 PII exclusion; §8 public-only). Research note only. |

---

## (e) Username-to-name bridges (handle in, display-name out)

These run the Sherlock direction in reverse leverage: they take a **handle** (which Sherlock already probes) and extract the human name the profile itself publishes. They do NOT take a bare name.

| Tool / repo | Input | Output (bridge fields) | Bare name? | Stars / License / Activity (2026-10-05) | Price | Legal/ToS risk | Fit |
|---|---|---|---|---|---|---|---|
| `soxoj/maigret` — https://github.com/soxoj/maigret | **Username** (`maigret johndoe`; multi-username, tags, Tor/I2P, cookies flags) | "Dossier": per-site presence (3k–6k sites claimed; auto-updated site DB) + **extracted profile fields — display name / reported full name, bio, photo links, linked usernames/IDs** — recursive pivoting, PDF/HTML/XMind reports | **NO as input — but YES as output: it is the bridge.** Feed it a handle, read back candidate real names with per-site provenance. | 38,293 ★ / **MIT** / pushed 2026-10-04 — VERY ACTIVE | Free (open source) | LOW for public-profile field extraction (public GETs); CAUTION on aggressive flags (session-file import option, block-bypass claims — NOT adopted) | **INCLUDE as interface pattern** (username → display-name extraction with per-site source + confidence; recursive-pivot shape). Reimplement clean-room (MIT, ours); never vendor site DB wholesale at v1 scale. Maps directly onto Sherlock `username_probe` enrichment. |
| `WebBreacher/WhatsMyName` — https://github.com/WebBreacher/WhatsMyName | **Username** (dataset consumed by checkers: `wmn-data.json` `{uri_check, e_code/e_string, m_code/m_string}`) | Presence hits per site (700+ sites); downstream tools surface the profile URL, from which display names are read | **NO (input); enables the bridge** (presence → profile page → published name). | 2,921 ★ / **CC BY-SA 4.0** (`LICENSE.md`; API reports NOASSERTION — README reality governs) / pushed 2026-09-16 — ACTIVE | Free (dataset) | LOW (public presence probes + rate-limit discipline) | **INCLUDE as data-shape pattern only.** Do NOT vendor `wmn-data.json` wholesale (share-alike); ship own tiny fixture list (MIT, ours). Same decision as research-osint-2.md — no change. |

---

## Cross-category verdict: the bare-name question

| Question | Answer |
|---|---|
| Does anything reputable resolve bare "First Last" → verified profiles? | **No open-source tool does.** Only commercial mashups (Webmii-pattern) accept a bare name, with homonym/accuracy limits and no identity proof. |
| Closest lawful open-source approximation? | **Two-hop bridge, both hops handle-anchored:** (1) user supplies handle(s) → Maigret/WMN-pattern presence + display-name extraction; (2) search-engine lookup on *extracted* display names only as corroboration, never as identification. Bare-name-first flow must refuse or request a handle. |
| Email/phone/breach/biometric shortcuts? | All need a non-name anchor AND are **permanently excluded from product** (AGENTS.md §0.2, §8b). Grading-only knowledge. |
| What fits Sherlock's public-only product lane? | **INCLUDE (pattern only):** Maigret dossier-field shape, WMN presence-check shape, Webmii-style per-source attribution + visibility-score shape. **EXCLUDE everything else** in this memo (AGPL/GPL/no-license code, login-gated GHunt, PII email/phone lanes, breach-credential stores, biometric search). |

---

## Dated sources

| # | Source | Fetched | What it substantiates |
|---|---|---|---|
| 1 | `api.github.com/repos/qeeqbox/social-analyzer` — 24,197 ★, AGPL-3.0, pushed 2026-01-12 | 2026-10-05 | (a) social-analyzer row |
| 2 | `api.github.com/repositories/489384246` (redirect target `antoniaci/blackbird`, ex-`p1ngul1n0`) — 8,909 ★, license null, pushed 2025-07-13 | 2026-10-05 | (a) Blackbird row; owner-move verified via 301 |
| 3 | `api.github.com/repos/soxoj/maigret` — 38,293 ★, MIT, pushed 2026-10-04 | 2026-10-05 | (e) Maigret row |
| 4 | `api.github.com/repos/megadose/holehe` — 15,086 ★, GPL-3.0, pushed 2024-09-10 | 2026-10-05 | (b) Holehe row (stale) |
| 5 | `api.github.com/repos/mxrch/GHunt` — 19,659 ★, license NOASSERTION, pushed 2026-04-10 | 2026-10-05 | (b) GHunt row |
| 6 | `api.github.com/repos/WebBreacher/WhatsMyName` — 2,921 ★, license NOASSERTION (repo LICENSE.md = CC BY-SA 4.0), pushed 2026-09-16 | 2026-10-05 | (e) WMN row |
| 7 | `api.github.com/repos/sherlock-project/sherlock` — 93,239 ★, MIT, pushed 2026-10-04 (name-collision reference) | 2026-10-05 | Name-flag context (AGENTS.md §0) |
| 8 | webmii.com/about + App Store listing (Webmii, dev Mathieu Morgensztern, paid app, visibility score, homonym keywords) | 2026-10-05 | (a) Webmii row |
| 9 | dehashed.com + dehashed.com/search + dehashed.com/api (v4.x, search operators incl. name, credit/subscription model, API pay-per-query) | 2026-10-05 | (c) Dehashed row |
| 10 | intelx.io + help.intelx.io/api + /api/limits (Search vs Leaks API, free/paid instances, Person/Phonebook tools, export caps) | 2026-10-05 | (c) IntelX row |
| 11 | pimeyes.com/en (+/pricing, /about, /privacy-policy) — tiers Open Plus/PROtect/Advanced, opt-out, face-fingerprint index claims | 2026-10-05 | (d) PimEyes row |
| 12 | europarl.europa.eu E-002586/2022 (PimEyes fundamental-rights question) + NYT 2022-05-26 ("A Face Search Engine Anyone Can Use Is Alarmingly Accurate") | 2026-10-05 (docs dated 2022; retrieved 2026-10-05) | (d) HIGH-RISK substantiation |
| 13 | epieos.com + epieos.com/pricing (Member free / Osinter €29.99-mo-30-req / Custom-Private) + tools.osintnewsletter.com epieos brief | 2026-10-05 | (b) Epieos row |
| 14 | haveibeenpwned.com/Subscription + /API/v3 (Core from ~$4.39/mo annual; Pro/High-RPM; Pwned-Passwords k-anonymity free) | 2026-10-05 | (b) HIBP row |
| 15 | `research-osint.md` (seed 2026-10-04) + `research-osint-2.md` (2026-10-04) — lane decisions (username INCLUDE-pattern / email-phone-breach-biometric-login EXCLUDE) | read 2026-10-05 | No-contradiction check — consistent |

*Verification: 2× pass logged in `research-namesearch.VERIFY.log` (2026-10-05). No secrets, no bypass instructions, no real-person PII in this file.*
