# routes_me.py
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlmodel import Session, select

from auth import SupabaseAuthUser, get_current_user
from database import get_session
from models import Customer, Dispensary, Listing, PreferredDispensary, Purchase
from services import feed as feed_rails
from services.display_name import compose as compose_display_name
from services.feed import RailItem

router = APIRouter(prefix="/me", tags=["me"])


# ---------------------------
# Helpers
# ---------------------------

def get_current_customer(
    user: SupabaseAuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Customer:
    try:
        auth_user_id = UUID(user.user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid auth user id")

    customer = session.exec(
        select(Customer).where(Customer.auth_user_id == auth_user_id)
    ).first()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not linked. Call /me/link-customer first.",
        )

    return customer


# ---------------------------
# Link customer endpoint
# ---------------------------

class LinkCustomerRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    marketing_opt_in: Optional[bool] = None


@router.post("/link-customer")
def link_customer(
    payload: LinkCustomerRequest,
    user: SupabaseAuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        auth_user_id = UUID(user.user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Supabase user_id is not a UUID")

    existing_link = session.exec(
        select(Customer).where(Customer.auth_user_id == auth_user_id)
    ).first()

    if existing_link:
        return {"customer_id": str(existing_link.id), "linked": True}

    phone = (payload.phone or user.phone or "").strip() or None
    email = (payload.email or user.email or "").strip().lower() or None

    if not phone and not email:
        raise HTTPException(status_code=400, detail="Provide phone or email")

    customer = None
    if phone:
        customer = session.exec(select(Customer).where(Customer.phone == phone)).first()
    if not customer and email:
        customer = session.exec(select(Customer).where(Customer.email == email)).first()

    if customer:
        if customer.auth_user_id and customer.auth_user_id != auth_user_id:
            raise HTTPException(status_code=409, detail="Customer already linked")

        customer.auth_user_id = auth_user_id
        if payload.name and not customer.name:
            customer.name = payload.name
        if payload.marketing_opt_in is not None:
            customer.marketing_opt_in = payload.marketing_opt_in
        customer.last_visit_at = customer.last_visit_at or datetime.utcnow()
        customer.updated_at = datetime.utcnow()

        session.add(customer)
        session.commit()
        session.refresh(customer)
        return {"customer_id": str(customer.id), "linked": True, "created": False}

    new_customer = Customer(
        name=payload.name,
        phone=phone,
        email=email,
        auth_user_id=auth_user_id,
        marketing_opt_in=bool(payload.marketing_opt_in)
        if payload.marketing_opt_in is not None
        else False,
        last_visit_at=datetime.utcnow(),
    )
    session.add(new_customer)
    session.commit()
    session.refresh(new_customer)
    return {"customer_id": str(new_customer.id), "linked": True, "created": True}


# ---------------------------
# GET /me — customer profile
# ---------------------------

def _serialize_customer(customer: Customer) -> dict:
    return {
        "id": str(customer.id),
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "marketing_opt_in": customer.marketing_opt_in,
    }


@router.get("")
def get_me(customer: Customer = Depends(get_current_customer)):
    return _serialize_customer(customer)


class UpdateMeRequest(BaseModel):
    name: Optional[str] = None
    marketing_opt_in: Optional[bool] = None


@router.post("")
def update_me(
    payload: UpdateMeRequest,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    """What the customer may change about themselves.

    Phone and email are deliberately not here: they are how the account is
    identified at sign-in and how a walk-in purchase is matched back to a
    person, so changing either is an identity change rather than a profile edit.
    """
    if payload.name is not None:
        name = payload.name.strip()
        customer.name = name or None
    if payload.marketing_opt_in is not None:
        customer.marketing_opt_in = payload.marketing_opt_in

    customer.updated_at = datetime.utcnow()
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return _serialize_customer(customer)


# ---------------------------
# GET /me/purchases
# ---------------------------

@router.get("/purchases")
def get_my_purchases(
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    purchases = session.exec(
        select(Purchase).where(Purchase.customer_id == customer.id)
    ).all()

    return [
        {
            "id": str(p.id),
            "purchased_at": p.purchased_at,
            "total_amount_cents": p.total_amount_cents,
            "source": p.source,
        }
        for p in purchases
    ]


# ---------------------------
# GET /me/preferences (placeholder)
# ---------------------------

@router.get("/preferences")
def get_preferences(customer: Customer = Depends(get_current_customer)):
    """
    Placeholder until terpene scoring is implemented.
    """
    return {
        "top_terpenes": [],
        "message": "Preference scoring not implemented yet"
    }


# ---------------------------
# Preferred dispensaries
# ---------------------------

def _serialize_dispensary(d: Dispensary) -> dict:
    return {
        "id": str(d.id),
        "name": d.name,
        "slug": d.slug,
        "address": d.address,
        "lat": d.lat,
        "lng": d.lng,
        "website_url": d.website_url,
        "accepts_pickup": d.accepts_pickup,
        "logo_url": d.logo_url,
        "banner_url": d.banner_url,
    }


def _preferred_dispensaries(session: Session, customer_id: UUID) -> List[Dispensary]:
    """The customer's followed stores, in the order they followed them."""
    rows = session.exec(
        select(Dispensary)
        .join(PreferredDispensary, PreferredDispensary.dispensary_id == Dispensary.id)
        .where(PreferredDispensary.customer_id == customer_id)
        .where(Dispensary.is_active == True)  # noqa: E712
        .order_by(PreferredDispensary.created_at)
    ).all()
    return list(rows)


@router.get("/preferred-dispensaries")
def list_preferred_dispensaries(
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    return [_serialize_dispensary(d) for d in _preferred_dispensaries(session, customer.id)]


@router.post("/preferred-dispensaries/{dispensary_id}")
def add_preferred_dispensary(
    dispensary_id: UUID,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    dispensary = session.get(Dispensary, dispensary_id)
    if not dispensary or not dispensary.is_active:
        raise HTTPException(status_code=404, detail="dispensary not found")

    existing = session.get(PreferredDispensary, (customer.id, dispensary_id))
    if not existing:
        session.add(PreferredDispensary(customer_id=customer.id, dispensary_id=dispensary_id))
        session.commit()

    return [_serialize_dispensary(d) for d in _preferred_dispensaries(session, customer.id)]


@router.delete("/preferred-dispensaries/{dispensary_id}")
def remove_preferred_dispensary(
    dispensary_id: UUID,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    existing = session.get(PreferredDispensary, (customer.id, dispensary_id))
    if existing:
        session.delete(existing)
        session.commit()

    return [_serialize_dispensary(d) for d in _preferred_dispensaries(session, customer.id)]


# ---------------------------
# GET /me/feed — the multi-dispensary home feed
# ---------------------------

RAILS = ("featured", "new", "recommended", "deals")


def _serialize_rail_item(item: RailItem, *, with_store: bool) -> dict:
    listing = item.listing
    payload = {
        "id": str(listing.id),
        "display_name": compose_display_name(
            scraped_name=listing.scraped_name,
            brand=listing.scraped_brand,
            product_line=listing.product_line,
            strain=listing.strain,
            subtype=listing.subtype,
            category=listing.scraped_category,
        ),
        "scraped_name": listing.scraped_name,
        "scraped_brand": listing.scraped_brand,
        "scraped_category": listing.scraped_category,
        "subtype": listing.subtype,
        "strain": listing.strain,
        "product_line": listing.product_line,
        "price_cents": listing.price_cents,
        "variant": listing.variant,
        "url": listing.url,
        "image_url": listing.image_url,
        "in_stock": listing.in_stock,
        # What the ranking knew. Absent facts are zero/None rather than missing
        # keys, so the card renders the same shape in every rail.
        "other_store_count": item.other_store_count,
        "other_avg_cents": item.other_avg_cents,
        "saving_cents": item.saving_cents,
    }
    if with_store:
        # The combined view mixes stores, so each card has to say where it is.
        payload["dispensary_id"] = str(listing.dispensary_id)
    return payload


def _product_key(listing: Listing) -> tuple:
    return (
        listing.scraped_brand,
        listing.scraped_category,
        listing.subtype,
        listing.product_line,
        listing.strain,
        listing.variant,
    )


def _dedupe_to_cheapest(items: List[RailItem]) -> List[RailItem]:
    """One card per product, at whichever followed store sells it cheapest.

    Without this the combined view is mostly the same few products repeated:
    anything stocked at all of a shopper's stores would crowd out everything
    that is only at one. `other_store_count` is reused to say how many of *their*
    stores have it, which is what the card shows.
    """
    best: dict[tuple, RailItem] = {}
    for item in items:
        key = _product_key(item.listing)
        seen = best.get(key)
        if seen is None:
            best[key] = item
            continue
        seen.other_store_count = max(seen.other_store_count, 1) + 1
        cheaper = (
            item.listing.price_cents is not None
            and (seen.listing.price_cents is None or item.listing.price_cents < seen.listing.price_cents)
        )
        if cheaper:
            item.other_store_count = seen.other_store_count
            best[key] = item
    return list(best.values())


def _build_rails(
    session: Session,
    dispensary_ids: List[UUID],
    customer_id: UUID,
    per_rail: int,
    category: Optional[str],
) -> dict:
    rails = {
        "featured": feed_rails.featured(session, dispensary_ids, per_rail),
        "new": feed_rails.new_arrivals(session, dispensary_ids, per_rail),
        "recommended": feed_rails.recommended(session, dispensary_ids, customer_id, per_rail),
        "deals": feed_rails.deals(session, dispensary_ids, per_rail),
    }
    if category:
        # Filtering after ranking keeps each rail's meaning: the newest edibles,
        # not the edibles among the newest of everything.
        rails = {
            name: [i for i in items if i.listing.scraped_category == category]
            for name, items in rails.items()
        }
    return rails


@router.get("/feed")
def get_feed(
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
    view: Literal["store", "combined"] = Query(default="store"),
    per_rail: int = Query(default=8, ge=1, le=24),
    category: Optional[str] = Query(default=None),
):
    """What a shopper should look at across the stores they follow.

    Two shapes of the same four rails. `store` keeps each store separate, which
    is how someone shops when they are picking a place to go to. `combined`
    pools them and dedupes, which is how someone shops when they are looking for
    a product and do not mind which of their stores has it.

    Both are built here rather than on the client because two of the four rails
    -- deals, and the recommendation fallback -- rank against every store we
    track, not just the shopper's.
    """
    dispensaries = _preferred_dispensaries(session, customer.id)
    if not dispensaries:
        return {"view": view, "sections": [], "combined": None, "dispensaries": []}

    dispensary_ids = [d.id for d in dispensaries]
    serialized_stores = [_serialize_dispensary(d) for d in dispensaries]

    if view == "combined":
        # Ranked across the whole followed set, then deduped, so a rail is the
        # best of everything rather than the best of each store in turn.
        rails = _build_rails(session, dispensary_ids, customer.id, per_rail * 2, category)
        return {
            "view": "combined",
            "sections": [],
            "combined": {
                name: [
                    _serialize_rail_item(item, with_store=True)
                    for item in _dedupe_to_cheapest(items)[:per_rail]
                ]
                for name, items in rails.items()
            },
            "dispensaries": serialized_stores,
        }

    sections = []
    for dispensary in dispensaries:
        rails = _build_rails(session, [dispensary.id], customer.id, per_rail, category)

        total_stmt = (
            select(func.count())
            .select_from(Listing)
            .where(Listing.dispensary_id == dispensary.id)
            .where(Listing.is_active == True)  # noqa: E712
            .where(Listing.in_stock == True)  # noqa: E712
        )
        if category:
            total_stmt = total_stmt.where(Listing.scraped_category == category)

        sections.append({
            "dispensary": _serialize_dispensary(dispensary),
            "total": session.exec(total_stmt).one(),
            "rails": {
                name: [_serialize_rail_item(item, with_store=False) for item in items]
                for name, items in rails.items()
            },
        })

    return {
        "view": "store",
        "sections": sections,
        "combined": None,
        "dispensaries": serialized_stores,
    }
