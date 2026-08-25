"""
import_dispensaries.py — Sync dispensaries.json into the DB.

Upserts dispensaries keyed on `slug`. On conflict, updates `address`,
`website_url`, and `location` (only when DB value is null/empty). On insert,
creates a row with name/slug/website_url/address/location populated from
the JSON.

`accepts_pickup` is synced in both directions on every run: the JSON is the
source of truth for which stores take orders, so an entry without the key is
actively set back to false. Omitting it is how you turn ordering off.

Usage:
  python scripts/import_dispensaries.py [--dry-run]

  DATABASE_URL must be set in the environment or in .env at the project root.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlmodel import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import session_scope
from models import Dispensary, PosType


def format_address(addr: dict) -> str:
    return f"{addr['street']}, {addr['city']}, {addr['state']} {addr['zip']}"


PLATFORM_TO_POS = {
    "alleaves": PosType.alleaves,
    "travel_agency": PosType.leaflogix,
}


def parse_args():
    p = argparse.ArgumentParser(description="Sync dispensaries.json into terpenomics DB")
    p.add_argument("--json", default="dispensaries.json", help="Path to dispensaries.json")
    p.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    src = Path(args.json)
    if not src.is_file():
        print(f"File not found: {src}", file=sys.stderr)
        return 1

    entries = json.loads(src.read_text())

    inserted = updated = unchanged = 0
    with session_scope() as s:
        existing = {d.slug: d for d in s.exec(select(Dispensary)).all()}

        for e in entries:
            slug = e["slug"]
            addr_str = format_address(e["address"]) if e.get("address") else None
            neighborhood = e.get("neighborhood")
            website = e.get("store_url")
            lat = e.get("latitude")
            lng = e.get("longitude")
            pos_type = PLATFORM_TO_POS.get(e.get("platform"), PosType.none)
            pos_tenant = (
                e.get("alleaves_tenant")
                or e.get("dutchie_id")
                or e.get("blaze_id")
            )
            accepts_pickup = bool(e.get("accepts_pickup", False))

            d = existing.get(slug)
            if d is None:
                d = Dispensary(
                    name=e["name"],
                    slug=slug,
                    website_url=website,
                    address=addr_str,
                    location=neighborhood,
                    lat=lat,
                    lng=lng,
                    pos_type=pos_type,
                    pos_tenant_id=pos_tenant,
                    accepts_pickup=accepts_pickup,
                )
                print(f"INSERT {slug:40s} address={addr_str!r} coords=({lat},{lng})")
                if not args.dry_run:
                    s.add(d)
                inserted += 1
                continue

            changes = []
            if d.address != addr_str and addr_str:
                changes.append(f"address: {d.address!r} -> {addr_str!r}")
                d.address = addr_str
            if not d.website_url and website:
                changes.append(f"website_url: None -> {website!r}")
                d.website_url = website
            if neighborhood and (not d.location or d.location in ("Brooklyn, NY", "New York, NY")):
                changes.append(f"location: {d.location!r} -> {neighborhood!r}")
                d.location = neighborhood
            if lat is not None and d.lat != lat:
                changes.append(f"lat: {d.lat} -> {lat}")
                d.lat = lat
            if lng is not None and d.lng != lng:
                changes.append(f"lng: {d.lng} -> {lng}")
                d.lng = lng
            # Unconditional: dropping the key from the JSON must turn ordering off.
            if d.accepts_pickup != accepts_pickup:
                changes.append(f"accepts_pickup: {d.accepts_pickup} -> {accepts_pickup}")
                d.accepts_pickup = accepts_pickup

            if changes:
                print(f"UPDATE {slug:40s} {'; '.join(changes)}")
                updated += 1
            else:
                unchanged += 1

        if args.dry_run:
            print("\n[dry-run] no changes committed")
            raise SystemExit(0)

    print(f"\ninserted={inserted} updated={updated} unchanged={unchanged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
