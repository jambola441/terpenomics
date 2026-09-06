#!/usr/bin/env python3
"""Give every store a starting set of featured listings.

Featuring is a person's job -- a store decides what it wants pushed this week --
but the admin surface for it does not exist yet, and an empty rail on every
store's feed reads as a broken screen rather than an unmade choice. So this
picks defaults that a store would plausibly have picked itself, and leaves them
to be replaced by hand.

The picks favour products that will *look* right in the rail: a photo, a
price, and lab data, spread across categories so a store's four picks are not
four jars of flower. Existing picks are never touched, so this is safe to re-run
and will not overwrite curation once it starts.

    python scripts/seed_featured.py                  # every store, 4 picks each
    python scripts/seed_featured.py --per-store 6
    python scripts/seed_featured.py --dispensary bergen-botanics
    python scripts/seed_featured.py --replace        # discard existing picks first
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from database import engine  # noqa: E402
from models import Dispensary, FeaturedListing, Listing, ListingCannabinoid  # noqa: E402


def pick_for(session: Session, dispensary_id, per_store: int) -> list[Listing]:
    """Presentable products, one per category before doubling up on any."""
    documented = (
        select(Listing.id)
        .join(ListingCannabinoid, ListingCannabinoid.listing_id == Listing.id)
        .where(Listing.dispensary_id == dispensary_id)
        .subquery()
    )

    candidates = session.exec(
        select(Listing)
        .where(Listing.dispensary_id == dispensary_id)
        .where(Listing.is_active == True)  # noqa: E712
        .where(Listing.in_stock == True)  # noqa: E712
        .where(Listing.price_cents.isnot(None))
        .where(Listing.image_url.isnot(None))
        # Lab data first, then the older rows: a product that has been on the
        # shelf a while and still sells is a safer default than yesterday's.
        .order_by(Listing.id.in_(select(documented.c.id)).desc(), Listing.created_at)
        .limit(200)
    ).all()

    picked: list[Listing] = []
    seen_categories: set[str] = set()
    for listing in candidates:
        category = listing.scraped_category or ""
        if category in seen_categories:
            continue
        seen_categories.add(category)
        picked.append(listing)
        if len(picked) == per_store:
            return picked

    # Fewer categories than slots: fill the rest with whatever is left.
    for listing in candidates:
        if len(picked) == per_store:
            break
        if listing not in picked:
            picked.append(listing)
    return picked


def seed(per_store: int, slug: str | None, replace: bool) -> None:
    with Session(engine) as session:
        stmt = select(Dispensary).where(Dispensary.is_active == True)  # noqa: E712
        if slug:
            stmt = stmt.where(Dispensary.slug == slug)
        dispensaries = session.exec(stmt.order_by(Dispensary.name)).all()

        if not dispensaries:
            print("no matching dispensaries", file=sys.stderr)
            raise SystemExit(1)

        for dispensary in dispensaries:
            existing = session.exec(
                select(FeaturedListing).where(FeaturedListing.dispensary_id == dispensary.id)
            ).all()

            if existing and not replace:
                print(f"{dispensary.name}: {len(existing)} already featured, left alone")
                continue
            for row in existing:
                session.delete(row)

            picks = pick_for(session, dispensary.id, per_store)
            if not picks:
                print(f"{dispensary.name}: nothing presentable to feature")
                continue

            for position, listing in enumerate(picks):
                session.add(FeaturedListing(
                    dispensary_id=dispensary.id,
                    listing_id=listing.id,
                    position=position,
                    note="seeded default",
                ))
            session.commit()
            print(f"{dispensary.name}: featured {len(picks)} "
                  f"({', '.join(p.scraped_category or '?' for p in picks)})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-store", type=int, default=4,
                        help="how many to feature per store (default: 4, one 2x2 screen)")
    parser.add_argument("--dispensary", help="slug of a single store to seed")
    parser.add_argument("--replace", action="store_true",
                        help="discard a store's existing picks instead of skipping it")
    args = parser.parse_args()

    seed(per_store=args.per_store, slug=args.dispensary, replace=args.replace)


if __name__ == "__main__":
    main()
