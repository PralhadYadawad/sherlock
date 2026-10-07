#!/usr/bin/env python3
"""Provision + verify the Supabase project. Needs SUPABASE_DB_URL in env.

Usage: SUPABASE_DB_URL='postgresql://postgres:PASS@db.<ref>.supabase.co:5432/postgres' \
       python3 scripts/supabase_remote.py [--seed]

Does: enable vector extension -> run supabase/schema.sql -> (optional --seed)
run supabase/seed_fake.sql -> assert 20 findings incl. DEMO-CASE-001 shape.
URL is never printed. Exits nonzero with reason on any failure.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import db  # noqa: E402


def _split_statements(text):
    """Split on ';' ignoring full-line '--' comments (sqlite file headers)."""
    _lines = [l for l in text.splitlines()
              if not l.strip().startswith("--")]
    return [s.strip() for s in "\n".join(_lines).split(";") if s.strip()]


def _run(conn, sql, label):
    cur = conn.cursor()
    try:
        cur.execute(sql)
    except Exception as exc:
        print("FAIL %s: %s: %s" % (label, type(exc).__name__, exc))
        return False
    return True


def main():
    if db.mode() != "postgres":
        print("FAIL: postgres driver missing or no URL "
              "(pip install 'psycopg[binary]' + set SUPABASE_DB_URL)")
        return 1
    try:
        conn = db.connect()
        conn.autocommit = True
    except Exception as exc:
        print("FAIL connect: %s: %s" % (type(exc).__name__, exc))
        return 1
    ok = True
    ok &= _run(conn, 'CREATE EXTENSION IF NOT EXISTS "vector";', "vector ext")
    with open(os.path.join(ROOT, "supabase/schema_pg.sql"),
              encoding="utf-8") as _fh:
        for _i, _stmt in enumerate(_split_statements(_fh.read())):
            ok &= _run(conn, _stmt, "schema_pg#%d" % _i)
    if "--seed" in sys.argv:
        with open(os.path.join(ROOT, "supabase/seed_pg.sql"),
                  encoding="utf-8") as _fh:
            for _i, _stmt in enumerate(_split_statements(_fh.read())):
                ok &= _run(conn, _stmt, "seed_pg#%d" % _i)
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(*) FROM findings;")
        _n = cur.fetchone()[0]
        print("findings: %d" % _n)
        ok &= _n >= 5
        cur.execute(
            "SELECT case_id FROM findings WHERE value LIKE '%demo.sleuth%' "
            "OR value LIKE '%example.com%' LIMIT 1;")
        _row = cur.fetchone()
        print("case probe: %s" % (_row[0] if _row else None))
        ok &= bool(_row and _row[0] == "DEMO-CASE-001")
    except Exception as exc:
        print("FAIL verify: %s: %s" % (type(exc).__name__, exc))
        ok = False
    conn.close()
    print("REMOTE " + ("ALL GREEN" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
