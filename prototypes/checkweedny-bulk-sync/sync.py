"""
CheckWeedNY bulk sync — prototype

Walks all active products in the database, looks each one up in the
CheckWeedNY COA API, and writes terpene data to product_terpenes.

Lookup priority:
  1. ?batch=<batch_id>  (from linked LabReport — exact, 1 result)
  2. ?brand=<brand>&product=<name>  (substring match, pick best hit)

A product is written only when:
  - parse_confidence >= 0.7 (configurable via --min-confidence)
  - terpene_count > 0

Usage:
  python sync.py                   # dry run (no DB writes)
  python sync.py --write           # actually write to DB
  python sync.py --write --skip-existing   # skip products that already have terpenes
  python sync.py --product-id <uuid>       # single product
  python sync.py --brand "Ayrloom"         # all products for a brand
"""

import argparse
import json
import os
import sys
import time
from typing import Optional
from uuid import UUID

import requests
from sqlmodel import Session, select, delete

# Make sure we can import from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from database import engine
from models import (
    LabReport,
    Product,
    ProductTerpene,
    Terpene,
    ProductCannabinoid,
    Cannabinoid,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHECKWEEDNY_API_BASE = "https://api.checkweedny.com/v1"
DEFAULT_MIN_CONFIDENCE = 0.7
REQUEST_TIMEOUT = 10  # seconds
RATE_LIMIT_DELAY = 0.25  # seconds between API calls

# ---------------------------------------------------------------------------
# Terpene name normalization (x007 risk mitigation)
#
# The CheckWeedNY API uses its own naming conventions. This map converts
# API compound names → our canonical names (from lab_report_parser.py).
# ---------------------------------------------------------------------------

TERPENE_NAME_MAP: dict[str, str] = {
    # Caryophyllene variants
    "Caryophyllene":              "β-Caryophyllene",
    "Beta-Caryophyllene":         "β-Caryophyllene",
    "B-Caryophyllene":            "β-Caryophyllene",
    "β-Caryophyllene":            "β-Caryophyllene",
    # Pinene variants
    "Alpha-Pinene":               "α-Pinene",
    "A-Pinene":                   "α-Pinene",
    "alpha-Pinene":               "α-Pinene",
    "Beta-Pinene":                "β-Pinene",
    "B-Pinene":                   "β-Pinene",
    "beta-Pinene":                "β-Pinene",
    # Humulene
    "Alpha-Humulene":             "Humulene",
    "A-Humulene":                 "Humulene",
    "alpha-Humulene":             "Humulene",
    # Terpineol
    "Alpha-Terpineol":            "Terpineol",
    "A-Terpineol":                "Terpineol",
    # Bisabolol
    "Alpha-Bisabolol":            "Bisabolol",
    "A-Bisabolol":                "Bisabolol",
    # Nerolidol
    "Trans-Nerolidol":            "trans-Nerolidol",
    "Cis-Nerolidol":              "cis-Nerolidol",
    # Ocimene
    "Beta-Ocimene":               "Ocimene",
    "B-Ocimene":                  "Ocimene",
    "Trans-Beta-Ocimene":         "Ocimene",
    "trans-b-Ocimene":            "Ocimene",
    # Cedrene
    "Alpha-Cedrene":              "α-Cedrene",
    # Phellandrene
    "Alpha-Phellandrene":         "α-Phellandrene",
    # Terpinene
    "Gamma-Terpinene":            "γ-Terpinene",
    "G-Terpinene":                "γ-Terpinene",
    "Alpha-Terpinene":            "α-Terpinene",
    # Other common aliases
    "1,8-Cineole":                "Eucalyptol",
    "Fenchyl Alcohol":            "Fenchol",
    "D-3-Carene":                 "Δ3-Carene",
    "Farnesene":                  "Farnesene",
    "Trans-Beta-Farnesene":       "Farnesene",
}


def normalize_terpene_name(api_name: str) -> str:
    """Convert API compound name to canonical terpene name."""
    return TERPENE_NAME_MAP.get(api_name, api_name)


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def _api_headers() -> dict:
    key = os.environ.get("CHECKWEEDNY_API_KEY", "")
    if not key:
        print("WARNING: CHECKWEEDNY_API_KEY not set — requests may be rejected")
    return {"X-API-Key": key, "Accept": "application/json"}


def lookup_by_batch(batch_id: str) -> Optional[dict]:
    """GET /v1/coas?batch=<batch_id> — returns the single matching record or None."""
    resp = requests.get(
        f"{CHECKWEEDNY_API_BASE}/coas",
        params={"batch": batch_id, "limit": 1},
        headers=_api_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    items = data.get("data") or data if isinstance(data, list) else []
    return items[0] if items else None


def lookup_by_brand_product(brand: str, product_name: str) -> Optional[dict]:
    """
    GET /v1/coas?brand=<brand>&product=<name>
    Returns the best match (highest parse_confidence with terpene_count > 0),
    or None if no results.
    """
    resp = requests.get(
        f"{CHECKWEEDNY_API_BASE}/coas",
        params={"brand": brand, "product": product_name, "limit": 50},
        headers=_api_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    items = data.get("data") or (data if isinstance(data, list) else [])
    if not items:
        return None

    # Prefer records with terpenes, then highest parse_confidence
    with_terpenes = [r for r in items if (r.get("terpene_count") or 0) > 0]
    candidates = with_terpenes or items
    return max(candidates, key=lambda r: r.get("parse_confidence") or 0.0)


def fetch_detail(coa_id: str) -> Optional[dict]:
    """GET /v1/coas/:id — returns full detail with terpenes array."""
    resp = requests.get(
        f"{CHECKWEEDNY_API_BASE}/coas/{coa_id}",
        headers=_api_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


# ---------------------------------------------------------------------------
# DB helpers (mirrors _apply_terpenes_to_product in lab_reports.py)
# ---------------------------------------------------------------------------

def product_has_terpenes(session: Session, product_id: UUID) -> bool:
    return session.exec(
        select(ProductTerpene).where(ProductTerpene.product_id == product_id).limit(1)
    ).first() is not None


def get_batch_id_for_product(session: Session, product_id: UUID) -> Optional[str]:
    """Return the most recent batch_id from any LabReport linked to this product."""
    report = session.exec(
        select(LabReport)
        .where(LabReport.product_id == product_id)
        .where(LabReport.batch_id.isnot(None))
        .order_by(LabReport.created_at.desc())
    ).first()
    return report.batch_id if report else None


def write_terpenes(session: Session, product_id: UUID, terpene_compounds: list[dict]) -> int:
    """
    Replace all ProductTerpene rows for this product with the API data.
    Returns number of terpenes written.
    """
    session.exec(delete(ProductTerpene).where(ProductTerpene.product_id == product_id))

    written = 0
    for compound in terpene_compounds:
        raw_name = compound.get("compound", "")
        pct = compound.get("value_pct")
        if not raw_name or pct is None:
            continue

        canonical_name = normalize_terpene_name(raw_name)
        terpene = session.exec(select(Terpene).where(Terpene.name == canonical_name)).first()
        if not terpene:
            terpene = Terpene(name=canonical_name)
            session.add(terpene)
            session.flush()

        session.add(ProductTerpene(
            product_id=product_id,
            terpene_id=terpene.id,
            percent=round(float(pct), 4),
        ))
        written += 1

    return written


# ---------------------------------------------------------------------------
# Per-product sync logic
# ---------------------------------------------------------------------------

class SyncResult:
    def __init__(self, product: Product):
        self.product = product
        self.status = "skipped"        # skipped | not_found | low_confidence | no_terpenes | written | dry_run
        self.coa_id: Optional[str] = None
        self.confidence: Optional[float] = None
        self.terpene_count: int = 0
        self.lookup_method: Optional[str] = None
        self.error: Optional[str] = None

    def __repr__(self):
        return (
            f"[{self.status:15s}] {str(self.product.name)[:40]:40s} "
            f"brand={str(self.product.brand or '')[:20]:20s} "
            f"coa={self.coa_id or '-':20s} "
            f"conf={self.confidence or '-':5} terpenes={self.terpene_count}"
        )


def sync_product(
    session: Session,
    product: Product,
    *,
    write: bool,
    skip_existing: bool,
    min_confidence: float,
) -> SyncResult:
    result = SyncResult(product)

    if skip_existing and product_has_terpenes(session, product.id):
        result.status = "skipped"
        return result

    list_record = None

    # --- Attempt 1: batch lookup ---
    batch_id = get_batch_id_for_product(session, product.id)
    if batch_id:
        time.sleep(RATE_LIMIT_DELAY)
        list_record = lookup_by_batch(batch_id)
        if list_record:
            result.lookup_method = "batch"

    # --- Attempt 2: brand + product name ---
    if list_record is None and product.brand:
        time.sleep(RATE_LIMIT_DELAY)
        list_record = lookup_by_brand_product(product.brand, product.name)
        if list_record:
            result.lookup_method = "brand+product"

    if list_record is None:
        result.status = "not_found"
        return result

    result.coa_id = list_record.get("id")
    result.confidence = list_record.get("parse_confidence")
    result.terpene_count = list_record.get("terpene_count") or 0

    if (result.confidence or 0.0) < min_confidence:
        result.status = "low_confidence"
        return result

    if result.terpene_count == 0:
        result.status = "no_terpenes"
        return result

    # Fetch detail for compound-level terpene data
    time.sleep(RATE_LIMIT_DELAY)
    detail = fetch_detail(result.coa_id)
    if not detail:
        result.status = "not_found"
        result.error = "detail fetch failed"
        return result

    terpene_compounds = detail.get("terpenes") or []
    if not terpene_compounds:
        result.status = "no_terpenes"
        return result

    result.terpene_count = len(terpene_compounds)

    if not write:
        result.status = "dry_run"
        return result

    written = write_terpenes(session, product.id, terpene_compounds)
    session.commit()
    result.terpene_count = written
    result.status = "written"
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sync terpene data from CheckWeedNY API")
    parser.add_argument("--write", action="store_true", help="Actually write to DB (default: dry run)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip products that already have terpenes")
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE,
                        help=f"Minimum parse_confidence threshold (default {DEFAULT_MIN_CONFIDENCE})")
    parser.add_argument("--product-id", help="Sync a single product by UUID")
    parser.add_argument("--brand", help="Sync only products matching this brand (case-insensitive substring)")
    args = parser.parse_args()

    if not args.write:
        print("DRY RUN — pass --write to commit changes to the database\n")

    with Session(engine) as session:
        query = select(Product).where(Product.is_active == True)
        if args.product_id:
            query = query.where(Product.id == UUID(args.product_id))
        if args.brand:
            query = query.where(Product.brand.ilike(f"%{args.brand}%"))

        products = session.exec(query).all()
        print(f"Found {len(products)} product(s) to process\n")

        results = []
        for product in products:
            try:
                r = sync_product(
                    session,
                    product,
                    write=args.write,
                    skip_existing=args.skip_existing,
                    min_confidence=args.min_confidence,
                )
            except Exception as exc:
                r = SyncResult(product)
                r.status = "error"
                r.error = str(exc)
            print(r)
            results.append(r)

        # Summary
        counts: dict[str, int] = {}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1

        print("\n--- Summary ---")
        for status, count in sorted(counts.items()):
            print(f"  {status:15s}: {count}")
        print(f"  {'total':15s}: {len(results)}")

        if not args.write and any(r.status == "dry_run" for r in results):
            would_write = sum(1 for r in results if r.status == "dry_run")
            print(f"\n{would_write} product(s) would be written — re-run with --write to apply")


if __name__ == "__main__":
    main()