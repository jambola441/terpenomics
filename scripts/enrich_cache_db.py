"""
enrich_cache_db.py — The enrich cache in Postgres (table enrich_cache), for runs with
no persistent disk: a Render cron job, a sandbox. enrich.py uses it when
ENRICH_CACHE=db.

enrich.py keeps one cache per store, {cache key: answer}, which is what keeps model
spend low: only new or changed listings are sent to a model. On disk that is a JSON
file per store (data/enrich_cache/<slug>.json), which a machine without a disk loses
after every run. Here it is one row per (slug, cache_key), reached over DATABASE_URL,
or over Supabase's REST API with DB_VIA_HTTP=1, like the rest of the pipeline.

Like the file cache, it never fails a run. A cache that cannot be read is treated as
empty, so that store re-enriches; one that cannot be written is reported and skipped,
so those rows re-enrich next run. Only entries that are new or changed since the
load are written.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TABLE = "enrich_cache"

# slug -> cache key -> the entry as loaded (canonical JSON), to write only what changed.
_loaded: dict[str, dict[str, str]] = {}


def _canon(entry) -> str:
    return json.dumps(entry, sort_keys=True, ensure_ascii=False)


def _via_http() -> bool:
    return os.environ.get("DB_VIA_HTTP", "").strip().lower() in ("1", "true", "yes")


def _connect():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set (or set DB_VIA_HTTP=1)")
    # Fail fast where 5432 is blocked (DB_ACCESS.md): the connect hangs, it is not refused.
    return psycopg2.connect(url, connect_timeout=10)


def load(slug: str) -> dict:
    """The store's cache, or {} — never an exception."""
    try:
        if _via_http():
            import db_http
            rows = db_http.select_all(
                TABLE, f"select=cache_key,entry&slug=eq.{urllib.parse.quote(slug, safe='')}"
                       f"&order=cache_key")
            cache = {r["cache_key"]: r["entry"] for r in rows}
        else:
            conn = _connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT cache_key, entry FROM {TABLE} WHERE slug = %s", (slug,))
                    cache = dict(cur.fetchall())
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001 — a cache problem must not fail the scrape
        print(f"  [warn] enrich cache for {slug} unreadable from Postgres ({exc}); "
              f"starting empty", file=sys.stderr)
        _loaded[slug] = {}
        return {}
    _loaded[slug] = {k: _canon(v) for k, v in cache.items()}
    return cache


def save(cache: dict, slug: str) -> int:
    """Write the entries that are new or changed since load(). Returns how many were
    written; 0 when nothing changed or the write failed (reported, never raised)."""
    before = _loaded.get(slug, {})
    changed = {k: v for k, v in cache.items() if before.get(k) != _canon(v)}
    if not changed:
        return 0
    try:
        if _via_http():
            import db_http
            now = datetime.now(timezone.utc).isoformat()
            rows = [{"slug": slug, "cache_key": k, "entry": v, "updated_at": now}
                    for k, v in changed.items()]
            for i in range(0, len(rows), 500):
                db_http.upsert(TABLE, rows[i:i + 500], on_conflict="slug,cache_key")
        else:
            import psycopg2.extras
            conn = _connect()
            try:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(
                        cur,
                        f"INSERT INTO {TABLE} (slug, cache_key, entry) VALUES %s "
                        f"ON CONFLICT (slug, cache_key) DO UPDATE "
                        f"SET entry = EXCLUDED.entry, updated_at = now()",
                        [(slug, k, psycopg2.extras.Json(v)) for k, v in changed.items()],
                        page_size=500)
                conn.commit()
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] enrich cache for {slug} not saved to Postgres ({exc}); "
              f"{len(changed)} answer(s) will be re-enriched next run", file=sys.stderr)
        return 0
    _loaded[slug] = {**before, **{k: _canon(v) for k, v in changed.items()}}
    return len(changed)
