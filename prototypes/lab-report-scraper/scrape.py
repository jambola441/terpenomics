"""
Lab report scraper — CheckWeedNY batch ID lookup.

Reads batch IDs from an Alleaves CSV (or any CSV with batch_id + sku + brand + name columns),
looks each one up on CheckWeedNY, and writes a normalized CSV.  With --write, also upserts
LabReport rows and ProductTerpene/ProductCannabinoid records via the project DB.

Usage:
    python scrape.py                            # dry run, writes results.csv
    python scrape.py --write                    # dry run + DB upsert
    python scrape.py --limit 10                 # cap requests (for testing)
    python scrape.py --min-confidence 0.7       # skip low-confidence hits

Requires: COA_API_KEY env var
          DATABASE_URL env var (for --write)
"""

import argparse
import csv
import json
import os
import sys

PROTOTYPE_DIR = os.path.dirname(__file__)
PROJECT_ROOT  = os.path.abspath(os.path.join(PROTOTYPE_DIR, "../.."))

DEFAULT_INPUT  = os.path.join(PROTOTYPE_DIR, "../alleaves-scraper/brooklynorganicbuds_listings.csv")
DEFAULT_OUTPUT = os.path.join(PROTOTYPE_DIR, "results.csv")
DEFAULT_DISPENSARY_SLUG = "brooklyn-organic-buds"


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

def load_batch_items(path: str) -> list[dict]:
    """Return [{batch_id, sku, brand, name}, ...] for rows with a non-empty batch_id."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [
        {
            "batch_id": r["batch_id"].strip(),
            "sku":      r.get("sku", "").strip(),
            "brand":    r.get("brand", "").strip(),
            "name":     r.get("name", "").strip(),
        }
        for r in rows
        if r.get("batch_id", "").strip()
    ]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def build_sku_map(dispensary_slug: str):
    """Return {sku: {listing_id, product_id}} for a dispensary."""
    sys.path.insert(0, PROJECT_ROOT)
    from database import engine
    from models import Dispensary, Listing
    from sqlmodel import Session, select

    with Session(engine) as session:
        dispensary = session.exec(
            select(Dispensary).where(Dispensary.slug == dispensary_slug)
        ).first()
        if not dispensary:
            raise RuntimeError(f"Dispensary '{dispensary_slug}' not found in DB")

        listings = session.exec(
            select(Listing).where(Listing.dispensary_id == dispensary.id)
        ).all()

    return {
        l.sku: {"listing_id": l.id, "product_id": l.product_id}
        for l in listings
        if l.sku
    }


def upsert_lab_report(entry, listing_id, product_id):
    """
    Insert or update a LabReport row for this batch_id + listing.
    Also writes ProductTerpene / ProductCannabinoid if product_id is set.
    Returns status string: "inserted" | "updated" | "no_product".
    """
    sys.path.insert(0, PROJECT_ROOT)
    from database import engine
    from models import (
        Cannabinoid, CannabinoidFamily, LabReport, LabReportStatus,
        ProductCannabinoid, ProductTerpene, Terpene,
    )
    from sqlalchemy import delete as sa_delete
    from sqlmodel import Session, select

    with Session(engine) as session:
        # Check for existing LabReport with this batch_id
        existing = session.exec(
            select(LabReport).where(LabReport.batch_id == entry.batch_id)
        ).first()

        if existing:
            report = existing
            action = "updated"
        else:
            report = LabReport()
            action = "inserted"

        report.listing_id              = listing_id
        report.product_id              = product_id
        report.batch_id                = entry.batch_id
        report.lab_name                = entry.lab_name
        report.lab_license             = entry.lab_license
        report.test_date               = entry.test_date
        report.product_name_on_report  = entry.product_name
        report.total_terpenes          = entry.total_terpenes
        report.pass_fail               = entry.pass_fail
        report.confidence              = int(round((entry.confidence or 0.0) * 5))  # 0–1 → 1–5
        report.raw_terpenes_json       = json.dumps([{"name": t.name, "percent": t.percent} for t in entry.terpenes])
        report.raw_cannabinoids_json   = json.dumps([{"name": c.name, "percent": c.percent} for c in entry.cannabinoids])

        if product_id and (entry.terpenes or entry.cannabinoids):
            report.status = LabReportStatus.applied
        else:
            report.status = LabReportStatus.extracted

        session.add(report)
        session.flush()

        if product_id:
            # Replace terpenes
            if entry.terpenes:
                session.exec(sa_delete(ProductTerpene).where(ProductTerpene.product_id == product_id))
                for t in entry.terpenes:
                    terpene = session.exec(select(Terpene).where(Terpene.name == t.name)).first()
                    if not terpene:
                        terpene = Terpene(name=t.name)
                        session.add(terpene)
                        session.flush()
                    session.add(ProductTerpene(product_id=product_id, terpene_id=terpene.id, percent=t.percent))

            # Replace cannabinoids
            if entry.cannabinoids:
                session.exec(sa_delete(ProductCannabinoid).where(ProductCannabinoid.product_id == product_id))
                for c in entry.cannabinoids:
                    cannabinoid = session.exec(select(Cannabinoid).where(Cannabinoid.name == c.name)).first()
                    if not cannabinoid:
                        cannabinoid = Cannabinoid(name=c.name, family=CannabinoidFamily.other)
                        session.add(cannabinoid)
                        session.flush()
                    session.add(ProductCannabinoid(product_id=product_id, cannabinoid_id=cannabinoid.id, percent=c.percent))

        session.commit()

    return action if product_id else "no_product"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape CheckWeedNY for a list of batch IDs")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input CSV with batch_id + sku columns")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help="Output CSV path")
    parser.add_argument("--limit", type=int, default=None, help="Max batch IDs to process")
    parser.add_argument("--min-confidence", type=float, default=0.0,
                        help="Skip results below this parse_confidence (0.0–1.0)")
    parser.add_argument("--write", action="store_true", help="Upsert results to DB")
    parser.add_argument("--dispensary-slug", default=DEFAULT_DISPENSARY_SLUG)
    args = parser.parse_args()

    sys.path.insert(0, PROTOTYPE_DIR)
    from checkweedny import fetch
    from schema import CSV_FIELDS, to_csv_row

    if not args.write:
        print("DRY RUN — pass --write to upsert to DB\n")

    items = load_batch_items(args.input)
    if args.limit:
        items = items[: args.limit]

    print(f"Input:  {args.input}  ({len(items)} batch IDs)")
    print(f"Output: {args.out}")
    print()

    sku_map = {}
    if args.write:
        print("Loading listing SKU map from DB...")
        sku_map = build_sku_map(args.dispensary_slug)
        print(f"  {len(sku_map)} listings loaded\n")

    counts: dict[str, int] = {}
    rows = []

    for i, item in enumerate(items, 1):
        batch_id = item["batch_id"]
        brand    = item["brand"]
        name     = item["name"]
        sku      = item["sku"]

        print(f"[{i:3d}/{len(items)}] {batch_id}  {brand} — {name} ... ", end="", flush=True)

        try:
            entry = fetch(batch_id)
        except Exception as exc:
            print(f"ERROR: {exc}")
            counts["error"] = counts.get("error", 0) + 1
            continue

        if entry is None:
            print("not found")
            counts["not_found"] = counts.get("not_found", 0) + 1
            continue

        if (entry.confidence or 0.0) < args.min_confidence:
            print(f"low confidence ({entry.confidence})")
            counts["low_confidence"] = counts.get("low_confidence", 0) + 1
            continue

        listing_info = sku_map.get(sku, {})
        listing_id   = listing_info.get("listing_id")
        product_id   = listing_info.get("product_id")

        db_status = ""
        if args.write:
            if listing_id:
                db_status = upsert_lab_report(entry, listing_id, product_id)
            else:
                db_status = "no_listing"

        tag = f"  [{db_status}]" if db_status else ""
        print(f"OK  terpenes={len(entry.terpenes)}  cannabinoids={len(entry.cannabinoids)}  conf={entry.confidence}{tag}")

        counts[db_status or "found"] = counts.get(db_status or "found", 0) + 1
        rows.append(to_csv_row(entry, brand=brand, product_name_scraped=name))

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print()
    print("--- Summary ---")
    for status, count in sorted(counts.items()):
        print(f"  {status:15s}: {count}")
    print(f"  {'csv_rows':15s}: {len(rows)}")
    print(f"\nCSV written to {args.out}")


if __name__ == "__main__":
    main()
