---
name: osint-triage
description: Entity-steered public OSINT triage (person names). Numbered playbook normalize-query-fetch-correlate-present; refuses login-gated, PII, and low-evidence claims.
---

# osint-triage skill — entity pipeline playbook (Phase 1)

> Clean-room OSINT orchestrator skill. Public sources only. No logins,
> no breach creds, no face-ID, no login/paywall bypass, no phone/address
> hunting. Published contacts only (with source link). Fake fixtures +
> DUMMY secrets. No network in tests. Never hallucinate — refuse with reason.
>
> Scope: all entities, all public pages. Front doors: plugin + dashboard +
> local connector. Server orchestrates; model search retrieves; code judges.
>
> Compatibility: DEMO-CASE-001 lane tools (`probe_username`,
> `intel_domain`, `save_reel`, `search_memory`, `case_summary`) remain.
> This playbook adds the Phase-1 person-entity path
> (`entity_search` → query set → fetch → `score_findings`/`refute` →
> `build_entity_cases`). All worked examples below use Kotabagi-shaped
> DUMMY fixtures (R Kotabagi / R Kotabaghi, Example University / Another
> Institute, DUMMY ORCIDs `0000-0002-1825-0097` / `0000-0002-1825-0098`,
> `example.com` URLs only). No real-person PII.

## Numbered playbook (follow in order, no skipping)

### 1. Normalize via `entity_search`

Call `entity_search(name)` first. It validates (PII refusal, URL rejection,
throttle), runs `entity.normalize` + `entity.variants` (≤12 deterministic,
base first), fans out lanes, and homonym-splits via
`correlate.build_entity_cases` (clusters never merged).

```python
res = tools.entity_search("R Kotabagi", user_id="analyst-1")
# offline (SHERLOCK_LIVE unset): DUMMY/example fixtures + reason mentioning
# "offline fixture ... (SHERLOCK_LIVE unset; DUMMY/example only)".
# variants include "r kotabagi" and "r kotabaghi"; cases == 2.
```

Do not invent spelling variants by hand. Use the returned `variants`
for step 2. Empty/URL/PII input fails closed (see N1).

### 2. Run the literal query set: variants × quoted-name × `site:` operators

Build quoted exact-phrase queries from every variant (base first), then
cross with `site:` scoping and affiliation hints. Literal shapes only —
the model must emit these strings verbatim, never a paraphrase:

```
"R Kotabagi"
"R Kotabaghi"
"R Kotabagi" site:example.com
"R Kotabaghi" site:example.com
"R Kotabagi" "Example University"
"R Kotabaghi" "Another Institute"
"R Kotabagi" "Example University" site:example.com
"R Kotabaghi" "Another Institute" site:example.com
```

Quoting rule (matches `websearch.build_query`): strip internal quotes,
wrap each phrase in double quotes, append `site:<host>` verbatim, e.g.
`build_query("R Kotabagi", "", "example.com")` →
`"R Kotabagi" site:example.com`. Never query emails/phones (PII refusal).

### 3. Fetch top-N URLs (cap 5, public GET only)

Collect result URLs from lane outputs, keep `example.com`-subtree public
GET targets only, cap 5 (`tools._extract_urls`, `_MAX_PAGE_URLS = 5`).
Golden fetched set (all `example.com`, all public):

```
https://example.com/profiles/r-kotabagi
https://example.com/profiles/r-kotabaghi
https://example.com/papers/001
https://example.com/papers/002
```

Never fetch login-walled/paywalled/credentialed/private-host URLs (refuse
per N2). Never invent a URL — every claimed URL in step 4 must appear in
this fetched set or it is refused as `hallucinated_url`.

### 4. Submit ALL findings to correlate (score → refute)

Submit every model-brought fact — including weak ones — to intake.
Never filter before intake; filtering is code's job:

```python
scored = correlate.score_findings(findings)          # evidence_score each
verdict = correlate.refute(scored, fetched_urls)     # kept vs refused
cases = correlate.build_entity_cases(query, verdict["kept"], base_case_id)
```

- `score_findings`: base confidence (high 3 / medium 2 / low 1, 0 when
  unparsable) +1 corroborated (same exact fact from ≥2 sources, or same
  ORCID / affiliation / claimed URL in ≥2 findings) +1
  published-contact provenance. Pure, deterministic.
- `refute`: first-match reason order `unparsable` > `login_walled_claim`
  > `pii_excluded` > `hallucinated_url` > `insufficient_evidence`
  (unpublished contacts — CONTACT_TYPES without a source link — and any
  `evidence_score` below threshold 2). `fetched_urls=None` skips the URL
  check; always pass the real step-3 set to enforce it.
- `check_urls(findings, fetched_urls)` returns violations only; `[]`
  means zero hallucinated URLs.

### 5. Present the case file or state refusals/gaps

- When `kept` is non-empty: present per-candidate cases from
  `build_entity_cases` (separate candidates, affiliation + ORCID pins,
  lanes, confidence + source per finding). State which fetched URLs back
  which claims. Omit refused items; list their reason codes separately.
- When `kept` is empty or lanes missed: state the gap with reason
  (e.g. `no entity data for 'X' (...; no hallucination)`), zero invented
  findings, one public-only next step. Never merge candidates to fill a
  gap. Never present a contact without its publishing-page link.

## Homonym rule (separate candidates, never merge)

Same or variant spellings (`Kotabagi`/`Kotabaghi`) resolve to ONE
candidate ONLY when affiliation/location/ORCID signals agree. Different
non-empty affiliations, locations, or ORCID/email ids MUST split and
MUST NEVER merge — even when names match exactly. Empty signals never
force a split. `build_entity_cases` enforces this; the model must present
each cluster as its own `candidate-N` case and must never combine facts
across `Example University` and `Another Institute` (golden: 5 + 4
findings, zero cross-affiliation leakage, ORCID pins stay separate).

## Published-contacts rule (with source link or omit)

A contact (`contact`/`email`/`phone`/`published_contact`) is kept ONLY
when it carries its publishing-page URL — embedded in `value`
(`lab@example.com (published at https://example.com/profiles/r-kotabagi)`)
or in `url`/`source_url`/`link` — AND that URL is in the step-3 fetched
set. Otherwise it is refused as `insufficient_evidence` with detail
`unpublished contact without source link (omit or add publishing-page
URL)`. `@example.com` demo addresses are published contacts, never PII;
non-`@example.com` emails and `+`-prefixed phones are PII (see N1).
ORCID ids (`0000-...`) are never phones.

## Refusal scripts (copy verbatim, fill brackets)

### R1 — PII (email/phone-to-account)

> `{"status": "rejected", "reason": "PII excluded (non-public email/phone;
> published @example.com contacts only)", "findings": []}`
> I can't look up accounts by email or phone. If you have a public profile
> URL or a person name plus a public affiliation, I can run the entity
> playbook on public sources only.

### R2 — login-walled / private / paywalled (no bypass, ever)

> `{"status": "rejected", "reason": "login-walled/private claim refused
> (public sources only; no bypass)", "findings": []}`
> That page needs a login (or is private/paywalled), so I can't fetch it
> and won't work around the wall. Paste a public URL, or give me a public
> affiliation/ORCID to corroborate instead.

### R3 — low-evidence / hallucinated / unparsable

> `{"status": "ok", "reason": "kept 9, refused 5 (see reasons)",
> "refused": [{"reason": "insufficient_evidence"}, {"reason":
> "hallucinated_url"}, {"reason": "unparsable"}]}`
> I kept only corroborated public facts (score ≥ 2, URLs in the fetched
> set). The rest are refused with reason codes: single low-confidence
> source with no corroboration/provenance → `insufficient_evidence`;
> claimed URL not in the fetched set → `hallucinated_url`; missing
> type/value/source/confidence → `unparsable`. No invented findings.

## Positive cases (must succeed — Kotabagi-shaped DUMMY fixtures)

### P1 — normalize `R Kotabagi` → 2 homonym candidates

Input: `tools.entity_search("R Kotabagi", "analyst-1")` (offline,
`SHERLOCK_LIVE` unset).

Expected (verified by execution): `status ok`, `live False`, reason
mentions `offline fixture` + `SHERLOCK_LIVE unset`; `variants[0]` is
`r kotabagi`, variants include `r kotabagi` and `r kotabaghi`
(full list: `r kotabagi`, `r kotabagee`, `r kotabaghi`, `r kotabhagi`,
`kotabagi r`, `rr kotabagi`, `r kkotabagi`, `r kottabagi`, `r kotabbagi`,
`r kotabaggi`, ≤12, deterministic); `homonym_clusters == 2`,
affiliations `Example University` + `Another Institute`, never merged.

### P2 — literal query set builds quoted `site:` queries

Input: variants from P1 → emit the 8 literal strings in §2.

Expected (verified by execution): `websearch.build_query("R Kotabagi",
"", "example.com")` returns `"R Kotabagi" site:example.com`;
`build_query("R Kotabaghi", "Another Institute")` returns
`"R Kotabaghi" "Another Institute"`; internal quotes stripped
(`build_query('R "Kotabagi"')` → `"R Kotabagi"`). No email/phone query
ever emitted.

### P3 — fetch top-N URLs (cap 5, `example.com` only)

Input: lane findings containing 4 golden profile/paper URLs + 1
out-of-scope `https://evil.test/x` + 6 extra `example.com` dummies.

Expected (verified by execution): `tools._extract_urls(findings)` keeps
only `https://example.com/...` entries, caps at 5, drops `evil.test`;
golden run keeps exactly the 4 fetched URLs in §3 (all in
`demo-data/fixtures/golden_case.json` `fetched_urls`).

### P4 — submit ALL 14 golden findings → kept 9, refused 5

Input: `golden_case.json` `findings` (9 valid mixed-lane + 5 traps) and
`fetched_urls` (§3) → `score_findings` → `refute`.

Expected (verified by execution): evidence scores
`[2, 2, 2, 2, 3, 2, 2, 2, 2, 3, 3, 2, 1, 0]` (indices 0–13); kept 9
(values sorted in fixture `kept_values`); refused exactly
`9:pii_excluded`, `10:login_walled_claim`, `11:hallucinated_url`,
`12:insufficient_evidence`, `13:unparsable` with the pinned detail
strings. High-score traps (9, 10 score 3) are still refused — PII/login
gates outrank scores. `check_urls(kept, fetched)` is `[]`.

### P5 — present case file: 2 candidates, published contact kept

Input: P4 `kept` → `build_entity_cases("R Kotabagi", kept,
"ENTITY-r-kotabagi")`.

Expected (verified by execution): 2 cases —
`ENTITY-r-kotabagi:candidate-1` (5 findings, `Example University`,
lanes `page_reader`/`scholar`/`websearch`, includes published contact
`lab@example.com (published at
https://example.com/profiles/r-kotabagi)`) and
`ENTITY-r-kotabagi:candidate-2` (4 findings, `Another Institute`,
same 3 lanes). No case mixes affiliations; ORCID `...0097` only in
candidate-1, `...0098` only in candidate-2; invented URL
`999-unfetched-secret` appears nowhere. Matches
`golden_case.json` `expected.cases` exactly.

## Negative cases (must refuse or fail closed — same fixtures)

### N1 — PII trap refused (`pii_excluded`, even when high-confidence)

Inputs: `entity_search("jane.doe@gmail.com")` → rejected, zero findings;
`refute([{"type": "contact", "value": "r.kotabagi@gmail.com",
"source": "websearch", "confidence": "high"}], fetched)` → kept `[]`,
refused `pii_excluded` (score 3 but PII outranks score); phone
`+91 98200 12345` (bare or inside prose) → `pii_excluded`; ORCID
`0000-0002-1825-0097` alone is NOT PII (no `+`, `@example.com` allowed).

Expected: `status rejected` (tools) or `pii_excluded` (intake), zero
kept, script R1. Never enrich, never hallucinate an owner.

### N2 — login-walled claim refused (`login_walled_claim`, no bypass)

Inputs: finding `Full publication list — login required to view (private
profile) https://example.com/profiles/r-kotabagi` (medium, fetched URL
present, score 3) → refused `login_walled_claim`; `page_reader` on a
login form → `rejected ... login-walled`; any "log in as me / here are
my cookies" → rejected, creds never stored/echoed.

Expected: kept excludes the-walled claim, reason cites public-only rule,
script R2. Offer public-only next step (public URL or affiliation/ORCID).

### N3 — low-evidence + invented URL + unparsable refused

Inputs (all `websearch`, `example.com`-shaped): lone rumor `R Kotabagi
rumored award (single anonymous blog, no affiliation, no ORCID)` (low,
score 1) → `insufficient_evidence`; unpublished contact
`lab@example.com` without link (medium) → `insufficient_evidence`
(`unpublished contact without source link`); invented link
`https://example.com/papers/999-unfetched-secret` (medium, score 2) →
`hallucinated_url`; empty-value finding → `unparsable`.

Expected: kept `[]` for these four alone; on the full golden set kept 9
/ refused 5 exactly as P4; `check_urls` flags only index 11; script R3.
Dashboard shows the empty/error state, never a fake card.

## Finding schema (frozen)

```json
{"type": "string", "value": "string", "source": "scholar|websearch|page_reader|username_probe|domain_intel|oembed_public", "confidence": "high|medium|low"}
```

Optional intake-only keys (never required, never break `normalize`):
`url` / `source_url` / `link` (provenance), `login_walled`, `access`.
Scored shape: `{"index", "finding", "raw", "evidence_score",
"source_count", "corroborated", "has_provenance", "claimed_urls",
"orcid", "affiliation"}`. Verdict shape: `{"kept": [...],
"refused": [{"index", "reason", "detail"}]}` with `reason` in
`unparsable | login_walled_claim | pii_excluded | hallucinated_url |
insufficient_evidence`.

## Honest TODOs (not half-builds)

- TODO(rename): `sherlock-project/sherlock` (~93k stars) owns this name in
  OSINT. Plugin display name defaults to "Sherlock"; rename before public
  launch (candidates: OpenLens, Lantern, TraceKit).
- TODO(saved): IG Saved/Liked has no API; Export-ZIP backfill is manual.
- TODO(live): entity lanes run on fixtures when `SHERLOCK_LIVE` is unset;
  live HTTP needs free-tier keys + rate limits + failure taxonomy.
- TODO(transcript): reel transcripts are stubs; prod path is public audio
  → self-hosted ASR with cache, public URLs only.
- TODO(db): Supabase schema + sqlite fallback owned by core crew; entity
  cases persist via `persist_findings` per candidate case id.
