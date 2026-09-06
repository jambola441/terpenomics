# services/feed.py
"""The rails the home feed is built from.

Four answers to "what should I look at", each from a different source:

  featured     what the store chose to push -- the one curated rail
  new          what arrived since the shopper last looked
  recommended  what fits what they have bought and rated
  deals        what costs less here than at the other stores carrying it

Deals and the recommendation fallback both lean on the same fact: we can see
the same product at every store we track, and a single store's own menu cannot.
That comparison is the reason to build the feed here rather than on the client,
which would need every store's whole catalogue to compute it.

Each rail returns `Listing` rows with the extra facts its ranking produced, so
the caller can serialize once without re-deriving anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from models import (
    FeaturedListing,
    ItemFeedback,
    Listing,
    Purchase,
    PurchaseItem,
)
from services.market import same_product

# How much of a store's shelf a ranking may scan. A rail shows a handful; this
# bounds what it costs to find them when a store carries thousands of rows.
SCAN_CAP = 400


@dataclass
class RailItem:
    """A listing plus whatever the rail that found it knows about it."""

    listing: Listing
    #: Stores other than this one carrying the same product, and their average
    #: price -- the whole market, not the shopper's own stores.
    market_store_count: int = 0
    other_avg_cents: Optional[int] = None
    #: How many of the shopper's followed stores have this product. Only the
    #: combined view knows it, and only after deduping.
    preferred_store_count: int = 0

    @property
    def saving_cents(self) -> Optional[int]:
        if self.other_avg_cents is None or self.listing.price_cents is None:
            return None
        return self.other_avg_cents - self.listing.price_cents


@dataclass
class TasteProfile:
    """What a shopper's own purchases say they like.

    Weighted rather than boolean: something bought and thumbed up is a stronger
    signal than something merely bought, and something thumbed down is evidence
    against, not the absence of evidence.
    """

    brands: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    strains: dict[str, int] = field(default_factory=dict)
    subtypes: dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.brands or self.categories or self.strains or self.subtypes)

    def score(self, listing: Listing) -> int:
        return (
            self.brands.get(listing.scraped_brand or "", 0) * 3
            + self.strains.get(listing.strain or "", 0) * 3
            + self.subtypes.get(listing.subtype or "", 0) * 2
            + self.categories.get(listing.scraped_category or "", 0)
        )


def _in_stock_at(dispensary_ids: Sequence[UUID]):
    """Rows a shopper could actually walk in and buy today."""
    return (
        select(Listing)
        .where(Listing.dispensary_id.in_(list(dispensary_ids)))
        .where(Listing.is_active == True)  # noqa: E712
        .where(Listing.in_stock == True)  # noqa: E712
    )


# ---------------------------
# Featured -- curated
# ---------------------------

def featured(session: Session, dispensary_ids: Sequence[UUID], limit: int) -> list[RailItem]:
    """What the stores picked, in the order they picked it.

    A pick that has since gone out of stock is dropped rather than shown greyed
    out: the rail is a recommendation to go and buy something.
    """
    if not dispensary_ids:
        return []

    rows = session.exec(
        select(Listing, FeaturedListing.position)
        .join(FeaturedListing, FeaturedListing.listing_id == Listing.id)
        .where(FeaturedListing.dispensary_id.in_(list(dispensary_ids)))
        .where(Listing.is_active == True)  # noqa: E712
        .where(Listing.in_stock == True)  # noqa: E712
        .order_by(FeaturedListing.position, Listing.scraped_name)
        .limit(limit)
    ).all()
    return [RailItem(listing=listing) for listing, _ in rows]


# ---------------------------
# New arrivals -- first seen
# ---------------------------

def new_arrivals(session: Session, dispensary_ids: Sequence[UUID], limit: int) -> list[RailItem]:
    """Newest first, by when we first saw the row.

    `created_at` is set on insert and left alone by the scraper's upsert, so it
    dates the product's arrival on the shelf rather than the last scrape.
    """
    if not dispensary_ids:
        return []

    rows = session.exec(
        _in_stock_at(dispensary_ids)
        .order_by(Listing.created_at.desc(), Listing.id)
        .limit(limit)
    ).all()
    return [RailItem(listing=listing) for listing in rows]


# ---------------------------
# The market, for deals and for popularity
# ---------------------------

def _market_comparison(
    session: Session,
    dispensary_ids: Sequence[UUID],
    limit: int,
    *,
    cheaper_only: bool,
):
    """The stores' listings that other stores also carry, with those stores' prices.

    A self-join on the product's identity, which `services.market` defines for
    every screen that makes this comparison -- a deal here has to mean the same
    thing as "3 other stores" on the menu.
    """
    mine = aliased(Listing)
    other = aliased(Listing)

    avg_other = func.avg(other.price_cents)
    store_count = func.count(func.distinct(other.dispensary_id))

    stmt = (
        select(mine, avg_other.label("avg_other"), store_count.label("store_count"))
        .join(other, and_(other.dispensary_id != mine.dispensary_id, *same_product(mine, other)))
        .where(mine.dispensary_id.in_(list(dispensary_ids)))
        .where(mine.is_active == True)  # noqa: E712
        .where(mine.in_stock == True)  # noqa: E712
        .where(mine.price_cents.isnot(None))
        .where(other.is_active == True)  # noqa: E712
        .where(other.in_stock == True)  # noqa: E712
        .where(other.price_cents.isnot(None))
        .group_by(mine.id)
    )

    if cheaper_only:
        # Strictly cheaper than the average elsewhere -- "the same as everywhere"
        # is not a deal.
        stmt = stmt.having(mine.price_cents < avg_other).order_by((avg_other - mine.price_cents).desc())
    else:
        stmt = stmt.order_by(store_count.desc(), mine.price_cents)

    return session.exec(stmt.limit(limit)).all()


def deals(session: Session, dispensary_ids: Sequence[UUID], limit: int) -> list[RailItem]:
    """Cheaper here than the average at the other stores carrying it.

    The saving is against the average rather than the lowest price elsewhere: a
    single cheap outlier somewhere across town should not make every other store
    look expensive.
    """
    if not dispensary_ids:
        return []

    return [
        RailItem(listing=listing, other_avg_cents=round(avg_other), market_store_count=count)
        for listing, avg_other, count in _market_comparison(
            session, dispensary_ids, limit, cheaper_only=True
        )
    ]


# ---------------------------
# Recommended -- what they bought and liked
# ---------------------------

def taste_profile(session: Session, customer_id: UUID) -> TasteProfile:
    """Read the shopper's purchases back as weights over product attributes."""
    rows = session.exec(
        select(PurchaseItem.feedback, Listing)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(Listing, Listing.id == PurchaseItem.listing_id)
        .where(Purchase.customer_id == customer_id)
    ).all()

    profile = TasteProfile()
    weights = {
        ItemFeedback.like: 3,
        ItemFeedback.neutral: 1,
        ItemFeedback.dislike: -4,
    }

    for feedback, listing in rows:
        # An unrated purchase still says they chose it once.
        weight = weights.get(feedback, 1) if feedback is not None else 1
        for bucket, value in (
            (profile.brands, listing.scraped_brand),
            (profile.categories, listing.scraped_category),
            (profile.strains, listing.strain),
            (profile.subtypes, listing.subtype),
        ):
            if value:
                bucket[value] = bucket.get(value, 0) + weight

    # A single thumbs-down outweighs the purchase that preceded it, which is the
    # point -- but only what stays negative is actually disliked.
    for bucket in (profile.brands, profile.categories, profile.strains, profile.subtypes):
        for key in [k for k, v in bucket.items() if v <= 0]:
            del bucket[key]

    return profile


def recommended(
    session: Session,
    dispensary_ids: Sequence[UUID],
    customer_id: UUID,
    limit: int,
) -> list[RailItem]:
    """What fits this shopper, or what fits everyone if we do not know them yet.

    With no purchases there is nothing personal to say, so the rail falls back to
    the products carried at the most stores -- broad agreement is the best proxy
    available, and it is honest about being one.
    """
    if not dispensary_ids:
        return []

    profile = taste_profile(session, customer_id)
    if profile.is_empty():
        return [
            RailItem(listing=listing, other_avg_cents=round(avg_other), market_store_count=count)
            for listing, avg_other, count in _market_comparison(
                session, dispensary_ids, limit, cheaper_only=False
            )
        ]

    # Pull what could match, then rank in Python: the score weighs four
    # attributes against each other, which SQL would express far less clearly.
    matches = or_(
        Listing.scraped_brand.in_(list(profile.brands)) if profile.brands else False,
        Listing.strain.in_(list(profile.strains)) if profile.strains else False,
        Listing.subtype.in_(list(profile.subtypes)) if profile.subtypes else False,
        Listing.scraped_category.in_(list(profile.categories)) if profile.categories else False,
    )
    candidates = session.exec(
        _in_stock_at(dispensary_ids).where(matches).limit(SCAN_CAP)
    ).all()

    ranked = sorted(
        candidates,
        key=lambda listing: (-profile.score(listing), listing.price_cents or 10**9),
    )
    return [RailItem(listing=listing) for listing in ranked[:limit]]
