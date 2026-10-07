"""Adapter registry: allow-list loader with builtin fixture fallback.

Contract (AGENTS.md section 2): core imports adapters via try/except with
builtin fixture fallback and NEVER crashes when an adapter module is missing.
Only allow-listed names may load.
"""

from __future__ import annotations

import importlib.util
import json
import os
import types

_BASE_ALLOW = ("username_probe", "domain_intel", "exif_local",
                "oembed_public")

# Optional entity lanes (orchestrator crew): added to the allow-list ONLY
# when their adapter files exist on disk. Guarded import stays unbreakable:
# missing files simply stay off the list (rejected, never crash). Present
# files on this box: websearch, scholar, company. page_reader has no file
# yet, so it stays rejected until a future crew lands it.
_OPTIONAL_ENTITY_LANES = ("websearch", "scholar", "company", "page_reader",
                          "deep_probe")


def _optional_present():
    here = os.path.dirname(os.path.abspath(__file__))
    present = []
    for _n in _OPTIONAL_ENTITY_LANES:
        try:
            if os.path.isfile(os.path.join(here, "adapters", _n + ".py")):
                present.append(_n)
        except Exception:
            continue
    return tuple(present)


ALLOW_LIST = _BASE_ALLOW + _optional_present()

_FIXTURE_FILES = {
    "username_probe": "username.json",
    "domain_intel": "domain.json",
    # exif_local has no fixture file: it parses user-supplied local bytes
    # only, so its fallback is always empty (never hallucinated).
    "oembed_public": "reel.json",
}

# Hardcoded fallback findings (used when fixture files are also absent).
# Values mirror demo-data/fixtures/*.json per AGENTS.md section 3.
_HARDCODED_FALLBACKS = {
    "username_probe": [
        {"type": "presence",
         "value": "DemoHub: https://example.com/users/demo.sleuth",
         "source": "username_probe", "confidence": "medium"},
        {"type": "presence",
         "value": "DemoCode: https://example.com/@demo.sleuth",
         "source": "username_probe", "confidence": "medium"},
        {"type": "presence",
         "value": "DemoBlog: https://example.com/blog/demo.sleuth",
         "source": "username_probe", "confidence": "medium"},
    ],
    "domain_intel": [
        {"type": "subdomain", "value": "blog.example.com",
         "source": "domain_intel", "confidence": "medium"},
        {"type": "subdomain", "value": "www.example.com",
         "source": "domain_intel", "confidence": "medium"},
        {"type": "contact", "value": "admin@example.com",
         "source": "domain_intel", "confidence": "low"},
    ],
    "oembed_public": [
        {"type": "author", "value": "@demo.archivist",
         "source": "oembed_public", "confidence": "medium"},
        {"type": "caption",
         "value": ("open-source research notes: tracing public handles "
                   "across demo sites for DEMO-CASE-001. Methods only, "
                   "no private data."),
         "source": "oembed_public", "confidence": "medium"},
        {"type": "transcript_link", "value": "https://example.com/resource-1",
         "source": "oembed_public", "confidence": "low"},
        {"type": "transcript_link", "value": "https://example.com/resource-2",
         "source": "oembed_public", "confidence": "low"},
    ],
    "exif_local": [],
    # Optional entity lanes have no fixture files: their fallback is always
    # empty (never hallucinated). Live data comes from the real adapters
    # when present; offline entity fixtures live in tools.py (SHERLOCK_LIVE
    # gating), not here.
    "websearch": [],
    "scholar": [],
    "company": [],
    "page_reader": [],
}

_DEMO_MATCH = {
    "username_probe": ("demo.sleuth", "@demo.sleuth"),
    "domain_intel": ("example.com",),
    "oembed_public": ("DMYosint001",),
    "exif_local": (),
    # Entity lanes match demo/example placeholders only (never real PII).
    "websearch": ("demo", "example"),
    "scholar": ("demo", "kotabagi", "example"),
    "company": ("example",),
    "page_reader": ("example.com",),
}


def fixture_dir() -> str:
    """Resolve the fixtures directory (override via SHERLOCK_FIXTURES)."""
    override = os.environ.get("SHERLOCK_FIXTURES")
    if override:
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "demo-data", "fixtures")


def _load_fixture_findings(name: str) -> list:
    fname = _FIXTURE_FILES.get(name)
    if not fname:
        return []
    path = os.path.join(fixture_dir(), fname)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        findings = data.get("findings", []) if isinstance(data, dict) else []
        return [dict(f) for f in findings if isinstance(f, dict)]
    except (OSError, ValueError):
        return [dict(f) for f in _HARDCODED_FALLBACKS.get(name, [])]


def _fallback_run(name: str, demo_markers: tuple):
    def run(target: str) -> dict:
        if not isinstance(target, str) or not target.strip():
            return {"status": "rejected", "reason": "empty target", "findings": []}
        t = target.strip()
        if any(m in t for m in demo_markers):
            return {"status": "ok", "reason": "fixture fallback",
                    "findings": _load_fixture_findings(name) or
                    [dict(f) for f in _HARDCODED_FALLBACKS.get(name, [])]}
        return {"status": "ok",
                "reason": "no fixtures for this target; no hallucination",
                "findings": []}

    return run


def _rejected_run(reason: str):
    def run(target: str) -> dict:
        return {"status": "rejected", "reason": reason, "findings": []}

    return run


def _load_from_file(name: str):
    """Try loading server/adapters/<name>.py by path. Returns module or None."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "adapters", name + ".py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            "sherlock_adapter_%s" % name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not callable(getattr(mod, "run", None)):
            return None
        return mod
    except Exception:
        return None


def load_adapter(name: str):
    """Load one adapter by allow-listed name. Never raises.

    Returns a namespace with NAME, run(target), and fallback: bool.
    Unknown names yield a rejected-adapter; missing/broken modules yield
    the builtin fixture fallback.
    """
    if not isinstance(name, str) or name not in ALLOW_LIST:
        ns = types.SimpleNamespace(
            NAME=name if isinstance(name, str) else "",
            run=_rejected_run("not allow-listed: %r" % (name,)),
            fallback=False,
            rejected=True,
        )
        return ns
    mod = _load_from_file(name)
    if mod is not None:
        return types.SimpleNamespace(
            NAME=getattr(mod, "NAME", name), run=mod.run,
            fallback=False, rejected=False)
    return types.SimpleNamespace(
        NAME=name, run=_fallback_run(name, _DEMO_MATCH.get(name, ())),
        fallback=True, rejected=False)


def list_adapters() -> list:
    """Load every allow-listed adapter (never raises)."""
    return [load_adapter(n) for n in ALLOW_LIST]


def run_adapter(name: str, target: str, **kwargs) -> dict:
    """Run one adapter safely; always returns the contract dict.

    Extra kwargs (stream routing, e.g. sites_cap for the deep_probe deep
    lane) forward to adapters that accept them; single-arg runs (fixture
    fallback shims, older callers/mocks) retry without kwargs. Never raises.
    """
    try:
        adapter = load_adapter(name)
        try:
            if kwargs:
                res = adapter.run(target, **kwargs)
            else:
                res = adapter.run(target)
        except TypeError:
            res = adapter.run(target)
    except Exception as exc:  # never crash callers
        return {"status": "rejected",
                "reason": "adapter error: %s" % type(exc).__name__,
                "findings": []}
    if not isinstance(res, dict):
        return {"status": "rejected", "reason": "bad adapter shape",
                "findings": []}
    res.setdefault("status", "rejected")
    res.setdefault("reason", "")
    res.setdefault("findings", [])
    if not isinstance(res["findings"], list):
        res["findings"] = []
    return res
