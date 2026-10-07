# AskMe — OSINT Tools Research (GitHub)

> Date: 2026-10-04 (UTC). Scope: `/home/markone/drive1/askme` only.
> Constraints: AGENTS.md §0 applies. Fake data only. No credentials. Public info only.
> Never include session cookies, tokens, or instructions to bypass auth.
> This file learns INTERFACE PATTERNS only. No code copying. No proprietary code reproduced.
> AskMe honest baseline: official Instagram Graph API CANNOT list personal Saved/Liked (even Creator/Business). Basic Display dead 2024-12-04. Only bulk-history path is manual Accounts Center Export JSON. Transcripts must be ASR from public-reel audio. No scraping with real session cookies in demo.

## Method + freshness

- `websearch` + `webfetch https://api.github.com/repos/{owner}/{repo}` on 2026-10-04 for stars/license/pushed_at.
- Stars are approximate point-in-time counts (GitHub API `stargazers_count`, `pushed_at`, `license.spdx_id`).
- "Last activity" = `pushed_at` from API, plus release notes where noted.
- ToS risk assessed from repo README/docs disclaimers + Instagram ToS / Graph API docs consensus (public knowledge, no bypass instructions).

---

## (a) General OSINT frameworks

| Repo | Stars (2026-10-04) | License (API) | Last activity | What it CAN do | vs AskMe constraints | Legal / ToS risk |
|---|---|---|---|---|---|---|
| `smicallef/spiderfoot` — https://github.com/smicallef/spiderfoot | ~22,783 | MIT | pushed 2026-04-13; v4.0 release 2022-04-07; still updated Oct 2026 per API | 200+ modules, CLI+web UI, SQLite backend, correlation engine, domain/IP/email/username pivoting, CSV/JSON/GEXF export | No IG Saved/Liked access. Useful only as pattern for modular enrichment + correlation + local DB. No reel-transcript path. | LOW for tool itself (aggregates public sources + user API keys). Risk only if operator points modules at ToS-protected endpoints without permission. |
| `laramies/theHarvester` — https://github.com/laramies/theHarvester | ~17,798 | GPL-2.0 | pushed 2026-10-02; v4.11.1 released 2026-06-03 — VERY ACTIVE | Emails/subdomains/hosts/people/breaches from 60+ public sources (crt.sh, GitHub-code, Shodan, etc.), CLI + REST + HarvestView | No IG Saved. Relevant only for author/domain enrichment (e.g. link domains in reel captions). Not a reel saver. | LOW when used on own/authorized targets with public sources. Many sources need own API keys; respect each provider ToS + rate limits. |
| `lanmaster53/recon-ng` — https://github.com/lanmaster53/recon-ng | ~5,960 | GPL-3.0 | pushed 2024-11-01 — STALE (~2y) | Metasploit-style modular recon shell, workspaces + marketplace modules, DB-tracked findings | No IG Saved. Pattern only: workspace + module UX. Long tail of unmaintained modules. | LOW-MEDIUM. Core is benign, but stale modules break / hit dead APIs. Do not rely for prod. |
| `lockfale/OSINT-Framework` — https://github.com/lockfale/OSINT-Framework | ~12,235 | MIT | pushed 2026-09-11 — ACTIVE (catalog) | Not a tool — interactive directory/taxonomy of OSINT resources (web UI at osintframework.com) | Useful as discovery checklist. No code to run. No Saved access. | NONE (links directory). Verify each linked resource individually. |
| `jivoi/awesome-osint` — https://github.com/jivoi/awesome-osint | ~29,904 | Other / NOASSERTION | pushed 2026-10-04 — ACTIVE (list) | Curated list of OSINT tools/resources by category | Discovery only. No Saved access. | NONE (list). Same caveat as above. |
| `sherlock-project/sherlock` — https://github.com/sherlock-project/sherlock | ~93,228 | MIT | pushed 2026-10-04 — VERY ACTIVE | Username presence check across 400+ sites via HTTP probes (no login). Good for cross-platform handle pivoting | CANNOT access private IG data or Saved. Can confirm public handle exists elsewhere. No caption/transcript. Useful enrichment hint only. | LOW (public HTTP probes). Can trigger rate limits / false positives. Respect site robots/ToS; do not use for harassment/doxxing. |
| `soxoj/maigret` — https://github.com/soxoj/maigret | ~38,267 | MIT | pushed 2026-10-04 — VERY ACTIVE | Username dossier across ~6K sites, successor-style to Sherlock with richer reports | Same as Sherlock: public presence only. No Saved, no private media. | LOW, same notes as Sherlock. Heavier scan = more rate-limit risk. |
| `s0md3v/Photon` — https://github.com/s0md3v/Photon | ~13,254 | GPL-3.0 | pushed 2026-09-04 — ACTIVE | Fast web crawler: URLs, emails, files, JS endpoints, leaked keys from a target site | Only for AskMe-owned surfaces (e.g. crawl resource links extracted from captions, with permission). Not for IG. | LOW on own sites; MEDIUM-HIGH if pointed at third-party sites aggressively (could violate ToS / look like abuse). Rate-limit + allowlist. |

## (b) Instagram-specific

| Repo | Stars (2026-10-04) | License (API) | Last activity | What it CAN do | vs AskMe constraints | Legal / ToS risk |
|---|---|---|---|---|---|---|
| `Datalux/Osintgram` — https://github.com/Datalux/Osintgram | ~14,776 | GPL-3.0 | pushed 2026-09-28 — ACTIVE | Interactive shell: public profile info, followers/following lists, posts/stories/hashtags/locations/tags (requires logged-in IG account; README: "You cannot see private profiles") | Does NOT solve Saved/Liked. Requires personal login = violates AskMe demo rule (no real session cookies). Breaks frequently on IG changes; large open-issue tail historically. | **RISKY** — requires username/password session; scrapes undocumented endpoints against Instagram ToS. Account-ban + 429 risk. Learn command-surface shape only (info/posts/followers commands); do NOT run with real creds, do NOT copy code. |
| `instaloader/instaloader` — https://github.com/instaloader/instaloader | ~13,489 | MIT | pushed 2026-09-06; v4.15.3 (Jul 2026) — ACTIVE | CLI+lib: public profiles/posts/captions/comments/hashtags/stories/metadata download; logged-out for public data, optional login for private/saved | Logged-out public metadata schema is the ONLY AskMe-relevant pattern (caption+timestamp+owner). Login/saved-media paths are out of scope for demo (risky, ban-prone). Respects AskMe "public-only" if restricted to logged-out. | CAUTION. Logged-out public metadata = lower risk but still undocumented-endpoint scraping (ToS gray, 429/IP-limit per socialcrawl.dev 2026-04-14 + scrapfly 2026-08-11). Login mode = **RISKY** (ban/2FA/checkpoint risk). Study `--dump-json` field names only; do not wire login in demo. |
| `megadose/toutatis` — https://github.com/megadose/toutatis | ~4,325 | GPL-3.0 | pushed 2024-12-05 — STALE; 355 open issues | Extracts obfuscated contact bits (email/phone-mask) for a target IG username via authenticated session (requires operator's own logged-in session — pattern excluded by AskMe rule) | Does NOT give Saved/transcripts. Directly conflicts with AskMe "no session cookies" rule. | **RISKY** — needs victim-adjacent session harvesting pattern + hits private-data edge. Privacy/ToS red flag. Do NOT use. Listed only to explicitly exclude. |
| `subzeroid/instagrapi` (active fork; original `adw0rd/instagrapi` stale) — https://github.com/subzeroid/instagrapi | ~6,892 | Other / MIT-claimed in docs (API returns NOASSERTION; check LICENSE file) | pushed 2026-10-04 — VERY ACTIVE | Full private-mobile-API wrapper: users/media/stories/DMs/comments/insights/uploads, session persistence, 2FA/challenge handling | Technically CAN fetch more than official API, but only via private API impersonation = fragile + ban-prone (maintainers + scrapfly 2026 survey agree). Violates AskMe demo rule. | **RISKY** — private-API automation against ToS; account bans, Telegram support group previously restricted by Meta. Study typed-response idea only (pydantic models); do NOT adopt transport/login. |
| `subzeroid/insto` + `subzeroid/aiograpi` (sister async lib, ~449 stars per search 2026) — https://github.com/subzeroid/insto | small (<500 each) | MIT (per store page) | active 2025-2026 | HikerAPI-backed CLI (`/info /posts /followers /dossier`) so no IG session in scope; optional `aiograpi` backend | HikerAPI = paid SaaS proxy — not free for demo. Interface shape (`URLs only --no-download` vs download) is a useful pattern. | MEDIUM — avoids personal session but still proxies undocumented endpoints via third party; cost + ToS-pass-through risk. Interface-only study. |
| Small forks (`EchterAlsFake/Osintgram2`, `galihap76/collector` ~310 stars, `0x0be/yesitsme` name/email-phone lookup) | <500 each | varies | sporadic 2024-2026 | Narrow utilities (email-registered check, profile-by-name) | No Saved/transcript value. Often break. | **RISKY** — several touch PII (email/phone-to-account). Exclude from AskMe. |

> Note on `adw0rd/instagrapi`: original repo widely referenced but stale/archived-era; community moved to `subzeroid/instagrapi` (see instagrapi.com + GitHub). Prefer the subzeroid API numbers above. Link to original intentionally omitted to avoid steering to stale code.

## (c) Transcript / media download

| Repo / Actor | Stars / signal (2026-10-04) | License / pricing | Last activity | What it CAN do | vs AskMe constraints | Legal / ToS risk |
|---|---|---|---|---|---|---|
| `yt-dlp/yt-dlp` — https://github.com/yt-dlp/yt-dlp | ~195,490 | Unlicense (public domain) | pushed 2026-09-27 — VERY ACTIVE; 1000+ extractors | CLI+lib: download public video/audio + `--dump-json` metadata, `--write-subs/--write-auto-subs`, `--skip-download --print` for metadata-only; IG extractor exists but reel-bulk + rate-limit issues open (#11151, #16257 filed Mar 2026) | Best-fit PATTERN for AskMe prod transcript path: fetch public reel → extract audio → ASR. For demo use stub; in prod call with public URL only, cache result (link rot per AGENTS.md §0.5). No login, no Saved. | CAUTION. Tool is general-purpose; operator is responsible for ToS/copyright. Defensible for own/CC-licensed/public reels with permission; commercial scraping of IG invites takedown + civil risk (see dev.to 2026 yt-dlp guide). Never bypass login walls; respect 429. Study flags + JSON schema only. |
| `mikf/gallery-dl` — https://github.com/mikf/gallery-dl | ~19,943 | GPL-2.0 | pushed 2026-10-03 — VERY ACTIVE | Bulk gallery downloader (IG/Twitter/Tumblr/etc.), powerful naming/config, cookie support, archive-dedup | Config/archival pattern useful, but IG bulk-reels/highlights still partial (issue #9555 May 2026; #9020 Feb 2026). Cookie mode violates demo rule. | **RISKY if with cookies/login** — cookie-based IG auth = ToS violation + ban risk. Logged-out study only (config file shape, `archive` dedup). Do NOT wire cookies in AskMe. |
| Apify `apify/instagram-scraper` — https://apify.com/apify/instagram-scraper | managed actor, pay-per-result (~$1.50/1K per socialcrawl 2026) | commercial, free tier | maintained 2026 (sample run 2026-06) | Public posts/reels metadata: caption, hashtags, mentions, likes/comments counts, videoUrl, displayUrl | No Saved. Paid + third-party scraping. For AskMe: interface reference only (field names match Instaloader-like schema). Not for demo (not free). | MEDIUM — vendor manages proxies/fingerprints (`curl_cffi`-style) but still hits unofficial endpoints; ToS risk passed through + cost. |
| Apify `crawlerbros/instagram-transcript-scraper` — https://apify.com/crawlerbros/instagram-transcript-scraper | from $5/1K transcripts | commercial | listed 2026 | Public IG video → transcript via auto-captions/Whisper path (`videoUrls`, `transcriptionMethod`, `whisperModel`, `includeSegments`) | Closest to AskMe `transcript_providers.py` interface. Demo uses stub; prod may call with explicit public URL + user consent. | MEDIUM — same scraping-pass-through + per-unit cost. Only public URLs; music-only reels unbilled pattern is worth copying as policy. |
| Apify `memo23/video-audio-transcriber` + `parsebird/video-audio-transcriber`, `linen_snack/instagram-videos-transcipt-subtitles-and-translate`, `x402farm/instagram-transcript-scraper` | community actors, per-second or per-minute billing | commercial | 2026 listings | Audio-track → faster-whisper / Whisper large-v3 → text + segments + SRT/VTT (`srtFileUrl`/`vttFileUrl`, `transcript_llm` field) | Ideal OUTPUT SHAPE for AskMe cache: `{text, segments[], srt, vtt, lang, hook3s}`. Study `transcript_llm` RAG-ready field (per use-apify.com 2026 transcript roundup). | MEDIUM — cost + ToS-pass-through. No private/deleted URLs. Cache everything. |

## (d) MCP / AI bridges (Composio / Truto-style toolkits)

| Repo / Product | Stars / signal (2026-10-04) | License / pricing | Last activity | What it CAN do | vs AskMe constraints | Legal / ToS risk |
|---|---|---|---|---|---|---|
| `ComposioHQ/composio` — https://github.com/ComposioHQ/composio ; toolkit https://composio.dev/toolkits/instagram | ~30,436 | MIT (repo) + commercial cloud | pushed 2026-10-04 — VERY ACTIVE | 1000+ toolkits, managed OAuth + token refresh, Tool Router, Instagram MCP (Business/Creator): publish, insights, comments, DMs via official Graph API | Aligns with AskMe Creator path (`sync_creator` needs Meta App + FB Page). CANNOT do personal Saved — confirms AGENTS.md §0.1. Best pattern for tool descriptions, OAuth handling, per-user scoping. | LOW — official-API route (review-gated, 200 req/hr/token). Must still pass Meta App Review for prod; no scraping. |
| Truto — https://truto.one + https://truto.one/integrations (incl. Instagram AI Beta) | commercial unified API + MCP servers (SOC2/ISO/GDPR) | commercial | active 2026 | One-call MCP server per integration, scoped methods/tags/TTL, no stored customer data (passthrough) | Same official-API ceiling as Composio: no personal Saved. Useful as "tool router done right" reference. | LOW — official-API route. Cost + review still apply. |
| `mcpware/instagram-mcp` (fork of `jlbadano/ig-mcp` 197 stars) — https://github.com/mcpware/instagram-mcp | ~46 (fork; upstream ~197) | MIT | pushed 2026-09-13 — ACTIVE | 23 tools for Graph API: posts/comments/DMs/stories/hashtags/reels/carousels/analytics via `INSTAGRAM_ACCESS_TOKEN` + FB app creds | Direct model for AskMe `server/tools.py` schemas + `.env` shape (use `DUMMY_...` only). No Saved — honest. | LOW — official API. Risk is only misconfig (leaking tokens in logs). Never log tokens. |
| `mikusnuz/meta-mcp` — https://github.com/mikusnuz/meta-mcp | ~26 | MIT | pushed 2026-08-29 — ACTIVE | 57 tools, Graph v25/v26, IG + Threads + GIPHY (Tenor removed Mar 2026), ghost posts, reply approvals | Broadest tool-catalog pattern. Same Saved ceiling. Good example of versioned API + changelog discipline. | LOW — official API. Same review/rate-limit notes. |
| `arjun1194/insta-mcp` (+ similar password-based MCPs) | small | varies | 2025-2026 | Account/activity/social-graph via username+password | Conflicts with AskMe security (password in `.env`/`credentials.json`). | **RISKY** — password-based IG automation = ban + credential-theft surface. Exclude. Prefer OAuth/token MCPs above. |

---

## What each category means for AskMe (honest mapping)

- General frameworks (SpiderFoot/theHarvester/Recon-ng/Sherlock/Maigret/Photon): **no Saved access**. At most they enrich public link domains or cross-platform handle presence. Do not promise otherwise.
- Instagram scrapers (Osintgram/Instaloader/Toutatis/instagrapi): technically fetch public (and with login, some private) data, but **all require scraping or private-API use except narrow logged-out paths**, need sessions, break on IG changes, and carry ban/ToS risk. They do NOT provide personal Saved history. Marked `future, risky` per AGENTS.md §0.7. No session cookies in demo.
- Download/transcript (yt-dlp/gallery-dl/Apify): **only viable prod path for public-reel transcripts** (download public audio → Whisper ASR → cache). No captions file exists on IG. Private/deleted = must fail. Demo stays on stub + oEmbed.
- MCP bridges (Composio/Truto/mcpware/meta-mcp): **only compliant path**, but limited to official Graph API (own Business/Creator media + insights + comments + Business Discovery for public Business/Creator). Confirms Saved gap; justifies Export-ZIP bulk path.

## Recommendation — 2-3 safe interface patterns for AskMe public-reel transcript/enrichment (no code copying)

1. **`yt-dlp` — transcript-fetch interface pattern (primary).**
   Learn: `--dump-json --skip-download --print title,description,uploader,timestamp` for metadata-only reads; `--write-auto-subs --sub-langs en --convert-subs srt` shape for caption fallback; Python-lib import (not shell-out) for automation; per-URL cache key + failure taxonomy (private/deleted/rate-limit → clean FAIL, no hallucination).
   Why safe: public-URL only, no login, matches AGENTS.md §0.5 + `transcript_providers.py` plan (stub → Supadata/self-Whisper). Do NOT copy extractor code; only adopt CLI/JSON field discipline.
2. **Official-API MCPs (`mcpware/instagram-mcp` + `mikusnuz/meta-mcp`, via Composio/Truto toolkit design) — tool-schema pattern.**
   Learn: tool description quality, OAuth env shape (`INSTAGRAM_ACCESS_TOKEN` etc. → `DUMMY_...` in AskMe), pagination, 200-req/hr guard, versioned API (v25→v26 changelog), never-log-tokens rule. Use for `sync_creator()` + `docs/META_SETUP.md`.
   Why safe: official Graph API, review-gated, no scraping. Explicitly CANNOT do Saved — keeps AskMe honest.
3. **Apify Whisper transcriber output shape (`memo23/video-audio-transcriber` / `crawlerbros/instagram-transcript-scraper`) — transcript-record pattern.**
   Learn: input `{videoUrls[], transcriptionMethod, whisperModel, includeSegments}` → output `{text, segments[{start,end,text}], srtFileUrl, vttFileUrl, lang, hook3s}` + `transcript_llm` RAG-ready field; music-only/no-speech → unbilled/empty with reason; cache SRT+VTT in KV store.
   Why safe: interface-only; demo keeps local stub files in `demo-data/transcripts/`. Prod calls only on explicit public reel URLs with consent; cache everything (link rot).

Explicitly NOT recommended for AskMe: Osintgram (session), Toutatis (session + PII edge), instagrapi private-API (ban/fragile), gallery-dl cookie mode, password-based MCPs. Listed above as RISKY with reasons.

---

## Dated sources

- GitHub API `api.github.com/repos/{...}` fetched 2026-10-04 for all star/license/pushed_at numbers above (SpiderFoot 22783 MIT 2026-04-13; theHarvester 17798 GPL-2.0 2026-10-02; recon-ng 5960 GPL-3.0 2024-11-01; OSINT-Framework 12235 MIT 2026-09-11; Osintgram 14776 GPL-3.0 2026-09-28; Instaloader 13489 MIT 2026-09-06; Toutatis 4325 GPL-3.0 2024-12-05; yt-dlp 195490 Unlicense 2026-09-27; gallery-dl 19943 GPL-2.0 2026-10-03; Sherlock 93228 MIT 2026-10-04; Composio 30436 MIT 2026-10-04; Photon 13254 GPL-3.0 2026-09-04; Maigret 38267 MIT 2026-10-04; awesome-osint 29904 Other 2026-10-04; subzeroid/instagrapi 6892 Other 2026-10-04; mcpware/instagram-mcp 46 MIT 2026-09-13; mikusnuz/meta-mcp 26 MIT 2026-08-29).
- Scrapfly "6 Best Open-Source Instagram Scrapers" 2026-08-11 (Instaloader 13,100 stars v4.15.3 Jul 26 2026; instagrapi fragile-in-prod note).
- SocialCrawl "Which Instagram Scrapers Still Work in 2026" 2026-04-14 (Graph API table; Basic Display dead 2024-12-04; `curl_cffi` + residential proxy note; unofficial `i.instagram.com/api/v1` + rotating `doc_id`).
- BrowserAct "Instagram Scraper GitHub Guide" 2026-08-26 (Instaloader 13,236 stars Jul 26 2026 push; login/2FA/rate-limit caveats).
- RingSafe "theHarvester Recon-ng OSINT Toolchain" 2026-04-25 (free-tier shrinkage, stale Recon-ng modules).
- theHarvester releases (4.11.1 on 2026-06-03, 4.11.0 on 2026-05-23) via github.com/laramies/theHarvester/releases.
- Osintgram README disclaimer ("FOR EDUCATIONAL PURPOSE ONLY … You cannot see private profiles") via github.com/Datalux/Osintgram.
- Instaloader docs https://instaloader.github.io/ (public+private scope, "Use at your own risk", MIT).
- yt-dlp issues #11151 (reel rate-limit/login-required) + #16257 opened 2026-03-17 (`/{username}/reels` bulk gap); dev.to "yt-dlp CLI Developers Actually Use in 2026" (100K+ stars, ToS/personal-archive/CC guidance).
- gallery-dl issues #9020 (Feb 2026 full-profile regression) + #9555 (May 2026 reels/highlights bulk gap, closed) + discussion #8198 (cookie config example — NOT to copy).
- Apify Store 2026: `apify/instagram-scraper` (sample 2026-06-22), `crawlerbros/instagram-transcript-scraper` API tab, `x402farm/instagram-transcript-scraper` (Whisper large-v3), `linen_snack/instagram-videos-transcipt-subtitles-and-translate`, `memo23/video-audio-transcriber` (per-second billing, SRT/VTT KV), use-apify.com "Best YouTube Transcript Scrapers 2026" (`transcript_llm` field).
- Composio https://composio.dev/toolkits/instagram (+ autogen page) + Developers Digest "Composio 101" 2026-02-28/06-05; Truto https://truto.one + /integrations (Instagram AI Beta, MCP-per-integration, SOC2/ISO/GDPR, no stored data).
- AGENTS.md §0 (AskMe honest constraints) — local file, read 2026-10-04.

## Link health (checked 2026-10-04)

- All `github.com/{owner}/{repo}` and `api.github.com/repos/{owner}/{repo}` links above returned 200 on fetch except `subzero-id/instagrapi` (wrong owner spelling → 404, corrected to `subzeroid/instagrapi` which returned 200). Original `adw0rd/instagrapi` not linked (stale; community moved to subzeroid fork per instagrapi.com).
- Apify actor URLs are store pages (may require login for run history, but README/pricing/API tabs are public). No broken actor slugs at write time.
- If any link 404s later (IG endpoints rotate `doc_id` every 2-4 weeks per SocialCrawl), treat as stale signal, not AskMe failure; re-fetch API `pushed_at` before relying.

## Compliance footer

- Public info only. No session cookies, tokens, passwords, or bypass instructions included. No secrets scanned in (none in this file by construction).
- High-risk tools flagged RISKY with reason inline. Demo rule stands: fake data + public oEmbed + stub transcripts; scrapers are `future, risky`.
- No contradiction found to AGENTS.md §0 on re-check 2026-10-04; no AGENTS.md update required.
