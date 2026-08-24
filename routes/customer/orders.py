from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field as PydField
from sqlmodel import Session, select

from database import get_session
from models import (
    Customer, Dispensary, Listing,
    Order, OrderItem, OrderPaymentMethod, OrderStatus,
)
from services import bitpay

router = APIRouter()

CANCELLABLE = {OrderStatus.pending_payment, OrderStatus.placed}


# ---------------------------
# Serialization
# ---------------------------

def serialize_order(order: Order, dispensary: Optional[Dispensary], items: list[OrderItem]) -> dict:
    out = {
        "id": str(order.id),
        "status": order.status,
        "payment_method": order.payment_method,
        "total_cents": order.total_cents,
        "pickup_name": order.pickup_name,
        "notes": order.notes,
        "created_at": order.created_at.isoformat(),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "dispensary_id": str(order.dispensary_id),
        "dispensary_name": dispensary.name if dispensary else None,
        "dispensary_slug": dispensary.slug if dispensary else None,
        "dispensary_address": dispensary.address if dispensary else None,
        "items": [
            {
                "id": str(i.id),
                "listing_id": str(i.listing_id),
                "name": i.product_name,
                "variant": i.variant,
                "image_url": i.image_url,
                "quantity": i.quantity,
                "unit_price_cents": i.unit_price_cents,
                "line_total_cents": i.line_total_cents,
            }
            for i in items
        ],
    }
    if order.payment_method == OrderPaymentMethod.bitpay:
        out["bitpay"] = {
            "invoice_id": order.bitpay_invoice_id,
            "invoice_url": order.bitpay_invoice_url,
            "invoice_status": order.bitpay_status,
        }
    return out


def _get_order_for_customer(session: Session, customer_id: UUID, order_id: UUID) -> Order:
    order = session.exec(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.customer_id == customer_id)
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    return order


def _order_items(session: Session, order_id: UUID) -> list[OrderItem]:
    return list(session.exec(
        select(OrderItem).where(OrderItem.order_id == order_id)
    ).all())


def _apply_invoice_status(order: Order, invoice_status: Optional[str]) -> None:
    """Map a BitPay invoice status onto the order. Only moves forward from
    pending_payment — a cancelled/completed order is never resurrected."""
    if not invoice_status:
        return
    order.bitpay_status = invoice_status
    if order.status != OrderStatus.pending_payment:
        return
    if invoice_status in bitpay.PAID_STATUSES:
        order.status = OrderStatus.placed
        order.paid_at = order.paid_at or datetime.now(timezone.utc)
    elif invoice_status in bitpay.DEAD_STATUSES:
        order.status = OrderStatus.expired


# ---------------------------
# POST /orders/bitpay/ipn  (BitPay webhook — no customer scoping)
# ---------------------------

@router.post("/orders/bitpay/ipn")
async def bitpay_ipn(request: Request, session: Session = Depends(get_session)):
    """BitPay instant payment notification. The IPN body is untrusted — we only
    take the invoice id from it and re-fetch the invoice from BitPay."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    data = body.get("data") if isinstance(body, dict) else None
    invoice_id = (data or body or {}).get("id") if isinstance(data or body, dict) else None
    if not invoice_id or not isinstance(invoice_id, str):
        raise HTTPException(status_code=400, detail="missing invoice id")

    order = session.exec(
        select(Order).where(Order.bitpay_invoice_id == invoice_id)
    ).first()
    if not order:
        # Unknown invoice — acknowledge so BitPay stops retrying
        return {"ok": True, "known": False}

    try:
        invoice = bitpay.get_invoice(invoice_id)
    except bitpay.BitPayError:
        raise HTTPException(status_code=502, detail="failed to verify invoice with BitPay")

    _apply_invoice_status(order, invoice.get("status"))
    order.updated_at = datetime.utcnow()
    session.add(order)
    session.commit()
    return {"ok": True, "known": True, "status": order.status}


# ---------------------------
# POST /{customer_id}/orders — checkout
# ---------------------------

class OrderItemCreate(BaseModel):
    listing_id: UUID
    quantity: int = PydField(default=1, ge=1, le=99)


class OrderCreate(BaseModel):
    dispensary_id: UUID
    payment_method: Literal["bitpay", "in_store"]
    items: list[OrderItemCreate] = PydField(min_length=1)
    pickup_name: Optional[str] = PydField(default=None, max_length=200)
    notes: Optional[str] = PydField(default=None, max_length=2000)
    # Origin the frontend wants BitPay to send the buyer back to after payment;
    # the server appends /portal/orders/{order_id}.
    redirect_origin: Optional[str] = PydField(default=None, max_length=500)


@router.post("/{customer_id}/orders", status_code=201)
def create_order(
    customer_id: UUID,
    payload: OrderCreate,
    session: Session = Depends(get_session),
):
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")

    dispensary = session.get(Dispensary, payload.dispensary_id)
    if not dispensary or not dispensary.is_active:
        raise HTTPException(status_code=404, detail="dispensary not found")
    if not dispensary.accepts_pickup:
        raise HTTPException(status_code=400, detail="dispensary does not support online orders")

    # Collapse duplicate listings into one line each
    quantities: dict[UUID, int] = {}
    for item in payload.items:
        quantities[item.listing_id] = quantities.get(item.listing_id, 0) + item.quantity

    listings = session.exec(
        select(Listing).where(Listing.id.in_(list(quantities.keys())))
    ).all()
    by_id = {l.id: l for l in listings}

    problems: list[str] = []
    for lid in quantities:
        listing = by_id.get(lid)
        if not listing or not listing.is_active or listing.dispensary_id != payload.dispensary_id:
            problems.append(f"listing {lid} is not available at this dispensary")
        elif not listing.in_stock:
            problems.append(f"{listing.scraped_name or lid} is out of stock")
        elif payload.payment_method == "bitpay" and listing.price_cents is None:
            problems.append(f"{listing.scraped_name or lid} has no price and cannot be paid online")
    if problems:
        raise HTTPException(status_code=400, detail="; ".join(problems))

    method = OrderPaymentMethod(payload.payment_method)
    if method == OrderPaymentMethod.bitpay and not bitpay.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Crypto payment is not available right now — choose pay in store",
        )

    order = Order(
        customer_id=customer_id,
        dispensary_id=payload.dispensary_id,
        payment_method=method,
        status=OrderStatus.placed if method == OrderPaymentMethod.in_store else OrderStatus.pending_payment,
        pickup_name=(payload.pickup_name or customer.name or None),
        notes=payload.notes,
    )

    total = 0
    order_items: list[OrderItem] = []
    for lid, qty in quantities.items():
        listing = by_id[lid]
        line_total = listing.price_cents * qty if listing.price_cents is not None else None
        if line_total is not None:
            total += line_total
        order_items.append(OrderItem(
            order_id=order.id,
            listing_id=lid,
            quantity=qty,
            unit_price_cents=listing.price_cents,
            line_total_cents=line_total,
            product_name=listing.scraped_name,
            variant=listing.variant,
            image_url=listing.image_url,
        ))
    order.total_cents = total

    if method == OrderPaymentMethod.bitpay:
        if total <= 0:
            raise HTTPException(status_code=400, detail="order total must be positive for crypto payment")
        redirect_url = None
        if payload.redirect_origin:
            redirect_url = f"{payload.redirect_origin.rstrip('/')}/portal/orders/{order.id}"
        try:
            invoice = bitpay.create_invoice(
                price_cents=total,
                order_id=str(order.id),
                buyer_email=customer.email,
                redirect_url=redirect_url,
            )
        except bitpay.BitPayNotConfigured:
            raise HTTPException(status_code=503, detail="Crypto payment is not available right now")
        except bitpay.BitPayError:
            raise HTTPException(status_code=502, detail="Failed to create BitPay invoice — try pay in store")
        order.bitpay_invoice_id = invoice["id"]
        order.bitpay_invoice_url = invoice["url"]
        order.bitpay_status = invoice["status"]

    session.add(order)
    for item in order_items:
        session.add(item)
    session.commit()
    session.refresh(order)

    result = serialize_order(order, dispensary, order_items)
    # Where the frontend should send the buyer to pay (bitpay only)
    result["checkout_url"] = order.bitpay_invoice_url
    return result


# ---------------------------
# GET /{customer_id}/orders
# ---------------------------

@router.get("/{customer_id}/orders")
def list_orders(
    customer_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if not session.get(Customer, customer_id):
        raise HTTPException(status_code=404, detail="customer not found")

    orders = session.exec(
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    if not orders:
        return []

    dispensaries = {
        d.id: d for d in session.exec(
            select(Dispensary).where(Dispensary.id.in_({o.dispensary_id for o in orders}))
        ).all()
    }
    items_by_order: dict[UUID, list[OrderItem]] = {}
    for item in session.exec(
        select(OrderItem).where(OrderItem.order_id.in_([o.id for o in orders]))
    ).all():
        items_by_order.setdefault(item.order_id, []).append(item)

    return [
        serialize_order(o, dispensaries.get(o.dispensary_id), items_by_order.get(o.id, []))
        for o in orders
    ]


# ---------------------------
# GET /{customer_id}/orders/{order_id}
# ---------------------------

@router.get("/{customer_id}/orders/{order_id}")
def get_order(
    customer_id: UUID,
    order_id: UUID,
    session: Session = Depends(get_session),
):
    order = _get_order_for_customer(session, customer_id, order_id)
    dispensary = session.get(Dispensary, order.dispensary_id)
    return serialize_order(order, dispensary, _order_items(session, order.id))


# ---------------------------
# POST /{customer_id}/orders/{order_id}/refresh-payment
# ---------------------------

@router.post("/{customer_id}/orders/{order_id}/refresh-payment")
def refresh_order_payment(
    customer_id: UUID,
    order_id: UUID,
    session: Session = Depends(get_session),
):
    """Poll BitPay for the invoice status. Fallback for when the IPN webhook
    isn't reachable (e.g. local dev); the order status view calls this while
    the order is pending_payment."""
    order = _get_order_for_customer(session, customer_id, order_id)

    if order.payment_method == OrderPaymentMethod.bitpay and \
            order.status == OrderStatus.pending_payment and order.bitpay_invoice_id:
        try:
            invoice = bitpay.get_invoice(order.bitpay_invoice_id)
        except bitpay.BitPayError:
            invoice = None  # keep current state; the client will retry
        if invoice:
            _apply_invoice_status(order, invoice.get("status"))
            order.updated_at = datetime.utcnow()
            session.add(order)
            session.commit()
            session.refresh(order)

    dispensary = session.get(Dispensary, order.dispensary_id)
    return serialize_order(order, dispensary, _order_items(session, order.id))


# ---------------------------
# POST /{customer_id}/orders/{order_id}/cancel
# ---------------------------

@router.post("/{customer_id}/orders/{order_id}/cancel")
def cancel_order(
    customer_id: UUID,
    order_id: UUID,
    session: Session = Depends(get_session),
):
    order = _get_order_for_customer(session, customer_id, order_id)
    if order.status not in CANCELLABLE:
        raise HTTPException(status_code=409, detail=f"order is {order.status} and cannot be cancelled")

    # NOTE: paid crypto orders reach `placed`; cancelling one does not refund it
    # automatically — refunds go through the BitPay dashboard for now.
    order.status = OrderStatus.cancelled
    order.updated_at = datetime.utcnow()
    session.add(order)
    session.commit()
    session.refresh(order)

    dispensary = session.get(Dispensary, order.dispensary_id)
    return serialize_order(order, dispensary, _order_items(session, order.id))
