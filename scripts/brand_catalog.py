#!/usr/bin/env python3
"""
brand_catalog.py — Acquire a brand's real product list and export it as a catalog.

Enrichment today extracts fields from a product name with a model, so every quality
number in this repo is computed from the same output it is meant to judge. A catalog
is the first external referent: a list of products the brand says it makes.

Acquisition is tiered, cheapest first, and the tier that answered is recorded per
catalog so coverage can be reported by provenance rather than as one lump number:

  1. shopify_products_json — /products.json?limit=250, free and already structured
  2. ld_json              — Product structured data on the site
  3. rendered_page        — page + model extraction, for sites with neither
  4. manual               — hand-curated, seeded from our own listings

Only tier 1 is implemented here. It covers the brands measured in CATALOG.md that
have a storefront (Ayrloom, STIIIZY); the rest need the later tiers.

One (product, variant) pair becomes one entry, because that is the grain our
listings are at — Ayrloom's 65 products carry 174 variants, and a listing is for a
specific size, not for the product family.

Usage
-----
  python scripts/brand_catalog.py fetch --brand Ayrloom --domain ayrloom.com
  python scripts/brand_catalog.py show  --brand Ayrloom
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper_common import slugify  # noqa: E402
import taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "data" / "catalogs"

TIMEOUT_SECONDS = 30
USER_AGENT = "terpenomics-catalog/1.0"

# Shopify tags are a free-text vocabulary, so this is per-source knowledge rather
# than a general rule. Tags that describe merchandising rather than the product
# ("new", "retail-only", "limited") are dropped; what survives names the category.
TAG_CATEGORY = {
    "gummy":    ("edible", "gummy"),
    "beverage": ("edible", "beverage"),
    "pre-roll": ("preroll", None),
    "vape":     ("vaporizers", None),
    "tincture": ("tinctures", "tincture"),
    "balm":     ("topical", "topical"),
    "swag":     ("merch", None),
}
MERCHANDISING_TAGS = {"new", "retail-only", "best-seller", "sale", "limited",
                      "bogos-gift", "sour", "d9"}


def norm_name(s: str) -> str:
    """Lowercase, fold separators, strip punctuation, collapse whitespace.

    Matching runs over this on both sides. Deliberately lossy: stores write the same
    product with different punctuation and separators ('Half + Half', 'half and
    half', 'Half/Half'), and 18,806 listings collapse to only 17,239 distinct
    (brand, name) pairs, so the normalisation has to absorb that variety.
    """
    s = re.sub(r"\s*[&+]\s*", " and ", (s or "").lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_brand(name: str, brand: str | None) -> str:
    """norm_name(name) without the brand's own words.

    How a catalog records a store's name for a product (catalog_bootstrap), and how a
    listing's name is compared with those records (catalog_match), so "Jetpacks - FJ
    Mini Afghani" and "FJ Mini Afghani" are one name — most stores put the brand in,
    some do not.
    """
    n = norm_name(name)
    b = norm_name(brand or "")
    if b:
        n = re.sub(rf"\b{re.escape(b)}\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
        return json.loads(r.read().decode("utf-8"))


def _clean_tags(tags: list[str]) -> list[str]:
    return [t for t in (tags or []) if t.lower() not in MERCHANDISING_TAGS]


def _category_for(tags: list[str]) -> tuple[str | None, str | None]:
    for t in _clean_tags(tags):
        hit = TAG_CATEGORY.get(t.lower())
        if hit:
            return hit
    return (None, None)


# Categories whose products are identified by a cultivar or flavour. A topical is a
# 'Restore balm', not a strain of anything, and merch never carries one — writing the
# title into strain for those is the same overload this work exists to remove.
STRAIN_BEARING = taxonomy.strain_bearing()


def _identity_for(title: str, tags: list[str], category: str | None
                  ) -> tuple[str | None, str | None]:
    """Split a catalog title into (product_line, strain).

    The split defect lives in product_line: groups of product rows that differ only
    there, with one side blank. Extraction cannot see a line that is absent from the
    name; the catalog can, because the brand groups its own products. And where the
    title *is* the product's identity, it is the strain — 'honeycrisp' splits three
    ways across stores ('Honeycrisp', 'Honeycrisp Cider', 'Honeycrisp Apple Cider')
    and the catalog settles it in one word.

    Three shapes, all read off the source rather than guessed:
      - an uppercase tag that is not merchandising ('UP' on three gummies)
      - a 'line: flavour' title ('mood: bliss' -> Mood / Bliss)
      - a '<line> balm' title (Revive/Restore/Rescue — the topical product-line
        problem REFACTOR.md recorded as blocked; a balm has no cultivar)
    """
    line = None
    for t in _clean_tags(tags):
        if t.isupper() and t.lower() not in TAG_CATEGORY:
            line = t
            break

    name = title.strip()
    m = re.match(r"^(\w+)\s+balm$", name, re.I)
    if m:
        return (line or m.group(1).title()), None
    if ":" in name:
        head, _, tail = name.partition(":")
        head, tail = head.strip(), tail.strip()
        if head and tail:
            return (line or head.title()), (tail.title() if category in STRAIN_BEARING
                                            else None)
    strain = name.title() if category in STRAIN_BEARING else None
    return line, strain


def _variant_label(v: dict) -> str | None:
    """Shopify variant title, minus its 'Default Title' placeholder."""
    t = (v.get("title") or "").strip()
    return None if not t or t.lower() == "default title" else t


def fetch_shopify(brand: str, domain: str) -> dict:
    """Tier 1. Returns a catalog dict ready to write."""
    url = f"https://{domain}/products.json?limit=250"
    payload = _fetch_json(url)
    products = payload.get("products", [])
    if not products:
        raise SystemExit(f"No products at {url} — not a Shopify storefront, or empty.")

    entries: list[dict] = []
    for p in products:
        title = (p.get("title") or "").strip()
        if not title:
            continue
        tags = p.get("tags") or []
        category, subtype = _category_for(tags)
        line, strain = _identity_for(title, tags, category)
        # A promotional placeholder is not a product. Left out of the catalog rather
        # than flagged, because anything present is a legitimate match target and
        # "Beverage (100% off)" would happily absorb every beverage listing.
        if re.search(r"\(\d+%\s*off\)", title, re.I):
            continue
        for v in p.get("variants", []):
            entries.append({
                "external_id": str(v.get("id")),
                # The product this variant belongs to, kept verbatim from the source.
                # Titles repeat across categories — Ayrloom sells 'honeycrisp' as a
                # vape, a beverage and a canned drink — so grouping variants by name
                # merges distinct products and lets a pre-roll resolve to a vape's
                # size. Grouping by the source's own id cannot make that mistake.
                "product_external_id": str(p.get("id")),
                "name": title,
                "product_line": line,
                "category": category,
                "subtype": subtype,
                "strain": strain,
                "variant": _variant_label(v),
                "attributes": None,
                "match_terms": sorted({norm_name(title)}),
                "source_tags": _clean_tags(tags),
                "product_key": str(p.get("id")),
                "source": "shopify_products_json",
            })

    return {
        "brand_slug": slugify(brand),
        "brand_name": brand,
        "source_url": url,
        "source_method": "shopify_products_json",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "product_count": len(products),
        "entries": entries,
    }


def catalog_path(brand_slug: str) -> Path:
    return CATALOG_DIR / f"{brand_slug}.json"


def save(catalog: dict) -> Path:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    path = catalog_path(catalog["brand_slug"])
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def load(brand_slug: str) -> dict:
    path = catalog_path(brand_slug)
    if not path.is_file():
        raise SystemExit(f"No catalog at {path} — run `brand_catalog.py fetch` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _connect():
    import psycopg2
    for line in (open(ROOT / ".env") if (ROOT / ".env").is_file() else []):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    return psycopg2.connect(url)


# Catalog-entry columns that arrived with db/migrations/0003.
EXTRA_COLUMNS = ("product_key", "source", "support")


def _entry_meta(catalog: dict):
    """The value an entry writes to each of EXTRA_COLUMNS."""
    default_source = catalog.get("source_method")

    def meta(e: dict, c: str):
        if c == "product_key":
            # Exports written before product_key existed carry the same value as
            # product_external_id, so pushing an old file backfills it.
            return e.get("product_key") or e.get("product_external_id")
        if c == "source":
            return e.get("source") or default_source
        return e.get(c)
    return meta


def push(catalog: dict, dry_run: bool = False, via_http: bool = False,
         replace: bool = False) -> dict:
    """Upsert a catalog into Postgres, the system of record — additively.

    A catalog is curated after it lands: the admin page edits sizes and strains and
    takes out products a store will never carry (Ayrloom's online-only hemp D9 line,
    98 entries, 2026-09-06). A re-fetch used to overwrite every field and set
    is_active = TRUE on everything the source still listed, so one refresh would
    have undone all of that. Now the rule is:

      new entries      inserted, active
      existing entries identity fields are never touched — name, line, category,
                       subtype, strain, variant, attributes stay as curated. Only
                       metadata refreshes: match_terms (union), last_seen_at,
                       support, and product_key/source when they were empty.
      deactivated      stay deactivated. Reactivating is a person's decision; the
                       entries the source lists again are counted and reported.
      vanished         storefront catalogs: deactivated, never deleted (listings hold
                       a foreign key to these rows). Bootstrap catalogs: left alone —
                       a product one store dropped this week is still a product.

    first_seen_at and the verified_* columns are never written by an update.

    replace=True is for re-proposing a bootstrap catalog: its earlier bootstrap
    entries that this proposal no longer contains are deactivated too, except any a
    person verified. Storefront catalogs already retire what their source dropped.

    Over DATABASE_URL by default. via_http=True applies the same rules over Supabase's
    REST API, for a machine that cannot open a Postgres connection (DB_ACCESS.md).
    Returns counts; prints them.
    """
    counts = (_push_http(catalog, dry_run, replace) if via_http
              else _push_postgres(catalog, dry_run, replace))
    if dry_run:
        print(f"[dry run] would push: {counts}")
    else:
        print(f"pushed {catalog['brand_name']}: {counts['inserted']} new, "
              f"{counts['refreshed']} refreshed (curated fields kept), "
              f"{counts['deactivated']} no longer on source deactivated")
    if counts["listed_again_but_inactive"]:
        print(f"  {counts['listed_again_but_inactive']} entries the source lists are inactive "
              f"here (taken out by hand, or gone and back) — left inactive; reactivate in "
              f"the admin if wanted")
    return counts


def _warn_unmigrated() -> None:
    print("  [warn] brand_catalog_entries lacks product_key/source/support — "
          "run scripts/db_migrate.py --run to record them")


def _push_postgres(catalog: dict, dry_run: bool, replace: bool = False) -> dict:
    """push() as one transaction over DATABASE_URL; a dry run rolls it back."""
    import psycopg2.extras
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO brand_catalogs (brand_slug, brand_name, source_url, source_method, fetched_at)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (brand_slug) DO UPDATE SET
            brand_name = EXCLUDED.brand_name,
            source_url = COALESCE(EXCLUDED.source_url, brand_catalogs.source_url),
            source_method = EXCLUDED.source_method,
            fetched_at = EXCLUDED.fetched_at,
            updated_at = now()
        RETURNING id
        """,
        (catalog["brand_slug"], catalog["brand_name"], catalog["source_url"],
         catalog["source_method"], catalog["fetched_at"]),
    )
    catalog_id = cur.fetchone()[0]

    # product_key / source / support are written when the columns exist, and skipped
    # with a warning when they do not, so a push never fails on a database that has
    # not been migrated yet.
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'brand_catalog_entries'
                     AND column_name IN ('product_key', 'source', 'support')""")
    extra = sorted(r[0] for r in cur.fetchall())
    if len(extra) < 3:
        _warn_unmigrated()
    meta = _entry_meta(catalog)

    rows = [(catalog_id, e["external_id"], e["name"], e["product_line"], e["category"],
             e["subtype"], e["strain"], e["variant"],
             json.dumps(e["attributes"]) if e.get("attributes") else None,
             e.get("match_terms") or [],
             *[meta(e, c) for c in extra])
            for e in catalog["entries"]]
    cols = ["catalog_id", "external_id", "name", "product_line", "category", "subtype",
            "strain", "variant", "attributes", "match_terms", *extra]
    metadata = {
        "product_key": "COALESCE(brand_catalog_entries.product_key, EXCLUDED.product_key)",
        "source": "COALESCE(brand_catalog_entries.source, EXCLUDED.source)",
        "support": "EXCLUDED.support",
    }
    sets = [f"{c} = {metadata[c]}" for c in extra]
    returned = psycopg2.extras.execute_values(
        cur,
        f"""
        INSERT INTO brand_catalog_entries ({", ".join(cols)})
        VALUES %s
        ON CONFLICT (catalog_id, external_id) DO UPDATE SET
            match_terms  = ARRAY(SELECT DISTINCT t FROM unnest(
                               COALESCE(brand_catalog_entries.match_terms, '{{}}')
                               || COALESCE(EXCLUDED.match_terms, '{{}}')) AS t ORDER BY t),
            {"".join(f"{x}, " for x in sets)}last_seen_at = now()
        RETURNING (xmax = 0) AS inserted, is_active
        """,
        rows, fetch=True,
    )
    inserted = sum(1 for ins, _ in returned if ins)
    back_inactive = sum(1 for ins, active in returned if not ins and not active)

    deactivated = 0
    seen = [e["external_id"] for e in catalog["entries"]]
    if catalog.get("source_method") != "listings_bootstrap":
        cur.execute(
            """
            UPDATE brand_catalog_entries SET is_active = FALSE
            WHERE catalog_id = %s AND is_active AND external_id <> ALL(%s)
            """,
            (catalog_id, seen),
        )
        deactivated = cur.rowcount
    elif replace and "source" in extra:
        cur.execute(
            """
            UPDATE brand_catalog_entries SET is_active = FALSE
            WHERE catalog_id = %s AND is_active AND external_id <> ALL(%s)
              AND source = 'listings_bootstrap' AND verified_fields IS NULL
            """,
            (catalog_id, seen),
        )
        deactivated = cur.rowcount
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    conn.close()
    return {"inserted": inserted, "refreshed": len(returned) - inserted,
            "listed_again_but_inactive": back_inactive, "deactivated": deactivated}


def _push_http(catalog: dict, dry_run: bool, replace: bool = False) -> dict:
    """push() over Supabase's REST API (scripts/db_http.py), for a machine that can
    reach the database only over HTTPS: a sandbox whose proxy carries no Postgres
    connections (DB_ACCESS.md).

    The same rules as _push_postgres, decided here from the catalog's current rows
    instead of inside one statement. It is not one transaction: a push that fails
    part-way leaves some entries written, and running it again finishes the job,
    because each step is idempotent. A dry run only reads.
    """
    import urllib.parse
    from concurrent.futures import ThreadPoolExecutor

    import db_http

    now = datetime.now(timezone.utc).isoformat()
    header = {"brand_name": catalog["brand_name"], "source_method": catalog["source_method"],
              "fetched_at": catalog["fetched_at"]}
    slug = urllib.parse.quote(catalog["brand_slug"])
    found = db_http.select("brand_catalogs", f"select=id&brand_slug=eq.{slug}")
    catalog_id = found[0]["id"] if found else None
    if not dry_run:
        if catalog_id:
            # source_url keeps the stored value when this catalog has none, like the
            # SQL path's COALESCE.
            url = {"source_url": catalog["source_url"]} if catalog.get("source_url") else {}
            db_http.update("brand_catalogs", f"id=eq.{catalog_id}",
                           {**header, **url, "updated_at": now})
        else:
            catalog_id = db_http.insert("brand_catalogs", {
                "brand_slug": catalog["brand_slug"], "source_url": catalog.get("source_url"),
                **header})[0]["id"]

    try:
        db_http.select("brand_catalog_entries", f"select={','.join(EXTRA_COLUMNS)}&limit=1")
        extra = list(EXTRA_COLUMNS)
    except db_http.DbHttpError as exc:
        if "42703" not in str(exc):           # undefined_column; anything else is real
            raise
        extra = []
        _warn_unmigrated()
    meta = _entry_meta(catalog)

    existing: dict[str, dict] = {}
    if catalog_id:
        cols = ["id", "external_id", "match_terms", "is_active", "verified_fields",
                *[c for c in extra if c != "support"]]
        for r in db_http.select_all("brand_catalog_entries",
                                    f"select={','.join(cols)}&catalog_id=eq.{catalog_id}"
                                    f"&order=id"):
            if r["external_id"] is not None:  # NULL never matches, as in SQL
                existing[r["external_id"]] = r

    new_rows, refreshes, back_inactive = [], [], 0
    for e in catalog["entries"]:
        row = {"catalog_id": catalog_id, "external_id": e["external_id"], "name": e["name"],
               "product_line": e["product_line"], "category": e["category"],
               "subtype": e["subtype"], "strain": e["strain"], "variant": e["variant"],
               "attributes": e.get("attributes") or None,
               "match_terms": e.get("match_terms") or [],
               **{c: meta(e, c) for c in extra}}
        cur = existing.get(e["external_id"])
        if cur is None:
            new_rows.append(row)
            continue
        back_inactive += not cur["is_active"]
        change = {"match_terms": sorted(set(cur.get("match_terms") or []) | set(row["match_terms"])),
                  "last_seen_at": now}
        for c in ("product_key", "source"):
            if c in extra:
                change[c] = cur[c] if cur.get(c) is not None else row[c]
        if "support" in extra:
            change["support"] = row["support"]
        refreshes.append((cur["id"], change))

    retire = []
    seen = {e["external_id"] for e in catalog["entries"]}
    if catalog.get("source_method") != "listings_bootstrap":
        retire = [str(r["id"]) for ext, r in existing.items() if r["is_active"] and ext not in seen]
    elif replace and "source" in extra:
        retire = [str(r["id"]) for ext, r in existing.items()
                  if r["is_active"] and ext not in seen and r.get("source") == "listings_bootstrap"
                  and r.get("verified_fields") is None]

    if not dry_run:
        for i in range(0, len(new_rows), 500):
            db_http.insert("brand_catalog_entries", new_rows[i:i + 500])
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda r: db_http.update("brand_catalog_entries", f"id=eq.{r[0]}", r[1]),
                          refreshes))
        for i in range(0, len(retire), 100):
            db_http.update("brand_catalog_entries", f"id=in.({','.join(retire[i:i + 100])})",
                           {"is_active": False})
    return {"inserted": len(new_rows), "refreshed": len(refreshes),
            "listed_again_but_inactive": back_inactive, "deactivated": len(retire)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Acquire and export brand catalogs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pu = sub.add_parser("push", help="Upsert a saved catalog into Postgres")
    pu.add_argument("--brand", required=True)
    pu.add_argument("--dry-run", action="store_true")
    pu.add_argument("--via-http", action="store_true",
                    help="Write over Supabase's REST API instead of DATABASE_URL (DB_ACCESS.md)")

    f = sub.add_parser("fetch", help="Fetch a brand catalog (tier 1: Shopify)")
    f.add_argument("--brand", required=True, help="Brand name as it appears in listings")
    f.add_argument("--domain", required=True, help="Storefront domain, e.g. ayrloom.com")
    f.add_argument("--dry-run", action="store_true", help="Print a summary, write nothing")

    s = sub.add_parser("show", help="Summarise a saved catalog")
    s.add_argument("--brand", required=True)

    args = ap.parse_args()

    if args.cmd == "fetch":
        cat = fetch_shopify(args.brand, args.domain)
        n_line = sum(1 for e in cat["entries"] if e["product_line"])
        n_cat = sum(1 for e in cat["entries"] if e["category"])
        print(f"{cat['brand_name']}: {cat['product_count']} products → "
              f"{len(cat['entries'])} entries  ({n_cat} with category, "
              f"{n_line} with product_line)")
        if args.dry_run:
            print("[dry run] nothing written.")
            return
        print(f"wrote {save(cat)}")
    elif args.cmd == "push":
        push(load(slugify(args.brand)), dry_run=args.dry_run, via_http=args.via_http)
    else:
        cat = load(slugify(args.brand))
        print(f"{cat['brand_name']}  [{cat['source_method']}]  fetched {cat['fetched_at']}")
        print(f"  {cat['product_count']} products, {len(cat['entries'])} entries")


if __name__ == "__main__":
    main()
