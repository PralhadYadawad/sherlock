"""deep_probe adapter — broad username sweep via the sherlock-project engine.

Third-party: sherlock-project (MIT License; https://github.com/sherlock-project/sherlock)
used as a pip dependency (`sherlock-project==0.4.15`), NOT vendored. Attribution +
full license in docs/THIRD_PARTY.md. This adapter file itself is clean-room
code, MIT (ours): it wraps the engine's `sherlock()` call, maps its
QueryStatus results onto our finding schema, and enforces our product rules
(demo scoping, pacing note, NSFW skip, no proxies, polite timeouts).

Role in the system: the DEEP lane. The fast lane (username_probe, 30 sites)
answers interactively in seconds; this lane sweeps ~400+ sites for
leave-no-stone runs and takes minutes. Same technique, more doors.
"""

from __future__ import annotations

import json
import os

NAME = "deep_probe"
LICENSE_NOTE = (
    "Wraps sherlock-project (MIT, "
    "https://github.com/sherlock-project/sherlock) as a pip dependency; "
    "adapter code is clean-room MIT (ours)."
)

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; public-presence-check)"

# Cap the sweep so one call stays bounded. Full list (~450 non-NSFW sites)
# is available via sites_cap=None; the default keeps deep scans in the
# low-minutes range on a decent link.
# High-signal doors first: capped sweeps check the important sites before
# the long tail of obscure ones (many of which WAF-gate datacenter IPs).
_PRIORITY_SITES = (
    "GitHub", "Reddit", "YouTube", "Twitter", "Twitch", "Instagram",
    "LinkedIn", "TikTok", "Pinterest", "Medium", "Flickr", "Vimeo",
    "Spotify", "DeviantArt", "Behance", "Dribbble", "GitLab", "BitBucket",
    "Kaggle", "HackerRank", "LeetCode", "Codepen", "Replit.com", "npm",
    "PyPi", "Docker Hub", "WordPress", "Blogger", "tumblr", "Steam",
    "Roblox", "Patreon", "mastodon.social", "mastodon.cloud",
    "Hugging Face", "Keybase", "SoundCloud", "SpeakerDeck",
)


def _order_sites(sites):
    """Priority doors first (stable), then the rest alphabetically."""
    _first = [_n for _n in _PRIORITY_SITES if _n in sites]
    _rest = sorted(_n for _n in sites if _n not in _PRIORITY_SITES)
    return { _n: sites[_n] for _n in _first + _rest }


DEFAULT_SITES_CAP = 150


def _engine():
    """Import engine pieces lazily so a missing dep degrades, never crashes."""
    try:
        from sherlock_project import sherlock as _sherlock_mod
        from sherlock_project.sites import SitesInformation
        from sherlock_project.result import QueryStatus
        from sherlock_project.notify import QueryNotify
        return _sherlock_mod, SitesInformation, QueryStatus, QueryNotify
    except Exception:
        return None, None, None, None


def _local_data_path():
    """Absolute path to the engine's bundled site list (no network)."""
    try:
        from importlib import resources as _res
        _p = _res.files("sherlock_project") / "resources" / "data.json"
        _s = str(_p)
        if os.path.isfile(_s):
            return _s
    except Exception:
        pass
    return None


def _load_site_data():
    """Load (name -> raw site-dict), NSFW skipped. Returns (sites, reason).

    Reads the engine's bundled data.json directly (no network, no
    exclusions fetch) and passes RAW dicts through: the engine consumes
    net_info["url"] / errorType / regexCheck itself. NSFW entries are
    skipped here (family-safe product).
    """
    _path = _local_data_path()
    if not _path:
        return None, "engine site list unavailable"
    if _engine()[0] is None:
        return None, "engine unavailable: install sherlock-project"
    try:
        with open(_path, encoding="utf-8") as _fh:
            _raw = json.load(_fh)
    except Exception:
        return None, "engine site list unreadable"
    if not isinstance(_raw, dict):
        return None, "engine site list malformed"
    _sites = {}
    for _name, _entry in _raw.items():
        if _name == "$schema" or not isinstance(_entry, dict):
            continue
        try:
            if _entry.get("isNSFW"):
                continue
            if not _entry.get("url"):
                continue
            _sites[_name] = _entry
        except Exception:
            continue
    if not _sites:
        return None, "engine site list empty after filtering"
    return _sites, None


def _query(handle, site_data, timeout=TIMEOUT):
    """Run the engine sweep. Isolated for tests (monkeypatch this)."""
    _sherlock_mod, _, QueryStatus, QueryNotify = _engine()

    class _Silent(QueryNotify):
        def start(self, message=None, id=None):
            return None

        def update(self, result=None):
            return None

        def finish(self, message=None):
            return None

    return _sherlock_mod.sherlock(
        handle, site_data, _Silent(), timeout=timeout)


def _map_results(results, QueryStatus):
    """Engine statuses -> (findings, errors, skipped). Never hallucinates.

    Note: results[site]["status"] is a QueryResult OBJECT wrapping the
    QueryStatus enum at .status (not the enum itself) — unwrap first.
    """
    _findings, _errors, _skipped = [], 0, 0
    for _site, _res in (results or {}).items():
        try:
            _wrapped = _res.get("status") if isinstance(_res, dict) else None
            _status = getattr(_wrapped, "status", _wrapped)
            _url = _res.get("url_user") or ""
        except Exception:
            _errors += 1
            continue
        if _status == QueryStatus.CLAIMED:
            if not _url.startswith("http"):
                _errors += 1
                continue
            _findings.append({
                "type": "presence",
                "value": "%s: %s" % (_site, _url),
                "source": NAME,
                "confidence": "medium",
            })
        elif _status in (QueryStatus.AVAILABLE, QueryStatus.ILLEGAL):
            _skipped += 1
        else:
            _errors += 1
    return _findings, _errors, _skipped


def _validator():
    """Borrow username_probe's handle validator (same package, our code).

    Registry loads adapters via spec_from_file_location (no package
    context), so a plain relative import fails there — fall back to
    loading the sibling by file path. Never raises; last resort rejects
    everything instead of crashing.
    """
    try:
        from .username_probe import _normalize_handle
        return _normalize_handle
    except Exception:
        pass
    try:
        import importlib.util as _ilu
        _sib = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "username_probe.py")
        _spec = _ilu.spec_from_file_location("_dp_username_probe", _sib)
        if _spec and _spec.loader:
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            return _mod._normalize_handle
    except Exception:
        pass

    def _closed(_t):
        return None, "internal error: handle validator unavailable"

    return _closed


def run(target: str, sites_cap: int | None = DEFAULT_SITES_CAP) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    handle, error = _validator()(target)
    if error:
        return {"status": "rejected", "reason": error, "findings": []}

    if handle == "demo.sleuth" or handle.startswith("demo."):
        return {
            "status": "ok",
            "reason": ("demo handles use the fast lane (username_probe, "
                       "pinned fixtures); the deep lane sweeps live sites "
                       "only for real handles"),
            "findings": [],
        }

    _sites, _err = _load_site_data()
    if _sites is None:
        return {"status": "rejected", "reason": _err, "findings": []}
    _sites = _order_sites(_sites)
    if sites_cap is not None:
        _sites = dict(list(_sites.items())[:sites_cap])
    if not _sites:
        return {"status": "rejected",
                "reason": "no sites left after cap/filter",
                "findings": []}

    try:
        _results = _query(handle, _sites)
    except Exception as exc:
        return {"status": "rejected",
                "reason": "deep sweep failed: %s" % type(exc).__name__,
                "findings": []}

    _, _, QueryStatus, _ = _engine()
    _findings, _errors, _skipped = _map_results(_results, QueryStatus)
    _total = len(_sites)
    if _findings:
        _reason = ("deep sweep: %d of %d sites hit for @%s (%d errored)" % (
            len(_findings), _total, handle, _errors))
    else:
        _reason = ("no live presence found for @%s "
                   "(deep sweep, %d sites checked, %d errored)" % (
                       handle, _total, _errors))
    return {"status": "ok", "reason": _reason, "findings": _findings}
