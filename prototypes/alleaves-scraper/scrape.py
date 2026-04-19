"""
scrape.py — Alleaves POS inventory scraper

Fetches all in-stock inventory for a tenant from the Alleaves POS API and
writes a CSV in the same format as the travel-agency scraper so that
scripts/import_listings.py can import it without modification.

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
import csv
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode


try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(1)


BASE_URL = "https://app.alleaves.com"
PAGE_SIZE = 100

CATEGORY_MAP = {
    "Flower":       "flower",
    "Pre-Roll":     "preroll",
    "Vaporizers":   "cart",
    "Concentrate":  "concentrate",
    "Edibles":      "edible",
    "Tinctures":    "tincture",
    "Topicals":     "topical",
    "Accessories":  "merch",
    "Apparel":      "merch",
    "Dog Treats":   "other",
}

CSV_COLUMNS = [
    "dispensary_slug", "sku", "product_uuid", "name", "brand", "category",
    "variant", "price_cents", "thc_percent", "cbd_percent", "classification",
    "in_stock", "product_url", "scraped_at",
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(client: httpx.Client, username: str, password: str) -> None:
    """Login and persist session cookies onto the client."""
    resp = client.post(
        "/api/account/login",
        json={"username": username, "password": password},
    )
    resp.raise_for_status()
    data = resp.json()
    if "redirect_url" not in data:
        raise RuntimeError(f"Login failed: {data}")


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def build_inventory_params(skip: int) -> str:
    """Build the form-encoded body for the inventory/search endpoint."""
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
        # exclude scrap areas
        "filter[filters][2][filters][0][field]": "area_type",
        "filter[filters][2][filters][0][value]": "scrap",
        "filter[filters][2][filters][0][operator]": "neq",
        "filter[filters][2][filters][1][field]": "area_type",
        "filter[filters][2][filters][1][value]": "true",
        "filter[filters][2][filters][1][operator]": "isnull",
        "filter[filters][2][logic]": "or",
        "id_location": "",
    }
    return urlencode(params)


def fetch_page(client: httpx.Client, skip: int) -> list[dict]:
    resp = client.post(
        "/api/inventory/search",
        content=build_inventory_params(skip),
        headers={
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest",
            "accept": "application/json",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response shape: {type(data)}")
    return data


def fetch_all(client: httpx.Client) -> list[dict]:
    """Paginate through all inventory records."""
    records = []
    seen_batches: set[str] = set()
    skip = 0
    total = None

    while True:
        page = fetch_page(client, skip)
        if not page:
            break

        if total is None and page:
            total = page[0].get("total_rows", 0)
            print(f"  Total inventory records: {total}")

        for r in page:
            batch_key = str(r.get("id_batch", ""))
            if batch_key in seen_batches:
                continue  # same batch in multiple areas — take first
            seen_batches.add(batch_key)
            records.append(r)

        skip += len(page)
        if len(page) < PAGE_SIZE or (total and skip >= total):
            break

        time.sleep(0.3)  # polite rate limiting

    return records


# ---------------------------------------------------------------------------
# Normalise
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """'Brooklyn Organic Buds' -> 'brooklyn-organic-buds'"""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def derive_variant(weight_useable, weight_useable_uom: str | None) -> str:
    if weight_useable is None:
        return ""
    uom = (weight_useable_uom or "").lower()
    if uom == "grams":
        val = float(weight_useable)
        return f"{val:g}g"
    elif uom == "milligrams":
        mg = float(weight_useable)
        if mg >= 1000:
            return f"{mg / 1000:g}g"
        return f"{int(mg)}mg"
    return ""


def map_category(raw_category: str | None) -> str:
    if not raw_category:
        return "other"
    top = raw_category.split(" > ")[0].strip()
    return CATEGORY_MAP.get(top, "other")


def normalise(r: dict, dispensary_slug: str, scraped_at: str) -> dict | None:
    """Return a CSV row dict, or None to skip the record."""
    item_name = (r.get("item") or "").strip()
    if not item_name:
        return None

    # Skip internal sample items
    if "SAMPLES" in item_name.upper():
        return None

    price_raw = r.get("price_otd_adult_use") or 0
    price_cents = int(round(float(price_raw) * 100))

    available = r.get("available") or 0

    return {
        "dispensary_slug": dispensary_slug,
        "sku":             r.get("batch") or str(r.get("id_batch", "")),
        "product_uuid":    str(r.get("id_batch", "")),
        "name":            item_name,
        "brand":           (r.get("brand") or "").strip() or "",
        "category":        map_category(r.get("category")),
        "variant":         derive_variant(r.get("weight_useable"), r.get("weight_useable_uom")),
        "price_cents":     price_cents,
        "thc_percent":     r.get("thc") or "",
        "cbd_percent":     r.get("cbd") or "",
        "classification":  "",
        "in_stock":        "TRUE" if available > 0 else "FALSE",
        "product_url":     "",
        "scraped_at":      scraped_at,
    }


def write_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Scrape Alleaves POS inventory to CSV")
    p.add_argument("--tenant", default="brooklynorganicbuds",
                   help="Alleaves tenant slug (default: brooklynorganicbuds)")
    p.add_argument("--out", default=None,
                   help="Output CSV path (default: <tenant>_listings.csv in script dir)")
    p.add_argument("--username", default=None,
                   help="Alleaves username (or set ALLEAVES_USER)")
    p.add_argument("--password", default=None,
                   help="Alleaves password (or set ALLEAVES_PASS)")
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

    scraped_at = datetime.now(timezone.utc).isoformat()

    print(f"Logging in as {username} ...")
    with httpx.Client(base_url=BASE_URL, timeout=30, follow_redirects=True) as client:
        login(client, username, password)
        print("  Logged in.")

        print("Fetching inventory ...")
        records = fetch_all(client)
        print(f"  Fetched {len(records)} unique inventory records.")

    # Derive dispensary slug from the location field of the first real record,
    # falling back to the tenant arg.
    location_name = next(
        (r.get("location") for r in records if r.get("location")),
        args.tenant,
    )
    dispensary_slug = slugify(location_name)
    print(f"  Dispensary slug: {dispensary_slug!r}")

    rows = []
    skipped = 0
    for r in records:
        row = normalise(r, dispensary_slug, scraped_at)
        if row is None:
            skipped += 1
        else:
            rows.append(row)

    write_csv(rows, out_path)
    print(f"\nWrote {len(rows)} rows to {out_path}  ({skipped} skipped)")


if __name__ == "__main__":
    main()
