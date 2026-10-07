# Sherlock — Free Data Lanes for Entity Search (people, companies, domains)

> Date checked: 2026-10-05 (UTC). Scope: `/home/markone/drive1/sherlock` only.
> Extends `research-osint.md` (seed, 2026-10-04) + `research-osint-2.md` (2026-10-04) — no contradiction found.
> Constraints: AGENTS.md §0 + §8b apply. Public sources only. Fake fixtures + free tiers only.
> No secrets, no live keys (`DUMMY_...` only), no PII of real people — example entities only
> (`Example Person / example.com / @demo.* / 00000000-0000-0000-0000-000000000000`-style).
> Every lane below lists: input → output, free cap (number + date checked), key model
> (keyless vs per-user key), official docs URL.
> Permanently EXCLUDED lanes are listed only to exclude (§7) — no instructions, no bypass.

## Method

- `websearch` discovery + `webfetch` of official docs/pricing pages on 2026-10-05.
- Caps are point-in-time vendor statements; re-check before wiring (Brave/Bing/OpenAlex all
  changed terms in 2025–2026 — see notes).
- "Keyless" = plain HTTPS GET, no credential. "Per-user key" = each operator brings their own
  free-tier key (never committed; `DUMMY_...` in `.env.example`). "Server key" = single shared
  key on our backend (burns one quota — avoid; prefer keyless or per-user-key).

---

## 1. Web search APIs with free tiers

| Lane | Input → Output | Free cap (checked 2026-10-05) | Key model | Official docs |
|---|---|---|---|---|
| **Brave Search API** | `q, count, country` → `web.results[{title,url,description}], infobox` | **$5 free credit/mo ≈ ~1,000 Search queries** at $5.00/1,000 (Data-for-AI Base). Old 2,000–5,000/mo no-card free plan **removed for new users ~Feb 2026** (multiple secondary reports; pricing page now credit-based). Verify at signup. | Per-user key (header `X-Subscription-Token`); server-callable but quota burns fast → per-user-key fit | https://brave.com/search/api/ ; pricing https://api-dashboard.search.brave.com/documentation/pricing |
| **Bing Web Search API** | n/a — **RETIRED 2026-10-05 note** | **Retired 2026-08-11** (Microsoft). Old F/free 1,000 txn/mo gone. Migration path = Azure AI Agent Grounding (~$35/1,000, secondary reports) — not free. | n/a (do not adopt) | Retirement coverage via https://learn.microsoft.com/answers/questions/5538194/ ; old pricing https://azure.microsoft.com/en-us/pricing/details/cognitive-services/bing-entity-search-api/ |
| **Serper.dev** (Google SERP proxy) | `q, gl, hl, num` → `organic[], knowledgeGraph, peopleAlsoAsk` | **2,500 free queries, no card** (advertised Jun–Oct 2026, secondary consensus); then $50/50,000 credits (~$1/1,000) | Per-user key (`X-API-KEY`); server-side callable, cache aggressively | https://serper.dev/ |
| **SerpApi** (reference only) | `q, engine` → `organic_results[]` | **100 free searches/mo** (secondary 2026 roundups) | Per-user key | https://serpapi.com/pricing |
| **DuckDuckGo** | `q` → Instant-Answer JSON only (definitions, Wikipedia abstracts) | Instant Answers API is free/keyless **but is NOT web search** (most queries return no instant answer — expected). **No official web-search API. HTML SERP scraping violates DDG ToS/policy → EXCLUDED** (no SERP scraping, per task rule). | Keyless (Instant Answers only) | Instant Answers: https://api.duckduckgo.com/api ; policy note via https://duckduckgo.com/duckduckgo-help-pages/features/instant-answers-and-other-features |

**Grade — web search.**
- *Product-fit:* **per-user-key, server-called + cached.** Brave/Serper quotas are per-key and
  burn in bulk; a single server key would exhaust in one demo day. Design: operator pastes their
  own free key (BYOK), server calls + 24h `fetch_log` cache, clean FAIL on 401/402/429.
  Client-side direct call is an alternative (key stays in browser) but leaks query to vendor
  from client IP — server-side with per-user key is the prod shape.
- *IN-jurisdiction (DPDP Act 2023):* search snippets about a person = personal data if they
  identify them. Lawful only on **publicly available data + stated purpose + consent-gate for
  non-public figures**; honor **correction/erasure-on-request** (§12: Data Principal may request
  erasure) and 24h cache TTL doubles as a deletion path (drop cached findings on request).
- *Homonym / entity-resolution:* web search is the **worst** for homonyms (common names collide).
  Never assert identity from one snippet. Require ≥2 corroborating signals (e.g. ORCID iD +
  employer domain, or LEI + registry address) before `medium`; single-snippet = `low` max.

---

## 2. Scholar / research (people → papers, affiliations)

| Lane | Input → Output | Free cap (checked 2026-10-05) | Key model | Official docs |
|---|---|---|---|---|
| **ORCID** | name / ORCID-iD / affiliation → `{orcid-id, employments, educations, works[]}` | **Anonymous: 12 req/s, burst 40, 25k reads/day/IP. Registered public client: 12 req/s, burst 40, 100k reads/day/client-ID. Member: 24 req/s, no quota.** Public API free for **non-commercial** use only (ToS). | Keyless (anonymous) for demo; free client-ID/secret for higher quota (per-user or server — quota is generous) | https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/ (quota table on-page, fetched 2026-10-05) |
| **OpenAlex** | name / DOI / ORCID / ROR → `authors[], authsorships, topics, cited_by` | **Changed Feb 2026: API key now REQUIRED for production; usage-based billing, $1/day free allowance per key.** Legacy `mailto=` polite-pool (100k/day) deprecated. | **Per-user/server key (free, $1/day free)** — was keyless, now key-gated | https://help.openalex.org/api/authentication/ ; pricing https://help.openalex.org/access/pricing/ ; change notice via https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/ |
| **Crossref REST** | DOI / name / affiliation → `works[{title, author, publisher, link}]` | **Keyless. Public pool throttled (list queries ~1 req/s); polite pool (add `mailto=you@example.com`) = higher limits + contactable.** Hard ceiling 50 req/s/IP → 10s deny on exceed. Headers `X-Rate-Limit-*` authoritative. | Keyless (+`mailto` string, not a secret) | https://www.crossref.org/documentation/retrieve-metadata/rest-api/ ; limits https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/ |
| **Semantic Scholar Academic Graph** | keywords / author / DOI → `papers[{title, abstract, authors, citationCount, tldr}]`, author lookup | **Keyless: 100 req/5 min (shared 1,000 rps global pool — degrades at peak). Free API key: 1 req/s sustained** on all endpoints. | Keyless for demo; free key (per-user/server) for prod | https://www.semanticscholar.org/product/api |
| **IRINS-pattern pages** (INFLIBNET, India) | researcher name → institutional profile page (position, papers, projects) | **No public API. Public profile pages only** (per-institute `https://<inst>.irins.org/profile/<id>`, hub https://irins.inflibnet.ac.in/). Free-as-in-public-pages; no bulk endpoint. | Keyless (public GET of profile pages; no key exists) | Hub https://irins.inflibnet.ac.in/ ; about https://irins.inflibnet.ac.in/about |

**Grade — scholar.**
- *Product-fit:* **server-side, keyless-first.** ORCID-anon + Crossref-polite + S2-keyless all work
  with zero secrets — ideal for default-on lanes with 24h cache. OpenAlex needs a free key now →
  per-user-key or single low-volume server key (fits inside $1/day at demo scale).
  IRINS = client-side link-out pattern (show profile URL, don't scrape at scale).
- *IN-jurisdiction:* researcher profiles are self-published/public-domain showcases (lowest DPDP
  friction). Still: purpose-limitation (research-attribution only), cache + delete-on-request.
  Indian faculty on IRINS = strong IN-relevance (affiliation disambiguates homonyms).
- *Homonym notes:* ORCID iD is the **gold disambiguator** (durable person-ID). OpenAlex
  `authorships` + ROR affiliation + Crossref `ORCID` in author objects corroborate.
  Name-only match = `low`; name + affiliation + ORCID = `medium`; never `high` from metadata alone.

---

## 3. Company lanes

| Lane | Input → Output | Free cap (checked 2026-10-05) | Key model | Official docs |
|---|---|---|---|---|
| **OpenCorporates API** | company name / number + jurisdiction → `{name, number, jurisdiction, status, officers, filings}` | **Key required. Default free: 200 req/month + 50 req/day** (API Reference v0.4.8, fetched 2026-10-05). Paid from ~£225/mo (Essentials). Free tier is demo-tiny. | Per-user key (`api_token`); server key burns out — BYOK only | https://api.opencorporates.com/documentation/API-Reference ; pricing https://opencorporates.com/pricing/ |
| **GLEIF LEI (Legal Entity Identifier)** | legal name / LEI / BIC / ISIN → `{lei, legalName, status, addresses, relationships (parent/child), registrationAuthority}` | **Free, keyless. 60 req/min/user** (Postman/official docs). Bulk Golden Copy + concatenated files free download. No charge, no key. | **Keyless — best company lane** (server-side, cached) | API landing https://www.gleif.org/en/lei-data/gleif-api ; interactive docs https://api.gleif.org/docs ; demo https://api.gleif.org/demo |
| **Clearbit-pattern** | domain/email → firmographic enrichment | **EXCLUDE from free lanes (paid-only, 2026-10-05).** Standalone Enrichment/Logo/Prospector APIs deprecated; free tools sunset 2025-04-30; now only via HubSpot Breeze credits (~$0.01/credit, from ~$45/mo per 2026 roundups). No free tier for API. Listed only to exclude. | n/a (commercial) | https://clearbit.com/ (acquisition notice); pricing roundups secondary |
| **MCA India (Ministry of Corporate Affairs)** | company/LLP name → master data (CIN, ROC, directors, status, filings index) | **Public pages only, no official API** (checked 2026-10-05). Path: mca.gov.in → MCA Services → View Company/LLP Master Data, **CAPTCHA-gated**. No key exists; automation against CAPTCHA = out of scope. | Keyless human-in-loop (client-side link-out + paste-back; no server scraping) | Portal https://www.mca.gov.in/ (guide pattern via MCA Services → Master Data) |

**Grade — company.**
- *Product-fit:* **GLEIF = server-side keyless default** (generous 60/min, structured JSON,
  relationship fields solve subsidiaries). OpenCorporates = **per-user-key optional** (200/mo
  cap means one shared key dies on day one — BYOK + cache, degrade to GLEIF when exhausted).
  MCA = **client-side** (operator looks up, pastes CIN; we store + link, never scrape CAPTCHA).
- *IN-jurisdiction:* company registry data is public-record (lowest DPDP friction for the
  **entity**, but **officer/director names are personal data** — display with purpose note,
  correction/delete-on-request path, no bulk officer harvesting).
- *Homonym notes:* company names collide across jurisdictions — **jurisdiction_code + company
  number (or LEI) is the identity**, never the bare name. GLEIF `registrationAuthority +
  lei` and OpenCorporates `jurisdiction_code/company_number` are the disambiguators;
  name-only = candidate list (`low`), LEI/CIN-pinned = `medium`.

---

## 4. Domain / infra lanes

| Lane | Input → Output | Free cap (checked 2026-10-05) | Key model | Official docs |
|---|---|---|---|---|
| **crt.sh (Certificate Transparency)** | `%.domain` → `[{name_value, issuer, not_before}]` → subdomains | **Free, keyless. No published cap**; community norm ~1 req/5s; server 429/502s under load (measured **502 from this box 2026-10-05** — treat as transient, DNS-fallback). | Keyless (server-side, already in `domain_intel`) | Front https://crt.sh/ ; query shape `https://crt.sh/?q=%25.<domain>&output=json` (no formal docs page; community-documented) |
| **DNS (stdlib socket)** | domain → `A/AAAA` | **Free, keyless, OS-resolver-limited** (no vendor cap; local rate = resolver policy). | Keyless (no key exists) | Python stdlib `socket.getaddrinfo` (already in adapter; no vendor docs) |
| **WHOIS (port 43) / RDAP (HTTPS JSON)** | domain/IP → registrar, creation/expiry, (redacted) contacts | **Free, keyless.** RDAP via IANA bootstrap; servers 429 on abuse (about.rdap.org documents 429 behavior). RDAP preferred (structured, GDPR-redacted). | Keyless | IANA bootstrap https://www.iana.org/assignments/rdap-dns ; explainer https://about.rdap.org/ ; RFC 9224 https://www.rfc-editor.org/info/rfc9224/ |
| **Shodan** | IP/domain → open ports, banners, vulns | **Key required (free account). Free plan = limited query + scan credits** (metered; exact quota on billing page — verify at signup; community: ~100 query credits/mo scale). Host-search metered per result page. | **Per-user key** (never server-shared) | Key/account https://developer.shodan.io/api/requirements ; billing https://account.shodan.io/billing ; credits https://help.shodan.io/the-basics/credit-types-explained |
| **Censys Search** | IP/domain/cert → hosts, certs, services | **Key required. Free community tier ≈ 250 queries/mo** (secondary 2026 consensus; credit model on pricing page — verify at signup). | **Per-user key** | API https://search.censys.io/api ; pricing https://censys.com/resources/pricing/ ; quickstart https://docs.censys.com/reference/get-started |
| **GitHub code search / REST search** | keyword/domain/leak-string → code, repos, commits | **Core REST: 60 req/hr keyless, 5,000/hr authed. Search: 30 req/min. Code search: 10 req/min** (changelog 2023-03-10, still current per docs). | Keyless (tiny) → **per-user PAT** for anything real | https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api ; code-search change https://github.blog/changelog/2023-03-10-changes-to-the-code-search-api/ |

**Grade — domain/infra.**
- *Product-fit:* **crt.sh + DNS + RDAP = server-side keyless defaults** (already our
  `domain_intel` shape; add RDAP as third source, same degrade-to-empty taxonomy).
  Shodan/Censys/GitHub-search = **per-user-key optional enrichment** (quotas too small to share;
  gate behind BYOK + explicit target consent; active-scan endpoints never auto-fire).
- *IN-jurisdiction:* infra data is non-personal (lowest DPDP friction) **until joined to a person**
  (e.g. registrant email in legacy WHOIS → treat as personal, redact by default since RDAP/GDPR
  redaction already hides it).
- *Homonym notes:* domains are near-unique identifiers (no homonym problem) — risk flips to
  **stale/parked/re-registered** domains. Check `creationDate` (RDAP) + cert `not_before`;
  sibling-subdomain scoping already enforced in `parse_ct_rows` (never claim out-of-scope names).

---

## 5. Social-public lanes

| Lane | Input → Output | Free cap (checked 2026-10-05) | Key model | Official docs |
|---|---|---|---|---|
| **Meta Graph API (official)** incl. Business Discovery | IG Business/Creator ID → media, captions, comments, insights | **Token required. ~200 req/hr/token** (app-scoped). App Review for prod; **no personal Saved/Liked endpoint (AGENTS.md §0.1 stands)**. | **Per-user token** (OAuth; `DUMMY_...` in repo) | https://developers.facebook.com/docs/instagram-platform/ ; oEmbed https://developers.facebook.com/documentation/instagram-platform/oembed |
| **oEmbed (public metadata)** | public post URL → `{author, title, html}` | **Token story changed twice:** token-required since 2020-10-24; **2025 reports (wpmayor) of tokenless restore, no App Review**. Treat as **verify-at-build**: code supports token if provided, keyless fallback otherwise. No quota published (fair-use). | Per-user token *or* keyless (probe at runtime) | Same oEmbed docs above; deprecation history via https://make.wordpress.org/core/2020/09/22/facebook-and-instagram-embeds-to-be-deprecated-october-24th/ |
| **Nitter / XCancel / X API** | n/a | **EXCLUDE (dead, 2026-10-05).** Nitter.net dark 2024 (API restrictions); X Corp cease-and-desist 2026-08-25 (repo + instances); XCancel offline Sep 2026 (fragile resurrections, legally tainted). X API has **no free tier for new devs** (pay-per-use). No unauthenticated X lane exists. Listed only to exclude. | n/a | Status via https://github.com/zedeus/nitter ; https://techcrunch.com/2026/08/25/x-sends-cease-and-desist-to-open-source-project-nitter-over-alleged-scraping/ ; https://en.wikipedia.org/wiki/Nitter |
| **Bluesky / AT Protocol (OPEN — big opportunity)** | handle / DID / keyword → `profile, posts, follows, searchActors, searchPosts` | **Free, keyless for public reads** via public AppView (`https://public.api.bsky.app`, `api.bsky.app`). Published limits: **~3,000 req/5 min/IP; 5,000 pts/hr + 35,000 pts/day account caps** (endpoint-weighted). No login for public data. Federation-friendly. | **Keyless (no key exists for reads)** — server-side default candidate | HTTP reference https://docs.bsky.app ; rate limits https://bsky.network/docs/rate-limits/ ; endpoints index https://endpoints.bsky.app/ |
| **Mastodon / Fediverse (OPEN — big opportunity)** | account / keyword / hashtag → `accounts, statuses, hashtags` (`/api/v2/search`, `/api/v1/accounts/search`, `/api/v1/timelines/tag/:tag`) | **Free, keyless on most instances for public endpoints. Default 300 req/5 min per account AND per IP** (hardcoded; tighter for media-create/account-create). Some instances require auth for trends/search — degrade cleanly per-instance. Federation-friendly. | **Keyless** (optional per-user token for authed instances) | Rate limits https://docs.joinmastodon.org/api/rate-limits/ ; search https://docs.joinmastodon.org/methods/search/ ; public-data guide https://docs.joinmastodon.org/client/public/ |

**Grade — social.**
- *Product-fit:* **Bluesky + Mastodon = server-side keyless defaults** (only social lanes with
  first-party open APIs — no ToS gray zone, generous caps, structured JSON; our `username_probe`
  already probes `bsky.app/profile/{handle}` + `mastodon.social/@{handle}` shapes).
  Graph/oEmbed = **per-user-token optional** (official but review-gated + quota-thin).
  X/Twitter = no lane (dead).
- *IN-jurisdiction:* social posts are user-published (consent-implied for public posts) but still
  personal data under DPDP when identifying someone → purpose-limitation + no bulk harvesting +
  delete-on-request (drop cached findings + refetch-stop). Private/deleted/suspended = clean miss.
- *Homonym notes:* handles are per-instance unique but **not cross-platform identity**
  (`@demo.sleuth` on bsky ≠ same human on mastodon). Corroborate via linked website / ORCID /
  GitHub profile URL before merging; display per-instance findings separately (our finding
  `value` already prefixes site name — keep that).

---

## 6. Username lane (existing + dataset shape)

| Lane | Input → Output | Free cap (checked 2026-10-05) | Key model | Official docs |
|---|---|---|---|---|
| **Sherlock `username_probe` (ours, live)** | handle → `presence[{site: url}]` (found/not-found/error per site) | **Keyless. ≤30 plain GETs/run, 10s timeout, 1 req/2s pacing (~60s worst case), 24h sqlite cache.** Measured 2026-10-05: `octocat` 9/30 hits; random handle 0/30 (title+handle gates kill soft-404s). | Keyless (own compute only) | Local: `server/adapters/username_probe.py` ; behavior spec `docs/LIVE.md` (2026-10-05) |
| **WhatsMyName dataset (shape only)** | handle → per-site presence spec | **Dataset is free data (CC BY-SA 4.0 — do NOT vendor wholesale).** No checker scripts since May 2023; site https://whatsmyname.app is manual. Per-site entry shape: `{name, uri_check` with `{account}` slot, `e_code`, `e_string`, `m_code`, `m_string`, `category`, `valid`/`known` flags} (~700 sites). | Keyless (data file; our own tiny fixture list, MIT, mirrors field names only) | Dataset https://github.com/WebBreacher/WhatsMyName/blob/main/wmn-data.json ; schema https://github.com/WebBreacher/WhatsMyName/blob/main/wmn-data-schema.json ; site https://whatsmyname.app/ |

**Grade — username.**
- *Product-fit:* **server-side keyless default** (already shipped). WMN shape informs future site
  entries (`e_string/m_string` discipline → our `classify_live_response` markers + title gate).
  Never vendor `wmn-data.json` (share-alike); keep our 30-shape curated list.
- *IN-jurisdiction:* handle-presence is public-fact probing (low friction) but aggregation across
  30–700 sites can de-anonymize → demo-scale only (one handle/invocation, cached 24h, no bulk
  enumeration loops — already a hard guardrail in `docs/LIVE.md` §4).
- *Homonym notes:* same handle ≠ same person (squatting, name reuse). Confidence caps at `medium`
  even multi-site; `high` never from presence alone. Title-must-name-handle gate (added after
  6-false-hit measurement) is the anti-homonym control — keep it.

---

## Lane matrix (entity × lane → method + cap + key model)

Legend: ✅ default-on (keyless, server) · 🔑 BYOK optional (per-user key) · 👤 client-side/human ·
❌ excluded. Caps as of 2026-10-05.

| Entity ↓ / Lane → | Web search | Scholar | Company | Domain/infra | Social-public | Username |
|---|---|---|---|---|---|---|
| **Person** | 🔑 Brave $5 credit/mo (~1k q) / Serper 2.5k free; per-user key; corroborate ×2 (homonym risk) | ✅ ORCID anon 25k/d/IP + Crossref-polite keyless + S2 100/5min keyless; 🔑 OpenAlex $1/d key; IRINS 👤 link-out | 👤 MCA/OC-officers (personal-data care); ✅ GLEIF keyless 60/min for org-tie | ✅ RDAP keyless (redacted); 🔑 GH-search 10/min code (BYOK) for leak-strings | ✅ **Bluesky keyless 3k/5min + Mastodon keyless 300/5min** (top picks); 🔑 Graph 200/hr/token; ❌ X/Nitter dead | ✅ probe 30 GETs keyless, cached; WMN shape-only (CC BY-SA, no vendor) |
| **Company** | 🔑 Brave/Serper as above (news/filings discovery) | ✅ Crossref (company pubs) / OpenAlex ROR-affiliation 🔑 | ✅ **GLEIF keyless 60/min** (default); 🔑 OC 200/mo+50/d BYOK; 👤 MCA CAPTCHA human; ❌ Clearbit paid-only | ✅ crt.sh keyless + DNS keyless + RDAP keyless (infra of company domains) | ✅ Bluesky/Mastodon org accounts keyless; 🔑 Graph Business Discovery 200/hr/token | ✅ handle-presence for brand handles (same probe) |
| **Domain** | 🔑 Brave/Serper (indexing/mentions) | n/a (weak fit) | ✅ GLEIF↔domain via org; 👤 MCA for .in owners | ✅ **crt.sh keyless + DNS keyless + RDAP keyless** (default triple); 🔑 Shodan limited-credits BYOK + Censys ~250/mo BYOK + GH-search BYOK | ✅ Bluesky/Mastodon link-mentions keyless (social footprint of domain) | ✅ probe for domain-named handles; WMN shape |

**Read across:** keyless defaults cover person+company+domain with zero secrets
(ORCID/Crossref/S2/GLEIF/crt.sh/DNS/RDAP/Bluesky/Mastodon/probe = 9 keyless lanes).
BYOK lanes (Brave/Serper/OpenAlex/OC/Shodan/Censys/GitHub/Graph) activate only with an operator
key + 24h cache. MCA/IRINS are human link-outs. Bing/X-Nitter/Clearbit/breach-PII are out.

---

## 7. Permanently EXCLUDED (listed only to exclude — no instructions)

Per AGENTS.md §0.2 + §8/§8b and the task's exclusion rule (breach creds, face-ID,
login-bypass, phone/address hunting). Each with reason:

1. **Breach-password / credential data** (incl. HIBP live email lookup, stealer logs, password
   range beyond k-anon pattern study) — PII + credential surface; interface pattern only
   (already in `research-osint-2.md` §b). No live breach lane.
2. **Face-ID / biometric identification** (any face-search or face-match service) — biometric PII,
   no public-data basis for a demo; excluded outright.
3. **Login/session/cookie bypass** (Osintgram/Toutatis/instagrapi-login/gallery-dl-cookie mode,
   password MCPs, form-POST probing, Holehe reset-flows, GHunt Google sessions) — ToS + credential
   risk; public-GET-only rule stands.
4. **Phone/address-to-account hunting** (Epieos-full, MailAccess, Blackbird-email, SherlockEye
   reverse-PII, any email/phone→identity lane) — direct PII lookup; permanently out.
5. **Bulk scraping / SERP scraping** (DDG-HTML, Google-HTML, IG-undocumented scraping, bulk
   enumeration loops, nuclei active scanning) — ToS/abuse surface; official APIs or single-shot
   public GET only.
6. **Dead/paid-only passed off as free** (Bing Search API retired 2025-08-11; X API no free tier;
   Nitter/XCancel dead + legally tainted; Clearbit standalone APIs deprecated, no free tier) —
   excluded to keep "free" honest.

---

## 8. DPDP Act (India) cross-cutting note (all lanes)

- **Basis:** Digital Personal Data Protection Act, 2023 (in force 2023-08-11; Rules 2025).
  Applies to digital personal data in India + extraterritorial processing for Indian principals.
- **What we rely on:** publicly available personal data (self-published profiles, public records,
  registry data) used for a **stated, limited purpose** (open-source research brief) — with
  **purpose limitation** (no repurposing, no bulk harvesting), **accuracy/correction handling**,
  and **erasure on Data Principal request** (delete cached findings + suppress re-fetch; 24h TTL
  bounds retention by default).
- **Highest-care fields:** officer/director names (company lane), registrant contacts (infra lane
  — prefer redacted RDAP), non-public-figure social content (social lane). Demo scale
  (single-target, cached, no enumeration) is itself a safeguard — keep it.
- **Not legal advice.** Lawyer review is out of scope per AGENTS.md §8 (TODO, not half-built).

## 9. Entity-resolution rule (homonyms — all lanes)

1. **Bare name/handle = candidate, never identity** (`low` max).
2. **Pinned ID = medium max:** ORCID iD, LEI, CIN (`jurisdiction+number`), DID, domain+RDAP-date.
3. **Merge across lanes only on shared pin** (e.g. same ORCID on paper + IRINS; same LEI on GLEIF
   + registry filing; same domain in cert + RDAP + DNS).
4. **Never `high`** from metadata/probe aggregation alone (human verification required).
5. Display per-source findings separately (existing finding schema already does this).

---

## Dated sources (all checked 2026-10-05 unless noted)

- Brave: https://brave.com/search/api/ ; https://api-dashboard.search.brave.com/documentation/pricing
  ($5 credit/mo; $5/1,000 Search; 50 qps capacity) + retirement-of-free-plan reports
  (firecrawl blog, reddit r/openclaw, scrapegraphai — Feb 2026 change, secondary).
- Bing retirement: https://learn.microsoft.com/en-us/answers/questions/5538194/
  + https://ppc.land/microsoft-ends-bing-search-apis-on-august-11-alternative-costs-40-483-more/
  (retired 2025-08-11; old S1 $25/1k, S3 $6/1k) + old pricing
  https://azure.microsoft.com/en-us/pricing/details/cognitive-services/bing-entity-search-api/.
- Serper: https://serper.dev/ + https://apiserpent.com/blog/serper-pricing-credits-explained
  (2,500 free, then $50/50k) + https://scrappa.co/serper-alternative (Jun 2026 re-confirm).
- DDG: https://api.duckduckgo.com/api (Instant Answers only) +
  https://duckduckgo.com/duckduckgo-help-pages/features/instant-answers-and-other-features.
- ORCID quota table (fetched 2026-10-05):
  https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/
  (anon 12/s+40 burst+25k/d/IP; public 12/s+40+100k/d/client; member 24/s+no quota; non-commercial ToS).
- OpenAlex: https://help.openalex.org/api/authentication/ +
  https://help.openalex.org/access/pricing/ ($1/day free) +
  https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/ (Feb 2026 key mandate).
- Crossref: https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
  + https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/ (polite pool via mailto).
- Semantic Scholar: https://www.semanticscholar.org/product/api (key 1 rps; keyless 100/5 min per
  libguides/dev.to secondary consensus).
- IRINS: https://irins.inflibnet.ac.in/ + https://irins.inflibnet.ac.in/about.
- OpenCorporates: https://api.opencorporates.com/documentation/API-Reference (v0.4.8: key required;
  default 200/mo + 50/day — fetched 2026-10-05) + https://opencorporates.com/pricing/.
- GLEIF: https://www.gleif.org/en/lei-data/gleif-api + https://api.gleif.org/docs +
  Postman mirror (60 req/min/user, free, no key — secondary mirror of official limit).
- Clearbit: https://clearbit.com/ (HubSpot notice) + deprecation roundups (derrick-app, cleanlist.ai,
  landbase, datamagnet — Logo API sunset Dec 2024/2025, Enrichment via HubSpot credits ~$0.01).
- MCA: https://www.mca.gov.in/ (Services → View Company/LLP Master Data, CAPTCHA — portal pattern,
  guides secondary: registerkaro, efilingcompany).
- crt.sh: https://crt.sh/ + community norm (~1 req/5s, no official cap — dev.to/secbyte/parse.bot
  secondary) + local measurement 502 on 2026-10-05 (`docs/LIVE.md` §2).
- RDAP: https://www.iana.org/assignments/rdap-dns + https://about.rdap.org/ (429 note) +
  https://www.rfc-editor.org/info/rfc9224/.
- Shodan: https://developer.shodan.io/api/requirements (free key w/ account) +
  https://account.shodan.io/billing + https://help.shodan.io/the-basics/credit-types-explained.
- Censys: https://search.censys.io/api + https://censys.com/resources/pricing/ +
  https://docs.censys.com/reference/get-started (free ≈250/mo secondary consensus).
- GitHub: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
  (60/hr anon, 5k/hr authed, search 30/min) +
  https://github.blog/changelog/2023-03-10-changes-to-the-code-search-api/ (code search 10/min).
- Graph/oEmbed: https://developers.facebook.com/docs/instagram-platform/ +
  https://developers.facebook.com/documentation/instagram-platform/oembed +
  https://make.wordpress.org/core/2020/09/22/facebook-and-instagram-embeds-to-be-deprecated-october-24th/
  (2020 token mandate) + tokenless-restore report 2025 (wpmayor, secondary — verify at build).
- Nitter dead: https://github.com/zedeus/nitter (2026-08-24 C&D note) +
  https://techcrunch.com/2026/08/25/x-sends-cease-and-desist-to-open-source-project-nitter-over-alleged-scraping/ +
  https://en.wikipedia.org/wiki/Nitter.
- Bluesky: https://docs.bsky.app + https://bsky.network/docs/rate-limits/
  (3k/5min/IP, 5k pts/hr, 35k pts/day) + https://endpoints.bsky.app/.
- Mastodon: https://docs.joinmastodon.org/api/rate-limits/ (300/5min, fetched 2026-10-05) +
  https://docs.joinmastodon.org/methods/search/ + https://docs.joinmastodon.org/client/public/.
- WMN: https://github.com/WebBreacher/WhatsMyName/blob/main/wmn-data.json (~700 sites) +
  schema https://github.com/WebBreacher/WhatsMyName/blob/main/wmn-data-schema.json +
  https://whatsmyname.app/ ; license CC BY-SA 4.0 per repo LICENSE.md (via `research-osint-2.md` 2026-10-04).
- Local: `server/adapters/username_probe.py`, `server/adapters/domain_intel.py`, `docs/LIVE.md`
  (measured 2026-10-05: `octocat` 9/30, random 0/30, crt.sh 502).
- DPDP Act: https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf
  (Act text: erasure-on-request §12-14 pattern) + https://fpf.org/blog/the-digital-personal-data-protection-act-of-india-explained/.

## Link health (checked 2026-10-05)

- All `docs.*` / `info.*` / `api.*` official links above returned 200 on webfetch except
  `api.gleif.org/docs` (not directly fetched — reached via gleif.org landing link instead;
  noted, not a failure) and `crt.sh/` (empty-page service, query-shape URL is the real interface).
- `api.github.com` not re-fetched here (done 2026-10-04 in `research-osint-2.md` — not repeated).
- If any vendor link 404s/terms-change later (Brave/OpenAlex precedent), treat as stale signal and
  re-fetch before wiring — not a Sherlock failure.

## Compliance footer

- Public info only. No session cookies, tokens, passwords, bypass instructions, or live targets.
  No secrets in this file by construction (no keys — only `DUMMY_...` policy + BYOK design).
- Example entities only; no real-person PII. Excluded lanes (§7) listed with reasons, no how-to.
- No contradiction to `research-osint.md`, `research-osint-2.md`, or AGENTS.md §0/§8b on re-check
  2026-10-05; no AGENTS.md update required.
