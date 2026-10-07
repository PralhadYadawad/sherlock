# Sherlock — Scraping Engine Research (client-side page-reader + server fallback)

> Date: 2026-10-05 (UTC). Scope: `/home/markone/drive1/sherlock` only.
> Extends `research-osint.md` (seed, 2026-10-04) + `research-osint-2.md` (expand, 2026-10-04) — does not redo them. No contradiction found.
> Constraints: AGENTS.md §0 + §8b apply. Public sources only. No logins, no session/cookie flows, no PII lanes, no password flows. Interface patterns only — no code copying (GPL/AGPL code NEVER copied into core; permissive libs reimplemented or used as unmodified dependencies only, none vendored for v1).
> This file names anti-bot *capabilities at feature level only* (e.g. "advertises challenge-handling") to grade product risk. It contains NO bypass instructions, NO session/cookie/token material, NO secrets.
> All star/license/pushed_at numbers from `api.github.com/repos/{owner}/{repo}` fetched 2026-10-05 unless noted. Stars are point-in-time; "activity" = `pushed_at`.

## Method + freshness

- `webfetch https://api.github.com/repos/{o}/{r}` for stars/license/pushed_at on 2026-10-05 (pass 1), re-fetched key repos same day (pass 2 — numbers stable, see `research-engine.VERIFY.log`).
- `websearch` + official docs (`scrapling.readthedocs.io`, `docs.firecrawl.dev`, `docs.crawl4ai.com`, `seleniumbase.io`, `maxun.dev`, PyPI pages) for: what it renders/fetches, anti-block posture, open-core vs hosted split, pricing.
- Posture grading (honest): **polite** = plain HTTP/browser fetch + robots respect + throttling, no fingerprint spoofing, no challenge-solving; **evasion-grade** = advertises fingerprint spoofing / challenge-solving / driver-patching / CAPTCHA handling. Evasion-grade = flagged **RISKY for product use** (ToS + account/IP-ban + breakage risk), regardless of license.
- Product lane for this file: **RESEARCH grading** — client-side page-reader (user already viewing the page; extract from own DOM, zero extra traffic) + polite server fallback (single public-GET, cached). Bulk crawling, login-gated extraction, and PII lanes stay out per AGENTS.md §0/§8b.

---

## 1. d4vinci/Scrapling — https://github.com/D4Vinci/Scrapling

- Stars / license / activity (API, 2026-10-05, verified 2x): **~85,716 stars, BSD-3-Clause, pushed 2026-10-04 — VERY ACTIVE** (created 2024-10; v0.4.6-era release notes cite stealth/privacy work; v0.4 introduced async Spider framework).
- What it renders/fetches: three fetcher tiers returning one unified `Response`/selector object — (a) static HTTP fetcher with browser-impersonation claims (TLS fingerprint + HTTP/2/3, auto headers); (b) dynamic browser fetcher (Playwright/Chromium automation, JS execution, resource blocking, network-idle/DOM waits); (c) stealth browser fetcher (patched-CDP engine + advertised anti-detection options). Plus: Scrapy-like async Spider API (concurrency limits, per-domain throttling, pause/resume checkpoints, proxy rotation, blocked-request detection, AutoThrottle), adaptive parser (element relocation after page changes), ad/domain blocking, proxy rotation, MCP server + CLI.
- JS rendering: **yes** — browser fetchers drive real Chromium (headed/headless), JS execution + waits + interception.
- Anti-block posture: **DUAL — polite subset + evasion-grade subset.** Polite side: optional `robots_txt_obey` flag (respects Disallow/Crawl-delay/Request-rate, per-domain cache), AutoThrottle/backoff on blocking signals, per-domain delays. Evasion side (flagged): stealth fetcher advertises fingerprint masking + automated challenge-handling for protected sites. Product rule: polite subset is gradeable; stealth/challenge-handling subset is **RISKY — excluded from product use**.
- License: **BSD-3-Clause (permissive)** — license-compatible, but per clean-room rule we adopt interface patterns only (fetcher-tier shape, unified Response, AutoThrottle/robots-flag discipline), never vendor code for v1.
- Activity 2026: very active (push 2026-10-04, open issues only ~14, Discord + docs site live).
- Breakage profile: browser-engine drift (Chromium/Playwright/patchright version skew), protected-site arms race (stealth features break silently when WAFs change), proxy cost. Static-fetcher tier is the stable part.
- Client vs server fit: **server only** (Python lib, needs browser binaries + infra). Not a client-side (browser/WASM/JS) candidate.
- Free-forever verdict: **free-forever as software** (BSD-3, self-hosted, own compute). Real cost = proxies + browser infra at scale.
- ToS notes: polite mode (robots obey + throttle + single-fetch + cache) = LOW on cooperative/public pages. Stealth/challenge-handling mode = **RISKY** (against site ToS, ban/IP risk, AGENTS.md §8 bulk-scraping out-of-scope). Login/session features excluded per §0.2.

## 2. Playwright (`microsoft/playwright` + `microsoft/playwright-python`) — https://github.com/microsoft/playwright

- Stars / license / activity (API, 2026-10-05): **core ~97,098 stars, Apache-2.0, pushed 2026-10-03 — VERY ACTIVE**; Python binding **~15,027 stars, Apache-2.0, pushed 2026-09-24 — VERY ACTIVE**.
- What it renders/fetches: full browser automation (Chromium + Firefox + WebKit), real JS execution, multi-context isolation, request interception, screenshots/PDF, codegen, sync+async APIs. The *reference* renderer everything else in this file builds on.
- JS rendering: **yes — best-in-class** (three engines, real user-grade rendering).
- Anti-block posture: **polite by default (honest: detectable).** Stock Playwright exposes automation tells (driver process, well-known handshake/fingerprint signals); stealth requires third-party patches/plugins (community `playwright-stealth` unmaintained since ~2025; successor shims exist but are arms-race code). 2026 benchmarks consistently show stock Playwright blocked more than direct-CDP or patched-Chromium stacks on protected targets. For product use this detectability is a *feature*: it keeps us on cooperative pages.
- License: **Apache-2.0 (permissive)** — compatible; standard dependency, nothing vendored.
- Activity 2026: very active (monthly releases; Sept 2026-era 1.63.x line per third-party tables).
- Breakage profile: browser-binary drift (pin versions; `playwright install` coupling), headless-vs-headed fingerprint differences, WAF rule changes. Mature API = low API-breakage.
- Client vs server fit: **server fallback renderer** (needs browser binaries; heavy for edge/client). Not client-side JS (it *drives* browsers, it doesn't run *in* the page).
- Free-forever verdict: **free-forever as software** (Apache-2.0, own infra). Cost = compute (RAM/CPU per browser context) at scale.
- ToS notes: polite automation (own/cooperative pages, robots, throttle, cache, no stealth plugins, no CAPTCHA-solving) = LOW. Adding stealth plugins or pointing it at protected third-party sites = **RISKY** (ToS + ban risk). Recommended product posture: stock Playwright, headed-or-headless per target tolerance, stealth plugins permanently excluded.

## 3. Crawl4AI (`unclecode/crawl4ai`) — https://github.com/unclecode/crawl4ai

- Stars / license / activity (API, 2026-10-05): **~84,764 stars, Apache-2.0, pushed 2026-09-25 — VERY ACTIVE** (PyPI `crawl4ai` 0.8.0 Jan 2026 → 0.9.x security releases 2026; Docker + `crawl4ai-setup`/`crawl4ai-doctor` tooling).
- What it renders/fetches: Playwright-backed async crawler returning **LLM-ready Markdown** (raw + heuristic "fit" filtering, citations/references), structured extraction (CSS/JSON + LLM-driven with chunking/BM25), deep-crawl strategies, crash-recovery/resume, CLI (`crwl`), Docker deployment. Ships a stealth-mode flag; Cloud API in closed beta (one-key hosted path).
- JS rendering: **yes** (inherits Playwright; `crawl4ai-setup` installs Chromium).
- Anti-block posture: **polite-leaning with an evasion option.** Default posture is cooperative crawling + content shaping; the advertised stealth flag + hosted-cloud proxy path push protected-site work off to infrastructure we don't control. Product rule: polite local mode is gradeable; stealth flag / cloud-proxy path = **excluded (RISKY + cost)**.
- License: **Apache-2.0 (permissive)** — compatible; still interface-patterns-only for v1 (no vendoring).
- Activity 2026: very active (229 open issues = large tail, but releases steady through Sept 2026).
- Breakage profile: heavy dependency stack (Playwright + extraction + optional LLM), config surface large, LLM-extraction cost/latency, cloud-beta API drift. Markdown-shaping ideas are the durable part.
- Client vs server fit: **server only** (Python + browser + Docker weight). Not client-side.
- Free-forever verdict: **free-forever as software** (Apache-2.0 self-host); LLM extraction + hosted Cloud = metered, not free.
- ToS notes: polite local crawls of cooperative pages (robots, throttle, cache) = LOW. Stealth-flag + bulk deep-crawl of third-party sites = **RISKY** (rate/ToS surface; AGENTS.md §8 excludes bulk). Adopt the *output shape* (`markdown` / `fit_markdown` / citations), not the crawl-at-scale posture.

## 4. Firecrawl (`firecrawl/firecrawl`) — https://github.com/firecrawl/firecrawl

- Stars / license / activity (API, 2026-10-05, verified 2x): **~188,667 stars, AGPL-3.0, pushed 2026-10-04 — VERY ACTIVE** (525 open issues; SDKs partly MIT per repo note, core AGPL-3.0).
- Open-core? **Yes — confirmed open-core.** Own docs (`docs.firecrawl.dev/contributing/open-source-or-cloud`, fetched 2026-10-05): OSS stack covers core scrape/crawl/map/search APIs; **managed proxy/anti-bot layer ("Fire-engine"), screenshots, page actions, Agent, Browser, Interact, dashboards, enterprise controls are Cloud/hosted-only.** Self-host = bring own proxies, handle blocked sites yourself, own auth/TLS/persistence/upgrades.
- Pricing (official pricing page, effective 2026-09-04, fetched 2026-10-05): **Free 1,000 credits/mo (no card; ~1,000 pages)**; Hobby $19/mo ($16 annual, 5K credits); Standard $99/mo ($83 annual, 100K); Growth $399/mo ($333 annual, 500K); Scale $749/mo ($599 annual, 1M); pay-as-you-go $5 increments on paid plans only; scrape/crawl/map ≈ 1 credit/page (+4 for JSON/structured formats), search 2 credits/10 results, Interact 2 credits/browser-minute.
- What it renders/fetches: hosted-or-self-hosted scrape→Markdown/structured-data API (search, scrape, crawl, map, monitor), LLM-backed extraction formats.
- JS rendering: **yes** (managed browsers on Cloud; Playwright-class processing in default OSS stack).
- Anti-block posture: **evasion-as-a-service on Cloud** (managed proxies + anti-bot layer), **polite-only when self-hosted without that layer**. Product read: Cloud path = ToS-pass-through (vendor scrapes on our behalf) + recurring cost; self-host path = cooperative-sites-only + ops burden.
- License: **AGPL-3.0 (strong copyleft, network-triggered)** — NEVER combined into core per AGENTS.md §0.3 spirit (stricter than GPL). API-call integration is license-clean but still excluded for v1 (cost + ToS-pass-through).
- Activity 2026: very active (push 2026-10-04, 2.5M+ weekly npm/PyPI downloads claimed).
- Breakage profile: credit-model drift, Cloud-only feature skew (self-host lags hosted), plan/limit changes.
- Client vs server fit: **server-side SaaS** (or heavy self-host). Not client-side.
- Free-forever verdict: **NOT free-forever** — 1K pages/mo free tier only; any real use is metered. Self-host is license-free but ops-expensive and anti-bot-less.
- ToS notes: Cloud scraping of third-party sites = **MEDIUM** (vendor manages fingerprints, but ToS risk passes through + per-unit cost; cache everything). Excluded from v1 bundle (commercial + AGPL + §8 bulk out-of-scope). Interface reference only (credit-per-page discipline, Markdown/JSON output shape).

## 5. Maxun (`getmaxun/maxun`) — https://github.com/getmaxun/maxun

- Stars / license / activity (API, 2026-10-05): **~17,656 stars, AGPL-3.0, pushed 2026-10-02 — VERY ACTIVE** (default branch `develop`; 105 open issues).
- What it renders/fetches: no-code web-data platform — recorder mode (browse → reusable extraction robot), AI/natural-language extraction, full-page scrape (Markdown/HTML/screenshots/summary), multi-page crawl, web search robots, scheduling/monitoring, website-to-API/Spreadsheet, docs/PDF parsing, SDK + CLI + MCP + REST.
- JS rendering: **yes** (Playwright Chromium under the hood; `npx playwright install --with-deps chromium` in setup).
- Anti-block posture: **mixed — polite infra + evasion + login features.** Advertises proxy rotation + fingerprinting ("stealth mode") and **behind-login extraction** — both flagged: stealth = **RISKY**, behind-login = **PERMANENTLY EXCLUDED** per AGENTS.md §0.2 (login/session/cookie tools). Self-host needs Postgres + Redis + MinIO + Node (heavy).
- License: **AGPL-3.0** — NEVER in core (same rule as Firecrawl).
- Activity 2026: active (push 2026-10-02; CLI + skills added Mar 2026).
- Breakage profile: full-stack ops (DB/queue/object-store/browser), recorder brittleness on layout change (auto-recovery claimed), hosted-credit coupling (`maxun status`/`credits` in CLI).
- Client vs server fit: **server platform** (self-host stack or hosted app). Not client-side.
- Free-forever verdict: **software is license-free (AGPL) but NOT free-forever in practice** — hosted = credits/plan; self-host = real infra + LLM-provider cost.
- ToS notes: behind-login + stealth-proxy posture = **RISKY/EXCLUDED** for product. No-code recorder UX is the only pattern worth studying (action-record → reusable robot), reimplemented in our own words if ever needed. Listed mostly to exclude.

## 6. gallery-dl / yt-dlp — DELTA only (seed §c stands)

- Seed decisions stand (public-URL-only download → local ASR path; cookie/login modes permanently excluded). Freshness re-check (API, 2026-10-05): **`yt-dlp/yt-dlp` ~195,594 stars, Unlicense, pushed 2026-09-27 — VERY ACTIVE** (was 195,490 on 2026-10-04); **`mikf/gallery-dl` ~19,946 stars, GPL-2.0, pushed 2026-10-03 — VERY ACTIVE** (was 19,943 on 2026-10-04).
- Delta vs seed: no new capability for the page-reader lane (both are media/download tools, not article readers). yt-dlp open-issue tail (~2.7K) and gallery-dl (~1K) confirm continued extractor-churn breakage — reinforces seed rule: metadata-only reads + per-URL cache + clean FAIL taxonomy.
- License reminder: gallery-dl **GPL-2.0** = never in core (subprocess-separate at most, none for v1); yt-dlp **Unlicense** = permissive, pattern-adoptable (`--dump-json` field discipline).
- Fit: **server-side media lane only**. Not page-reader engines. No change to recommendation.

## 7. Undetected drivers: nodriver + SeleniumBase-type (`ultrafunkamsterdam/nodriver`, `seleniumbase/SeleniumBase`)

- `ultrafunkamsterdam/nodriver` (API, 2026-10-05): **~4,804 stars, AGPL-3.0, pushed 2026-05-13 — ~5mo gap (BORDERLINE/stale-leaning).** Successor of `undetected-chromedriver` (same author); direct-CDP async Python, no Selenium/chromedriver binary. Advertises resistance to named WAF/anti-bot systems. Independent May 2026 benchmark (31 Cloudflare-gated targets × 7 tools) scored it best (28 OK / 0 blocked) — but Sept 2026 third-party teardown documents unmaintained defects (headless UA leak, no test suite/CI, single maintainer, closed tracker) and recommends the community `zendriver` fork (AGPL-3.0, Sept 2026 fixes) for new Chromium-only work. Neither tool hides IP or machine fingerprint — driver-layer only.
- `seleniumbase/SeleniumBase` (API, 2026-10-05): **~13,051 stars, MIT, pushed 2026-10-02 — VERY ACTIVE** (4.54.x Sept 2026 line). Full automation framework; UC Mode (patched-driver stealth) superseded by **CDP Mode** (direct-CDP control, CAPTCHA-handling helpers, "Stealthy Playwright" bridge, recorder, MCP server).
- Anti-block posture: **both evasion-grade by design** (driver patching / CDP-disconnect tricks / CAPTCHA-handling helpers). **Flagged RISKY for product use — excluded from product lanes** (ToS, ban risk, AGENTS.md §0.2 bypass-instruction ban, §8 bulk out-of-scope). SeleniumBase's *non-stealth* framework patterns (recorder, syntax formats, dashboard) are the only gradeable part, and only as UX reference.
- License split matters: **nodriver AGPL-3.0 = never in core**; **SeleniumBase MIT = license-clean but evasion modes still excluded on ToS grounds** (license ≠ permission to evade).
- Breakage profile: worst in this file — every browser/WAF update can silently re-detect them; pinned-version discipline required; nodriver's 5-month push gap + unmerged-fix reports = do-not-found-on.
- Client vs server fit: **server only** (drive installed Chrome). Not client-side.
- Free-forever verdict: free-forever as software; operationally expensive (proxies, profile/CAPTCHA ops, maintenance churn).
- ToS notes: **RISKY — listed to exclude.** No bypass instructions reproduced in this file (feature names only, per research-lane rule).

## 8. Readability / extraction libs: trafilatura, Mozilla Readability, python-readability

- `adbar/trafilatura` (API, 2026-10-05): **~6,909 stars, Apache-2.0, pushed 2026-10-02 — VERY ACTIVE.** Python + CLI: boilerplate removal / main-text + metadata (title/author/date/site) + comments extraction, outputs TXT/Markdown/CSV/JSON/XML/TEI, sitemap/feed + URL-queue support with **politeness rules**, language detection, `readability`+`jusText` fallbacks. Independent benchmarks repeatedly top-ranked on F-score (~0.90–0.91) vs readability-lxml (~0.80–0.82), news-please, newspaper3k.
- `mozilla/readability` (API, 2026-10-05): **~11,480 stars, Apache-2.0, pushed 2026-08-04 — ACTIVE (~2mo).** The Firefox Reader-Mode core as a **standalone JS library** — DOM-in/article-out, no network of its own.
- `buriy/python-readability` (API, 2026-10-05): **~2,897 stars, Apache-2.0, pushed 2026-08-27 — ACTIVE.** Python port tracking readability.js (a.k.a. `readability-lxml` in benchmarks).
- What they render/fetch: **nothing — extraction only.** They take already-fetched HTML/DOM and return clean article text. No JS rendering, no network, no anti-bot surface at all.
- Anti-block posture: **polite by construction** (trafilatura's crawler helpers document politeness; the extractors themselves emit zero traffic). Cleanest ToS posture in this file.
- Breakage profile: lowest — pure parsing, no browser, no WAF interaction. Failure mode is *quality* degradation on unusual layouts (JS-shell pages with no server-rendered text), handled by clean empty-with-reason.
- Client vs server fit: **the split answer — Mozilla Readability = CLIENT-SIDE pick (runs in-page/WASM/bundled JS on the user's own DOM); trafilatura / readability-lxml = SERVER fallback pick (extract over politely-fetched HTML).**
- Free-forever verdict: **free-forever** (all Apache-2.0, zero keys, zero infra beyond own compute; trafilatura optional language-data add-ons still free).
- ToS notes: **LOW across the board.** No evasion, no extra requests, robots-respecting queue helpers. First-class product citizens.

---

## Comparison table

| Engine | Renders / fetches | Anti-block posture (honest) | License (API) | Activity 2026 | Breakage profile | Client vs server fit | Free-forever? | ToS / product verdict |
|---|---|---|---|---|---|---|---|---|
| Scrapling | Static HTTP + Playwright-Chromium JS + spider crawl; unified Response | DUAL: polite (robots flag, AutoThrottle) + evasion (stealth fetcher, challenge-handling) | BSD-3-Clause | VERY ACTIVE (push 2026-10-04, ~85.7K★) | Browser/WAF drift on stealth tier; static tier stable | Server only | Software yes; proxies/infra extra | Polite subset gradeable; stealth tier **RISKY — excluded** |
| Playwright (+python) | Full render: Chromium/Firefox/WebKit, interception, PDF/shots | **Polite by default (detectable)**; stealth only via 3rd-party patches | Apache-2.0 | VERY ACTIVE (push 2026-10-03 / 09-24, ~97.1K+15.0K★) | Binary drift (pin versions); mature API | **Server fallback renderer** | Software yes; compute extra | LOW when stock+polite; stealth plugins **excluded** |
| Crawl4AI | Playwright render → LLM-ready Markdown + structured extract + deep crawl | Polite-leaning + optional stealth flag / cloud-proxy path | Apache-2.0 | VERY ACTIVE (push 2026-09-25, ~84.8K★) | Heavy stack; LLM cost; 229-issue tail | Server only | Software yes; LLM/Cloud metered | Output shape adopted; stealth/bulk **excluded** |
| Firecrawl | Scrape/crawl/map/search → Markdown/structured (OSS or Cloud) | OSS = polite-only; **Cloud = evasion-as-a-service** | **AGPL-3.0** | VERY ACTIVE (push 2026-10-04, ~188.7K★) | Credit-model + Cloud-only skew drift | Server SaaS / heavy self-host | **No** (1K free pages/mo, then metered) | **Excluded v1** (AGPL + cost + pass-through); interface ref only |
| Maxun | No-code robots: record/AI extract, scrape, crawl, search, monitor | Mixed: polite infra + **stealth mode + behind-login** | **AGPL-3.0** | VERY ACTIVE (push 2026-10-02, ~17.7K★) | Full-stack ops (PG/Redis/MinIO/browser); recorder brittleness | Server platform | **No** (credits/infra/LLM) | **Excluded** (AGPL + login + stealth); recorder UX ref only |
| yt-dlp (delta) | Public media download + `--dump-json` metadata | Neutral tool; login paths exist | Unlicense | VERY ACTIVE (push 2026-09-27, ~195.6K★) | Extractor churn (~2.7K open issues) | Server media lane | Software yes | Seed stands: public-only + cache + FAIL taxonomy |
| gallery-dl (delta) | Bulk gallery download, archive-dedup | Neutral tool; cookie mode exists | **GPL-2.0** | VERY ACTIVE (push 2026-10-03, ~19.9K★) | Extractor churn (~1K open issues) | Server media lane | Software yes | Seed stands: **never in core**; cookie mode excluded |
| nodriver | Drives installed Chrome over direct CDP (async Python) | **Evasion-grade by design** | **AGPL-3.0** | BORDERLINE (push 2026-05-13, ~4.8K★) | WAF/browser drift; unmaintained defects reported Sept 2026; `zendriver` fork noted | Server only | Software yes; proxies/ops extra | **RISKY — listed to exclude** |
| SeleniumBase (UC/CDP) | Selenium framework + CDP stealth + Playwright bridge | **Evasion-grade modes** (+ CAPTCHA helpers) | MIT | VERY ACTIVE (push 2026-10-02, ~13.1K★) | Arms-race breakage on stealth modes | Server only | Software yes | License-clean but modes **RISKY — excluded**; UX ref only |
| trafilatura | Extraction only (HTML→ text/meta, politeness helpers) | **Polite by construction** | Apache-2.0 | VERY ACTIVE (push 2026-10-02, ~6.9K★) | Lowest (parser-only; quality varies by layout) | **Server fallback extractor** | **Yes** | **LOW — product citizen** |
| mozilla/readability | Extraction only (DOM→ article, in-page JS) | **Polite by construction (zero traffic)** | Apache-2.0 | ACTIVE (push 2026-08-04, ~11.5K★) | Lowest (parser-only) | **Client-side page-reader pick** | **Yes** | **LOW — product citizen** |
| python-readability | Extraction only (readability.js port) | **Polite by construction** | Apache-2.0 | ACTIVE (push 2026-08-27, ~2.9K★) | Lowest (parser-only) | Server fallback (paired w/ trafilatura) | **Yes** | **LOW — product citizen** |

---

## Recommendation — engine pick for client-side page-reader + server fallback

1. **Client-side page-reader: `mozilla/readability` (primary).** Runs inside the user's own page context (extension content-script / bundled JS / WASM-adjacent) on the already-rendered DOM — zero extra network traffic, zero bot surface, zero keys, Apache-2.0, Firefox-maintained. Adapter contract: DOM-in → `{title, text, excerpt}` finding or clean empty-with-reason; never hallucinate on JS-shell pages. No fetch, no evasion, nothing to break when WAFs change.
2. **Server fallback: stock Playwright (polite, no stealth plugins) fetch → `trafilatura` extract (primary) / `readability-lxml` fallback.** Single public-GET per target, 10s timeout, identifying UA, 1 req/2s pacing, robots-respect, 24h cache, fixture fallback when down — the existing `docs/LIVE.md` discipline, extended from presence-probes to one article fetch. Playwright used *stock* (its detectability keeps us honest: cooperative pages render, protected pages fail clean into `ok` + `[]` with reason). Trafilatura (Apache-2.0, benchmark-best F-score, politeness helpers) shapes the finding (`{title, text_markdown, author/date when present}`); Crawl4AI's `markdown`/`fit_markdown`/citation field shape is the interface reference, without adopting its stack.
3. **Explicitly NOT adopted:** Scrapling stealth fetcher / challenge-handling (RISKY; polite-tier patterns only as reference), Firecrawl Cloud + self-host (AGPL + metered + pass-through; interface ref only), Maxun (AGPL + behind-login + stealth; recorder-UX ref only), nodriver / SeleniumBase UC-CDP-CAPTCHA modes (evasion-grade, RISKY; nodriver additionally AGPL + borderline-stale), gallery-dl code in core (GPL-2.0; cookie mode excluded), any bulk-crawl posture (AGENTS.md §8).

## Failure taxonomy (page-reader lane; never hallucinated)

- `ok` + findings: extracted title + body text with source URL + confidence (multi-signal → medium, single → low, never high from scrape alone).
- `ok` + `[]`: JS-shell/empty (no readable text), 429/5xx upstream, WAF/bot-gate page (classified as error, not content), malformed URL.
- `rejected`: login-walled, PII-gated, or non-public target (reason names the rule, no fetch attempted).

---

## Dated sources

- GitHub API `api.github.com/repos/{...}` fetched 2026-10-05 (pass 1) + re-fetch pass 2 same day: D4Vinci/Scrapling 85716/BSD-3-Clause/2026-10-04T19:47:53Z (stable 2x); microsoft/playwright 97098/Apache-2.0/2026-10-03; microsoft/playwright-python 15027/Apache-2.0/2026-09-24; unclecode/crawl4ai 84764/Apache-2.0/2026-09-25; firecrawl/firecrawl 188667→188668/AGPL-3.0/2026-10-04 (stable 2x); getmaxun/maxun 17656/AGPL-3.0/2026-10-02; yt-dlp/yt-dlp 195594/Unlicense/2026-09-27; mikf/gallery-dl 19946/GPL-2.0/2026-10-03; ultrafunkamsterdam/nodriver 4804/AGPL-3.0/2026-05-13; seleniumbase/SeleniumBase 13051/MIT/2026-10-02; adbar/trafilatura 6909/Apache-2.0/2026-10-02; mozilla/readability 11480/Apache-2.0/2026-08-04; buriy/python-readability 2897/Apache-2.0/2026-08-27.
- Scrapling docs: `scrapling.readthedocs.io` intro (adaptive framework, Spider/AutoThrottle/robots-flag claims) + `d4vinci-scrapling.mintlify.app` fetchers/architecture/stealth/MCP pages (three fetcher tiers, patchright-based stealth tier, challenge-handling + fingerprint options named at feature level); releases v0.4 (Spider/proxy-rotation) + v0.4.6 (ad-blocking/DoH/page_setup) via github.com/D4Vinci/Scrapling/releases.
- Firecrawl: `docs.firecrawl.dev/contributing/open-source-or-cloud` (open-core split: core OSS vs Fire-engine/proxies/screenshots/actions/Agent/Browser/Interact hosted-only; fetched 2026-10-05) + `firecrawl.dev/pricing` (1K free credits/mo; Hobby $19/$16; Standard $99/$83; Growth $399/$333; Scale $749/$599; 1 credit/page +4 JSON; effective 2026-09-04).
- Crawl4AI: `crawl4ai.org` + `docs.crawl4ai.com/core/quickstart` + PyPI `crawl4ai`/`Crawl4AI` (0.8.0 Jan 2026 → 0.9.x 2026; `AsyncWebCrawler`, Markdown/citations, stealth flag, Docker/CLI).
- Maxun: `maxun.dev` + `docs.maxun.dev/sdk/node-sdk/sdk-scrape` + README via github.com/getmaxun/maxun (recorder/AI/scrape/crawl/search, AGPL-3.0, Playwright-Chromium setup, proxy/fingerprint + behind-login features named at feature level).
- nodriver/SeleniumBase: `ultrafunkamsterdam/nodriver` README (undetected-chromedriver successor, direct-CDP, no-Selenium); send.win undetected-chromedriver-vs-nodriver comparison 2026-09-27 (AGPL note, IP/fingerprint limits, zendriver fork); ScrapingBee nodriver tutorial 2026-09-30 (0.50.3 May 2026, headless-UA + no-test-suite defects); ianlpaterson anti-detect benchmark 2026-05-13 (nodriver 28 OK/0 blocked of 31 Cloudflare targets, protocol-fingerprint analysis); `seleniumbase.io` UC-Mode + CDP-Mode docs (patched-driver → direct-CDP evolution, CAPTCHA helpers named at feature level); SeleniumBase 4.54.x Sept 2026 via PyPI.
- Playwright detectability context: `playwright-stealth` PyPI (unmaintained proof-of-concept note) + `pw-stealth-enhanced` PyPI 0.1.0 Apr 2026 (successor shim, MIT) + greekr4/playwright-bot-bypass README (rebrowser/Runtime-fix/headed-Chrome layering narrative) — cited for posture grading only, no bypass detail reproduced.
- Extraction libs: trafilatura PyPI/docs evaluation tables (F-score ~0.90–0.91 vs readability-lxml ~0.80–0.82; politeness/sitemap/queue features) + go-trafilatura benchmark mirrors; `mozilla/readability` repo (Reader-Mode core, Apache-2.0).
- Seed deltas: `research-osint.md` §c (yt-dlp 195490 Unlicense 2026-09-27; gallery-dl 19943 GPL-2.0 2026-10-03) — numbers above are the 2026-10-05 delta.
- AGENTS.md §0/§8b + `docs/LIVE.md` (public-GET-only, pacing, robots/ToS, failure taxonomy) — local files, read 2026-10-05.

## Link health (checked 2026-10-05)

- All `api.github.com/repos/{o}/{r}` links above returned 200 except `mozilla/readability.js` (404 — wrong slug; canonical is `mozilla/readability`, which returned 200 and is used in the table).
- `github.com/{o}/{r}` canonical links used throughout; `p1ngul1n0`-style renames not involved in this file.
- Pricing/docs pages are public (run-history/billing tabs may need login; pricing + open-source-vs-cloud + README tabs public). If any link 404s later, treat as stale signal and re-fetch `pushed_at` before relying — not a Sherlock failure.

## Compliance footer

- Public info only. No session cookies, tokens, passwords, bypass instructions, live targets, or secrets in this file by construction.
- Evasion-grade tools/modes flagged RISKY with reason inline (Scrapling stealth tier, nodriver, SeleniumBase UC/CDP/CAPTCHA modes, Maxun behind-login + stealth, Firecrawl Cloud pass-through, Crawl4AI stealth flag). Login-gated + PII + bulk postures excluded per AGENTS.md §0/§8b.
- Copyleft code (AGPL: Firecrawl/Maxun/nodriver; GPL-2.0: gallery-dl) NEVER copied into core — interface patterns only. Permissive libs (BSD/Apache/MIT/Unlicense) also pattern-only for v1; no vendoring.
- No contradiction found to `research-osint.md`, `research-osint-2.md`, or AGENTS.md §0/§8b on re-check 2026-10-05; no AGENTS.md update required.
