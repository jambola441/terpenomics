"""Pickup orders placed from the customer portal.

These live under /me rather than /customer because they are authenticated. The
rest of the portal identifies a customer by a UUID in the path, which is fine
for reading a public menu but not for a write that puts goods on hold under
someone's name -- so an order is always resolved from the caller's Supabase
token, and `customer_id` is never accepted from the client.

No money moves here. The customer pays at the counter, so the totals this module
computes are a quote both sides can agree on, not a charge.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field as PydField
from sqlmodel import Session, select

from database import get_session
from models import (
    Customer,
    Dispensary,
    Listing,
    Order,
    OrderItem,
    OrderStatus,
    utcnow,
)
from routes_me import get_current_customer
from services.display_name import compose as compose_display_name


def _display_name(listing: Listing) -> str:
    """What this listing is called on screen, for the order snapshot.

    The snapshot is what the customer reads back and what the counter hands
    over, so it carries the name they ordered under rather than the store's
    catalogue string. `listing_id` keeps the lineage either way.
    """
    return compose_display_name(
        scraped_name=listing.scraped_name,
        brand=listing.scraped_brand,
        product_line=listing.product_line,
        strain=listing.strain,
        subtype=listing.subtype,
        category=listing.scraped_category,
    )

router = APIRouter(prefix="/me/orders", tags=["orders"])

# Ambiguous glyphs removed: this gets read aloud at a counter and copied off a
# phone screen, so 0/O and 1/I/L would cost more than the entropy they add.
_PICKUP_ALPHABET = "ACDEFGHJKMNPQRTUVWXY2346789"
_PICKUP_CODE_LEN = 6

MAX_LINES = 40
MAX_QTY_PER_LINE = 12
MAX_OPEN_ORDERS = 5


def _new_pickup_code(session: Session) -> str:
    """A code that is unique among orders still awaiting collection.

    Codes are only ever disambiguated against open orders, so they recycle once
    an order closes. Collisions are checked rather than assumed away.
    """
    open_states = (OrderStatus.submitted, OrderStatus.ready)
    for _ in range(20):
        code = "".join(secrets.choice(_PICKUP_ALPHABET) for _ in range(_PICKUP_CODE_LEN))
        clash = session.exec(
            select(Order.id)
            .where(Order.pickup_code == code)
            .where(Order.status.in_(open_states))
        ).first()
        if not clash:
            return code
    raise HTTPException(status_code=503, detail="Could not allocate a pickup code")


# ---------------------------
# Serialization
# ---------------------------

def serialize_order(order: Order, dispensary: Optional[Dispensary] = None) -> dict:
    d = dispensary or order.dispensary
    return {
        "id": str(order.id),
        "status": order.status,
        "pickup_code": order.pickup_code,
        "total_amount_cents": order.total_amount_cents,
        "note": order.note,
        "submitted_at": order.submitted_at.isoformat(),
        "ready_at": order.ready_at.isoformat() if order.ready_at else None,
        "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        "dispensary_id": str(order.dispensary_id),
        "dispensary_name": d.name if d else None,
        "dispensary_slug": d.slug if d else None,
        "dispensary_address": d.address if d else None,
        # Payment is always at the counter. Stated on the record rather than
        # implied, so a client never has to hardcode the assumption.
        "payment_method": "pay_at_pickup",
        "items": [
            {
                "id": str(i.id),
                "listing_id": str(i.listing_id) if i.listing_id else None,
                "name": i.name,
                "brand": i.brand,
                "variant": i.variant,
                "image_url": i.image_url,
                "quantity": i.quantity,
                "unit_price_cents": i.unit_price_cents,
                "line_amount_cents": i.line_amount_cents,
            }
            for i in sorted(order.items, key=lambda x: x.name)
        ],
    }


# ---------------------------
# POST /me/orders
# ---------------------------

class OrderLineCreate(BaseModel):
    listing_id: UUID
    quantity: int = PydField(default=1, ge=1, le=MAX_QTY_PER_LINE)


class OrderCreate(BaseModel):
    dispensary_id: UUID
    items: list[OrderLineCreate] = PydField(min_length=1, max_length=MAX_LINES)
    note: Optional[str] = PydField(default=None, max_length=500)


@router.post("", status_code=201)
def create_order(
    payload: OrderCreate,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    dispensary = session.get(Dispensary, payload.dispensary_id)
    if not dispensary or not dispensary.is_active:
        raise HTTPException(status_code=404, detail="Dispensary not found")
    if not dispensary.accepts_pickup:
        raise HTTPException(
            status_code=409,
            detail="This dispensary is not accepting pickup orders",
        )

    # One order per store. The cart is single-dispensary by construction in the
    # UI, but the endpoint cannot assume the UI is the only caller.
    merged: dict[UUID, int] = {}
    for line in payload.items:
        merged[line.listing_id] = merged.get(line.listing_id, 0) + line.quantity
    for listing_id, qty in merged.items():
        if qty > MAX_QTY_PER_LINE:
            raise HTTPException(
                status_code=422,
                detail=f"Quantity for listing {listing_id} exceeds {MAX_QTY_PER_LINE}",
            )

    open_count = len(session.exec(
        select(Order.id)
        .where(Order.customer_id == customer.id)
        .where(Order.status.in_((OrderStatus.submitted, OrderStatus.ready)))
    ).all())
    if open_count >= MAX_OPEN_ORDERS:
        raise HTTPException(
            status_code=429,
            detail="You have too many orders awaiting pickup",
        )

    listings = session.exec(
        select(Listing).where(Listing.id.in_(list(merged.keys())))
    ).all()
    by_id = {l.id: l for l in listings}

    missing = [str(lid) for lid in merged if lid not in by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown listing(s): {', '.join(sorted(missing))}",
        )

    # Price is taken from the listing, never from the request. A client that
    # sends its own totals is ignored -- the store's number is the only one that
    # can be honored at the counter.
    order_items: list[OrderItem] = []
    total = 0
    for listing_id, qty in merged.items():
        listing = by_id[listing_id]
        if listing.dispensary_id != dispensary.id:
            raise HTTPException(
                status_code=422,
                detail="All items must come from the same dispensary",
            )
        if not listing.is_active or not listing.in_stock:
            raise HTTPException(
                status_code=409,
                detail=f"{_display_name(listing)} is no longer available",
            )

        unit = listing.price_cents
        line_total = (unit or 0) * qty
        total += line_total
        order_items.append(OrderItem(
            listing_id=listing.id,
            quantity=qty,
            unit_price_cents=unit,
            line_amount_cents=line_total,
            name=_display_name(listing),
            brand=listing.scraped_brand,
            variant=listing.variant,
            image_url=listing.image_url,
        ))

    order = Order(
        customer_id=customer.id,
        dispensary_id=dispensary.id,
        status=OrderStatus.submitted,
        pickup_code=_new_pickup_code(session),
        total_amount_cents=total,
        note=(payload.note or "").strip() or None,
        items=order_items,
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    return serialize_order(order, dispensary)


# ---------------------------
# GET /me/orders
# ---------------------------

@router.get("")
def list_my_orders(
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows = session.exec(
        select(Order, Dispensary)
        .join(Dispensary, Dispensary.id == Order.dispensary_id)
        .where(Order.customer_id == customer.id)
        .order_by(Order.submitted_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [serialize_order(order, dispensary) for order, dispensary in rows]


# ---------------------------
# GET /me/orders/{order_id}
# ---------------------------

@router.get("/{order_id}")
def get_my_order(
    order_id: UUID,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    # Someone else's order is reported as missing rather than forbidden: an
    # order id should not be a way to probe for which ids exist.
    if not order or order.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Order not found")
    return serialize_order(order)


# ---------------------------
# POST /me/orders/{order_id}/cancel
# ---------------------------

@router.post("/{order_id}/cancel")
def cancel_my_order(
    order_id: UUID,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    if not order or order.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status in (OrderStatus.completed, OrderStatus.cancelled):
        raise HTTPException(
            status_code=409,
            detail=f"Order is already {order.status}",
        )

    now: datetime = utcnow()
    order.status = OrderStatus.cancelled
    order.cancelled_at = now
    order.updated_at = now
    session.add(order)
    session.commit()
    session.refresh(order)
    return serialize_order(order)
