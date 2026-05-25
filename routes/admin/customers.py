from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select, or_, func

from auth import SupabaseAuthUser
from database import get_session
from models import Customer, Listing, Purchase, PurchaseItem
from .auth import require_admin
from .serializers import serialize_customer, serialize_purchase_item

router = APIRouter()


class CustomerCreate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    marketing_opt_in: bool = False


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    marketing_opt_in: Optional[bool] = None


@router.get("/customers")
def list_customers(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Customer)

    if q:
        qq = q.strip()
        like = f"%{qq}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(like),
                Customer.email.ilike(like),
                Customer.phone.ilike(like),
            )
        )

    stmt = stmt.order_by(Customer.created_at.desc()).offset(offset).limit(limit)
    customers = session.exec(stmt).all()

    return [serialize_customer(c) for c in customers]


@router.post("/customers")
def create_customer(
    payload: CustomerCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    c = Customer(
        id=uuid4(),
        name=payload.name.strip() if payload.name else None,
        phone=payload.phone.strip() if payload.phone else None,
        email=payload.email.strip() if payload.email else None,
        marketing_opt_in=payload.marketing_opt_in,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    return serialize_customer(c)


@router.get("/customers/{customer_id}")
def get_customer_detail(
    customer_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    return serialize_customer(c)


@router.get("/customers/{customer_id}/purchases")
def get_customer_purchases(
    customer_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    id_stmt = (
        select(Purchase.id)
        .where(Purchase.customer_id == customer_id)
        .order_by(Purchase.purchased_at.desc())
        .offset(offset)
        .limit(limit)
    )
    purchase_ids = session.exec(id_stmt).all()

    if not purchase_ids:
        return []

    rows = session.exec(
        select(Purchase, PurchaseItem, Listing)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id, isouter=True)
        .join(Listing, Listing.id == PurchaseItem.listing_id, isouter=True)
        .where(Purchase.id.in_(purchase_ids))
        .order_by(Purchase.purchased_at.desc())
    ).all()

    purchases_by_id = {}
    for purchase, item, listing in rows:
        pur_id = str(purchase.id)
        if pur_id not in purchases_by_id:
            purchases_by_id[pur_id] = {
                "id": pur_id,
                "purchased_at": purchase.purchased_at.isoformat(),
                "total_amount_cents": purchase.total_amount_cents,
                "source": purchase.source,
                "notes": purchase.notes,
                "items": [],
            }

        if item is None or listing is None:
            continue

        item_id = str(item.id)
        items = purchases_by_id[pur_id]["items"]
        if not any(x["id"] == item_id for x in items):
            items.append(serialize_purchase_item(item, listing))

    order = {str(pid): i for i, pid in enumerate(purchase_ids)}
    return sorted(purchases_by_id.values(), key=lambda x: order.get(x["id"], 10**9))


@router.post("/customers/{customer_id}")
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    if payload.name is not None:
        c.name = payload.name.strip() or None
    if payload.phone is not None:
        c.phone = payload.phone.strip() or None
    if payload.email is not None:
        c.email = payload.email.strip() or None
    if payload.marketing_opt_in is not None:
        c.marketing_opt_in = payload.marketing_opt_in

    session.add(c)
    session.commit()
    session.refresh(c)

    return serialize_customer(c)


@router.get("/customers/{customer_id}/terpene-scores")
def get_customer_terpene_scores(
    customer_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    window_days: int = 180,
):
    # Terpene scoring not yet reimplemented for listing-level terpene data
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    return {
        "customer_id": str(customer_id),
        "window_days": window_days,
        "cutoff": cutoff.isoformat(),
        "scores": [],
    }


@router.get("/customers/{customer_id}/recommended-products")
def get_recommended_products(
    customer_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    limit: int = Query(default=10, ge=1, le=50),
    window_days: int = Query(default=180, ge=1, le=3650),
):
    # Recommendations not yet reimplemented for listing-level terpene data
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")
    return []
