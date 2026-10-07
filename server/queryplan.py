"""GPT-search loop support module ("orchestrate, don't fetch").

Loop contract (wiring note for the orchestrator crew — this module does
NOT fetch; it only plans queries and validates model-returned URLs):

  1. Skill instructs model: ``skills/osint-triage/SKILL.md`` tells the
     model the numbered playbook step "search the public web for these
     queries" using :func:`build_queries` output (deterministic query
     set, each tagged with ``purpose`` + ``lane``).
  2. Model searches: retrieval happens with the MODEL's browsing/search
     tool, not our server. Our server never fetches SERPs here (no
     network in this module, stdlib only).
  3. URLs back via intake: model pastes found URLs back; the intake tool
     (orchestrator: ``server/tools.py`` candidate ``intake_urls``) calls
     :func:`parse_found_urls` then :func:`intake_package`, which stamps
     every bundle ``provenance = "model-retrieved, unverified"``.
  4. Correlate scores: orchestrator feeds ``package["urls"]`` as the
     ``fetched_urls`` set into ``correlate.check_urls`` /
     ``correlate.refute`` + ``correlate.score_findings``. Because the
     provenance is model-retrieved/unverified, scoring MUST stay
     skeptical: single-source model claims start at low confidence and
     any claimed URL outside the fetched set is refused as
     ``hallucinated_url``. Homonym-split (``entity.split_homonyms`` via
     ``correlate.build_entity_cases``) still applies — clusters never
     merge.

Wiring contract (orchestrator implements, NOT this module):
  - ``SKILL.md``: add a step "run build_queries(name) -> search each
    query with browsing -> return URLs via intake_package".
  - ``server/tools.py``: expose an intake entry point that accepts
    ``intake_package`` dicts (validate shape, never trust URLs as
    findings — pass them as the fetched-URL allow-list only).
  - ``server/registry.py`` / ``adapters/*``: UNCHANGED (frozen, sibling
    crews). No adapter edits here.
  - ``server/correlate.py``: already provides ``score_findings`` /
    ``refute`` / ``check_urls`` — no changes needed.

Pure functions, stdlib only, no network. DUMMY/example fixtures only.
"""

from __future__ import annotations

import re
import unicodedata
import urllib.parse

MAX_QUERIES = 12
MAX_URLS = 10

PROVENANCE_NOTE = "model-retrieved, unverified"

_PURPOSES = frozenset({"baseline", "variant", "site", "affiliation"})
_LANES = frozenset({"web", "linkedin", "github", "scholar", "news"})

# Site-constrained lanes in fixed order (deterministic).
_SITE_LANES: tuple = (
    ("site:linkedin.com", "linkedin"),
    ("site:github.com", "github"),
    ("site:scholar.google.com", "scholar"),
    ("news", "news"),
)

_URL_RE = re.compile(r"https?://[^\s\"'<>`]+", re.IGNORECASE)

_PRIVATE_IPV4_RES = (
    re.compile(r"^127\."),
    re.compile(r"^10\."),
    re.compile(r"^192\.168\."),
    re.compile(r"^0\.0\.0\.0$"),
    re.compile(r"^172\.(1[6-9]|2[0-9]|3[01])\."),
)


# ---------------- name normalization + variants (self-contained) ----------------
# Mirrors the rule SUBSET of server/entity.py relevant to query fan-out
# (ph/f, ee/i, aspirated-h for the Kotabagi/Kotabaghi lesson, doubling).
# Self-contained on purpose: query planning must stay hermetic even if
# entity.py is absent; the orchestrator may optionally pass
# entity.variants() output in later, but this module never imports it.


def _normalize(name) -> str:
    """Lowercase, strip diacritics, collapse whitespace. Non-string -> ""."""
    if not isinstance(name, str):
        return ""
    s = name.strip()
    if not s:
        return ""
    s = s.casefold()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def _name_variants(normalized_base: str) -> list:
    """Deterministic transliteration variants (first-seen order, capped)."""
    seen: list = []
    known: set = set()

    def add(cand: str) -> None:
        if cand and cand not in known:
            known.add(cand)
            seen.append(cand)

    add(normalized_base)
    base = normalized_base
    # ph <-> f
    if "ph" in base:
        add(base.replace("ph", "f"))
    if "f" in base and "ph" not in base:
        add(base.replace("f", "ph"))
    elif "f" in base:
        add(base.replace("f", "ph"))
    # ee <-> i
    if "ee" in base:
        add(base.replace("ee", "i"))
    if re.search(r"(?<!e)i(?!e)", base):
        add(base.replace("i", "ee"))
    # aspirated h (Kotabagi <-> Kotabaghi lesson)
    for asp, plain in (("gh", "g"), ("bh", "b"), ("dh", "d")):
        if asp in base:
            add(base.replace(asp, plain))
    for asp, plain in (("gh", "g"), ("bh", "b"), ("dh", "d")):
        if plain in base and asp not in base:
            add(re.sub(plain + r"(?!h)", asp, base))
    # single/double consonant collapse
    collapsed = re.sub(r"([bcdfgjklmnpqrstvwxz])\1", r"\1", base)
    if collapsed != base:
        add(collapsed)
    return seen


# ---------------- build_queries ----------------

def _clean_affiliation(affil) -> str:
    if not isinstance(affil, str):
        return ""
    return " ".join(affil.strip().split())[:128]


def build_queries(name, affiliation: str = "") -> list:
    """Deterministic public-search query set for a person name.

    Each item: ``{"query": str, "purpose": str, "lane": str}`` where
    ``purpose`` in {baseline, variant, site, affiliation} and ``lane``
    in {web, linkedin, github, scholar, news}. Order is fixed
    (baseline -> variants -> site-constrained -> affiliation guesses),
    deduplicated by exact query string, capped at ``MAX_QUERIES`` (12).

    ``affiliation`` is optional: when given, two ``"name" affiliation``
    guesses are appended; when empty, generic ``professor``/``university``
    guesses keep the affiliation lane covered without inventing an org.

    Pure, never raises; empty/non-string name -> [].
    """
    try:
        base = _normalize(name)
    except Exception:
        return []
    if not base:
        return []
    if not re.search(r"[A-Za-z0-9]", base):
        return []  # punctuation-only input plans nothing
    try:
        affil = _clean_affiliation(affiliation)
    except Exception:
        affil = ""

    out: list = []
    seen_q: set = set()

    def push(q: str, purpose: str, lane: str) -> None:
        if len(out) >= MAX_QUERIES:
            return
        q = " ".join(q.split())
        if not q or q in seen_q:
            return
        seen_q.add(q)
        out.append({"query": q, "purpose": purpose, "lane": lane})

    try:
        variants = _name_variants(base)
    except Exception:
        variants = [base]

    # 1. baseline: exact quoted full name.
    push('"%s"' % base, "baseline", "web")

    # 2. variant fan-out (quoted).
    for v in variants[1:]:
        push('"%s"' % v, "variant", "web")
        if len(out) >= MAX_QUERIES:
            break

    # 3. site-constrained on the base spelling.
    for suffix, lane in _SITE_LANES:
        if len(out) >= MAX_QUERIES:
            break
        if lane == "news":
            push('"%s" news' % base, "site", lane)
        else:
            push('"%s" %s' % (base, suffix), "site", lane)

    # 4. affiliation guesses.
    if len(out) < MAX_QUERIES:
        if affil:
            push('"%s" %s' % (base, affil), "affiliation", "web")
        else:
            push('"%s" professor' % base, "affiliation", "web")
    if len(out) < MAX_QUERIES:
        if affil:
            push('"%s" "%s"' % (base, affil), "affiliation", "web")
        else:
            push('"%s" university OR college OR institute' % base,
                 "affiliation", "web")

    return out[:MAX_QUERIES]


# ---------------- parse_found_urls ----------------

def _strip_trailing_punct(url: str) -> str:
    # Trailing prose punctuation is never part of the URL.
    s = url.strip()
    s = s.rstrip(".,;:)]}'\"`!?")
    return s.strip()


def _is_public_http(url: str) -> bool:
    """True for fetchable public http(s) shapes; False for non-public."""
    try:
        if not isinstance(url, str) or not url:
            return False
        parts = urllib.parse.urlsplit(url)
        if parts.scheme.lower() not in ("http", "https"):
            return False
        host = (parts.hostname or "").lower().rstrip(".")
        if not host:
            return False
        if host in ("localhost",):
            return False
        if host.endswith((".local", ".internal", ".lan", ".invalid",
                           ".example", ".test")):
            return False
        if host.endswith(".onion"):
            return False
        if host in ("::1", "[::1]"):
            return False
        if host.startswith("[") and host.endswith("]"):
            return False  # other literal IPv6: treat as non-public shape
        if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
            for rx in _PRIVATE_IPV4_RES:
                if rx.search(host):
                    return False
            if host.startswith("169.254."):
                return False
            return True
        if "@" in (parts.netloc or ""):
            return False  # credential-in-URL shape
        return True
    except Exception:
        return False


def parse_found_urls(text_or_list) -> list:
    """Extract + validate http(s) URLs from model output.

    Accepts a prose string or a list/tuple of strings (mixed garbage
    tolerated). Extracts ``http(s)://`` candidates, strips trailing
    prose punctuation, drops non-URLs / duplicates (normalized:
    lowercased, trailing ``/`` stripped) / non-public shapes
    (non-http schemes, localhost, private/loopback IPv4, ``.local`` /
    ``.onion`` and similar, credential-in-URL), keeps first-seen order,
    caps at ``MAX_URLS`` (10). Pure, never raises; garbage -> [].
    """
    try:
        if isinstance(text_or_list, str):
            blobs = [text_or_list]
        elif isinstance(text_or_list, (list, tuple)):
            blobs = [b for b in text_or_list if isinstance(b, str)]
        else:
            return []
    except Exception:
        return []
    out: list = []
    seen: set = set()
    try:
        for blob in blobs:
            for m in _URL_RE.findall(blob):
                cand = _strip_trailing_punct(m)
                if not cand:
                    continue
                if not _is_public_http(cand):
                    continue
                # Normalize for dedupe + output: strip trailing slash(es).
                norm = cand.rstrip("/")
                key = norm.lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(norm)
                if len(out) >= MAX_URLS:
                    return out
    except Exception:
        pass
    return out[:MAX_URLS]


# ---------------- intake_package ----------------

def intake_package(urls, query: str = "") -> dict:
    """Bundle model-retrieved URLs for correlate (skeptical provenance).

    ``urls`` may be a string, list, or mixed garbage — always cleaned
    via :func:`parse_found_urls`. Returns::

      {"query": str, "urls": [...<=10...], "url_count": int,
       "provenance": "model-retrieved, unverified",
       "note": "model-retrieved, unverified: treat as low-confidence
                until fetched + scored by correlate (anti-hallucination
                check required)."}

    Never raises; garbage input -> empty ``urls`` with ``query`` coerced
    to ``""``.
    """
    try:
        q = query.strip()[:256] if isinstance(query, str) else ""
    except Exception:
        q = ""
    try:
        cleaned = parse_found_urls(urls)
    except Exception:
        cleaned = []
    return {
        "query": q,
        "urls": list(cleaned),
        "url_count": len(cleaned),
        "provenance": PROVENANCE_NOTE,
        "note": ("model-retrieved, unverified: treat as low-confidence "
                 "until fetched + scored by correlate "
                 "(anti-hallucination check required)."),
    }
