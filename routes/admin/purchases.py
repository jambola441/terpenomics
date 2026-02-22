from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field as PydField
from sqlmodel import Session, select, func, or_

from auth import SupabaseAuthUser
from database import get_session
from models import Customer, Product, Purchase, PurchaseItem
from .auth import require_admin
from .serializers import serialize_purchase

router = APIRouter()


class PurchaseCreate(BaseModel):
    customer_id: UUID
    purchased_at: Optional[datetime] = None
    source: Literal["manual", "pos_import"] = "manual"
    external_id: Optional[str] = None
    notes: Optional[str] = None


class PurchaseItemAdd(BaseModel):
    product_id: UUID
    quantity: int = PydField(default=1, ge=1, le=100)
    line_amount_cents: int = PydField(ge=0)
    external_id: Optional[str] = None


class PurchaseItemFeedbackUpdate(BaseModel):
    feedback: Optional[Literal["like", "dislike", "neutral"]] = None  # null clears it


@router.get("/purchases")
def list_purchases(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    source: Optional[Literal["manual", "pos_import"]] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(
            Purchase.id,
            Purchase.customer_id,
            Purchase.purchased_at,
            Purchase.total_amount_cents,
            Purchase.source,
            Purchase.external_id,
            Customer.name,
            Customer.phone,
            func.count(PurchaseItem.id).label("item_count"),
        )
        .select_from(Purchase)
        .join(Customer, Customer.id == Purchase.customer_id)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id, isouter=True)
        .group_by(
            Purchase.id,
            Purchase.customer_id,
            Purchase.purchased_at,
            Purchase.total_amount_cents,
            Purchase.source,
            Purchase.external_id,
            Customer.name,
            Customer.phone,
        )
        .order_by(Purchase.purchased_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if source:
        stmt = stmt.where(Purchase.source == source)

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Purchase.external_id.ilike(like),
            )
        )

    rows = session.exec(stmt).all()

    return [
        {
            "id": str(r[0]),
            "customer_id": str(r[1]),
            "purchased_at": r[2].isoformat(),
            "total_amount_cents": r[3],
            "source": r[4],
            "external_id": r[5],
            "customer_name": r[6],
            "customer_phone": r[7],
            "item_count": r[8],
        }
        for r in rows
    ]


@router.post("/purchases")
def create_purchase(
    payload: PurchaseCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    customer = session.get(Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")

    purchased_at = payload.purchased_at or datetime.now(timezone.utc)

    p = Purchase(
        id=uuid4(),
        customer_id=payload.customer_id,
        purchased_at=purchased_at,
        total_amount_cents=0,
        source=payload.source,
        external_id=payload.external_id,
        notes=payload.notes,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session.add(p)
    session.commit()
    session.refresh(p)

    return serialize_purchase(p)


@router.post("/purchases/{purchase_id}/items")
def add_purchase_item(
    purchase_id: UUID,
    payload: PurchaseItemAdd,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    purchase = session.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status_code=404, detail="purchase not found")

    product = session.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="product not found")

    item = PurchaseItem(
        id=uuid4(),
        purchase_id=purchase_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        line_amount_cents=payload.line_amount_cents,
        external_id=payload.external_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session.add(item)
    session.commit()
    session.refresh(item)

    return {
        "id": str(item.id),
        "purchase_id": str(item.purchase_id),
        "product_id": str(item.product_id),
        "product_name": product.name,
        "quantity": item.quantity,
        "line_amount_cents": item.line_amount_cents,
        "feedback": getattr(item, "feedback", None),
        "feedback_at": item.feedback_at.isoformat() if getattr(item, "feedback_at", None) else None,
    }


@router.post("/purchases/{purchase_id}/finalize")
def finalize_purchase(
    purchase_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    purchase = session.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status_code=404, detail="purchase not found")

    total = session.exec(
        select(func.coalesce(func.sum(PurchaseItem.line_amount_cents), 0))
        .where(PurchaseItem.purchase_id == purchase_id)
    ).one()

    purchase.total_amount_cents = int(total)
    purchase.updated_at = datetime.now(timezone.utc)

    session.add(purchase)
    session.commit()
    session.refresh(purchase)

    return serialize_purchase(purchase)


@router.post("/purchase-items/{purchase_item_id}/feedback")
def set_purchase_item_feedback(
    purchase_item_id: UUID,
    payload: PurchaseItemFeedbackUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    item = session.get(PurchaseItem, purchase_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="purchase_item not found")

    item.feedback = payload.feedback
    item.feedback_at = datetime.now(timezone.utc) if payload.feedback is not None else None

    session.add(item)
    session.commit()
    session.refresh(item)

    return {
        "id": str(item.id),
        "feedback": item.feedback,
        "feedback_at": item.feedback_at.isoformat() if item.feedback_at else None,
    }
