"""Correlate: dedupe, confidence-rank, and case assembly."""

from __future__ import annotations

import os
import re

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
VALID_CONFIDENCE = frozenset(CONFIDENCE_RANK)

DEMO_CASE_ID = "DEMO-CASE-001"
DEMO_SEARCH_PHRASES = ("osint demo case", "demo-case-001", "demo case")

# Guarded entity import (orchestrator crew): correlate must never crash when
# server/entity.py is absent. entity.py is pure/stdlib, but the loader below
# keeps the import unbreakable for packaging-verify + hermetic tests.
_entity_mod = None
try:  # package import when server/ is a package
    from . import entity as _entity_mod  # type: ignore
except Exception:
    _entity_mod = None
if _entity_mod is None:
    try:
        import importlib.util as _ilu

        _epath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "entity.py")
        if os.path.isfile(_epath):
            _espec = _ilu.spec_from_file_location("sherlock_entity", _epath)
            _emod = _ilu.module_from_spec(_espec)
            _espec.loader.exec_module(_emod)
            if callable(getattr(_emod, "split_homonyms", None)):
                _entity_mod = _emod
    except Exception:
        _entity_mod = None


def _clean_str(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def normalize_finding(raw) -> dict | None:
    """Validate one finding dict; return cleaned copy or None."""
    if not isinstance(raw, dict):
        return None
    ftype = _clean_str(raw.get("type"))
    value = _clean_str(raw.get("value"))
    source = _clean_str(raw.get("source"))
    conf = _clean_str(raw.get("confidence")).lower()
    if not ftype or not value or not source:
        return None
    if conf not in VALID_CONFIDENCE:
        return None
    if len(ftype) > 128 or len(value) > 1024 or len(source) > 128:
        return None
    return {"type": ftype, "value": value, "source": source,
            "confidence": conf}


def dedupe_findings(findings: list) -> list:
    """Dedupe by (type, value); keep highest confidence; merge sources."""
    best: dict = {}
    for raw in findings or []:
        f = normalize_finding(raw)
        if f is None:
            continue
        key = (f["type"], f["value"])
        cur = best.get(key)
        if cur is None:
            f["sources"] = [f["source"]]
            best[key] = f
        else:
            if f["source"] not in cur["sources"]:
                cur["sources"].append(f["source"])
            if CONFIDENCE_RANK[f["confidence"]] > CONFIDENCE_RANK[cur["confidence"]]:
                cur["confidence"] = f["confidence"]
                cur["source"] = f["source"]
    return list(best.values())


def rank_findings(findings: list) -> list:
    """Sort by confidence desc, then type, then value (stable)."""
    paired = []
    for raw in findings or []:
        c = normalize_finding(raw)
        if c is None:
            continue
        if isinstance(raw, dict) and isinstance(raw.get("sources"), list) \
                and raw["sources"]:
            # preserve merged sources when input already deduped
            kept = [s for s in raw["sources"] if isinstance(s, str)]
            c["sources"] = list(dict.fromkeys(kept)) or [c["source"]]
        paired.append(c)
    return sorted(paired, key=lambda f: (
        -CONFIDENCE_RANK[f["confidence"]], f["type"], f["value"]))


def assemble_case(case_id: str, findings: list) -> dict:
    """Build a case bundle: deduped + ranked findings grouped by lane."""
    deduped = dedupe_findings(findings)
    ranked = sorted(deduped, key=lambda f: (
        -CONFIDENCE_RANK[f["confidence"]], f["type"], f["value"]))
    lanes: dict = {}
    for f in ranked:
        lanes.setdefault(f["source"], []).append(f)
    return {
        "case_id": case_id,
        "finding_count": len(ranked),
        "lanes": sorted(lanes),
        "by_lane": lanes,
        "findings": ranked,
    }


def build_demo_case(username_findings: list, domain_findings: list,
                    reel_findings: list) -> dict:
    """Assemble DEMO-CASE-001 from the three lane fixture sets."""
    all_findings = list(username_findings or []) + \
        list(domain_findings or []) + list(reel_findings or [])
    case = assemble_case(DEMO_CASE_ID, all_findings)
    case["title"] = "OSINT demo case"
    case["aliases"] = ["osint demo case", DEMO_CASE_ID,
                       "@demo.sleuth", "example.com"]
    return case


def _score_case(query: str, case: dict) -> float:
    q = query.strip().lower()
    if not q:
        return 0.0
    text = " ".join([
        str(case.get("case_id", "")),
        str(case.get("title", "")),
        " ".join(case.get("aliases", []) or []),
        " ".join(case.get("lanes", []) or []),
    ]).lower()
    if q in ("osint demo case", "demo-case-001", "demo case") and \
            case.get("case_id") == DEMO_CASE_ID:
        return 100.0
    tokens = [t for t in q.split() if t]
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in text)
    if hits == 0:
        return 0.0
    score = hits / len(tokens)
    if case.get("case_id") == DEMO_CASE_ID and \
            any(t in ("osint", "demo", "case") for t in tokens):
        score += 0.5
    return score


def search_cases(query: str, cases: list) -> list:
    """Rank cases for a query; DEMO-CASE-001 wins on 'osint demo case'."""
    scored = []
    for c in cases or []:
        if not isinstance(c, dict):
            continue
        s = _score_case(query if isinstance(query, str) else "", c)
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda p: -p[0])
    return [c for _, c in scored]


# ---------------- entity homonym-split integration (orchestrator) ----------------

_ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b")
_AFFIL_PREFIX_RE = re.compile(r"affiliation\s*:\s*([^,;()]+)",
                              re.IGNORECASE)
_ORG_SUFFIX_RE = re.compile(
    r"([A-Z][A-Za-z&.'-]*(?:\s+[A-Z][A-Za-z&.'-]*)*\s+"
    r"(University|Institute|College|Corporation|Corp|Labs|Lab|School"
    r"|Department|Press))")


def _extract_affiliation(finding: dict) -> str:
    """Best-effort affiliation string from an adapter finding (never raises)."""
    try:
        if not isinstance(finding, dict):
            return ""
        for _k in ("affiliation", "org", "affil"):
            _v = finding.get(_k)
            if isinstance(_v, str) and _v.strip():
                return _v.strip()[:256]
        _val = finding.get("value")
        if not isinstance(_val, str) or not _val.strip():
            return ""
        _m = _AFFIL_PREFIX_RE.search(_val)
        if _m and _m.group(1).strip():
            return _m.group(1).strip()[:256]
        _m2 = _ORG_SUFFIX_RE.search(_val)
        if _m2 and _m2.group(1).strip():
            return _m2.group(1).strip()[:256]
        return ""
    except Exception:
        return ""


def _extract_orcid(finding: dict) -> str:
    """ORCID id from explicit keys or finding value ("" when absent)."""
    try:
        if not isinstance(finding, dict):
            return ""
        for _k in ("orcid", "ORCID"):
            _v = finding.get(_k)
            if isinstance(_v, str):
                _m0 = _ORCID_RE.search(_v)
                if _m0:
                    return _m0.group(0)
                if _v.strip():
                    return _v.strip()[:64]
        _val = finding.get("value")
        if isinstance(_val, str):
            _m = _ORCID_RE.search(_val)
            if _m:
                return _m.group(0)
        return ""
    except Exception:
        return ""


def _extract_location(finding: dict) -> str:
    try:
        if not isinstance(finding, dict):
            return ""
        for _k in ("location", "loc", "place"):
            _v = finding.get(_k)
            if isinstance(_v, str) and _v.strip():
                return _v.strip()[:256]
        return ""
    except Exception:
        return ""


def _slug_entity(name: str) -> str:
    try:
        _s = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip().lower())
        _s = _s.strip("-")[:48] or "unknown"
        return _s
    except Exception:
        return "unknown"


def build_entity_cases(query_name, findings, base_case_id=None) -> list:
    """Cluster adapter findings into separate case candidates.

    Integration point for ``entity.split_homonyms``: each cluster becomes
    its own case via :func:`assemble_case` on that cluster's members ONLY
    (dedupe per cluster, never globally — clusters are never merged).

    Returns [] for empty/garbage input. Never raises.
    """
    try:
        if not isinstance(query_name, str) or not query_name.strip():
            return []
        _q = query_name.strip()[:128]
        _cleaned = []
        for _f in (findings or []):
            _c = normalize_finding(_f)
            if _c is not None:
                _cleaned.append(_c)
        if not _cleaned:
            return []
        _base = (base_case_id.strip()[:64] if isinstance(base_case_id, str)
                 and base_case_id.strip() else "ENTITY-" + _slug_entity(_q))
        if _entity_mod is None:
            _single = assemble_case(_base + ":candidate-1", _cleaned)
            _single["cluster_id"] = "candidate-1"
            _single["affiliation"] = ""
            _single["query"] = _q
            return [_single]
        _records = []
        for _i, _f in enumerate(_cleaned):
            _records.append({
                "name": _q,
                "affiliation": _extract_affiliation(_f),
                "location": _extract_location(_f),
                "orcid": _extract_orcid(_f),
                "source": _f.get("source", ""),
                "_idx": _i,
            })
        try:
            _clusters = _entity_mod.split_homonyms(_records)
        except Exception:
            _clusters = []
        if not _clusters:
            _single = assemble_case(_base + ":candidate-1", _cleaned)
            _single["cluster_id"] = "candidate-1"
            _single["affiliation"] = ""
            _single["query"] = _q
            return [_single]
        _cases = []
        for _n, _cl in enumerate(_clusters, start=1):
            _cid = _cl.get("cluster_id") if isinstance(_cl, dict) else ""
            if not isinstance(_cid, str) or not _cid:
                _cid = "candidate-%d" % _n
            _indices = []
            try:
                for _mi in (_cl.get("member_indices") or []):
                    if isinstance(_mi, int) and 0 <= _mi < len(_cleaned):
                        _indices.append(_mi)
            except Exception:
                _indices = []
            if not _indices:
                continue
            _members = [_cleaned[_i] for _i in sorted(set(_indices))]
            _case = assemble_case("%s:%s" % (_base, _cid), _members)
            _case["cluster_id"] = _cid
            try:
                _case["affiliation"] = _cl.get("affiliation", "")
            except Exception:
                _case["affiliation"] = ""
            _case["query"] = _q
            _cases.append(_case)
        return _cases
    except Exception:
        return []


# ---------------- findings-intake scoring/refutation (Phase 1, additive) ----------------
# Pure functions for model-brought facts. Additive only: existing builders
# above are untouched. Never raises on garbage; no network; DUMMY/example
# fixtures only.
#
# Pipeline: score_findings(findings) -> refute(scored, fetched_urls) ->
# build_entity_cases(kept). Every claimed URL must appear in the fetched
# set (anti-hallucination); homonym split stays in build_entity_cases
# (clusters never merged); PII/login-walled claims are refused, never kept.

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_INTL_RE = re.compile(r"\+\d[\d\s().-]{6,}\d")
_LOGIN_WALLED_RE = re.compile(
    r"login\s*(required|wall|-wall|needed)|log\s*in\s*to|sign\s*in\s*to\s*view"
    r"|authentication\s*required|private\s*profile|members?\s*only"
    r"|subscribe\s*to\s*continue|paywall|password\s*required"
    r"|login-walled|sign-in\s*required",
    re.IGNORECASE)

CONTACT_TYPES = frozenset({"contact", "email", "phone",
                           "published_contact"})
INTAKE_REASONS = frozenset({"unparsable", "login_walled_claim",
                            "pii_excluded", "hallucinated_url",
                            "insufficient_evidence"})
MIN_EVIDENCE_SCORE = 2


def _normalize_url(u) -> str:
    try:
        if not isinstance(u, str):
            return ""
        s = u.strip()
        if not s:
            return ""
        # strip trailing punctuation from prose extraction, then trailing /
        # (so https://example.com/x and https://example.com/x/ match).
        s = s.rstrip(".,;)]}")
        s = s.strip()
        if s.lower().startswith(("http://", "https://")):
            s = s.rstrip("/")
        return s.lower()[:512]
    except Exception:
        return ""


def _normalize_fetched_set(fetched_urls) -> set:
    out = set()
    try:
        if fetched_urls is None:
            return out
        if isinstance(fetched_urls, str):
            fetched_urls = [fetched_urls]
        for u in (fetched_urls or []):
            n = _normalize_url(u)
            if n:
                out.add(n)
    except Exception:
        pass
    return out


def extract_claimed_urls(finding) -> list:
    """All http(s) URLs claimed inside one finding (deduped, order-kept).

    Looks in ``value`` plus optional ``url``/``source_url``/``link``/
    ``source_link`` keys. Never raises; non-dict -> [].
    """
    try:
        if not isinstance(finding, dict):
            return []
        blobs = []
        v = finding.get("value")
        if isinstance(v, str) and v:
            blobs.append(v)
        for k in ("url", "source_url", "link", "source_link"):
            w = finding.get(k)
            if isinstance(w, str) and w.strip():
                blobs.append(w.strip())
        out = []
        seen = set()
        for b in blobs:
            for m in _URL_RE.findall(b):
                n = _normalize_url(m)
                if n and n not in seen:
                    seen.add(n)
                    out.append(n)
        return out
    except Exception:
        return []


def _finding_text_blob(raw, cleaned) -> str:
    try:
        parts = []
        for src in (raw, cleaned):
            if not isinstance(src, dict):
                continue
            for k in ("value", "url", "source_url", "link",
                      "source_link", "email", "phone", "orcid"):
                v = src.get(k)
                if isinstance(v, str) and v.strip():
                    parts.append(v.strip())
        return " ".join(parts)
    except Exception:
        return ""


def _is_pii(raw, cleaned) -> bool:
    """True when the finding carries non-public personal data.

    PII = non-@example.com email anywhere in the blob, international
    phone pattern (requires leading ``+`` so ORCID/years never match),
    explicit ``type`` in {email, phone}, or explicit ``email``/``phone``
    keys with non-example values. @example.com addresses are published
    demo contacts, never PII.
    """
    try:
        blob = _finding_text_blob(raw, cleaned)
        if not blob:
            return False
        for m in _EMAIL_RE.findall(blob):
            if not m.lower().endswith("@example.com"):
                return True
        if _PHONE_INTL_RE.search(blob):
            return True
        for src in (raw, cleaned):
            if not isinstance(src, dict):
                continue
            t = src.get("type")
            if isinstance(t, str) and t.strip().lower() in ("email",
                                                            "phone"):
                # bare email/phone-typed findings are PII unless the
                # value itself is an @example.com published contact.
                v = src.get("value", "")
                if isinstance(v, str) and "@" in v:
                    if v.strip().lower().endswith("@example.com"):
                        continue
                return True
            for k in ("email", "phone"):
                v = src.get(k)
                if isinstance(v, str) and v.strip():
                    if k == "email" and \
                            v.strip().lower().endswith("@example.com"):
                        continue
                    return True
        return False
    except Exception:
        return False


def _is_login_walled(raw, cleaned) -> bool:
    """True when the finding claims login-gated/private content."""
    try:
        for src in (raw, cleaned):
            if not isinstance(src, dict):
                continue
            if src.get("login_walled") is True:
                return True
            acc = src.get("access")
            if isinstance(acc, str) and acc.strip().lower() in (
                    "login_required", "login", "private", "paywalled",
                    "auth_required"):
                return True
            t = src.get("type")
            if isinstance(t, str) and t.strip().lower() == \
                    "login_walled_claim":
                return True
        blob = _finding_text_blob(raw, cleaned)
        if blob and _LOGIN_WALLED_RE.search(blob):
            return True
        return False
    except Exception:
        return False


def _has_contact_provenance(raw, cleaned) -> bool:
    """Published-contact provenance: contact type + source link.

    True only for CONTACT_TYPES whose value embeds an http(s) URL or
    whose raw dict carries url/source_url/link/source_link. Non-contact
    types always return False (provenance N/A, no bonus).
    """
    try:
        ctype = ""
        for src in (cleaned, raw):
            if isinstance(src, dict):
                t = src.get("type")
                if isinstance(t, str) and t.strip():
                    ctype = t.strip().lower()
                    break
        if ctype not in CONTACT_TYPES:
            return False
        if extract_claimed_urls(raw):
            return True
        if extract_claimed_urls(cleaned):
            return True
        return False
    except Exception:
        return False


def _intake_orcid(raw, cleaned) -> str:
    try:
        for src in (raw, cleaned):
            o = _extract_orcid(src) if isinstance(src, dict) else ""
            if o:
                return o
        return ""
    except Exception:
        return ""


def _intake_affil(raw, cleaned) -> str:
    try:
        for src in (raw, cleaned):
            a = _extract_affiliation(src) if isinstance(src, dict) else ""
            if a:
                return a.strip().lower()[:256]
        return ""
    except Exception:
        return ""


def score_findings(findings) -> list:
    """Evidence score per finding (pure, deterministic, never raises).

    Score = base confidence (high 3 / medium 2 / low 1, 0 when
    unparsable) +1 corroborated +1 published-contact provenance.
    Corroborated = same exact (type, value) from >=2 distinct sources,
    OR same ORCID in >=2 findings, OR same affiliation in >=2 findings,
    OR same claimed URL in >=2 findings. Source diversity is the
    distinct-source count behind the exact-duplicate signal; the
    ORCID/affiliation/URL signals capture cross-lane corroboration.

    Returns a list (input order) of::
      {"index", "finding" (cleaned or None), "raw",
       "evidence_score", "source_count", "corroborated",
       "has_provenance", "claimed_urls", "orcid", "affiliation"}
    """
    try:
        if not isinstance(findings, list) or not findings:
            return []
    except Exception:
        return []
    # First pass: normalize + collect global corroboration counts.
    cleaned_list = []
    try:
        for raw in findings:
            try:
                cleaned_list.append(normalize_finding(raw))
            except Exception:
                cleaned_list.append(None)
    except Exception:
        return []
    try:
        exact_sources: dict = {}
        orcid_counts: dict = {}
        affil_counts: dict = {}
        url_counts: dict = {}
        per_urls: list = []
        per_orcid: list = []
        per_affil: list = []
        for i, raw in enumerate(findings):
            c = cleaned_list[i] if i < len(cleaned_list) else None
            urls = extract_claimed_urls(raw)
            if not urls and isinstance(c, dict):
                urls = extract_claimed_urls(c)
            # dedupe within finding, keep normalized
            urls = list(dict.fromkeys([u for u in urls if u]))
            per_urls.append(urls)
            for u in urls:
                url_counts[u] = url_counts.get(u, 0) + 1
            o = _intake_orcid(raw if isinstance(raw, dict) else {},
                              c if isinstance(c, dict) else {})
            per_orcid.append(o)
            if o:
                orcid_counts[o] = orcid_counts.get(o, 0) + 1
            a = _intake_affil(raw if isinstance(raw, dict) else {},
                              c if isinstance(c, dict) else {})
            per_affil.append(a)
            if a:
                affil_counts[a] = affil_counts.get(a, 0) + 1
            if isinstance(c, dict):
                key = (c.get("type", ""), c.get("value", ""))
                src = c.get("source", "")
                bucket = exact_sources.setdefault(key, set())
                if isinstance(src, str) and src:
                    bucket.add(src)
                # raw may carry extra sources list (deduped shape)
                if isinstance(raw, dict):
                    extra = raw.get("sources")
                    if isinstance(extra, list):
                        for s in extra:
                            if isinstance(s, str) and s:
                                bucket.add(s)
    except Exception:
        exact_sources, orcid_counts, affil_counts, url_counts = {}, {}, {}, {}
        per_urls = [[] for _ in findings]
        per_orcid = ["" for _ in findings]
        per_affil = ["" for _ in findings]
    out = []
    try:
        for i, raw in enumerate(findings):
            c = cleaned_list[i] if i < len(cleaned_list) else None
            urls = per_urls[i] if i < len(per_urls) else []
            o = per_orcid[i] if i < len(per_orcid) else ""
            a = per_affil[i] if i < len(per_affil) else ""
            if not isinstance(c, dict):
                out.append({"index": i, "finding": None, "raw": raw,
                            "evidence_score": 0, "source_count": 0,
                            "corroborated": False,
                            "has_provenance": False,
                            "claimed_urls": list(urls),
                            "orcid": o or "", "affiliation": a or ""})
                continue
            base = CONFIDENCE_RANK.get(c.get("confidence", ""), 0)
            key = (c.get("type", ""), c.get("value", ""))
            srcs = exact_sources.get(key, set())
            source_count = len(srcs)
            corroborated = False
            try:
                if source_count >= 2:
                    corroborated = True
                elif o and orcid_counts.get(o, 0) >= 2:
                    corroborated = True
                elif a and affil_counts.get(a, 0) >= 2:
                    corroborated = True
                else:
                    for u in urls:
                        if url_counts.get(u, 0) >= 2:
                            corroborated = True
                            break
            except Exception:
                corroborated = False
            try:
                has_prov = _has_contact_provenance(
                    raw if isinstance(raw, dict) else {}, c)
            except Exception:
                has_prov = False
            score = int(base) + (1 if corroborated else 0) + \
                (1 if has_prov else 0)
            out.append({"index": i, "finding": dict(c), "raw": raw,
                        "evidence_score": score,
                        "source_count": int(source_count),
                        "corroborated": bool(corroborated),
                        "has_provenance": bool(has_prov),
                        "claimed_urls": list(urls),
                        "orcid": o or "", "affiliation": a or ""})
    except Exception:
        pass
    return out


def check_urls(findings_or_scored, fetched_urls) -> list:
    """Anti-hallucination URL check (pure, never raises).

    Every claimed URL in every finding must appear in ``fetched_urls``
    (normalized exact match). Returns violations only::
      [{"index", "claimed", "hallucinated"}]
    Empty list = no hallucinated URLs. ``fetched_urls=None`` skips the
    check (returns []); pass the real fetched set to enforce.
    """
    try:
        if fetched_urls is None:
            return []
        fetched = _normalize_fetched_set(fetched_urls)
        # Accept raw findings or scored entries from score_findings().
        items = findings_or_scored if isinstance(
            findings_or_scored, list) else []
        out = []
        for i, item in enumerate(items):
            try:
                idx = item.get("index", i) if isinstance(item, dict) \
                    and "finding" in item else i
                if isinstance(item, dict) and "finding" in item and \
                        "claimed_urls" in item:
                    claimed = item.get("claimed_urls") or []
                    raw = item.get("raw")
                    finding = item.get("finding")
                    blob_src = raw if isinstance(raw, dict) else finding
                else:
                    claimed = extract_claimed_urls(item)
                    blob_src = item
                claimed = [u for u in (claimed or [])
                           if isinstance(u, str) and u]
                bad = [u for u in claimed if u not in fetched]
                if bad:
                    out.append({"index": idx, "claimed": list(claimed),
                                "hallucinated": list(bad)})
            except Exception:
                continue
        return out
    except Exception:
        return []


def refute(findings_or_scored, fetched_urls=None,
           min_score: int = MIN_EVIDENCE_SCORE) -> dict:
    """Split findings into kept vs reason-coded refusals (pure).

    Accepts raw findings OR scored entries from :func:`score_findings`.
    ``fetched_urls`` enables the anti-hallucination check (None skips).
    First-match reason order (deterministic): ``unparsable`` >
    ``login_walled_claim`` > ``pii_excluded`` > ``hallucinated_url`` >
    ``insufficient_evidence`` (includes unpublished contacts: a
    CONTACT_TYPES finding without a source link, and any finding with
    ``evidence_score`` below ``min_score``, default 2).

    Returns ``{"kept": [cleaned...], "refused": [{"index", "reason",
    "detail"}]}``. Never raises.
    """
    try:
        items = findings_or_scored if isinstance(
            findings_or_scored, list) else []
    except Exception:
        return {"kept": [], "refused": []}
    try:
        mins = int(min_score)
    except Exception:
        mins = MIN_EVIDENCE_SCORE
    # Normalize to scored form (reuse caller's scores when present so
    # SKILL step 4 (score then refute) is stable).
    scored = []
    try:
        use_scores = bool(items) and all(
            isinstance(x, dict) and "finding" in x and
            "evidence_score" in x for x in items)
    except Exception:
        use_scores = False
    try:
        if use_scores:
            scored = items
        elif items:
            scored = score_findings(items)
        else:
            return {"kept": [], "refused": []}
    except Exception:
        return {"kept": [], "refused": []}
    try:
        fetched = None if fetched_urls is None else \
            _normalize_fetched_set(fetched_urls)
    except Exception:
        fetched = None
    kept: list = []
    refused: list = []
    try:
        for entry in scored:
            try:
                if not isinstance(entry, dict):
                    refused.append({"index": -1, "reason": "unparsable",
                                    "detail": "non-dict entry"})
                    continue
                idx = entry.get("index", 0)
                try:
                    idx = int(idx)
                except Exception:
                    idx = 0
                finding = entry.get("finding")
                raw = entry.get("raw")
                raw_d = raw if isinstance(raw, dict) else {}
                score = entry.get("evidence_score", 0)
                try:
                    score = int(score)
                except Exception:
                    score = 0
                if not isinstance(finding, dict) or \
                        normalize_finding(finding) is None and \
                        normalize_finding(raw_d) is None:
                    # unparsable when neither cleaned nor raw validates
                    if not isinstance(finding, dict):
                        refused.append(
                            {"index": idx, "reason": "unparsable",
                             "detail": "unparsable finding "
                                       "(missing type/value/source/confidence)"})
                        continue
                c = finding if isinstance(finding, dict) else raw_d
                if _is_login_walled(raw_d, c):
                    refused.append(
                        {"index": idx, "reason": "login_walled_claim",
                         "detail": "login-walled/private claim refused "
                                   "(public sources only; no bypass)"})
                    continue
                if _is_pii(raw_d, c):
                    refused.append(
                        {"index": idx, "reason": "pii_excluded",
                         "detail": "PII excluded (non-public email/phone; "
                                   "published @example.com contacts only)"})
                    continue
                claimed = entry.get("claimed_urls")
                if claimed is None:
                    try:
                        claimed = extract_claimed_urls(raw_d)
                    except Exception:
                        claimed = []
                if fetched is not None:
                    try:
                        bad = [u for u in (claimed or [])
                               if isinstance(u, str) and u and u not in fetched]
                    except Exception:
                        bad = []
                    if bad:
                        refused.append(
                            {"index": idx,
                             "reason": "hallucinated_url",
                             "detail": "claimed URL not in fetched set: %s"
                                       % bad[0][:120]})
                        continue
                # Published-contacts rule: contact without source link.
                try:
                    ctype = ""
                    if isinstance(c, dict):
                        t = c.get("type")
                        if isinstance(t, str):
                            ctype = t.strip().lower()
                    no_prov = (ctype in CONTACT_TYPES and not bool(
                        entry.get("has_provenance", False)))
                    # recompute when caller passed raw findings directly
                    if ctype in CONTACT_TYPES and \
                            "has_provenance" not in entry:
                        no_prov = not _has_contact_provenance(raw_d, c)
                except Exception:
                    no_prov = False
                if no_prov:
                    refused.append(
                        {"index": idx, "reason": "insufficient_evidence",
                         "detail": "unpublished contact without source link "
                                   "(omit or add publishing-page URL)"})
                    continue
                if score < mins:
                    refused.append(
                        {"index": idx, "reason": "insufficient_evidence",
                         "detail": "evidence_score %d below threshold %d "
                                   "(single low-confidence source, no "
                                   "corroboration/provenance)" % (score, mins)})
                    continue
                kept.append(dict(c))
            except Exception:
                try:
                    refused.append({"index": -1, "reason": "unparsable",
                                    "detail": "unparsable finding"})
                except Exception:
                    pass
                continue
        return {"kept": kept, "refused": refused}
    except Exception:
        return {"kept": [], "refused": []}
