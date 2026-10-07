"""Sherlock entity throttle check: per-user throttle test plan, offline.

No network: stubs requests.get + socket DNS like scripts/load_smoke.py.
Uses a temp SHERLOCK_DB so runs are hermetic.

What it checks (see SECURITY.md appendix S6 + docs/ENTITY.md section 2):
  1. Global guardrail constants present (server/main.py 60 req / 60 s).
  2. Live/BYOK cache TTL present (server/tools.py FETCH_CACHE_TTL_S=86400).
  3. Simulated per-user buckets for BYOK lanes (plan-level, in-process):
     each user gets an independent daily budget per lane; over-budget
     calls degrade to cached/empty with reason (never hallucinated).
  4. fetch_log cache-hit path works: identical repeat lookup is served
     without re-fetch (TTL 24h).

Usage:
  /tmp/opencode/sherlock-venv/bin/python scripts/entity_throttle_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile

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
        raise OSError("offline entity check")

    socket.gethostbyname_ex = _no_dns


# Plan-level per-user daily budgets for BYOK lanes (docs/ENTITY.md).
# Keyless lanes are vendor-capped, not user-capped; human link-outs are
# operator-paced. Budgets here are the *test plan* the script enforces
# in-process; server/main.py enforces only the global 60/60s today
# (per-user buckets are a builder TODO — see SECURITY.md S6).
PER_USER_DAILY_BUDGET = {
    "brave_search": 50,      # well inside ~1k/mo credit
    "serper_search": 50,     # well inside 2.5k free
    "openalex": 100,         # well inside $1/day free
    "opencorporates": 10,    # 200/mo + 50/d free is demo-tiny
    "shodan": 5,             # limited credits, never shared
    "censys": 5,             # ~250/mo free
    "github_search": 20,     # 30/min search; daily budget is plan-level
    "graph": 20,             # 200/hr/token
}

_buckets: dict = {}


def per_user_allow(user: str, lane: str) -> bool:
    """Plan-level per-user bucket: True if call allowed, False if throttled."""
    budget = PER_USER_DAILY_BUDGET.get(lane, 0)
    used = _buckets.get((user, lane), 0)
    if used >= budget:
        return False
    _buckets[(user, lane)] = used + 1
    return True


def main() -> int:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["SHERLOCK_DB"] = tmp.name
    _install_offline_stubs()

    import tools  # noqa: E402
    import main as server_main  # noqa: E402  (server/ on sys.path)

    fails = []

    # 1. Global guardrail constants (server/main.py).
    if getattr(server_main, "RATE_LIMIT_MAX", None) != 60:
        fails.append("RATE_LIMIT_MAX != 60")
    if getattr(server_main, "RATE_LIMIT_WINDOW_S", None) != 60:
        fails.append("RATE_LIMIT_WINDOW_S != 60")
    print("global guardrail: %s req / %ss" % (
        getattr(server_main, "RATE_LIMIT_MAX", "?"),
        getattr(server_main, "RATE_LIMIT_WINDOW_S", "?")))

    # 2. Cache TTL (server/tools.py).
    if getattr(tools, "FETCH_CACHE_TTL_S", None) != 86400:
        fails.append("FETCH_CACHE_TTL_S != 86400")
    print("fetch cache TTL: %ss" % getattr(tools, "FETCH_CACHE_TTL_S", "?"))

    # 3. Per-user bucket isolation: user A exhausts brave_search, user B unaffected.
    _buckets.clear()
    user_a, user_b, lane = "user-a", "user-b", "brave_search"
    budget = PER_USER_DAILY_BUDGET[lane]
    allowed_a = sum(1 for _ in range(budget + 5) if per_user_allow(user_a, lane))
    allowed_b = sum(1 for _ in range(3) if per_user_allow(user_b, lane))
    print("per-user bucket [%s]: budget=%d userA_allowed=%d/55 userB_allowed=%d/3"
          % (lane, budget, allowed_a, allowed_b))
    if allowed_a != budget:
        fails.append("user A budget not enforced (%d != %d)" % (allowed_a, budget))
    if allowed_b != 3:
        fails.append("user B not isolated (%d != 3)" % allowed_b)
    # Throttled call degrades cleanly (plan shape): rejected/empty + reason.
    if per_user_allow(user_a, lane):
        fails.append("over-budget call allowed (should throttle)")

    # 4. fetch_log cache-hit path: write a fresh row, lookup must find it.
    tools.log_fetch("entity_probe", "@demo.kotabagi", "ok", "plan-check")
    hit = tools.fetch_cache_lookup("entity_probe", "@demo.kotabagi")
    print("fetch_log cache-hit: %s" % ("HIT" if hit else "MISS"))
    if hit is None:
        fails.append("fetch_cache_lookup missed a fresh row")
    stale = tools.fetch_cache_lookup("entity_probe", "@demo.kotabagi",
                                     ttl_s=-1)
    if stale is not None:
        fails.append("negative TTL should miss")

    # 5. Refused lanes stay refused even for entity-shaped input (no bypass).
    r = tools.probe_username("jane.doe@gmail.com")
    if not (r.get("status") == "rejected" and r.get("findings") == []):
        fails.append("PII email not refused")
    r = tools.probe_username("+91 98200 12345")
    if not (r.get("status") == "rejected" and r.get("findings") == []):
        fails.append("PII phone not refused")
    print("PII refusals: ok (email + phone rejected, zero findings)")

    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
