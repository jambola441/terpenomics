from datetime import datetime, timezone
from typing import Literal, Optional, List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field as PydField
from sqlmodel import Session, select, func, or_

from auth import SupabaseAuthUser
from database import get_session
from models import Customer, Product, Purchase, PurchaseItem
from .auth import require_admin
from .serializers import serialize_purchase, serialize_purchase_item

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

    stmt = stmt.order_by(Purchase.purchased_at.desc()).offset(offset).limit(limit)

    rows = session.exec(stmt).all()

    return [
        {
            "id": str(r.id),
            "customer_id": str(r.customer_id),
            "purchased_at": r.purchased_at.isoformat(),
            "total_amount_cents": r.total_amount_cents,
            "source": r.source,
            "external_id": r.external_id,
            "customer_name": r.name,
            "customer_phone": r.phone,
            "item_count": r.item_count,
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

    return serialize_purchase_item(item, product.name)


@router.post("/purchases/{purchase_id}/items/batch")
def add_purchase_items_batch(
    purchase_id: UUID,
    items: List[PurchaseItemAdd],
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """
    Batch create multiple purchase items for a purchase.
    Validates all products exist before creating any items.
    """
    purchase = session.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status_code=404, detail="purchase not found")
    
    if not items:
        raise HTTPException(status_code=400, detail="items list cannot be empty")
    
    if len(items) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 items allowed per batch")
    
    # Validate all products exist before creating any items
    product_ids = [item.product_id for item in items]
    products = session.exec(
        select(Product).where(Product.id.in_(product_ids))
    ).all()
    
    products_by_id = {p.id: p for p in products}
    
    for item in items:
        if item.product_id not in products_by_id:
            raise HTTPException(
                status_code=404,
                detail=f"product not found: {item.product_id}"
            )
    
    # Create all items
    created_items = []
    now = datetime.now(timezone.utc)
    
    for item_data in items:
        item = PurchaseItem(
            id=uuid4(),
            purchase_id=purchase_id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            line_amount_cents=item_data.line_amount_cents,
            external_id=item_data.external_id,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        created_items.append((item, products_by_id[item_data.product_id]))
    
    session.commit()
    
    # Refresh and return all items
    result = []
    for item, product in created_items:
        session.refresh(item)
        result.append(serialize_purchase_item(item, product.name))

    return result


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
