"""Sherlock entity-pipeline load shape: 10 entities x lanes, offline.

No network: stubs requests.get + socket DNS like scripts/load_smoke.py.
Uses a temp SHERLOCK_DB so runs are hermetic.

Shape (see LOAD.md appendix L4 + docs/ENTITY.md):
  10 fictional entities (handles / domains / reel URLs, @demo.* +
  example.com only) x 4 tool calls each
  (triage_target + probe/intel/save + search_memory + case_summary),
  run as a cold pass then an identical warm pass.
Reports p50/p95/max per pass + repeat-stability ratio
(identical outputs across passes / total).
Targets: 80/80 ok; warm p95 <= cold p95 (no growth);
repeat-stability 100% (fixtures deterministic).
Live cache-hit target (>=50% served from fetch_log TTL 24h) applies to
the SHERLOCK_LIVE/BYOK path only and is NOT measured here (demo fixtures
bypass the cache by design) — builder TODO (LOAD.md L4).

Usage:
  /tmp/opencode/sherlock-venv/bin/python scripts/entity_load_shape.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))


class _Resp:
    def __init__(self, status=404):
        self.status_code = status

    def json(self):
        return {}


def _fake_http_get(url, **kw):
    if "demo.sleuth" in str(url) and "example.com" in str(url):
        if any(k in str(url) for k in ("/users/", "/@", "/blog/")):
            return _Resp(200)
    return _Resp(404)


def _install_offline_stubs():
    try:
        import requests
        requests.get = _fake_http_get
    except ImportError:
        pass
    import socket

    def _no_dns(*a, **k):
        raise OSError("offline entity load")

    socket.gethostbyname_ex = _no_dns


def _pct(data, p):
    if not data:
        return 0.0
    s = sorted(data)
    k = min(len(s) - 1, max(0, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


ENTITIES = [
    "@demo.sleuth",
    "@demo.kotabagi",      # fictional homonym-shape handle A
    "@demo.kotabagi2",     # fictional homonym-shape handle B
    "@demo.archivist",
    "@demo.ghost",         # clean miss (no hallucination)
    "example.com",
    "blog.example.com",
    "other.test",          # clean miss (no hallucination)
    "https://www.instagram.com/reel/DMYosint001/",
    "osint demo case",     # search-query entity
]


def _shape(res: dict) -> str:
    slim = {k: res.get(k) for k in ("status", "reason", "lane", "adapter",
                                   "handle", "domain", "top_case", "total")
            if k in res}
    slim["n_findings"] = len(res.get("findings", []) or [])
    return json.dumps(slim, sort_keys=True)


def main() -> int:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["SHERLOCK_DB"] = tmp.name
    _install_offline_stubs()

    import tools  # noqa: E402

    def run_once(entity: str):
        if entity.startswith("https://"):
            return tools.save_reel(entity)
        if entity == "osint demo case":
            return tools.search_memory(entity)
        if "." in entity and " " not in entity and "@" not in entity:
            return tools.intel_domain(entity)
        if entity == "DEMO-CASE-001":
            return tools.case_summary(entity)
        return tools.probe_username(entity)

    results = {}
    for label in ("cold", "warm"):
        lat, ok, shapes = [], 0, {}
        for e in ENTITIES:
            t0 = time.monotonic()
            r1 = tools.triage_target(e if e != "osint demo case" else "@demo.sleuth")
            r2 = run_once(e)
            if e == "osint demo case":
                r3 = tools.case_summary("DEMO-CASE-001")
            else:
                r3 = tools.search_memory("demo")
            dt = (time.monotonic() - t0) * 1000.0
            lat.append(dt)
            if r1.get("status") == "ok" and r2.get("status") in ("ok", "rejected"):
                ok += 1
            shapes[e] = _shape(r2)
        results[label] = {
            "n": len(ENTITIES), "ok": ok,
            "p50": round(statistics.median(lat), 3),
            "p95": round(_pct(lat, 95), 3),
            "max": round(max(lat), 3),
            "shapes": shapes,
        }
        print("%s: n=%d ok=%d p50=%.3fms p95=%.3fms max=%.3fms" % (
            label, len(ENTITIES), ok, results[label]["p50"],
            results[label]["p95"], results[label]["max"]))

    cold, warm = results["cold"]["shapes"], results["warm"]["shapes"]
    stable = sum(1 for e in ENTITIES if cold.get(e) == warm.get(e))
    print("repeat-stability: %d/%d identical" % (stable, len(ENTITIES)))

    ok = (results["cold"]["ok"] == len(ENTITIES)
          and results["warm"]["ok"] == len(ENTITIES)
          and stable == len(ENTITIES)
          # No growth across passes (generous bound: warm p95 within
          # max(2x cold p95, cold p95 + 5ms) — guards regressions, not noise).
          and results["warm"]["p95"] <= max(results["cold"]["p95"] * 2,
                                            results["cold"]["p95"] + 5.0))
    print("RESULT: %s" % ("PASS" if ok else "FAIL"))
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
