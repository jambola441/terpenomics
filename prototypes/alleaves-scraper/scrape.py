"""
scrape.py — Alleaves POS scraper

Two-pass approach:
  1. /api/inventory/item/search  — full product catalog (stable id_item, descriptions, images)
  2. /api/inventory/search        — current inventory to determine in_stock per id_item

Usage:
    python prototypes/alleaves-scraper/scrape.py \\
        --tenant brooklynorganicbuds \\
        --out prototypes/alleaves-scraper/brooklynorganicbuds_listings.csv

    Credentials via env vars (preferred) or flags:
        ALLEAVES_USER / ALLEAVES_PASS
        --username / --password

Output columns (identical to travel_agency_listings.csv):
    dispensary_slug, sku, product_uuid, name, brand, category, variant,
    price_cents, thc_percent, cbd_percent, classification, in_stock,
    product_url, scraped_at
"""

import argparse
import os
import re
import sys
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../scripts"))
from scraper_common import _norm, canonical_brands, map_category, now_iso, store_slug, write_csv  # noqa: E402
from enrich import enrich  # noqa: E402

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(1)


BASE_URL = "https://app.alleaves.com"
PAGE_SIZE = 100

TAX_RATES = {1: 1.13, 2: 1.09}

_API_HEADERS = {
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
    "accept": "application/json",
}

CARROT_SETTINGS_URL = "https://api.nevada.getcarrot.io/api/v1/store/settings/public2"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(client: httpx.Client, username: str, password: str) -> None:
    resp = client.post(
        "/api/account/login",
        json={"username": username, "password": password},
    )
    resp.raise_for_status()
    data = resp.json()
    if "redirect_url" not in data:
        raise RuntimeError(f"Login failed: {data}")


# ---------------------------------------------------------------------------
# Pass 1 — item catalog
# ---------------------------------------------------------------------------

def _item_params(skip: int) -> str:
    page = skip // PAGE_SIZE + 1
    return urlencode({
        "take": PAGE_SIZE,
        "skip": skip,
        "page": page,
        "pageSize": PAGE_SIZE,
    })


def fetch_all_items(client: httpx.Client) -> list[dict]:
    """Return all non-deleted catalog items, deduplicated by id_item."""
    records: list[dict] = []
    seen: set[str] = set()
    skip = 0
    total = None

    while True:
        resp = client.post(
            "/api/inventory/item/search",
            content=_item_params(skip),
            headers=_API_HEADERS,
        )
        resp.raise_for_status()
        page: list[dict] = resp.json()
        if not page:
            break

        if total is None:
            total = page[0].get("total_rows", 0)
            print(f"  Total catalog items: {total}")

        for r in page:
            key = str(r.get("id_item", ""))
            if key and key not in seen:
                seen.add(key)
                records.append(r)

        skip += len(page)
        if len(page) < PAGE_SIZE or (total and skip >= total):
            break

        time.sleep(0.3)

    return records


# ---------------------------------------------------------------------------
# Pass 2 — in-stock ids from inventory
# ---------------------------------------------------------------------------

def _inventory_params(skip: int) -> str:
    page = skip // PAGE_SIZE + 1
    params = {
        "take": PAGE_SIZE,
        "skip": skip,
        "page": page,
        "pageSize": PAGE_SIZE,
        "filter[logic]": "and",
        "filter[filters][0][field]": "status",
        "filter[filters][0][value][]": "open",
        "filter[filters][0][operator]": "eq",
        "filter[filters][1][field]": "has_inventory",
        "filter[filters][1][value]": "true",
        "filter[filters][1][operator]": "eq",
        "filter[filters][2][field]": "area_type",
        "filter[filters][2][value]": "Retail",
        "filter[filters][2][operator]": "eq",
        "id_location": "",
    }
    return urlencode(params)


def fetch_in_stock_ids(client: httpx.Client) -> dict[str, str]:
    """Return {id_item: batch} for items with available > 0. First batch per item wins."""
    in_stock: dict[str, str] = {}
    skip = 0
    total = None

    while True:
        resp = client.post(
            "/api/inventory/search",
            content=_inventory_params(skip),
            headers=_API_HEADERS,
        )
        resp.raise_for_status()
        page: list[dict] = resp.json()
        if not page:
            break

        if total is None:
            total = page[0].get("total_rows", 0)
            print(f"  Total inventory records: {total}")

        for r in page:
            if (r.get("available") or 0) > 0:
                item_id = str(r.get("id_item", ""))
                if item_id and item_id not in in_stock:
                    in_stock[item_id] = r.get("batch") or ""

        skip += len(page)
        if len(page) < PAGE_SIZE or (total and skip >= total):
            break

        time.sleep(0.3)

    return in_stock


# ---------------------------------------------------------------------------
# Pass 3 — Carrot/Typesense storefront cross-reference
# ---------------------------------------------------------------------------

def fetch_storefront_products(space_id: str, location_id: str = "1") -> dict[str, dict]:
    """Return {batchName: slug} for all products published on the Carrot storefront."""
    with httpx.Client(timeout=15) as c:
        resp = c.get(
            CARROT_SETTINGS_URL,
            params={"locId": location_id},
            headers={"Carrot-Space-Id": space_id, "Accept": "application/json"},
        )
        resp.raise_for_status()
        settings = resp.json()

    ts_node = settings["typesense_nodes"]
    ts_key = settings["typesense_public_key"]
    indexes = settings.get("typesense_indexes_by_location", {})
    index_name = indexes.get(location_id) or indexes.get(int(location_id))
    if not index_name:
        raise RuntimeError(f"No Typesense index for location {location_id}")

    published: dict[str, str] = {}
    page = 1
    with httpx.Client(timeout=15) as c:
        while True:
            resp = c.get(
                f"https://{ts_node}/collections/{index_name}/documents/search",
                params={"q": "*", "per_page": 250, "page": page, "include_fields": "batchName,slug,option1Price"},
                headers={"X-Typesense-Api-Key": ts_key},
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            for hit in hits:
                doc = hit["document"]
                bn = doc.get("batchName")
                slug = doc.get("slug")
                if bn and slug:
                    published[bn] = {"slug": slug, "price": doc.get("option1Price")}
            if len(hits) < 250:
                break
            page += 1

    return published


# ---------------------------------------------------------------------------
# Normalise
# ---------------------------------------------------------------------------

def _product_url(store_url: str, brand: str, name: str) -> str:
    if not store_url:
        return ""
    brand_part = store_slug(brand.strip())
    name_part = store_slug(name)
    slug = f"{brand_part}-{name_part}" if brand_part else name_part
    return f"{store_url}/{slug}"


def derive_variant(weight_useable, uom_weight_useable: str | None) -> str:
    if weight_useable is None:
        return ""
    uom = (uom_weight_useable or "").lower()
    if uom == "grams":
        return f"{float(weight_useable):g}g"
    elif uom == "milligrams":
        mg = float(weight_useable)
        if mg >= 1000:
            return f"{mg / 1000:g}g"
        return f"{int(mg)}mg"
    return ""


def map_classification(strain_type: str | None) -> str:
    if not strain_type:
        return ""
    return strain_type.lower()  # "Hybrid" → "hybrid", "Indica" → "indica", etc.


# Inline patterns removed from within each section (not whole-section drops)
_INLINE_REMOVE_RE = re.compile(
    r'\[[\d.,]+\s*(?:g|oz|ml|mg|lb|pk|ct)\]'   # [1g], [3.5g]
    r'|[\d.,]+\s*(?:g|oz|ml|mg|lb)\b'           # 0.50g, 3.5g, 100mg
    r'|\([shib/]+\)',                            # (H), (S), (I)
    re.I,
)


def resolve_brand(name: str, raw_brand: str, known_brands: set[str]) -> str:
    """If brand is missing, detect it from name parts against the known brand set."""
    if raw_brand:
        return raw_brand
    sep = ' | ' if ' | ' in name else (' - ' if ' - ' in name else None)
    if not sep:
        return raw_brand
    norm_brands = {_norm(b): b for b in known_brands}
    for part in name.split(sep):
        pl = _norm(part)
        if pl in norm_brands:
            return norm_brands[pl]
        for nb, orig in norm_brands.items():
            if pl.startswith(nb + ' '):
                return orig
    return raw_brand


def clean_name(name: str, brand: str) -> str:
    """Remove brand and quantity substrings inline, normalize separator to |."""
    if brand:
        name = re.sub(re.escape(brand), '', name, flags=re.I)
        name = re.sub(r'^[\s|\-]+|[\s|\-]+$', '', name).strip()

    if ' | ' in name:
        sep = ' | '
    elif ' - ' in name:
        sep = ' - '
    else:
        return re.sub(r'\s{2,}', ' ', name).strip()

    parts = [p.strip() for p in name.split(sep)]
    kept = []
    for part in parts:
        part = _INLINE_REMOVE_RE.sub('', part).strip(' ,')
        if part:
            kept.append(part)
    return ' | '.join(kept).strip() if kept else name


def normalise(
    r: dict,
    in_stock_ids: dict[str, str],
    dispensary_slug: str,
    scraped_at: str,
    known_brands: set[str],
    store_url: str = "",
    batch_to_slug: dict[str, str] | None = None,
) -> dict | None:
    item_name = (r.get("item") or "").strip()
    if not item_name:
        return None

    item_id = str(r.get("id_item", ""))
    batch_id = in_stock_ids.get(item_id, "")
    brand = resolve_brand(item_name, (r.get("brand") or "").strip(), known_brands)

    carrot_entry = (batch_to_slug or {}).get(batch_id)
    carrot_price = carrot_entry.get("price") if carrot_entry else None
    if carrot_price is not None:
        price_cents = int(round(float(carrot_price) * 100))
    else:
        tax_rate = TAX_RATES.get(r.get("id_tax_category"), 1.13)
        price_raw = r.get("price_retail_adult_use") or r.get("price_retail") or 0
        price_cents = int(round(float(price_raw) * tax_rate * 100))

    thc = r.get("strain_percent_thc")
    cbd = r.get("strain_percent_cbd")

    media = r.get("media_list") or []
    image_url = (media[0].get("content") or "").strip() if media else ""

    return {
        "dispensary_slug": dispensary_slug,
        "sku":             item_id,
        "batch_id":        batch_id,
        "name":            clean_name(item_name, brand),
        "brand":           brand,
        "category":        map_category(r.get("category")),
        "variant":         derive_variant(r.get("weight_useable"), r.get("uom_weight_useable")),
        "price_cents":     price_cents,
        "thc_percent":     thc if thc else "",
        "cbd_percent":     cbd if cbd else "",
        "classification":  map_classification(r.get("strain_type")),
        "in_stock":        "TRUE" if item_id in in_stock_ids else "FALSE",
        "product_url":     (
            f"{store_url}/{batch_to_slug[batch_id]['slug']}"
            if batch_to_slug and batch_id and batch_id in batch_to_slug
            else _product_url(store_url, brand, item_name)
        ),
        "image_url":       image_url,
        "scraped_at":      scraped_at,
        "description":     " ".join(str(r.get("product_description") or "").split()),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Scrape Alleaves POS catalog to CSV")
    p.add_argument("--tenant", default="brooklynorganicbuds",
                   help="Alleaves tenant ID (used in API auth)")
    p.add_argument("--dispensary-slug", default="brooklyn-organic-buds",
                   help="Dispensary slug for the CSV")
    p.add_argument("--out", default=None)
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--store-url", default="https://brooklynorganicbuds.com/store/product",
                   help="Storefront base URL for product links")
    p.add_argument("--carrot-space-id", default="318",
                   help="Carrot space ID for storefront cross-reference (set empty to skip)")
    p.add_argument("--carrot-location-id", default="1")
    return p.parse_args()


def main():
    args = parse_args()

    username = args.username or os.environ.get("ALLEAVES_USER")
    password = args.password or os.environ.get("ALLEAVES_PASS")
    if not username or not password:
        print("Error: provide --username/--password or set ALLEAVES_USER/ALLEAVES_PASS",
              file=sys.stderr)
        sys.exit(1)

    out_path = args.out or os.path.join(
        os.path.dirname(__file__), f"{args.tenant}_listings.csv"
    )
    dispensary_slug = args.dispensary_slug
    scraped_at = now_iso()

    print(f"Logging in as {username} ...")
    with httpx.Client(base_url=BASE_URL, timeout=30, follow_redirects=True) as client:
        login(client, username, password)
        print("  Logged in.")

        print("Pass 1 — fetching item catalog ...")
        items = fetch_all_items(client)
        print(f"  {len(items)} unique items.")

        print("Pass 2 — fetching inventory for in-stock status ...")
        in_stock_ids = fetch_in_stock_ids(client)
        print(f"  {len(in_stock_ids)} items in retail inventory.")

    batch_to_slug: dict[str, dict] = {}
    if args.carrot_space_id:
        print("Pass 3 — cross-referencing Carrot storefront ...")
        storefront = fetch_storefront_products(args.carrot_space_id, args.carrot_location_id)
        print(f"  {len(storefront)} products published to storefront.")
        batch_to_slug = storefront
        before = len(in_stock_ids)
        in_stock_ids = {
            item_id: batch
            for item_id, batch in in_stock_ids.items()
            if batch in storefront
        }
        print(f"  {len(in_stock_ids)} in stock after storefront filter ({before - len(in_stock_ids)} unpublished).")

    raw_brands = {(r.get("brand") or "").strip() for r in items if r.get("brand")}
    brand_canon = canonical_brands(raw_brands)
    known_brands = set(brand_canon.values())

    rows = []
    skipped = 0
    for r in items:
        if r.get("brand"):
            r = {**r, "brand": brand_canon.get(r["brand"].strip(), r["brand"].strip())}
        row = normalise(r, in_stock_ids, dispensary_slug, scraped_at, known_brands, args.store_url, batch_to_slug)
        if row is None:
            skipped += 1
        else:
            rows.append(row)

    print("\nEnriching listings (subtype + strain) ...")
    enrich(rows)

    write_csv(rows, out_path)
    print(f"\nWrote {len(rows)} rows to {out_path}  ({skipped} skipped)")


if __name__ == "__main__":
    main()
