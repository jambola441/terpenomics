#!/usr/bin/env python3
"""
db_http.py — Reach the database over HTTPS when port 5432 is unreachable.

Why this exists: sandboxed environments (Claude Code on the web, CI runners
behind an HTTPS-only egress proxy) can open TLS to 443 and nothing else. A
psycopg connection to the Supabase pooler on :5432 does not fail fast there,
it hangs until timeout — so every script that imports `database.engine` dies
before main() ever runs.

Supabase serves the same database over two HTTPS APIs. This module wraps both:

  * PostgREST — row CRUD against any table, using SUPABASE_URL and
    SUPABASE_SERVICE_ROLE_KEY. No new credentials: the app already has these.
    Cannot run DDL, joins, or aggregates.
  * Management API — arbitrary SQL, DDL included, using SUPABASE_ACCESS_TOKEN
    (a personal access token from supabase.com/dashboard/account/tokens).
    Optional; only needed for the migrate.py class of work.

Scope: ad-hoc surgery, inspection, and migrations from a sandbox. Long batch
jobs (enrich.py, import_listings.py) should still run where 5432 is reachable
— they are chatty enough that per-statement HTTP round-trips would dominate.

Stdlib only, on purpose: this has to work in an environment where `pip install`
may itself be blocked.

Usage:
    python scripts/db_http.py check
    python scripts/db_http.py sql "SELECT count(*) FROM listings"
    python scripts/db_http.py select listings "select=id,strain&limit=5"
    python scripts/db_http.py insert terpenes '{"name": "myrcene"}'
    python scripts/db_http.py update listings "id=eq.42" '{"in_stock": false}'
    python scripts/db_http.py delete listings "id=eq.42"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

def _load_dotenv() -> None:
    """Mirror database.py's .env loading without importing it.

    database.py pulls in sqlmodel and builds an engine at import time. In the
    sandboxes this module exists for, those dependencies are often not even
    installed — so this file stays free of them.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key not in os.environ:
                os.environ[key] = val


_load_dotenv()

MANAGEMENT_API = "https://api.supabase.com"
TIMEOUT_SECONDS = float(os.getenv("DB_HTTP_TIMEOUT", "60"))

# Cloudflare fronts api.supabase.com and rejects urllib's default
# "Python-urllib/3.x" agent outright, with a 403 whose body is only
# "error code: 1010". That reads exactly like a rejected token, so it is worth
# never sending the default. Any named agent gets through.
USER_AGENT = "terpenomics-db-http/1.0"


class DbHttpError(RuntimeError):
    """An HTTPS call to Supabase failed, with the response body attached."""


def _request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Optional[bytes] = None,
) -> tuple[int, str]:
    headers = {"User-Agent": USER_AGENT, **headers}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # The body is where Postgres puts the actual error (constraint name,
        # column, hint). Surfacing only the status code would waste a round trip.
        detail = exc.read().decode("utf-8")
        if "1010" in detail:
            detail += (
                "\n(Cloudflare rejected the client signature, not the credential. "
                "Check that the request sends a named User-Agent.)"
            )
        raise DbHttpError(f"{method} {url} -> {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DbHttpError(f"{method} {url} -> {exc.reason}") from exc


# --------------------------------------------------------------------------
# PostgREST — row CRUD. Works with the credentials already in the environment.
# --------------------------------------------------------------------------

def _rest_config() -> tuple[str, str]:
    base = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not base or not key:
        raise DbHttpError(
            "PostgREST needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY. "
            "Set them in the environment (see .env.example)."
        )
    return base, key


def _rest_headers(key: str, *, write: bool) -> dict[str, str]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if write:
        headers["Content-Type"] = "application/json"
        # Without this PostgREST returns 204 and no body, so callers cannot tell
        # what was actually written.
        headers["Prefer"] = "return=representation"
    return headers


def rest(
    method: str,
    table: str,
    query: str = "",
    payload: Any = None,
) -> Any:
    """Call PostgREST directly. `query` is a raw querystring, e.g. "id=eq.7"."""
    base, key = _rest_config()
    url = f"{base}/rest/v1/{urllib.parse.quote(table)}"
    if query:
        url = f"{url}?{query}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    _, text = _request(method, url, _rest_headers(key, write=body is not None), body)
    return json.loads(text) if text.strip() else []


def select(table: str, query: str = "") -> list[dict[str, Any]]:
    return rest("GET", table, query)


def insert(table: str, rows: Any) -> list[dict[str, Any]]:
    return rest("POST", table, payload=rows)


def upsert(table: str, rows: Any, on_conflict: str) -> list[dict[str, Any]]:
    base, key = _rest_config()
    url = f"{base}/rest/v1/{urllib.parse.quote(table)}?on_conflict={urllib.parse.quote(on_conflict)}"
    headers = _rest_headers(key, write=True)
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"
    _, text = _request("POST", url, headers, json.dumps(rows).encode("utf-8"))
    return json.loads(text) if text.strip() else []


def update(table: str, query: str, changes: dict[str, Any]) -> list[dict[str, Any]]:
    if not query:
        raise DbHttpError("update requires a filter, e.g. \"id=eq.42\" — refusing to touch every row.")
    return rest("PATCH", table, query, changes)


def delete(table: str, query: str) -> list[dict[str, Any]]:
    if not query:
        raise DbHttpError("delete requires a filter, e.g. \"id=eq.42\" — refusing to empty the table.")
    return rest("DELETE", table, query)


# --------------------------------------------------------------------------
# Management API — arbitrary SQL, including DDL.
# --------------------------------------------------------------------------

def _project_ref() -> str:
    ref = (os.getenv("SUPABASE_PROJECT_REF") or "").strip()
    if ref:
        return ref
    # Derive it from SUPABASE_URL: https://<ref>.supabase.co
    host = urllib.parse.urlparse((os.getenv("SUPABASE_URL") or "").strip()).hostname or ""
    ref = host.split(".", 1)[0]
    if not ref:
        raise DbHttpError("Cannot determine the project ref. Set SUPABASE_PROJECT_REF or SUPABASE_URL.")
    return ref


def run_sql(query: str) -> Any:
    """Execute arbitrary SQL. Returns the result rows as a list of dicts."""
    token = (os.getenv("SUPABASE_ACCESS_TOKEN") or "").strip()
    if not token:
        raise DbHttpError(
            "Arbitrary SQL needs SUPABASE_ACCESS_TOKEN — a personal access token from\n"
            "  https://supabase.com/dashboard/account/tokens\n"
            "Add it to the environment, then retry. Row CRUD (select/insert/update/\n"
            "delete) works without it."
        )
    url = f"{MANAGEMENT_API}/v1/projects/{_project_ref()}/database/query"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    _, text = _request("POST", url, headers, json.dumps({"query": query}).encode("utf-8"))
    return json.loads(text) if text.strip() else []


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------

def check() -> int:
    """Report which access paths are usable from here. Exit code 0 if any is."""
    ok = False

    print("PostgREST (row CRUD)")
    try:
        # The root endpoint returns the schema document. Probing that rather
        # than a named table keeps this check honest when the schema changes.
        base, key = _rest_config()
        _request("GET", f"{base}/rest/v1/", _rest_headers(key, write=False))
        print("  available — select/insert/update/delete/upsert on any table")
        ok = True
    except DbHttpError as exc:
        print(f"  unavailable: {exc}")

    print("\nManagement API (arbitrary SQL + DDL)")
    try:
        run_sql("SELECT 1 AS ok")
        print("  available — run_sql() and `db_http.py sql ...`")
        ok = True
    except DbHttpError as exc:
        print(f"  unavailable: {exc}")

    print("\nDirect Postgres (:5432)")
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        host = urllib.parse.urlparse(url).hostname
        print(f"  configured for {host}:5432 — usable only where raw TCP egress is allowed.")
        print("  If scripts hang on import, that egress is blocked; use the paths above.")
    else:
        print("  DATABASE_URL is not set.")

    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="report which access paths work from here")

    p_sql = sub.add_parser("sql", help="run arbitrary SQL (needs SUPABASE_ACCESS_TOKEN)")
    p_sql.add_argument("query", help="the SQL to execute; use - to read from stdin")

    p_sel = sub.add_parser("select", help="read rows via PostgREST")
    p_sel.add_argument("table")
    p_sel.add_argument("query", nargs="?", default="", help='PostgREST querystring, e.g. "limit=5&select=id"')

    p_ins = sub.add_parser("insert", help="insert rows via PostgREST")
    p_ins.add_argument("table")
    p_ins.add_argument("json", help="a JSON object or array of objects")

    p_upd = sub.add_parser("update", help="update rows via PostgREST")
    p_upd.add_argument("table")
    p_upd.add_argument("query", help='filter, e.g. "id=eq.42"')
    p_upd.add_argument("json", help="a JSON object of column changes")

    p_del = sub.add_parser("delete", help="delete rows via PostgREST")
    p_del.add_argument("table")
    p_del.add_argument("query", help='filter, e.g. "id=eq.42"')

    args = parser.parse_args()

    try:
        if args.command == "check":
            return check()
        if args.command == "sql":
            query = sys.stdin.read() if args.query == "-" else args.query
            result = run_sql(query)
        elif args.command == "select":
            result = select(args.table, args.query)
        elif args.command == "insert":
            result = insert(args.table, json.loads(args.json))
        elif args.command == "update":
            result = update(args.table, args.query, json.loads(args.json))
        elif args.command == "delete":
            result = delete(args.table, args.query)
        else:  # argparse already rejects anything else
            return 2
    except DbHttpError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
