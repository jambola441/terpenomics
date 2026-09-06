# services/market.py
"""What the same product costs at the other stores.

The one thing this system knows that a dispensary's own menu cannot: we see
every store's shelf at once, so we can say whether the price in front of a
shopper is a good one. Three screens ask that question in three shapes -- the
deals rail asks "what is cheap here", a listing asks "where else is this and
for how much", a menu asks it of a hundred rows at a time -- but they must all
mean the same thing by "the same product", or a card and the page it opens will
disagree about how many stores carry it.

That definition lives here, once: `same_product`. `context_for` is the bulk
answer, one aggregate query for a whole page of listings rather than a query
per row.
"""
from __future__ import annotations

from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from models import Dispensary, Listing

# A product's identity, as the portal keys it everywhere else -- the five-part
# key the product page is addressed by, plus the brand. Two rows matching on
# all six are the same thing on two shelves.
KEY_COLUMNS = ("scraped_category", "subtype", "product_line", "strain", "variant")
IDENTITY_COLUMNS = KEY_COLUMNS + ("scraped_brand",)


def same_product(mine, other) -> list:
    """Join conditions matching two listing aliases on product identity.

    Every identity column is nullable and SQL will not match NULL to NULL, so
    each side is coalesced -- the same trick the listings uniqueness index uses.
    Without it an unbranded product, or one with no subtype, would look unique
    to every other row including its own twin across town.
    """
    return [
        func.coalesce(getattr(mine, column), "") == func.coalesce(getattr(other, column), "")
        for column in IDENTITY_COLUMNS
    ]


def context_for(session: Session, listing_ids: Sequence[UUID]) -> dict[str, dict]:
    """For each listing, how its price stands against the other stores carrying it.

    One query for the whole page. Keyed by listing id as a string, and a listing
    nobody else carries is simply absent -- the caller decides what to say about
    that, since "only here" reads differently on a menu than on a product page.

    Only stores a shopper could actually buy from count: active stores, active
    listings, in stock, priced. An out-of-stock row somewhere is not an
    alternative, and an unpriced one cannot be compared.
    """
    if not listing_ids:
        return {}

    mine = aliased(Listing)
    other = aliased(Listing)

    stmt = (
        select(
            mine.id,
            mine.price_cents,
            func.count(func.distinct(other.dispensary_id)).label("stores"),
            func.min(other.price_cents).label("min_cents"),
            func.avg(other.price_cents).label("avg_cents"),
            func.max(other.price_cents).label("max_cents"),
        )
        .join(
            other,
            and_(other.dispensary_id != mine.dispensary_id, *same_product(mine, other)),
        )
        .join(Dispensary, Dispensary.id == other.dispensary_id)
        .where(mine.id.in_(list(listing_ids)))
        .where(other.is_active == True)  # noqa: E712
        .where(other.in_stock == True)  # noqa: E712
        .where(other.price_cents.isnot(None))
        .where(Dispensary.is_active == True)  # noqa: E712
        .group_by(mine.id, mine.price_cents)
    )

    context: dict[str, dict] = {}
    for listing_id, price_cents, stores, min_cents, avg_cents, max_cents in session.exec(stmt).all():
        context[str(listing_id)] = {
            "other_store_count": stores,
            "min_cents": min_cents,
            "avg_cents": round(avg_cents) if avg_cents is not None else None,
            "max_cents": max_cents,
            # A row with no price of its own is not the cheapest, it is
            # uncomparable; saying "best price" about it would be a guess.
            "is_cheapest": price_cents is not None and min_cents is not None and price_cents <= min_cents,
        }
    return context


def empty_context() -> dict:
    """What a product nobody else carries looks like.

    Spelled out rather than left to the client, so every screen renders the
    no-comparison case the same way.
    """
    return {
        "other_store_count": 0,
        "min_cents": None,
        "avg_cents": None,
        "max_cents": None,
        "is_cheapest": False,
    }


def context_or_empty(context: dict[str, dict], listing_ids: Iterable[UUID]) -> dict[str, dict]:
    """`context_for`'s answer, filled in for the listings it had nothing to say about."""
    return {str(lid): context.get(str(lid), empty_context()) for lid in listing_ids}
