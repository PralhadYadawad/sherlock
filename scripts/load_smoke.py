"""Sherlock load smoke: 100 triages + 100 searches, offline fixtures only.

No network: stubs requests.get + socket DNS like server/test_core.py.
Uses a temp SHERLOCK_DB so runs are hermetic. Prints p50/p95 latencies.

Usage:
  /tmp/opencode/sherlock-venv/bin/python scripts/load_smoke.py
  /tmp/opencode/sherlock-venv/bin/python scripts/load_smoke.py --triages 100 --searches 100
"""

from __future__ import annotations

import argparse
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
        raise OSError("offline smoke")

    socket.gethostbyname_ex = _no_dns


def _pct(data, p):
    if not data:
        return 0.0
    s = sorted(data)
    k = min(len(s) - 1, max(0, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--triages", type=int, default=100)
    ap.add_argument("--searches", type=int, default=100)
    args = ap.parse_args()

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["SHERLOCK_DB"] = tmp.name
    _install_offline_stubs()

    import tools  # noqa: E402  (server/ on sys.path)

    triage_targets = ["@demo.sleuth", "example.com",
                      "https://www.instagram.com/reel/DMYosint001/"]
    search_queries = ["osint demo case", "demo.sleuth", "example.com"]

    triage_lat, search_lat = [], []
    triage_ok = search_ok = 0

    for i in range(args.triages):
        t = triage_targets[i % len(triage_targets)]
        t0 = time.monotonic()
        res = tools.triage_target(t)
        triage_lat.append((time.monotonic() - t0) * 1000.0)
        if res.get("status") == "ok":
            triage_ok += 1

    for i in range(args.searches):
        q = search_queries[i % len(search_queries)]
        t0 = time.monotonic()
        res = tools.search_memory(q)
        search_lat.append((time.monotonic() - t0) * 1000.0)
        if res.get("status") == "ok":
            search_ok += 1

    def summ(lat):
        return {
            "n": len(lat),
            "p50_ms": round(statistics.median(lat), 3) if lat else 0.0,
            "p95_ms": round(_pct(lat, 95), 3),
            "max_ms": round(max(lat), 3) if lat else 0.0,
        }

    t, s = summ(triage_lat), summ(search_lat)
    print("triages: n=%d ok=%d p50=%.3fms p95=%.3fms max=%.3fms"
          % (t["n"], triage_ok, t["p50_ms"], t["p95_ms"], t["max_ms"]))
    print("searches: n=%d ok=%d p50=%.3fms p95=%.3fms max=%.3fms"
          % (s["n"], search_ok, s["p50_ms"], s["p95_ms"], s["max_ms"]))
    ok = triage_ok == args.triages and search_ok == args.searches
    print("RESULT: %s" % ("PASS" if ok else "FAIL"))
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
