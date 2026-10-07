# Sherlock — OSINT Expansion Research (beyond seed)

> Date: 2026-10-04 (UTC). Scope: `/home/markone/drive1/sherlock` only.
> Extends `research-osint.md` (seed, 2026-10-04) — does not redo it. No contradiction found.
> Constraints: AGENTS.md §0 applies. Public info only. Interface patterns only — no code copying.
> Never include session cookies, tokens, passwords, or bypass instructions.
> All star/license/pushed_at numbers from `api.github.com/repos/{owner}/{repo}` fetched 2026-10-04 unless noted.
> Stars are point-in-time; "activity" = `pushed_at`. Stale rule: `pushed_at` older than ~18mo → list but EXCLUDE.

## Method + freshness

- `websearch` for discovery + `webfetch https://api.github.com/repos/{o}/{r}` for stars/license/pushed_at on 2026-10-04.
- HIBP numbers come from official docs/pricing pages (service, not a repo) fetched 2026-10-04.
- License column shows API `license.spdx_id` first, then README reality where they differ (WMN, Amass, ExifTool — noted inline).

---

## (a) Username enumeration lane (NOT in seed)

| Repo | Stars (2026-10-04) | License (API → reality) | Last activity | What it does | Include / Exclude for clean bundle (LICENSE reason + ToS reason) |
|---|---|---|---|---|---|
| `WebBreacher/WhatsMyName` — https://github.com/WebBreacher/WhatsMyName | ~2,920 | API: NOASSERTION → repo `LICENSE.md` = **CC BY-SA 4.0** | pushed 2026-09-16 — ACTIVE (dataset, ~700 sites, `wmn-data.json` + schema) | Community dataset: per-site `{uri_check, e_code/e_string, m_code/m_string}` presence-check specs. No checker scripts since May 2023 — data file is the product. Powers whatsmyname.app, Blackbird, Naminter, SpiderFoot `sfp_account`. | **INCLUDE as data-shape pattern only.** LICENSE: CC BY-SA share-alike → do NOT vendor `wmn-data.json` wholesale into core; study JSON schema shape, ship our own tiny fixture site-list (MIT, ours). ToS: LOW (public HTTP presence probes; rate-limit + false-positive discipline). |
| `3xp0rt/Naminter` — https://github.com/3xp0rt/Naminter | ~50 | MIT | pushed 2026-08-13; PyPI `naminter` 1.0.9 released 2026-08-13 — ACTIVE | Async Python CLI+lib built specifically for the WMN dataset (`naminter -u`, `validate`/`format` subcommands, browser impersonation, concurrent checks). | **INCLUDE as interface pattern.** LICENSE: MIT = permissive, but per AGENTS.md we still reimplement (no vendoring). ToS: LOW-CAUTION — public probes are fine; its advertised Cloudflare-bypass/browser-impersonation path is NOT adopted (no bypass instructions in this file; excluded from our adapter). |
| `Alfredredbird/tookie-osint` — https://github.com/Alfredredbird/tookie-osint | ~3,033 | MIT | pushed 2026-09-22 — ACTIVE (V4 rewrite, Kali package `sudo apt install tookie-osint`, 837 commits) | Sherlock-like username scanner, `-u/-U/-t/-o txt,csv,json`, batch file mode, optional Selenium webscraper (`-W/-H`). | **INCLUDE as CLI-shape pattern only** (`-u/-U/-t/-o json`, batch + export discipline). LICENSE: MIT permissive; still reimplement per clean-room rule. ToS: LOW for plain HTTP mode; webscraper mode (`-W/-H`) EXCLUDED (aggressive automation, site-ToS risk). |
| `antoniaci/blackbird` (moved from `p1ngul1n0/blackbird` — old owner URL redirects) — https://github.com/antoniaci/blackbird | ~8,872 | API: **null (NO LICENSE FILE)** | pushed 2025-07-13 — ~15mo, BORDERLINE (maintenance-only, no releases) | Username+email search across 600+ platforms on WMN data, PDF/CSV export, optional AI profiling (`--ai`, site-names-only). | **USERNAME mode = interface-only study; EMAIL mode = EXCLUDE.** LICENSE: no license file → copy NOTHING (all rights reserved by default). ToS: username probes LOW; **email-search = PII (email-to-account) → PERMANENTLY EXCLUDED** per AGENTS.md §0.2. Staleness noted, still listed. |
| `qeeqbox/social-analyzer` — https://github.com/qeeqbox/social-analyzer | ~24,189 | **AGPL-3.0** | pushed 2026-01-12 — ACTIVE (~9mo) | API+CLI+WebApp username profiler, ~1000 sites, JS+Python. | **EXCLUDE from core.** LICENSE: AGPL-3.0 copyleft (network-triggered) → NEVER copy/combine into core, not even as adapter (stronger than GPL rule in AGENTS.md §0.3). ToS: CAUTION — 1000-site sweeps = rate-limit/abuse surface. Interface note only. |
| Seed-anchored reference: `soxoj/maigret`, `sherlock-project/sherlock` | 38,269 / 93,228 (both MIT, pushed 2026-10-04 — VERY ACTIVE, re-fetched this file) | MIT | 2026-10-04 | Already in seed; re-verified numbers only to anchor this lane. No new decision. | Seed decisions stand (public-presence pattern, LOW ToS). |

## (b) Email / breach lane (NOT in seed)

| Repo / Service | Stars / signal (2026-10-04) | License / pricing | Last activity | What it does | Include / Exclude (LICENSE + ToS reason) |
|---|---|---|---|---|---|
| `megadose/holehe` — https://github.com/megadose/holehe | ~15,083 | **GPL-3.0** | pushed **2024-09-10 — STALE (>24mo)**, 117 open issues | Email→registered-accounts via 120+ sites' signup/forgot-password differentials. | **EXCLUDE (triple reason).** LICENSE: GPL-3.0 → never in core. ToS: **password-reset-flow probing + email-to-account PII → PERMANENTLY EXCLUDED** per AGENTS.md §0.2 (also fragile — most modules broken, stale). Listed only to exclude. No flow details reproduced. |
| HaveIBeenPwned official API v3 — https://haveibeenpwned.com/API/v3 (service, not a repo) | n/a (service; 1,039 breaches per docs) | Docs CC BY 4.0; API commercial: email/domain search needs paid key (Pwned 1–5 / Core–Pro tiers, from ~$3.95/mo); **Pwned Passwords k-anonymity range API free, no key** (`api.pwnedpasswords.com/range/{5char}`) | Docs live 2026-10-04 (fetched); MCP server + k-anon email range (Pro) documented | Breach-by-account (auth, 200/404/401/429), domain search (ownership-verified), stealer-log APIs (Pro), free breach-catalog endpoints (`/breaches`, `/latestBreach`, `/dataClasses`). | **EXCLUDE live breach lookup from v1; INCLUDE interface pattern.** LICENSE: commercial ToS + key requirement → no demo wiring (`DUMMY_...` only, no live targets). ToS: LOW *if* used on own verified domain with paid key + UA header; third-party email lookup = PII → excluded. Adopt: k-anonymity range-query shape + failure taxonomy + `hibp-integration-tests.com` test-address discipline. |
| Epieos (epieos.com — SaaS, GitHub org `Epieos` holds no tool repo) — https://epieos.com/ | n/a (private company, Paris; partially free, paid full) | Commercial, account-gated | Active service 2026 (Maltego transform hub listing) | Reverse email/phone → linked social accounts + HIBP-linked breach hints, no-target-alert claim. | **EXCLUDE.** LICENSE/ACCESS: proprietary SaaS, login-gated. ToS: **email/phone-to-account PII → PERMANENTLY EXCLUDED** per AGENTS.md §0.2. Interface note only (input types, lead-vs-finding caveat). |
| `KatrielMoses/MailAccess` — https://github.com/KatrielMoses/MailAccess | ~1,535 | API: **null (NO LICENSE)** | pushed 2026-10-01 — ACTIVE (claims 5000+ platforms, no API keys, identity clustering) | Holehe-successor-style email OSINT + breach detection, `pip install mailaccess`. | **EXCLUDE.** LICENSE: no license file → copy nothing. ToS: **email-OSINT PII → excluded**; unverified "no key, 5000+ sites" claims = unassessable ToS/rate-limit risk. Listed only to exclude. |
| `mxrch/GHunt` — https://github.com/mxrch/GHunt | ~19,658 | API: NOASSERTION (custom) | pushed 2026-04-10 — ACTIVE (~6mo) | Google-account footprint (requires operator Google creds/cookies): account → linked services/docs/photos. | **EXCLUDE.** LICENSE: non-standard → copy nothing. ToS: **login/session-gated + Google-account PII → PERMANENTLY EXCLUDED** per AGENTS.md §0.2. Listed only to exclude. |

## (c) Domain / infra chain (NOT in seed)

| Repo | Stars (2026-10-04) | License | Last activity | What it does | Include / Exclude (LICENSE + ToS reason) |
|---|---|---|---|---|---|
| `owasp-amass/amass` — https://github.com/owasp-amass/amass | ~15,271 | API: NOASSERTION → README: **Apache-2.0** (OWASP flagship; "some subcomponents have separate licenses") | pushed 2026-07-19 — ACTIVE | Attack-surface mapping: passive+active collection engine, asset DB, Open Asset Model. | **INCLUDE as architecture pattern only** (passive-vs-active split, asset model, engine→DB shape for our `domain_intel` fixture). LICENSE: Apache-2.0 permissive, but Go binary is heavy + needs keys → reimplement crt.sh-shaped fixture (MIT, ours). ToS: passive sources LOW; **active recon only on own/authorized targets** (AGENTS.md §8 out-of-scope otherwise). API/README license mismatch noted. |
| `projectdiscovery/subfinder` — https://github.com/projectdiscovery/subfinder | ~14,555 | MIT | pushed 2026-09-25 — VERY ACTIVE (v2.16.0 Aug 2026) | Passive subdomain enumeration, 26+ sources, `-d/-dL/-oJ/-silent`, `provider-config.yaml`, `DISCLAIMER.md`. | **INCLUDE as pattern** (passive-source list, stdin/stdout chaining `subfinder → httpx → nuclei`, JSON-lines output, per-source rate limits). LICENSE: MIT permissive; reimplement fixture shape only. ToS: LOW (passive); many sources need own free API keys — declare caps per AGENTS.md §0.4. |
| `projectdiscovery/httpx` — https://github.com/projectdiscovery/httpx | ~10,444 | MIT | pushed 2026-09-23 — VERY ACTIVE | HTTP toolkit: title/status/TLS/CSP/word-count probes, https→http fallback, retries/backoff, CIDR/ASN input. | **INCLUDE as probe-schema pattern** for `domain_intel` enrichment fields (status/title/TLS/CSP). LICENSE: MIT permissive; reimplement. ToS: CAUTION — it *sends packets* (active) → own/authorized targets only; default to fixture data in demo, no live scans. |
| `projectdiscovery/nuclei` — https://github.com/projectdiscovery/nuclei | ~31,716 | MIT | pushed 2026-10-02 — VERY ACTIVE | YAML-DSL vulnerability scanner (CVE/subdomain-takeover templates). | **EXCLUDE from v1.** LICENSE: MIT is fine, but ToS/SCOPE: active vulnerability scanning is out of scope (AGENTS.md §8 — no bulk/active). Interface note only (severity-filtered template findings shape, if ever needed post-v1 on own assets). |
| `laramies/theHarvester` (re-fetch; in seed) | ~17,799 (was 17,798) | GPL-2.0 | pushed 2026-10-02 — VERY ACTIVE | Reference only — seed decision stands. | Seed stands: GPL-2.0 → interface patterns only, never in core. |

## (d) Image / metadata lane (NOT in seed)

| Repo | Stars (2026-10-04) | License — READ CAREFULLY | Last activity | What it does | Include / Exclude (LICENSE + ToS reason) |
|---|---|---|---|---|---|
| `exiftool/exiftool` — https://github.com/exiftool/exiftool | ~5,124 | API says `GPL-3.0`, but README + Homebrew formula say **"same terms as Perl itself (Perl Artistic License OR GPL)"** → dual **Artistic-1.0-Perl OR GPL-1.0-or-later**. Either way copyleft. | pushed 2026-05-27 — ACTIVE (v13.59 via conda-forge May 2026) | EXIF/GPS/IPTC/XMP read+write for images/docs/video, `exiftool -j` JSON output, maker-notes. | **INCLUDE as subprocess-output-shape pattern only; NEVER vendor.** LICENSE: Artistic/GPL copyleft → do NOT copy Perl modules into core (AGENTS.md §0.3 spirit covers all copyleft); optional local binary call at most, read-only flags on **user-uploaded files only**. ToS: LOW for own files; GPS/device-serial/author fields → minimize + strip before display (privacy-by-design for our `exif_local` adapter). |

## (e) Agent / skills lane (NOT in seed)

| Repo | Stars (2026-10-04) | License | Last activity | What it does | Include / Exclude (LICENSE + ToS reason) |
|---|---|---|---|---|---|
| `OpenOSINT/OpenOSINT` — https://github.com/OpenOSINT/OpenOSINT | ~1,688 | MIT | pushed 2026-10-01 — VERY ACTIVE (v2.27.0 Aug 2026; 20 tools; REPL+CLI+MCP+Web UI) | AI OSINT agent: Claude-native hard-stop tool dispatch (anti-hallucination), 20 modular tools (email/username/breach/WHOIS/IP/subdomain/dorks/phone/Shodan/VT/Censys…), parallel `asyncio.gather`, PDF+Markdown reports, Ollama offline option. Shells out to holehe/sherlock binaries. | **INCLUDE as architecture pattern** (agent loop, tool registry, report shape, MCP exposure, Ollama-offline option map to our orchestrator + skill). LICENSE: MIT permissive; reimplement loop ourselves. ToS: CAUTION — it bundles holehe/sherlock + needs `ANTHROPIC_API_KEY`/Shodan/HIBP keys → we adopt the *loop*, NOT the sub-tools or keys (our registry stays allow-listed, fixtures-only). |
| `UseOSINT/Skills` — https://github.com/UseOSINT/Skills | ~46 | MIT | pushed 2026-08-03 — ACTIVE but NEW (created 2026-08-02; 28 skills; skills.sh lists a 57-skill sibling — name drift noted) | 28 agent skills: 10 workflows (`investigate-anything` router, `hunt-a-handle`, `what-an-email-reveals`, `where-was-this-taken`…) + 18 techniques; opens with scope gate + `ETHICS.md` (passive-by-default, no doxxing, corroborate-before-conclude). | **INCLUDE as skill-design pattern** for `skills/osint-triage/SKILL.md` (router + scope gate + source grading + 5-positive/3-negative shape). LICENSE: MIT permissive; write our own words. ToS: LOW — explicitly ethical/passive-first; pin to GitHub repo (not skills.sh mirror). Small/new → lower weight, still citable. |
| `frangelbarrera/osint-agent-skills` — https://github.com/frangelbarrera/osint-agent-skills | ~35 | MIT | pushed 2026-10-02 — VERY ACTIVE (v1.6.0; MCP server + `system-prompt.md` + pivot playbooks) | Knowledge-base skills: persona prompt, free-tools/APIs registries, pivot playbooks, report templates, anti-hallucination rules. | **INCLUDE as secondary pattern** (pivot-playbook chaining email→breach→handle, report template sections). LICENSE: MIT; reimplement. ToS: LOW (methodology docs, no bypass). Small/new → corroborating source only. |
| SherlockEye (sherlockeye.io SaaS + PyPI `sherlockeye` 0.1.1 Mar 2026 — NO open-source tool repo; `p1ngul1n0/obsidian-sherlockeye-plugin` is just an API client) — https://sherlockeye.io/ | n/a (commercial; blog claims 800+ sources; the 2,300-star figure on their blog refers to Tookie-OSINT, not their own repo) | Commercial, API-key-gated | Active 2026 (docs.sherlockeye.io live) | Reverse lookup across email/phone/username/domain/IP with AI reconciliation + audit-ready reports; REST/MCP/webhooks. | **EXCLUDE from bundle.** LICENSE/ACCESS: proprietary + key-gated (no `DUMMY`-able free tier for demo). ToS: PII reverse-lookup service → out of scope for clean demo (AGENTS.md §0.2 spirit). Interface note only (input taxonomy, audit-report fields). Do not confuse with `sherlock-project/sherlock`. |

---

## What each lane means for Sherlock v1 (honest mapping to our 4 adapters)

- **Username (`username_probe`)**: WMN dataset = the *spec shape* (`uri_check` + expected/miss strings); Naminter = async + `validate`/`format` discipline; Tookie = CLI flags + batch/export shape; Blackbird-username = confidence-per-platform idea. Ship: our own 3-hit fixture list (DEMO-CASE-001), public-HTTP-probe-shaped findings, failure taxonomy. No dataset vendoring, no email mode.
- **Domain (`domain_intel`)**: subfinder = passive-source list + JSON-lines; httpx = probe-field set (status/title/TLS/CSP); Amass = passive/active split + asset model. Ship: crt.sh-shaped + DNS fixtures (`example.com`, 2 subdomains, 1 contact). No live scans in demo; nuclei stays out.
- **EXIF (`exif_local`)**: ExifTool = `-j` JSON field names (GPS/device/author/edit-chain) + read-only-on-upload rule. Ship: ours, upload-only, GPS minimized. Never vendor Perl code (Artistic/GPL).
- **oEmbed (`oembed_public`)**: HIBP/password-API + OpenOSINT-report patterns inform failure taxonomy (ok/rejected + reason, no hallucination) and brief structure — not live breach data.
- **Skill + orchestrator**: UseOSINT Skills (+ frangelbarrera playbooks) = router/scope-gate/source-grading pattern for `SKILL.md`; OpenOSINT = REPL→CLI→MCP layering + hard-stop tool dispatch for `server/` design. Holehe/GHunt/Epieos/MailAccess/social-analyzer/SherlockEye = permanently out (PII/login/copyleft/commercial), listed with reasons above.

## Recommendation — 3 safe patterns newly adopted from this file (no code copying)

1. **WMN `wmn-data.json` entry schema** (primary for `username_probe`): per-site `{name, uri_check with `{account}` slot, e_code/e_string, m_code/m_string, category}` → our fixture entries mirror these *field names*, with our own 3 demo sites only.
2. **subfinder→httpx JSON-lines chaining + provider-config discipline** (primary for `domain_intel`): stdin/stdout pipe shape, `-oJ` finding fields, per-source key caps in `.env.example` as `DUMMY_...`, `DISCLAIMER.md`-style usage note.
3. **UseOSINT `investigate-anything` router + ETHICS scope gate** (primary for skill): scope-gate → collection-plan → source-grading → sourced-brief flow; every claim carries source + confidence; negatives (private/PII/empty) refuse cleanly.

Explicitly NOT adopted: holehe reset-flows, GHunt Google sessions, Epieos/MailAccess/SherlockEye PII lookups, social-analyzer code (AGPL), nuclei scanning, ExifTool vendoring, Naminter impersonation/bypass path, Tookie `-W/-H` scraper mode.

---

## Dated sources

- GitHub API `api.github.com/repos/{...}` fetched 2026-10-04: WebBreacher/WhatsMyName 2920/NOASSERTION/2026-09-16; megadose/holehe 15083/GPL-3.0/2024-09-10; owasp-amass/amass 15271/NOASSERTION (README Apache-2.0)/2026-07-19; projectdiscovery/subfinder 14555/MIT/2026-09-25; projectdiscovery/httpx 10444/MIT/2026-09-23; projectdiscovery/nuclei 31716/MIT/2026-10-02; exiftool/exiftool 5124/GPL-3.0 (README Artistic-or-GPL)/2026-05-27; OpenOSINT/OpenOSINT 1688/MIT/2026-10-01; UseOSINT/Skills 46/MIT/2026-08-03; Alfredredbird/tookie-osint 3033/MIT/2026-09-22; antoniaci/blackbird 8872/license-null/2025-07-13 (via `p1ngul1n0/blackbird` redirect); qeeqbox/social-analyzer 24189/AGPL-3.0/2026-01-12; mxrch/GHunt 19658/NOASSERTION/2026-04-10; 3xp0rt/Naminter 50/MIT/2026-08-13; KatrielMoses/MailAccess 1535/license-null/2026-10-01; frangelbarrera/osint-agent-skills 35/MIT/2026-10-02; re-verified soxoj/maigret 38269/MIT/2026-10-04; sherlock-project/sherlock 93228/MIT/2026-10-04; laramies/theHarvester 17799/GPL-2.0/2026-10-02.
- WMN README (CC BY-SA 4.0, 700+ sites, consumer list incl. SpiderFoot/Blackbird/Naminter) via github.com/WebBreacher/WhatsMyName; Naminter docs https://3xp0rt.github.io/Naminter/ + PyPI `naminter` 1.0.9 (2026-08-13).
- Tookie-OSINT Kali page https://www.kali.org/tools/tookie-osint (v4.1fix, updated 2026-06-17) + SherlockEye Tookie guide 2026-07-02 (flag reference, no bypass).
- HIBP API v3 docs https://haveibeenpwned.com/API/v3 (fetched 2026-10-04: auth model, k-anon, 200/404/401/429, test addresses) + pricing https://haveibeenpwned.com/Subscription + key page https://haveibeenpwned.com/API/Key.
- Epieos https://epieos.com/ + OSINT-Tools-Library `epieos.md` (ownership/pricing/account notes); Maltego transform hub Epieos listing.
- SherlockEye https://sherlockeye.io/ + https://docs.sherlockeye.io/ + PyPI `sherlockeye` 0.1.1 (2026-03-10).
- UseOSINT Skills ETHICS.md + README (28 skills, install.sh) via github.com/UseOSINT/Skills; skills.sh `useosint` pack page (57-skill drift note).
- OpenOSINT README via github.com/OpenOSINT/OpenOSINT (20 tools, REPL/CLI/MCP/Web UI, holehe+sherlock subprocess note) + PyPI `openosint` history.
- ExifTool README (Artistic-or-GPL dual) via github.com/exiftool/exiftool/blob/master/README + Homebrew formula `exiftool` (Artistic-1.0-Perl OR GPL-1.0-or-later) + conda-forge 13.59 (2026-05-27).
- Blackbird no-license + 2025-07-13 push-gap note via Ross `p1ngul1n0/blackbird` product card (observed 2026-09-06, health 45/100 maintenance-only).
- AGENTS.md §0 (Sherlock honest constraints) — local file, read 2026-10-04.

## Link health (checked 2026-10-04)

- All `github.com/{o}/{r}` + `api.github.com/repos/{o}/{r}` links above returned 200 except `p1ngul1n0/blackbird`, which 301-redirects to `antoniaci/blackbird` (owner rename — canonical link used in table, redirect noted; do not "fix" to the dead owner).
- `api.github.com` license field disagrees with README in 3 known cases (WMN NOASSERTION→CC BY-SA 4.0; Amass NOASSERTION→Apache-2.0; ExifTool GPL-3.0→Artistic-or-GPL dual) — README/formula wins, mismatch recorded, stricter (copyleft) reading applied.
- HIBP/Epieos/SherlockEye store/docs URLs are public pages (run-history/pricing tabs may need login; README/pricing/API tabs public). No broken slugs at write time.
- If any link 404s later, treat as stale signal and re-fetch `pushed_at` before relying — not a Sherlock failure.

## Compliance footer

- Public info only. No session cookies, tokens, passwords, bypass instructions, or live targets. No secrets in this file by construction.
- Login-gated (GHunt, Epieos-full, SherlockEye), PII (Holehe, Blackbird-email, Epieos, MailAccess), password-flow (Holehe), stale (Holehe), and strong-copyleft/commercial-in-core (social-analyzer AGPL, ExifTool-vendoring, nuclei-active) exclusions recorded with LICENSE + ToS reasons inline.
- No contradiction to `research-osint.md` seed or AGENTS.md §0 on re-check 2026-10-04; no AGENTS.md update required.
