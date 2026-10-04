#!/usr/bin/env python3
"""
db_migrate.py — Apply db/migrations/*.sql in order, and remember what ran.

Until now this repo changed its schema with one-off scripts and nothing recorded
which had run, so production drifted from every checked-in definition (the products
view, listings.attributes) and a fresh database could not be rebuilt with confidence.
This is the smallest thing that fixes that: numbered SQL files, applied once each,
recorded in a `schema_migrations` table with a checksum so an edited migration is
noticed rather than silently skipped.

Write migrations to be idempotent (IF NOT EXISTS, CREATE OR REPLACE) — the first ones
codify what production already has, and are no-ops there.

  python scripts/db_migrate.py              # show what is pending, change nothing
  python scripts/db_migrate.py --run        # apply pending migrations, each in its own transaction
  python scripts/db_migrate.py --status     # applied / pending / edited-since-applied

Needs DATABASE_URL (direct Postgres, as on Render). From a sandbox where 5432 is
blocked, pass --via-http to use the Supabase Management API (SUPABASE_ACCESS_TOKEN;
see DB_ACCESS.md) — that path cannot wrap a migration in a transaction, so it is for
idempotent migrations only, which is all this directory should contain anyway.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "db" / "migrations"
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

TRACKING_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    text PRIMARY KEY,
  name       text NOT NULL,
  checksum   text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
"""


def migrations() -> list[tuple[str, str, str, str]]:
    """(version, filename, sql, checksum) in order."""
    out = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        m = _NAME.match(path.name)
        if not m:
            sys.exit(f"bad migration filename {path.name!r} — want NNNN_snake_case.sql")
        sql = path.read_text(encoding="utf-8")
        out.append((m.group(1), path.name, sql, hashlib.sha256(sql.encode()).hexdigest()[:16]))
    versions = [v for v, *_ in out]
    if len(versions) != len(set(versions)):
        sys.exit("two migrations share a version number")
    return out


class Postgres:
    def __init__(self, url: str):
        import psycopg2
        self.conn = psycopg2.connect(url)

    def query(self, sql: str) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall() if cur.description else []

    def apply(self, version: str, name: str, sql: str, checksum: str) -> None:
        with self.conn:              # one transaction: the migration and its record
            with self.conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (version, name, checksum) "
                            "VALUES (%s, %s, %s)", (version, name, checksum))

    def setup(self) -> None:
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(TRACKING_DDL)


class ManagementApi:
    def __init__(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import db_http
        self.db = db_http

    def query(self, sql: str) -> list[tuple]:
        return [tuple(r.values()) for r in self.db.run_sql(sql)]

    def apply(self, version: str, name: str, sql: str, checksum: str) -> None:
        self.db.run_sql(sql)
        self.db.run_sql("INSERT INTO schema_migrations (version, name, checksum) VALUES "
                        f"('{version}', '{name}', '{checksum}')")

    def setup(self) -> None:
        self.db.run_sql(TRACKING_DDL)


def _load_env() -> None:
    """The repo-root .env, via db_http's loader — one parser for every script."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import db_http  # noqa: F401  (loads .env on import)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply numbered SQL migrations")
    ap.add_argument("--run", action="store_true", help="Apply pending migrations")
    ap.add_argument("--status", action="store_true", help="List every migration's state")
    ap.add_argument("--via-http", action="store_true",
                    help="Use the Supabase Management API instead of DATABASE_URL")
    args = ap.parse_args(argv)
    _load_env()

    if args.via_http:
        db = ManagementApi()
    else:
        url = os.environ.get("DATABASE_URL")
        if not url:
            print("DATABASE_URL not set (or use --via-http)", file=sys.stderr)
            return 1
        db = Postgres(url)

    db.setup()
    applied = {v: c for v, c in db.query("SELECT version, checksum FROM schema_migrations")}
    pending, edited = [], []
    for version, name, sql, checksum in migrations():
        if version not in applied:
            pending.append((version, name, sql, checksum))
        elif applied[version] != checksum:
            edited.append(name)
        if args.status:
            state = ("pending" if version not in applied else
                     "EDITED since applied" if applied[version] != checksum else "applied")
            print(f"  {name:48} {state}")

    for name in edited:
        print(f"[warn] {name} changed after it was applied — write a new migration instead",
              file=sys.stderr)
    if not pending:
        print("Up to date.")
        return 0
    if not args.run:
        print(f"{len(pending)} pending (nothing applied — pass --run):")
        for version, name, sql, _ in pending:
            print(f"\n-- {name}\n{sql.strip()}")
        return 0
    for version, name, sql, checksum in pending:
        print(f"applying {name} ...")
        db.apply(version, name, sql, checksum)
    print(f"Applied {len(pending)} migration(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
