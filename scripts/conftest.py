"""Fixtures shared by the pipeline tests (scripts/test_*.py)."""

import json
import os
import sys
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEST_DB = os.environ.get("TEST_DATABASE_URL")


class RestOverPostgres:
    """Stands in for Supabase's REST API in tests: the PostgREST calls the pipeline
    makes through db_http (select, insert, upsert, update, delete; select_all pages
    through select), run as SQL against a test database. Rows come back through JSON,
    as from PostgREST, so a timestamp arrives as a string and a uuid as text. Like
    PostgREST, a bulk write needs every object to carry the same keys."""

    def __init__(self, conn):
        import psycopg2.extras
        self.conn, self.extras = conn, psycopg2.extras

    @staticmethod
    def _parse(query):
        cols, conds, args, order, limit, offset = "*", [], [], "", "", ""
        for part in filter(None, query.split("&")):
            key, _, val = part.partition("=")
            val = urllib.parse.unquote(val)
            if key == "select":
                cols = val
            elif key == "order":
                order = " ORDER BY " + ", ".join(
                    c.replace(".desc", " DESC").replace(".asc", "") for c in val.split(","))
            elif key == "limit":
                limit = f" LIMIT {int(val)}"
            elif key == "offset":
                offset = f" OFFSET {int(val)}"
            elif val.startswith("eq."):
                conds.append(f"{key}::text = %s")
                args.append(val[3:])
            elif val.startswith("in.(") and val.endswith(")"):
                conds.append(f"{key}::text = ANY(%s)")
                args.append([v.strip('"') for v in val[4:-1].split(",")])
            elif val in ("is.true", "is.false", "is.null"):
                conds.append(f"{key} IS {val[3:].upper()}")
            elif key == "or" and val.startswith("(") and val.endswith(")"):
                terms = []
                for term in val[1:-1].split(","):
                    col, op, rest = term.split(".", 2)
                    if op == "gte":
                        terms.append(f"{col} >= %s")
                        args.append(rest)
                    elif op == "is" and rest == "null":
                        terms.append(f"{col} IS NULL")
                    else:
                        raise AssertionError(f"PostgREST filter not modelled here: {part}")
                conds.append("(" + " OR ".join(terms) + ")")
            else:
                raise AssertionError(f"PostgREST filter not modelled here: {part}")
        where = f" WHERE {' AND '.join(conds)}" if conds else ""
        return cols, where, args, order + limit + offset

    def _run(self, sql, args, many=None):
        import db_http
        import psycopg2
        try:
            with self.conn.cursor(cursor_factory=self.extras.RealDictCursor) as cur:
                if many is not None:
                    rows = self.extras.execute_values(cur, sql, many, fetch=True)
                else:
                    cur.execute(sql, args)
                    rows = cur.fetchall()
        except psycopg2.Error as exc:            # PostgREST answers with the SQLSTATE
            raise db_http.DbHttpError(f'-> 400: {{"code":"{exc.pgcode}","message":"{exc}"}}') \
                from exc
        return json.loads(json.dumps([dict(r) for r in rows], default=str))

    def _value(self, v):
        return self.extras.Json(v) if isinstance(v, dict) else v

    def _rows(self, rows):
        rows = rows if isinstance(rows, list) else [rows]
        assert rows and all(r.keys() == rows[0].keys() for r in rows), \
            "PostgREST: all objects in a bulk write must have the same keys"
        return list(rows[0]), [tuple(self._value(r[c]) for c in rows[0]) for r in rows]

    def select(self, table, query=""):
        cols, where, args, tail = self._parse(query)
        return self._run(f"SELECT {cols} FROM {table}{where}{tail}", args)

    def insert(self, table, rows):
        cols, values = self._rows(rows)
        return self._run(f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s RETURNING *",
                         None, many=values)

    def upsert(self, table, rows, on_conflict):
        """resolution=merge-duplicates: every column sent replaces the stored one."""
        cols, values = self._rows(rows)
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
        return self._run(f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
                         f"ON CONFLICT ({on_conflict}) DO UPDATE SET {sets} RETURNING *",
                         None, many=values)

    def update(self, table, query, changes):
        assert query, "db_http refuses an unfiltered update"
        _, where, args, _ = self._parse(query)
        sets = ", ".join(f"{c} = %s" for c in changes)
        return self._run(f"UPDATE {table} SET {sets}{where} RETURNING *",
                         [*map(self._value, changes.values()), *args])

    def delete(self, table, query):
        assert query, "db_http refuses an unfiltered delete"
        _, where, args, _ = self._parse(query)
        return self._run(f"DELETE FROM {table}{where} RETURNING *", args)


@pytest.fixture
def via_rest(monkeypatch):
    """via_rest(conn): from here on, db_http's REST calls are answered from that test
    database. Returns the stand-in."""
    import db_http

    def install(conn):
        rest = RestOverPostgres(conn)
        for name in ("select", "insert", "upsert", "update", "delete"):
            monkeypatch.setattr(db_http, name, getattr(rest, name))
        return rest
    return install


@pytest.fixture
def fresh_db(monkeypatch):
    """A throwaway database (TEST_DATABASE_URL) with the production schema and every
    migration applied. Skips when TEST_DATABASE_URL is not set."""
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    psycopg2 = pytest.importorskip("psycopg2")
    import db_migrate

    root = Path(__file__).resolve().parent.parent
    conn = psycopg2.connect(TEST_DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    cur.execute((root / "db" / "schema" / "pipeline.sql").read_text())
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    assert db_migrate.main(["--run"]) == 0
    yield conn
    conn.close()
