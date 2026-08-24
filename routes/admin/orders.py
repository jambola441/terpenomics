from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import SupabaseAuthUser
from database import get_session
from models import Customer, Dispensary, Order, OrderItem, OrderStatus
from routes.customer.orders import serialize_order
from .auth import require_admin

router = APIRouter()

# Store-side transitions; payment-driven transitions (pending_payment → placed /
# expired) come from BitPay, not from here.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.placed: {OrderStatus.completed, OrderStatus.cancelled},
    OrderStatus.pending_payment: {OrderStatus.cancelled},
}


class OrderStatusUpdate(BaseModel):
    status: Literal["completed", "cancelled"]


@router.get("/orders")
def list_orders(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    status: Optional[OrderStatus] = Query(default=None),
    dispensary_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Order).order_by(Order.created_at.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    if dispensary_id:
        stmt = stmt.where(Order.dispensary_id == dispensary_id)
    orders = session.exec(stmt.offset(offset).limit(limit)).all()
    if not orders:
        return []

    dispensaries = {
        d.id: d for d in session.exec(
            select(Dispensary).where(Dispensary.id.in_({o.dispensary_id for o in orders}))
        ).all()
    }
    customers = {
        c.id: c for c in session.exec(
            select(Customer).where(Customer.id.in_({o.customer_id for o in orders}))
        ).all()
    }
    items_by_order: dict[UUID, list[OrderItem]] = {}
    for item in session.exec(
        select(OrderItem).where(OrderItem.order_id.in_([o.id for o in orders]))
    ).all():
        items_by_order.setdefault(item.order_id, []).append(item)

    result = []
    for o in orders:
        row = serialize_order(o, dispensaries.get(o.dispensary_id), items_by_order.get(o.id, []))
        customer = customers.get(o.customer_id)
        row["customer_id"] = str(o.customer_id)
        row["customer_name"] = customer.name if customer else None
        row["customer_email"] = customer.email if customer else None
        result.append(row)
    return result


@router.get("/orders/{order_id}")
def get_order(
    order_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    dispensary = session.get(Dispensary, order.dispensary_id)
    items = list(session.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all())
    row = serialize_order(order, dispensary, items)
    customer = session.get(Customer, order.customer_id)
    row["customer_id"] = str(order.customer_id)
    row["customer_name"] = customer.name if customer else None
    row["customer_email"] = customer.email if customer else None
    return row


@router.post("/orders/{order_id}/status")
def update_order_status(
    order_id: UUID,
    payload: OrderStatusUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    target = OrderStatus(payload.status)
    if target not in ALLOWED_TRANSITIONS.get(order.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"cannot move order from {order.status} to {target}",
        )

    order.status = target
    order.updated_at = datetime.utcnow()
    session.add(order)
    session.commit()
    session.refresh(order)

    dispensary = session.get(Dispensary, order.dispensary_id)
    items = list(session.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all())
    return serialize_order(order, dispensary, items)
