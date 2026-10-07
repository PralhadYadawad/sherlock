"""db layer tests — mode switching + sqlite path. No network, ever."""
import os

import db


def test_mode_sqlite_by_default(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.mode() == "sqlite"


def test_mode_postgres_when_configured_and_drivable(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL",
                       "postgresql://u:DUMMY@localhost/db")
    try:
        __import__("psycopg")
    except ImportError:
        import pytest
        pytest.skip("psycopg not installed")
    assert db.mode() == "postgres"


def test_mode_sqlite_when_no_driver(monkeypatch):
    import builtins
    monkeypatch.setenv("SUPABASE_DB_URL",
                       "postgresql://u:DUMMY@localhost/db")
    _real = builtins.__import__

    def _fake(name, *a, **k):
        if name in ("psycopg", "psycopg2"):
            raise ImportError("blocked")
        return _real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _fake)
    assert db.mode() == "sqlite"


def test_dsn_missing_raises(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    try:
        db.dsn()
        raise AssertionError("should have raised")
    except RuntimeError:
        pass


def test_sqlite_connect_memory():
    conn = db.connect_sqlite(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE t (id TEXT)")
    cur.execute("INSERT INTO t VALUES ('x')")
    assert cur.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    conn.close()
