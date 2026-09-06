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
STRAIN_BEARING = {"vaporizers", "preroll", "edible", "tinctures", "flower",
                  "concentrate"}


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


def push(catalog: dict, dry_run: bool = False) -> None:
    """Upsert a catalog into Postgres, the system of record.

    Entries are matched on (catalog_id, external_id) — the source's own variant id —
    so a re-fetch updates in place rather than duplicating. Two things are never
    written by an update: first_seen_at, which would erase when we first saw the
    product, and the verified_* columns, because a human sign-off must survive a
    re-fetch exactly as it survives a scrape on listings.

    Products that vanish from the source are deactivated, never deleted: listings
    carry a foreign key to these rows, so a delete would dangle it and destroy the
    history of what was on the menu.
    """
    import psycopg2.extras
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO brand_catalogs (brand_slug, brand_name, source_url, source_method, fetched_at)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (brand_slug) DO UPDATE SET
            brand_name = EXCLUDED.brand_name,
            source_url = EXCLUDED.source_url,
            source_method = EXCLUDED.source_method,
            fetched_at = EXCLUDED.fetched_at,
            updated_at = now()
        RETURNING id
        """,
        (catalog["brand_slug"], catalog["brand_name"], catalog["source_url"],
         catalog["source_method"], catalog["fetched_at"]),
    )
    catalog_id = cur.fetchone()[0]

    rows = [(catalog_id, e["external_id"], e["name"], e["product_line"], e["category"],
             e["subtype"], e["strain"], e["variant"],
             json.dumps(e["attributes"]) if e.get("attributes") else None,
             e.get("match_terms") or []) for e in catalog["entries"]]
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO brand_catalog_entries
            (catalog_id, external_id, name, product_line, category, subtype,
             strain, variant, attributes, match_terms)
        VALUES %s
        ON CONFLICT (catalog_id, external_id) DO UPDATE SET
            name         = EXCLUDED.name,
            product_line = EXCLUDED.product_line,
            category     = EXCLUDED.category,
            subtype      = EXCLUDED.subtype,
            strain       = EXCLUDED.strain,
            variant      = EXCLUDED.variant,
            attributes   = EXCLUDED.attributes,
            match_terms  = EXCLUDED.match_terms,
            is_active    = TRUE,
            last_seen_at = now()
        """,
        rows,
    )
    seen = [e["external_id"] for e in catalog["entries"]]
    cur.execute(
        """
        UPDATE brand_catalog_entries SET is_active = FALSE
        WHERE catalog_id = %s AND is_active AND external_id <> ALL(%s)
        """,
        (catalog_id, seen),
    )
    deactivated = cur.rowcount
    if dry_run:
        conn.rollback()
        print(f"[dry run] would upsert {len(rows)} entries, deactivate {deactivated}")
    else:
        conn.commit()
        print(f"pushed {len(rows)} entries; deactivated {deactivated} no longer on source")
    conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Acquire and export brand catalogs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pu = sub.add_parser("push", help="Upsert a saved catalog into Postgres")
    pu.add_argument("--brand", required=True)
    pu.add_argument("--dry-run", action="store_true")

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
        push(load(slugify(args.brand)), dry_run=args.dry_run)
    else:
        cat = load(slugify(args.brand))
        print(f"{cat['brand_name']}  [{cat['source_method']}]  fetched {cat['fetched_at']}")
        print(f"  {cat['product_count']} products, {len(cat['entries'])} entries")


if __name__ == "__main__":
    main()
