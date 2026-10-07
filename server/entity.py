"""Entity normalization + resolution (Kotabagi/Kotabaghi lesson as code).

Pure functions, stdlib only, no network. DUMMY/example fixtures only.

Lesson encoded: the same person name can appear with different
transliteration spellings (``Kotabagi`` vs ``Kotabaghi``, ``ph``/``f``,
``ee``/``i``, single/double consonants). Variant spellings must resolve
to one candidate ONLY when affiliation/location signals agree; different
affiliations must NEVER merge (homonym split).
"""

from __future__ import annotations

import re
import unicodedata

MAX_VARIANTS = 12
VALID_CONFIDENCE = ("high", "medium", "low")

_CONSONANTS = "bcdfgjklmnpqrstvwxz"  # h excluded: part of aspirate digraphs
_DOUBLED_RE = re.compile(r"([bcdfgjklmnpqrstvwxz])\1")
_AFFIL_KEYS = ("affiliation", "org", "affil")
_LOC_KEYS = ("location", "loc", "place")
_ID_KEYS = ("orcid", "email")


def normalize(name) -> str:
    """Trim, casefold, NFKD-strip diacritics, collapse whitespace.

    Non-string input -> ``""``. Never raises.
    """
    if not isinstance(name, str):
        return ""
    s = name.strip()
    if not s:
        return ""
    s = s.casefold()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def _add_unique(seen: list, known: set, cand: str) -> None:
    if cand and cand not in known:
        known.add(cand)
        seen.append(cand)


def variants(name) -> list:
    """Spelling/transliteration variants of a person name.

    Deterministic order (fixed rule sequence, first-seen dedupe),
    capped at ``MAX_VARIANTS`` (12). All outputs are normalized.
    Returns ``[]`` for empty/non-string input.

    Rules (in order):
    0. normalized base (always first)
    1. ph<->f swap (global replace, both directions if applicable)
    2. ee<->i swap (global replace, both directions if applicable)
    3. aspirated h: gh->g / bh->b / dh->d, and reverse g->gh / b->bh /
       d->dh for standalone consonants (covers Kotabagi<->Kotabaghi)
    4. with/without middle initial + dot stripping (``"a r kotabagi"``
       from ``"a r. kotabagi"``; removal only, never invents initials)
    5. surname-first order (last token moved front)
    6. single/double consonant collapse + doubling (fills remaining cap)
    """
    base = normalize(name)
    if not base:
        return []
    seen: list = []
    known: set = set()

    def add(cand: str) -> None:
        _add_unique(seen, known, cand)

    add(base)

    # 1. ph <-> f (transliteration spelling).
    if "ph" in base:
        add(base.replace("ph", "f"))
    if "f" in base:
        add(base.replace("f", "ph"))

    # 2. ee <-> i (transliteration spelling).
    if "ee" in base:
        add(base.replace("ee", "i"))
    if "i" in base:
        add(base.replace("i", "ee"))

    # 3. Aspirated consonants (transliteration lesson: Kotabagi<->Kotabaghi).
    for asp, plain in (("gh", "g"), ("bh", "b"), ("dh", "d")):
        if asp in base:
            add(base.replace(asp, plain))
    for asp, plain in (("gh", "g"), ("bh", "b"), ("dh", "d")):
        if plain in base and asp not in base:
            add(re.sub(plain + r"(?!h)", asp, base))

    # 4. Dots + middle initial (removal only).
    if "." in base:
        add(" ".join(base.replace(".", "").split()))
    tokens = base.split(" ")
    if len(tokens) == 3:
        mid = tokens[1].replace(".", "")
        if len(mid) == 1 and mid.isalpha():
            add(tokens[0] + " " + tokens[2])

    # 5. Surname-first order (last token front).
    if len(tokens) >= 2:
        add(tokens[-1] + " " + " ".join(tokens[:-1]))

    # 6. Single/double consonants.
    collapsed = _DOUBLED_RE.sub(r"\1", base)
    if collapsed != base:
        add(collapsed)
    doubled = set(m.group(1) for m in _DOUBLED_RE.finditer(base))
    singles_in_order: list = []
    for ch in base:
        if ch in _CONSONANTS and ch not in doubled \
                and ch not in singles_in_order:
            singles_in_order.append(ch)
    for ch in singles_in_order:
        if len(seen) >= MAX_VARIANTS:
            break
        idx = base.find(ch)
        if idx >= 0:
            add(base[:idx] + ch + base[idx:])

    return seen[:MAX_VARIANTS]


def _finding_name(f: dict) -> str:
    if not isinstance(f, dict):
        return ""
    for key in ("name", "value"):
        v = f.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _finding_field(f: dict, keys: tuple) -> str:
    if not isinstance(f, dict):
        return ""
    for key in keys:
        v = f.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _finding_sources(f: dict) -> list:
    if not isinstance(f, dict):
        return []
    out: list = []
    src = f.get("source")
    if isinstance(src, str) and src.strip():
        out.append(src.strip())
    srcs = f.get("sources")
    if isinstance(srcs, list):
        for s in srcs:
            if isinstance(s, str) and s.strip() and s.strip() not in out:
                out.append(s.strip())
    return out


def _norm_field(value: str) -> str:
    return normalize(value)


def _names_compatible(n1: str, n2: str) -> bool:
    a, b = normalize(n1), normalize(n2)
    if not a or not b:
        return True  # empty name never forces a split
    if a == b:
        return True
    try:
        va = set(variants(a))
        vb = set(variants(b))
    except Exception:
        return False
    return bool(va & vb)


def _hard_id(f: dict, key: str) -> str:
    v = f.get(key) if isinstance(f, dict) else ""
    return normalize(v) if isinstance(v, str) else ""


def _compatible(m1: dict, m2: dict) -> bool:
    """Two findings may share a cluster only if all hard signals agree."""
    a1 = _norm_field(_finding_field(m1, _AFFIL_KEYS))
    a2 = _norm_field(_finding_field(m2, _AFFIL_KEYS))
    if a1 and a2 and a1 != a2:
        return False  # NEVER merge different affiliations
    l1 = _norm_field(_finding_field(m1, _LOC_KEYS))
    l2 = _norm_field(_finding_field(m2, _LOC_KEYS))
    if l1 and l2 and l1 != l2:
        return False
    for key in _ID_KEYS:  # orcid/email mismatch = different persons
        i1, i2 = _hard_id(m1, key), _hard_id(m2, key)
        if i1 and i2 and i1 != i2:
            return False
    if not _names_compatible(_finding_name(m1), _finding_name(m2)):
        return False
    return True


def _cluster_confidence(member_count: int, n_sources: int,
                         has_affil: bool) -> str:
    if n_sources >= 2 and has_affil:
        return "high"
    if n_sources >= 2 or has_affil:
        return "medium"
    return "low"


def split_homonyms(findings) -> list:
    """Cluster findings into person candidates (homonym split).

    Split signals (hard, never merged across):
    - different non-empty affiliations (``affiliation``/``org``/``affil``)
    - different non-empty locations (``location``/``loc``/``place``)
    - different non-empty ``orcid``/``email`` ids
    - incompatible names (neither equal nor sharing a variant)

    Empty signals never force a split. Output order is deterministic
    (first-seen cluster order; members in input order; sources sorted).
    Each cluster carries ``confidence`` + ``sources``/``supporting_sources``.
    Pure function; never raises on garbage (skips non-dict entries).
    """
    if not isinstance(findings, list) or not findings:
        return []
    indexed: list = []
    for i, f in enumerate(findings):
        if isinstance(f, dict):
            indexed.append((i, f))
    if not indexed:
        return []

    clusters: list = []  # each: {"members": [(idx, dict)], }
    for idx, f in indexed:
        placed = False
        for cl in clusters:
            if all(_compatible(m, f) for _, m in cl["members"]):
                cl["members"].append((idx, f))
                placed = True
                break
        if not placed:
            clusters.append({"members": [(idx, f)]})

    out: list = []
    for cl in clusters:
        members = cl["members"]
        first_idx, first_f = members[0]
        names: list = []
        for _, m in members:
            disp = _finding_name(m)
            if disp and disp not in names:
                names.append(disp)
        affil = ""
        for _, m in members:
            v = _finding_field(m, _AFFIL_KEYS)
            if v:
                affil = v
                break
        loc = ""
        for _, m in members:
            v = _finding_field(m, _LOC_KEYS)
            if v:
                loc = v
                break
        sources: list = []
        for _, m in members:
            for s in _finding_sources(m):
                if s not in sources:
                    sources.append(s)
        sources = sorted(sources)
        co_signals: list = []
        for _, m in members:
            for key in ("coauthors", "co_signals", "email", "orcid",
                        "handle", "url"):
                v = m.get(key)
                if isinstance(v, str) and v.strip() \
                        and v.strip() not in co_signals:
                    co_signals.append(v.strip())
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item.strip() \
                                and item.strip() not in co_signals:
                            co_signals.append(item.strip())
        co_signals = sorted(co_signals)
        key = "%s|%s|%s" % (_norm_field(_finding_name(first_f)),
                            _norm_field(affil), _norm_field(loc))
        conf = _cluster_confidence(len(members), len(sources), bool(affil))
        member_dicts = [dict(m) for _, m in members]
        out.append({
            "key": key,
            "names": names,
            "affiliation": affil,
            "location": loc,
            "members": member_dicts,
            "member_indices": [i for i, _ in members],
            "member_count": len(members),
            "confidence": conf,
            "sources": list(sources),
            "supporting_sources": list(sources),
            "co_signals": co_signals,
        })
    return out
