"""Sherlock core orchestrator: FastAPI + MCP streamable HTTP.

Guarded imports: the module imports cleanly even when fastapi (or the
sibling adapter files) are absent — pure helpers below are always
available and covered by tests.
"""

from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

MAX_BODY_BYTES = 1024 * 1024  # 1 MB cap
RATE_LIMIT_MAX = 60
RATE_LIMIT_WINDOW_S = 60
# Cap distinct client buckets so the in-memory rate table cannot grow
# without bound (one entry per source IP; oldest evicted past the cap).
RATE_BUCKETS_MAX_CLIENTS = 10000

ALLOWED_ORIGINS = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://example.com",
]

_rate_buckets: dict = {}


def log_event(event: str, **fields) -> None:
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "event": event}
    rec.update(fields)
    try:
        print(json.dumps(rec), flush=True)
    except Exception:
        print("event=%s" % event, flush=True)


def is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    o = origin.rstrip("/")
    for allow in ALLOWED_ORIGINS:
        a = allow.rstrip("/")
        if o == a:
            return True
        if o.startswith("http://localhost:") or \
                o.startswith("http://127.0.0.1:"):
            return True
    return False


def enforce_size(body: bytes) -> bool:
    """True when body fits the 1 MB cap."""
    if body is None:
        return True
    return len(body) <= MAX_BODY_BYTES


def check_rate_limit(client_id: str, now: float | None = None) -> bool:
    """Sliding-window gate: True = allowed. Testable without FastAPI."""
    now = time.time() if now is None else now
    key = client_id or "anon"
    bucket = _rate_buckets.get(key)
    if bucket is None:
        if len(_rate_buckets) >= RATE_BUCKETS_MAX_CLIENTS:
            _rate_buckets.pop(next(iter(_rate_buckets)))
        bucket = _rate_buckets.setdefault(key, [])
    cutoff = now - RATE_LIMIT_WINDOW_S
    while bucket and bucket[0] <= cutoff:
        bucket.pop(0)
    if len(bucket) >= RATE_LIMIT_MAX:
        return False
    bucket.append(now)
    return True


def reset_rate_limits() -> None:
    _rate_buckets.clear()


def _load_tools():
    """Load server/tools.py by path, cached. Call _clear_caches in tests."""
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE
    import importlib.util
    path = os.path.join(HERE, "tools.py")
    spec = importlib.util.spec_from_file_location("sherlock_server_tools",
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _TOOLS_CACHE = mod
    return mod


_TOOLS_CACHE = None
_REGISTRY_CACHE = None


def _clear_caches() -> None:
    """Drop cached tool/registry modules (tests only)."""
    global _TOOLS_CACHE, _REGISTRY_CACHE
    _TOOLS_CACHE = None
    _REGISTRY_CACHE = None


def handle_mcp(message: dict) -> dict:
    """Minimal JSON-RPC MCP handler (streamable-HTTP body processor)."""
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "invalid request"}}
    mid = message.get("id")
    method = message.get("method")
    try:
        tools = _load_tools()
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32603,
                          "message": "tools unavailable: %s" % exc}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid,
                "result": {"tools": tools.TOOL_SCHEMAS}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = {"triage_target": tools.triage_target,
              "probe_username": tools.probe_username,
              "intel_domain": tools.intel_domain,
              "save_reel": tools.save_reel,
              "search_memory": tools.search_memory,
              "case_summary": tools.case_summary}.get(name)
        if fn is None or not isinstance(args, dict):
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602,
                              "message": "unknown tool %r" % (name,)}}
        try:
            result = fn(**args)
        except TypeError as exc:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602,
                              "message": "bad arguments: %s" % exc}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32603,
                              "message": "tool error: %s"
                              % type(exc).__name__}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": "unknown method %r" % (method,)}}


# ---- FastAPI app (guarded; falls back to None when fastapi missing) ----
try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    HAS_FASTAPI = True
except Exception:  # pragma: no cover - fallback path
    FastAPI = None
    Request = None
    CORSMiddleware = None
    JSONResponse = None
    HAS_FASTAPI = False

app = None
if HAS_FASTAPI:
    app = FastAPI(title="Sherlock", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Mcp-Session-Id"],
    )

    @app.middleware("http")
    async def _guards(request: Request, call_next):
        origin = request.headers.get("origin")
        if not is_origin_allowed(origin):
            return JSONResponse(status_code=403,
                                content={"detail": "origin not allowed"})
        try:
            declared = int(request.headers.get("content-length") or 0)
        except (TypeError, ValueError):
            declared = 0
        if declared > MAX_BODY_BYTES:
            return JSONResponse(status_code=413,
                                content={"detail": "body exceeds 1MB"})
        body = await request.body()
        if not enforce_size(body):
            return JSONResponse(status_code=413,
                                content={"detail": "body exceeds 1MB"})
        client = request.client.host if request.client else "anon"
        if not check_rate_limit(client):
            return JSONResponse(status_code=429,
                                content={"detail": "rate limit exceeded"})
        log_event("request", method=request.method, path=request.url.path)
        return await call_next(request)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "sherlock"}

    @app.get("/ready")
    async def ready():
        return {"ready": True, "adapters": list(_allow_list())}

    @app.post("/mcp")
    async def mcp(request: Request):
        try:
            message = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"jsonrpc": "2.0", "id": None,
                         "error": {"code": -32700,
                                   "message": "invalid JSON"}})
        return JSONResponse(content=handle_mcp(message))


def _allow_list() -> tuple:
    """Allow-listed adapter names, cached (call _clear_caches in tests)."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    try:
        _load_tools()
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "sherlock_server_registry",
            os.path.join(HERE, "registry.py"))
        reg = _ilu.module_from_spec(spec)
        spec.loader.exec_module(reg)
        _REGISTRY_CACHE = tuple(reg.ALLOW_LIST)
    except Exception:
        _REGISTRY_CACHE = ("username_probe", "domain_intel", "exif_local",
                           "oembed_public")
    return _REGISTRY_CACHE


def health_payload() -> dict:
    return {"status": "ok", "service": "sherlock"}


def ready_payload() -> dict:
    return {"ready": True, "adapters": list(_allow_list())}
