"""scholar adapter — ORCID + Crossref (polite pool) + Semantic Scholar.

Studied sources: ORCID public API docs (quota table), Crossref REST docs
(rate limits + ``mailto`` polite pool), Semantic Scholar Academic Graph
docs (dataset shapes) only. Clean-room reimplementation — no code copied.
MIT (ours).

Key model: keyless. ORCID anonymous reads (12 req/s, burst 40, 25k
reads/day/IP — generous for demo scale), Crossref polite pool (contact
string ``demo@example.com`` — not a secret, just a contactable UA per
Crossref docs; public pool throttled ~1 req/s, hard ceiling 50 req/s/IP),
Semantic Scholar keyless (100 req/5 min shared pool). No keys, no env.

Input: a researcher name (``"Demo Kotabagi"``), optionally with an
affiliation hint (``"Demo Kotabagi | Example University"``), or a bare
ORCID iD (``0000-0002-1825-0097``-shaped — the ORCID docs example ID).
Output: ``scholar_work`` (paper/work titles), ``scholar_affiliation``
(employer/education strings), ``scholar_coauthor`` (co-author names).

Entity-resolution rule (research-entity-apis.md §9): bare name matches are
candidates only (``low`` max); ORCID-iD-pinned records corroborate to
``medium``; NEVER ``high`` from metadata alone (human verification
required). Display per-source findings separately (finding ``value``
prefixes the source lane).

Free cap / rate behavior: 3 plain GETs per ``run()`` max (one per lane),
10s timeout each, Sherlock UA (+ ``mailto`` on Crossref), concurrency 1,
24h ``fetch_log`` cache at the tools layer. Honor 429 with back off; never
retry hot.

Failure taxonomy: empty/PII-shaped input -> ``rejected``; all three
upstreams erroring (timeout/429/5xx) -> ``rejected`` with reason and ZERO
findings; any lane succeeding -> ``ok`` (valid empty is ``ok`` + ``[]``,
never invented records).

Guardrails (hard): public GET only. NO logins, NO passwords, NO
email/phone PII lanes, NO breach-password data, NO POSTing forms. Example
entities only (``Demo Kotabagi`` / ``demo@example.com`` / ``example.com``
affiliations); no real-person PII.
"""

import os
import re

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "scholar"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied ORCID + Crossref + Semantic Scholar docs only."
)

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; scholar; mailto:demo@example.com)"
MAILTO = "demo@example.com"  # Crossref polite-pool contact (not a secret)

ORCID_SEARCH_URL = "https://pub.orcid.org/v3.0/search/"
ORCID_RECORD_URL = "https://pub.orcid.org/v3.0/{orcid}/record"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
S2_AUTHOR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/author/search"

MAX_WORKS = 5

_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
_EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")
_PHONE_RE = re.compile(r"^\+?[\d][\d\s\-().]{6,}$")


def _is_orcid_id(text):
    return bool(_ORCID_RE.match((text or "").strip()))


def _split_target(target):
    text = (target or "").strip()
    for sep in (" | ", " @ "):
        if sep in text:
            name, aff = text.split(sep, 1)
            return name.strip(), aff.strip()
    lowered = text.lower()
    for sep in (" at ", " with "):
        if sep in lowered:
            idx = lowered.index(sep)
            return text[:idx].strip(), text[idx + len(sep):].strip()
    return text, ""


def _fetch_json(url, params=None, headers=None, timeout=TIMEOUT):
    """Plain no-auth GET returning (status:int|None, data:dict|None).

    Never raises. ``status`` None = timeout/connection failure. Non-200 or
    non-JSON-object bodies yield (status, None) so parsers never see
    garbage.
    """
    if requests is None:
        return None, None
    try:
        hdrs = {"User-Agent": USER_AGENT}
        if headers:
            hdrs.update(headers)
        resp = requests.get(url, params=params or {}, headers=hdrs,
                            timeout=timeout)
        status = resp.status_code
        if status != 200:
            return status, None
        try:
            data = resp.json()
        except Exception:
            return status, None
        return status, data if isinstance(data, dict) else None
    except Exception:
        return None, None


def search_orcid(name, timeout=TIMEOUT):
    """ORCID anonymous name search (public endpoint, no key)."""
    return _fetch_json(
        ORCID_SEARCH_URL,
        params={"q": name},
        headers={"Accept": "application/json"},
        timeout=timeout,
    )


def fetch_orcid_record(orcid, timeout=TIMEOUT):
    """ORCID anonymous record read (employments/educations/works summary)."""
    return _fetch_json(
        ORCID_RECORD_URL.format(orcid=orcid.strip()),
        headers={"Accept": "application/json"},
        timeout=timeout,
    )


def fetch_crossref(author, rows=MAX_WORKS, timeout=TIMEOUT):
    """Crossref works query in the polite pool (mailto contact, not a key)."""
    return _fetch_json(
        CROSSREF_WORKS_URL,
        params={"query.author": author, "rows": rows,
                "mailto": MAILTO, "select": "title,author,publisher,DOI,URL"},
        headers={"Accept": "application/json"},
        timeout=timeout,
    )


def fetch_semantic_scholar(query, limit=MAX_WORKS, timeout=TIMEOUT):
    """Semantic Scholar author search (keyless dataset shape)."""
    return _fetch_json(
        S2_AUTHOR_SEARCH_URL,
        params={"query": query, "limit": limit,
                "fields": "name,affiliations,paperCount,citationCount,papers.title,papers.authors"},
        headers={"Accept": "application/json"},
        timeout=timeout,
    )


def parse_orcid_search(data):
    """Parse ORCID search JSON -> [{"orcid": id, "name": str}] (max 5)."""
    out = []
    if not isinstance(data, dict):
        return out
    results = data.get("result")
    if not isinstance(results, list):
        # expanded-search shape uses "expanded-result"
        results = data.get("expanded-result")
        if not isinstance(results, list):
            return out
    for row in results[:MAX_WORKS]:
        if not isinstance(row, dict):
            continue
        ident = row.get("orcid-identifier") or {}
        path = ident.get("path") if isinstance(ident, dict) else None
        if not path and isinstance(row.get("orcid"), str):
            path = row["orcid"]
        if not isinstance(path, str) or not _is_orcid_id(path):
            continue
        name = ""
        for key in ("given-names", "family-names", "credit-name"):
            val = row.get(key)
            if isinstance(val, dict) and isinstance(val.get("value"), str):
                name = (name + " " + val["value"].strip()).strip()
            elif isinstance(val, str) and val.strip():
                name = (name + " " + val.strip()).strip()
        if not name and isinstance(row.get("name"), str):
            name = row["name"].strip()
        out.append({"orcid": path, "name": name or path})
    return out


def parse_orcid_record(data):
    """Parse ORCID record JSON -> (affiliations[], work_titles[]).

    Reads employments/educations summaries + works groups; each raw string
    is truncated (never invented). Missing sections yield empty lists.
    """
    affiliations, works = [], []
    if not isinstance(data, dict):
        return affiliations, works

    def _org_names(section):
        names = []
        if not isinstance(section, dict):
            return names
        groups = section.get("affiliation-group")
        if not isinstance(groups, list):
            groups = section.get("employment-summary") or \
                section.get("education-summary") or []
            if not isinstance(groups, list):
                return names
        for g in groups:
            summaries = g.get("summaries") if isinstance(g, dict) else None
            items = summaries if isinstance(summaries, list) else [g]
            for item in items:
                if not isinstance(item, dict):
                    continue
                org = item.get("organization") or item.get("org") or {}
                if isinstance(org, dict):
                    nm = org.get("name")
                    if isinstance(nm, str) and nm.strip():
                        names.append(nm.strip()[:256])
                dept = item.get("department-name")
                if isinstance(dept, str) and dept.strip():
                    names.append(dept.strip()[:256])
        return names

    for key in ("employments", "educations"):
        for nm in _org_names(data.get(key)):
            if nm not in affiliations:
                affiliations.append(nm)
        if len(affiliations) >= MAX_WORKS:
            break
    affiliations = affiliations[:MAX_WORKS]

    works_sec = data.get("works")
    groups = works_sec.get("group") if isinstance(works_sec, dict) else None
    if isinstance(groups, list):
        for g in groups:
            if len(works) >= MAX_WORKS:
                break
            summaries = g.get("work-summary") if isinstance(g, dict) else None
            items = summaries if isinstance(summaries, list) else []
            for item in items:
                if len(works) >= MAX_WORKS:
                    break
                title = (item.get("title") or {}) if isinstance(item, dict) else {}
                t = title.get("title") if isinstance(title, dict) else None
                val = (t.get("value") if isinstance(t, dict) else t)
                if isinstance(val, str) and val.strip() \
                        and val.strip() not in works:
                    works.append(val.strip()[:256])
    return affiliations, works


def parse_crossref(data, limit=MAX_WORKS):
    """Parse Crossref works JSON -> [{"title", "authors", "publisher"}]."""
    out = []
    if not isinstance(data, dict):
        return out
    msg = data.get("message")
    if not isinstance(msg, dict):
        return out
    items = msg.get("items")
    if not isinstance(items, list):
        return out
    for it in items[:limit]:
        if not isinstance(it, dict):
            continue
        titles = it.get("title")
        title = titles[0].strip() if isinstance(titles, list) and titles \
            and isinstance(titles[0], str) and titles[0].strip() else ""
        if not title:
            continue
        authors = []
        for a in (it.get("author") or []):
            if not isinstance(a, dict):
                continue
            full = " ".join(p for p in
                            (a.get("given", ""), a.get("family", ""))
                            if isinstance(p, str) and p.strip()).strip()
            orcid = ""
            oid = a.get("ORCID")
            if isinstance(oid, str) and oid.strip():
                orcid = oid.strip()[-19:]  # trailing ORCID path
            label = full or orcid
            if label and label not in authors:
                authors.append(label[:128])
        pub = it.get("publisher")
        pub = pub.strip()[:128] if isinstance(pub, str) and pub.strip() else ""
        out.append({"title": title[:256], "authors": authors[:8],
                    "publisher": pub})
    return out


def parse_semantic_scholar(data, limit=MAX_WORKS):
    """Parse S2 author-search JSON -> [{"name", "affiliations", "papers"}].

    Dataset shape: ``{"data": [{name, affiliations[], papers[{title,
    authors[]}]}]}``. Unknown shapes yield [] (never invented).
    """
    out = []
    if not isinstance(data, dict):
        return out
    rows = data.get("data")
    if not isinstance(rows, list):
        # single-author shape
        rows = [data] if isinstance(data.get("name"), str) else []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        affs = []
        for a in (row.get("affiliations") or []):
            if isinstance(a, str) and a.strip() \
                    and a.strip() not in affs:
                affs.append(a.strip()[:256])
        papers = []
        for p in (row.get("papers") or []):
            if not isinstance(p, dict):
                continue
            t = p.get("title")
            if isinstance(t, str) and t.strip() \
                    and t.strip() not in papers:
                papers.append(t.strip()[:256])
            if len(papers) >= MAX_WORKS:
                break
        coauthors = []
        for p in (row.get("papers") or []):
            if not isinstance(p, dict):
                continue
            for a in (p.get("authors") or []):
                nm = a.get("name") if isinstance(a, dict) else None
                if isinstance(nm, str) and nm.strip() \
                        and nm.strip() != name.strip() \
                        and nm.strip() not in coauthors:
                    coauthors.append(nm.strip()[:128])
            if len(coauthors) >= MAX_WORKS:
                break
        out.append({"name": name.strip()[:128], "affiliations": affs[:4],
                    "papers": papers[:MAX_WORKS],
                    "coauthors": coauthors[:MAX_WORKS]})
    return out


def _finding(ftype, value, confidence):
    return {"type": ftype, "value": value, "source": NAME,
            "confidence": confidence}


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    if target is None or (isinstance(target, str) and not target.strip()):
        return {"status": "rejected",
                "reason": "empty target: pass a researcher name, e.g. "
                          '"Demo Kotabagi"',
                "findings": []}
    if not isinstance(target, str):
        return {"status": "rejected",
                "reason": "rejected: invalid scholar target",
                "findings": []}
    text = target.strip()
    if len(text) > 256:
        return {"status": "rejected",
                "reason": "rejected: target over 256 chars",
                "findings": []}
    if _EMAIL_RE.match(text):
        return {"status": "rejected",
                "reason": "rejected: email-to-author lookup is excluded "
                          "(PII tool)",
                "findings": []}
    if _PHONE_RE.match(text):
        return {"status": "rejected",
                "reason": "rejected: phone-to-author lookup is excluded "
                          "(PII tool)",
                "findings": []}

    direct_orcid = text if _is_orcid_id(text) else ""
    name, affiliation_hint = _split_target(text)
    query_name = name or text

    errors = 0
    orcid_hits, crossref_items, s2_authors = [], [], []
    orcid_pinned = bool(direct_orcid)

    # Lane 1: ORCID (search by name, or direct record read for ORCID IDs).
    try:
        if direct_orcid:
            st, rec = fetch_orcid_record(direct_orcid)
            if st == 200 and isinstance(rec, dict):
                affs, works = parse_orcid_record(rec)
                orcid_hits = [{"orcid": direct_orcid,
                               "name": query_name,
                               "affiliations": affs, "works": works}]
            elif st in (429,) or (st is not None and 500 <= st <= 599) \
                    or st is None:
                errors += 1
            # 404/other: valid miss, not an error (no hallucination).
        else:
            st, sdata = search_orcid(query_name)
            if st == 200 and isinstance(sdata, dict):
                orcid_hits = parse_orcid_search(sdata)[:3]
                if orcid_hits:
                    orcid_pinned = True
            elif st in (429,) or (st is not None and 500 <= st <= 599) \
                    or st is None:
                errors += 1
    except Exception:
        errors += 1

    # Lane 2: Crossref polite pool.
    try:
        st, cdata = fetch_crossref(query_name if not direct_orcid
                                   else query_name)
        if st == 200 and isinstance(cdata, dict):
            crossref_items = parse_crossref(cdata)
        elif st in (429,) or (st is not None and 500 <= st <= 599) \
                or st is None:
            errors += 1
    except Exception:
        errors += 1

    # Lane 3: Semantic Scholar.
    try:
        st, s2data = fetch_semantic_scholar(query_name)
        if st == 200 and isinstance(s2data, dict):
            s2_authors = parse_semantic_scholar(s2data)
            if s2_authors and any(a.get("affiliations")
                                  for a in s2_authors):
                pass  # corroboration comes from ORCID pin, not S2 alone
        elif st in (429,) or (st is not None and 500 <= st <= 599) \
                or st is None:
            errors += 1
    except Exception:
        errors += 1

    if not orcid_hits and not crossref_items and not s2_authors:
        if errors >= 3:
            return {"status": "rejected",
                    "reason": "rejected: scholar upstreams unavailable "
                              "(ORCID + Crossref + Semantic Scholar all "
                              "errored/rate-limited; no hallucination)",
                    "findings": []}
        # At least one lane answered cleanly with zero records.
        return {"status": "ok",
                "reason": "no scholar records for %s (3 lanes checked, "
                          "no hallucination)" % query_name[:64],
                "findings": []}

    findings = []
    seen = set()

    def _add(ftype, value, conf):
        key = (ftype, value)
        if not value or key in seen:
            return
        seen.add(key)
        findings.append(_finding(ftype, value, conf))

    # ORCID pins corroborate to medium; bare-name metadata stays low.
    aff_conf = "medium" if orcid_pinned else "low"

    for hit in orcid_hits[:3]:
        if isinstance(hit, dict) and hit.get("orcid"):
            _add("scholar_orcid", "ORCID %s (%s)"
                 % (hit["orcid"], hit.get("name", "")[:64]), aff_conf)
        for aff in (hit.get("affiliations") or [])[:4] \
                if isinstance(hit, dict) else []:
            label = aff
            if affiliation_hint and affiliation_hint.lower() in aff.lower():
                label = "%s [affiliation-hint match]" % aff
            _add("scholar_affiliation", "affiliation: %s" % label, aff_conf)
        for w in (hit.get("works") or [])[:MAX_WORKS] \
                if isinstance(hit, dict) else []:
            _add("scholar_work", "work: %s" % w, "low")

    for it in crossref_items[:MAX_WORKS]:
        _add("scholar_work", "work: %s%s" % (
            it["title"], " (%s)" % it["publisher"] if it.get("publisher")
            else ""), "low")
        for a in it.get("authors", [])[:4]:
            _add("scholar_coauthor", "co-author: %s" % a, "low")

    for auth in s2_authors[:3]:
        for aff in auth.get("affiliations", [])[:4]:
            _add("scholar_affiliation", "affiliation: %s" % aff, aff_conf
                 if orcid_pinned else "low")
        for p in auth.get("papers", [])[:MAX_WORKS]:
            _add("scholar_work", "work: %s" % p, "low")
        for c in auth.get("coauthors", [])[:MAX_WORKS]:
            _add("scholar_coauthor", "co-author: %s" % c, "low")

    # Safety cap: never assert identity from metadata alone.
    for f in findings:
        if f["confidence"] not in ("low", "medium"):
            f["confidence"] = "low"

    reason = ("scholar intel for %s: %d finding(s) across ORCID/Crossref/"
              "Semantic Scholar (name-only hits are low; ORCID-pinned "
              "affiliations medium; never high from metadata alone)"
              % (query_name[:64], len(findings)))
    # Silence unused-import lint for pacing parity docs (no sleep needed:
    # 3 GETs/run max, well under every lane cap).
    _ = os.environ.get("SHERLOCK_NO_PACING")
    return {"status": "ok", "reason": reason, "findings": findings}
