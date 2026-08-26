"""Admin view of incoming pickup orders.

This is the fulfillment side of routes/orders.py: staff see what was submitted
and move it through the lifecycle. Nothing here takes payment -- `completed`
means the customer collected the order and paid in store.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func

from auth import SupabaseAuthUser
from database import get_session
from models import (
    Customer,
    Dispensary,
    Order,
    OrderItem,
    ORDER_TRANSITIONS,
    OrderStatus,
    utcnow,
)
from .auth import require_admin

router = APIRouter()

_STATUS_TIMESTAMP = {
    OrderStatus.ready: "ready_at",
    OrderStatus.completed: "completed_at",
    OrderStatus.cancelled: "cancelled_at",
}


@router.get("/orders")
def list_orders(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    status: Optional[Literal["submitted", "ready", "completed", "cancelled"]] = Query(default=None),
    dispensary_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(
            Order.id,
            Order.status,
            Order.pickup_code,
            Order.total_amount_cents,
            Order.note,
            Order.submitted_at,
            Order.dispensary_id,
            Dispensary.name,
            Customer.id,
            Customer.name,
            Customer.phone,
            func.count(OrderItem.id).label("item_count"),
        )
        .select_from(Order)
        .join(Dispensary, Dispensary.id == Order.dispensary_id)
        .join(Customer, Customer.id == Order.customer_id)
        .join(OrderItem, OrderItem.order_id == Order.id, isouter=True)
        .group_by(
            Order.id, Order.status, Order.pickup_code, Order.total_amount_cents,
            Order.note, Order.submitted_at, Order.dispensary_id,
            Dispensary.name, Customer.id, Customer.name, Customer.phone,
        )
    )
    if status:
        stmt = stmt.where(Order.status == status)
    if dispensary_id:
        stmt = stmt.where(Order.dispensary_id == dispensary_id)

    # Open orders first -- staff are working a queue, not browsing history.
    rows = session.exec(
        stmt.order_by(Order.submitted_at.desc()).offset(offset).limit(limit)
    ).all()

    return [
        {
            "id": str(oid),
            "status": ostatus,
            "pickup_code": code,
            "total_amount_cents": total,
            "note": note,
            "submitted_at": submitted_at.isoformat(),
            "dispensary_id": str(disp_id),
            "dispensary_name": disp_name,
            "customer_id": str(cust_id),
            "customer_name": cust_name,
            "customer_phone": cust_phone,
            "item_count": item_count,
        }
        for (oid, ostatus, code, total, note, submitted_at, disp_id,
             disp_name, cust_id, cust_name, cust_phone, item_count) in rows
    ]


@router.get("/orders/{order_id}")
def get_order(
    order_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    dispensary = session.get(Dispensary, order.dispensary_id)
    customer = session.get(Customer, order.customer_id)

    return {
        "id": str(order.id),
        "status": order.status,
        "pickup_code": order.pickup_code,
        "total_amount_cents": order.total_amount_cents,
        "note": order.note,
        "payment_method": "pay_at_pickup",
        "submitted_at": order.submitted_at.isoformat(),
        "ready_at": order.ready_at.isoformat() if order.ready_at else None,
        "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        "dispensary_id": str(order.dispensary_id),
        "dispensary_name": dispensary.name if dispensary else None,
        "customer_id": str(order.customer_id),
        "customer_name": customer.name if customer else None,
        "customer_phone": customer.phone if customer else None,
        "customer_email": customer.email if customer else None,
        "allowed_transitions": sorted(ORDER_TRANSITIONS[order.status]),
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


class OrderStatusUpdate(BaseModel):
    status: Literal["ready", "completed", "cancelled"]


@router.post("/orders/{order_id}/status")
def set_order_status(
    order_id: UUID,
    payload: OrderStatusUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    target = OrderStatus(payload.status)
    allowed = ORDER_TRANSITIONS[order.status]
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot move an order from {order.status} to {target}"
                + (f"; allowed: {', '.join(sorted(allowed))}" if allowed else " (terminal state)")
            ),
        )

    now = utcnow()
    order.status = target
    setattr(order, _STATUS_TIMESTAMP[target], now)
    order.updated_at = now
    session.add(order)
    session.commit()
    session.refresh(order)

    return get_order(order_id, session=session, _=_)
