"""
catalog_store.py — Read brand catalogs from the system of record.

Postgres holds the catalogs (scripts/brand_catalog.py `push`, the admin pages edit
them in place). Until now the pipeline read `data/catalogs/<brand>.json` instead — an
export the admin API regenerates on request. On Render the API's disk is not the
worker's disk, so an edit made in the admin UI never reached matching unless someone
also regenerated the file *and* committed it. That is a second source of truth with a
manual sync step, and it had already drifted (the file carries a product grouping the
table does not).

So this reads the database first — over PostgREST when SUPABASE_URL and the service
role key are set (HTTPS, which works from a sandbox), otherwise over DATABASE_URL (the
scrape worker has only that) — and falls back to the export files only under "auto"
when neither reaches it: an offline run on a CSV handoff still works, and says so.

Every catalog comes back in the export's shape, with two additions on each entry:
  id            the entry's database id, which is what listings.catalog_entry_id holds
  product_key   which entries are sizes of one product (see _product_key)

    import catalog_store
    catalogs = catalog_store.load_all()            # {brand_key: catalog}
    cat = catalog_store.for_brand(catalogs, "Ayrloom")
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "data" / "catalogs"


def brand_key(brand: str | None) -> str:
    """The key catalogs are filed under: lowercase, '&' folded to 'and', no punctuation.

    The same folding canonical.py uses for its brand-scoped maps, so 'Papa & Barkley'
    and 'Papa and Barkley' land on one catalog.
    """
    s = re.sub(r"\s*[&+]\s*", " and ", (brand or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s)).strip()


def _norm(s: str | None) -> str:
    from brand_catalog import norm_name
    return norm_name(s or "")


def _product_key(entry: dict) -> str:
    """Which product an entry is a size of.

    The table's own `product_key` when the migration has added it. Otherwise the
    source's product id from the export file (brand_catalog.py keeps it there), and
    failing both, name + category: a title repeats across categories — Ayrloom sells
    'honeycrisp' as a vape and as a beverage — so the name alone would merge products
    a store can never confuse.
    """
    for k in ("product_key", "product_external_id"):
        if entry.get(k):
            return str(entry[k])
    return f"name:{_norm(entry.get('name'))}|{entry.get('category') or ''}"


def _from_files() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not CATALOG_DIR.is_dir():
        return out
    for path in sorted(CATALOG_DIR.glob("*.json")):
        try:
            cat = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [warn] unreadable catalog {path.name}: {e}", file=sys.stderr)
            continue
        for e in cat.get("entries") or []:
            e.setdefault("is_active", True)
            e["product_key"] = _product_key(e)
        cat["_source"] = f"file:{path.name}"
        out[brand_key(cat.get("brand_name"))] = cat
    return out


def _assemble(catalog_rows: list[dict], entry_rows: list[dict], source: str) -> dict[str, dict]:
    """Shape table rows like the export, whichever transport fetched them."""
    # The export file carries product_external_id, which the table had no column for
    # before db/migrations/0003. Carry it across by external_id so variants stay
    # grouped by the source's own product, exactly as the file grouped them.
    from_file: dict[str, str] = {}
    for cat in _from_files().values():
        for e in cat.get("entries") or []:
            if e.get("external_id") and e.get("product_external_id"):
                from_file[str(e["external_id"])] = str(e["product_external_id"])
    by_catalog: dict[str, list[dict]] = {}
    for e in entry_rows:
        e = dict(e)
        e["id"] = str(e["id"])
        e["catalog_id"] = str(e["catalog_id"])
        if not e.get("product_key") and e.get("external_id") in from_file:
            e["product_external_id"] = from_file[e["external_id"]]
        e["product_key"] = _product_key(e)
        by_catalog.setdefault(e["catalog_id"], []).append(e)
    out: dict[str, dict] = {}
    for c in catalog_rows:
        c = dict(c)
        c["id"] = str(c["id"])
        c["entries"] = by_catalog.get(c["id"], [])
        c["_source"] = source
        out[brand_key(c.get("brand_name"))] = c
    return out


def _from_db() -> dict[str, dict]:
    import db_http
    catalogs = db_http.select_all("brand_catalogs", "select=*&order=brand_slug")
    entries = db_http.select_all(
        "brand_catalog_entries", "select=*&is_active=is.true&order=catalog_id,id")
    return _assemble(catalogs, entries, "db")


def _from_postgres(url: str) -> dict[str, dict]:
    import psycopg2
    # Fail fast where 5432 is blocked (DB_ACCESS.md): the connect hangs, it is not refused.
    conn = psycopg2.connect(url, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            return load_from_cursor(cur)
    finally:
        conn.close()


def load_from_cursor(cur) -> dict[str, dict]:
    """Catalogs over an open psycopg2 cursor — what the importer uses, so catalog reads
    and listing writes share one connection and one view of the data."""
    cur.execute("SELECT * FROM brand_catalogs ORDER BY brand_slug")
    cols = [d[0] for d in cur.description]
    catalogs = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.execute("SELECT * FROM brand_catalog_entries WHERE is_active ORDER BY catalog_id, id")
    cols = [d[0] for d in cur.description]
    entries = [dict(zip(cols, r)) for r in cur.fetchall()]
    return _assemble(catalogs, entries, "db")


def entries_by_id(catalogs: dict[str, dict]) -> dict[str, tuple[dict, dict]]:
    """entry id -> (catalog, entry), for resolving a stored catalog_entry_id."""
    return {e["id"]: (cat, e) for cat in catalogs.values()
            for e in cat.get("entries") or [] if e.get("id")}


def _load_dotenv() -> None:
    """The repo-root .env, via db_http's loader — one parser for every script."""
    import db_http  # noqa: F401  (loads .env on import)


def load_all(source: str = "auto") -> dict[str, dict]:
    """Every catalog, keyed by brand_key(brand_name).

    source: "db" | "file" | "auto". "db" reads Postgres — PostgREST when SUPABASE_URL +
    SUPABASE_SERVICE_ROLE_KEY are set, else DATABASE_URL — and raises if it cannot.
    "auto" does the same but falls back to the export files with a warning rather
    than failing a fleet run.
    """
    _load_dotenv()
    have_rest = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    url = os.getenv("DATABASE_URL")
    if source == "file" or (source == "auto" and not (have_rest or url)):
        return _from_files()
    try:
        if have_rest:
            return _from_db()
        if url:
            return _from_postgres(url)
        raise RuntimeError("no database credentials (SUPABASE_URL + service role key, "
                           "or DATABASE_URL)")
    except Exception as e:  # noqa: BLE001
        if source == "db":
            raise
        print(f"  [warn] catalogs from DB failed ({e}); using data/catalogs/ files",
              file=sys.stderr)
        return _from_files()


def for_brand(catalogs: dict[str, dict], brand: str | None) -> dict | None:
    return catalogs.get(brand_key(brand))


def snapshot(catalogs: dict[str, dict], directory: Path = CATALOG_DIR) -> list[Path]:
    """Write catalogs as export files — for an offline handoff, not a sync step."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    keep = ("external_id", "product_key", "name", "product_line", "category", "subtype",
            "strain", "variant", "attributes", "match_terms", "source", "support")
    for cat in catalogs.values():
        doc = {k: cat.get(k) for k in ("brand_slug", "brand_name", "source_url",
                                       "source_method", "fetched_at")}
        doc["entries"] = [{k: e.get(k) for k in keep if k in e or k == "product_key"}
                          for e in cat.get("entries") or []]
        path = directory / f"{cat['brand_slug']}.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Inspect or snapshot brand catalogs")
    ap.add_argument("--source", choices=["auto", "db", "file"], default="auto")
    ap.add_argument("--snapshot", action="store_true",
                    help="Write the catalogs to data/catalogs/ for an offline run")
    args = ap.parse_args()
    cats = load_all(args.source)
    for key, cat in sorted(cats.items()):
        products = len({e["product_key"] for e in cat.get("entries") or []})
        print(f"{cat.get('brand_name'):30} {cat.get('source_method') or '?':24} "
              f"{products:>5} products {len(cat.get('entries') or []):>6} entries  [{cat['_source']}]")
    if args.snapshot:
        for p in snapshot(cats):
            print(f"wrote {p.relative_to(ROOT)}")
