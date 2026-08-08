#!/usr/bin/env python3
"""
scrape_graphql.py — Dutchie GraphQL menu scraper

Scrapes any store with a `dutchie_id` (MongoDB ObjectID) in stores.json by calling
the public Dutchie GraphQL API at dutchie.com/graphql.  No API key needed; uses
curl_cffi safari17_0 TLS impersonation to bypass Cloudflare.

Covers all Dutchie-powered Brooklyn dispensaries regardless of how their frontend
is deployed (WP embed iframe, Dutchie eCommerce Next.js, or direct dutchie.com URL).

Usage
-----
  # Batch all stores with a dutchie_id in stores.json:
  python scrape_graphql.py --all [--out-dir ./]

  # Single store by dutchie_id:
  python scrape_graphql.py --dutchie-id 66d24bbc7ee915c729faa0a0 \
                            --dispensary-slug soulmate-fort-greene \
                            --name "Soulmate"
"""

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../scripts"))
from scraper_common import apply_brand_aliases, canonical_brands, map_category, normalize_variant, now_iso, stamped_path, write_csv  # noqa: E402
from enrich import enrich, write_usage  # noqa: E402

try:
    from curl_cffi import requests as cffi_req
except ImportError:
    print("curl_cffi is required: pip install curl_cffi", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DELAY_SECS  = 1.0
PER_PAGE    = 48
GQL_URL     = "https://dutchie.com/graphql"
IMPERSONATE = "safari17_0"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept":         "application/json",
    "Content-Type":   "application/json",
    "Origin":         "https://dutchie.com",
    "Referer":        "https://dutchie.com/",
}

HERE        = os.path.dirname(os.path.abspath(__file__))
ROOT        = os.path.abspath(os.path.join(HERE, "../.."))
STORES_JSON = os.path.join(ROOT, "dispensaries.json")

# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------

PRODUCTS_QUERY = """
query FilteredProducts(
  $productsFilter: productsFilterInput!
  $page: Int
  $perPage: Int
) {
  filteredProducts(
    filter: $productsFilter
    page: $page
    perPage: $perPage
  ) {
    products {
      _id
      Name
      brand { name }
      Options
      Prices
      recPrices
      THCContent { unit range }
      CBDContent { unit range }
      Image
      strainType
      type
      description
    }
    queryInfo {
      totalCount
      totalPages
    }
  }
}
"""

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _parse_potency(content: dict | None) -> str:
    """Return a human-readable potency string from a THCContent/CBDContent object.

    range is a list of 1-2 floats; unit is PERCENTAGE or MILLIGRAMS.
    We take the max value.  Returns "" when data is absent or zero.
    """
    if not content:
        return ""
    rng = content.get("range")
    if not rng:
        return ""
    val = max(rng)
    if val == 0:
        return ""
    unit = content.get("unit", "PERCENTAGE")
    if unit == "MILLIGRAMS":
        return f"{val:g}mg"
    return f"{val:g}"


def normalise_gql(p: dict, dispensary_slug: str, scraped_at: str) -> list[dict]:
    """One row per option/variant tier in the product."""
    name   = str(p.get("Name") or "").strip()
    brand  = str((p.get("brand") or {}).get("name") or "").strip()
    cat    = map_category(str(p.get("type") or "").strip())
    desc   = " ".join(str(p.get("description") or "").split())
    strain = str(p.get("strainType") or "").strip().lower()
    if strain in ("n/a", ""):
        strain = ""

    thc   = _parse_potency(p.get("THCContent"))
    cbd   = _parse_potency(p.get("CBDContent"))
    sku   = str(p.get("_id") or "").strip()
    image = str(p.get("Image") or "").strip()

    options = p.get("Options") or ["N/A"]
    prices  = p.get("recPrices") or p.get("Prices") or []

    rows = []
    for i, opt in enumerate(options):
        price_raw   = prices[i] if i < len(prices) else None
        price_cents = int(round(float(price_raw) * 100)) if price_raw is not None else ""
        variant     = normalize_variant(opt) if opt and opt.strip().upper() != "N/A" else ""
        rows.append({
            "dispensary_slug": dispensary_slug,
            "sku":             sku,
            "batch_id":        "",  # reserved for real batch/lot IDs (METRC); Dutchie doesn't expose one
            "name":            name,
            "brand":           brand,
            "category":        cat,
            "variant":         variant,
            "price_cents":     price_cents,
            "thc_percent":     thc,
            "cbd_percent":     cbd,
            "classification":  strain,
            "in_stock":        "TRUE",
            "product_url":     "",
            "image_url":       image,
            "scraped_at":      scraped_at,
            "description":     desc,
        })
    return rows


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def _gql_payload(dutchie_id: str, page: int) -> dict:
    return {
        "operationName": "FilteredProducts",
        "variables": {
            "productsFilter": {
                "dispensaryId":              dutchie_id,
                "Status":                    "Active",
                "bypassOnlineThresholds":    True,
                "removeProductsBelowOptionThresholds": False,
            },
            "page":    page,
            "perPage": PER_PAGE,
        },
        "query": PRODUCTS_QUERY,
    }


def _fetch_gql_page(dutchie_id: str, page: int, retries: int = 3) -> list[dict]:
    """Fetch one GQL page in an independent session (thread-safe). Retries on transient errors."""
    last_exc: Exception = Exception("no attempts made")
    for attempt in range(retries):
        try:
            session = cffi_req.Session(impersonate=IMPERSONATE)
            resp = session.post(GQL_URL, json=_gql_payload(dutchie_id, page), headers=HEADERS, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            if "errors" in body:
                raise RuntimeError(body["errors"][0].get("message", "?"))
            fp = (body.get("data") or {}).get("filteredProducts") or {}
            return fp.get("products") or []
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"page {page} failed after {retries} attempts: {last_exc}") from last_exc


def scrape_store(
    session: cffi_req.Session,
    dutchie_id: str,
    dispensary_slug: str,
    dispensary_name: str,
    out_path: str,
    parallel: bool = False,
    no_enrich: bool = False,
    model: str = "haiku",
) -> int:
    print(f"\n{'='*60}")
    print(f"Scraping: {dispensary_name}")
    print(f"  dutchie_id: {dutchie_id}")

    scraped_at = now_iso()
    all_rows:  list[dict] = []
    seen_ids:  set[str]   = set()

    # Page 1 — always fetch first to learn total_pages
    resp = session.post(GQL_URL, json=_gql_payload(dutchie_id, 1), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    body = resp.json()

    if "errors" in body:
        print(f"  [ERROR] {body['errors'][0].get('message','?')}")
        return 0

    fp          = (body.get("data") or {}).get("filteredProducts") or {}
    qi          = fp.get("queryInfo") or {}
    total_count = qi.get("totalCount") or 0
    total_pages = qi.get("totalPages") or 0
    products_1  = fp.get("products") or []

    print(f"  Total products: {total_count}  Total pages: {total_pages} (perPage={PER_PAGE})")

    for p in products_1:
        pid = str(p.get("_id") or "")
        if pid not in seen_ids:
            seen_ids.add(pid)
            all_rows.extend(normalise_gql(p, dispensary_slug, scraped_at))
    print(f"  page=  1  unique products: {len(seen_ids)}")

    remaining = list(range(2, total_pages + 1))

    if remaining and parallel:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        pages_data: dict[int, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=min(len(remaining), 6)) as executor:
            futures = {executor.submit(_fetch_gql_page, dutchie_id, p): p for p in remaining}
            for future in as_completed(futures):
                pg = futures[future]
                pages_data[pg] = future.result()  # raises → exits executor, fails scrape
                print(f"  page={pg:3d}  fetched ({len(pages_data[pg])} products)")
        for pg in sorted(pages_data):
            for p in pages_data[pg]:
                pid = str(p.get("_id") or "")
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_rows.extend(normalise_gql(p, dispensary_slug, scraped_at))
    elif remaining:
        for page in remaining:
            time.sleep(DELAY_SECS)
            resp = session.post(GQL_URL, json=_gql_payload(dutchie_id, page), headers=HEADERS, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            if "errors" in body:
                print(f"  [ERROR] {body['errors'][0].get('message','?')}")
                break
            fp       = (body.get("data") or {}).get("filteredProducts") or {}
            products = fp.get("products") or []
            for p in products:
                pid = str(p.get("_id") or "")
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_rows.extend(normalise_gql(p, dispensary_slug, scraped_at))
            print(f"  page={page:3d}  unique products: {len(seen_ids)}")

    if not all_rows:
        print("  [WARN] No rows collected")
        return 0

    raw_brands  = {r["brand"] for r in all_rows if r["brand"]}
    brand_canon = canonical_brands(raw_brands)
    for r in all_rows:
        if r["brand"]:
            r["brand"] = brand_canon.get(r["brand"], r["brand"])
    apply_brand_aliases(all_rows)

    if not no_enrich:
        print("  Enriching (subtype + strain) ...")
    usage = enrich(all_rows, no_enrich=no_enrich, model=model)
    write_usage(usage, out_path)

    write_csv(all_rows, out_path)
    print(f"  Wrote {len(all_rows)} rows → {out_path}")
    return len(all_rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Scrape Dutchie-powered dispensary menus via GraphQL"
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--all",        action="store_true",
                      help="Scrape all stores with dutchie_id in stores.json")
    mode.add_argument("--dutchie-id", default=None,
                      help="MongoDB ObjectID of the dispensary")

    p.add_argument("--dispensary-slug", default=None)
    p.add_argument("--name",    default="", help="Human-readable dispensary name")
    p.add_argument("--out",     default=None, help="Output CSV path (single-store mode)")
    p.add_argument("--out-dir", default=os.path.join(ROOT, "data/scrapes"),
                      help="Output directory for --all mode")
    p.add_argument("--parallel",   action="store_true", help="Fetch pages 2..N concurrently")
    p.add_argument("--no-enrich",  action="store_true", help="Skip Haiku enrichment")
    p.add_argument("--model",      default="haiku", help="Enrichment model id (see MODELS in scripts/enrich.py)")
    return p.parse_args()


def load_stores() -> list[dict]:
    with open(STORES_JSON) as f:
        all_stores = json.load(f)
    stores = [s for s in all_stores if s.get("platform") == "dutchie_graphql"]
    for s in stores:
        s.setdefault("dispensary_slug", s.get("slug", ""))
    return stores


def main():
    args = parse_args()

    session = cffi_req.Session(impersonate=IMPERSONATE)

    if args.all:
        stores     = load_stores()
        total_rows = 0
        skipped    = 0

        for s in stores:
            dutchie_id = s.get("dutchie_id")
            if not dutchie_id:
                platform = s.get("platform", "unknown")
                print(f"\n[SKIP] {s['name']} — no dutchie_id (platform={platform})")
                skipped += 1
                continue

            out_path = os.path.join(args.out_dir, stamped_path(f"{s['dispensary_slug']}_listings.csv"))
            n = scrape_store(
                session,
                dutchie_id,
                s["dispensary_slug"],
                s["name"],
                out_path,
                parallel=args.parallel,
                no_enrich=args.no_enrich,
                model=args.model,
            )
            total_rows += n
            if n == 0:
                skipped += 1
            else:
                time.sleep(DELAY_SECS)

        print(f"\n{'='*60}")
        print(f"Done. Total rows: {total_rows}  Skipped/failed: {skipped}")

    else:
        if not args.dutchie_id:
            print("Provide --dutchie-id or --all", file=sys.stderr)
            sys.exit(1)

        disp_slug = (
            args.dispensary_slug
            or re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
            or args.dutchie_id
        )
        out_path = args.out or stamped_path(os.path.join(HERE, f"{disp_slug}_listings.csv"))
        scrape_store(session, args.dutchie_id, disp_slug, args.name or args.dutchie_id, out_path, parallel=args.parallel, no_enrich=args.no_enrich, model=args.model)


if __name__ == "__main__":
    main()
