"""db.py — Postgres (Supabase) with sqlite fallback. Never crashes on import.

- If SUPABASE_DB_URL (or DATABASE_URL) is set AND a postgres driver is
  importable -> Postgres mode (psycopg v3 preferred, psycopg2 fallback).
- Otherwise -> sqlite fallback (local file or :memory:). Offline tests and
  demos always work; the committed suite never requires network.
- Secrets: URL comes from env only, never logged, never committed.
"""
from __future__ import annotations

import os
import sqlite3

_PG_DRIVERS = ("psycopg", "psycopg2")


def mode():
    """'postgres' when configured AND drivable, else 'sqlite'."""
    if not (os.environ.get("SUPABASE_DB_URL")
            or os.environ.get("DATABASE_URL")):
        return "sqlite"
    for _d in _PG_DRIVERS:
        try:
            __import__(_d)
            return "postgres"
        except Exception:
            continue
    return "sqlite"


def dsn():
    """Connection string from env. Raises RuntimeError when absent."""
    _url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not _url:
        raise RuntimeError("no SUPABASE_DB_URL/DATABASE_URL configured")
    return _url


def connect_sqlite(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def connect():
    """Connect in the current mode. Postgres errors propagate (loud)."""
    if mode() == "postgres":
        for _d in _PG_DRIVERS:
            try:
                _mod = __import__(_d)
                return _mod.connect(dsn())
            except ImportError:
                continue
    return connect_sqlite(os.environ.get("ASKME_DB_PATH",
                                         os.environ.get("SHERLOCK_DB",
                                                        ":memory:")))
