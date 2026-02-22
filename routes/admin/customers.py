from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select, or_, func, case

from auth import SupabaseAuthUser
from database import get_session
from models import (
    Customer,
    Purchase,
    PurchaseItem,
    Product,
    ProductTerpene,
    Terpene,
)
from .auth import require_admin
from .serializers import serialize_customer, serialize_purchase_item

DEFAULT_TERPENE_PERCENT = 0.10
BRAND_WEIGHT = 1000

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
    """Get basic customer information (without purchases)."""
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
    """Get paginated purchase history for a customer (without terpene data)."""
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    # Step 1: Get purchase IDs for this page (prevents row multiplication in pagination)
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

    # Step 2: Fetch full data only for these purchase IDs
    rows = session.exec(
        select(Purchase, PurchaseItem, Product)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id, isouter=True)
        .join(Product, Product.id == PurchaseItem.product_id, isouter=True)
        .where(Purchase.id.in_(purchase_ids))
        .order_by(Purchase.purchased_at.desc())
    ).all()

    purchases_by_id = {}
    for purchase, item, product in rows:
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

        if item is None or product is None:
            continue

        item_id = str(item.id)
        items = purchases_by_id[pur_id]["items"]
        if not any(x["id"] == item_id for x in items):
            items.append(serialize_purchase_item(item, product.name))

    # Preserve ordering from purchase_ids
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
    """Calculate terpene preference scores using database aggregation."""
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    if window_days < 1 or window_days > 3650:
        raise HTTPException(status_code=400, detail="window_days must be between 1 and 3650")

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    # Calculate scores using SQL aggregation.
    # COALESCE uses DEFAULT_TERPENE_PERCENT when percent is NULL.
    weighted_score = func.sum(
        case(
            (PurchaseItem.feedback == "like", func.coalesce(ProductTerpene.percent, DEFAULT_TERPENE_PERCENT)),
            (PurchaseItem.feedback == "dislike", -func.coalesce(ProductTerpene.percent, DEFAULT_TERPENE_PERCENT)),
            else_=0.0,
        )
    ).label("score")

    stmt = (
        select(
            Terpene.name,
            weighted_score,
            func.count(case((PurchaseItem.feedback == "like", 1))).label("likes"),
            func.count(case((PurchaseItem.feedback == "dislike", 1))).label("dislikes"),
            func.count(case((PurchaseItem.feedback == "neutral", 1))).label("neutrals"),
        )
        .select_from(PurchaseItem)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(ProductTerpene, ProductTerpene.product_id == PurchaseItem.product_id)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id)
        .where(Purchase.customer_id == customer_id)
        .where(Purchase.purchased_at >= cutoff)
        .where(PurchaseItem.feedback.isnot(None))
        .group_by(Terpene.id, Terpene.name)
        .order_by(weighted_score.desc())
    )

    rows = session.exec(stmt).all()

    scores = [
        {
            "terpene": row[0],
            "score": float(row[1]) if row[1] else 0.0,
            "likes": row[2],
            "dislikes": row[3],
            "neutrals": row[4],
        }
        for row in rows
    ]

    return {
        "customer_id": str(customer_id),
        "window_days": window_days,
        "cutoff": cutoff.isoformat(),
        "scores": scores,
    }


@router.get("/customers/{customer_id}/recommended-products")
def get_recommended_products(
    customer_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    limit: int = Query(default=10, ge=1, le=50),
    window_days: int = Query(default=180, ge=1, le=3650),
):
    """
    Get product recommendations based on customer's terpene preferences.
    Returns products ranked by terpene similarity score.
    """
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    # Step 1: Get customer's terpene scores
    terpene_scores_stmt = (
        select(
            Terpene.id,
            Terpene.name,
            func.sum(
                case(
                    (PurchaseItem.feedback == "like", func.coalesce(ProductTerpene.percent, DEFAULT_TERPENE_PERCENT)),
                    (PurchaseItem.feedback == "dislike", -func.coalesce(ProductTerpene.percent, DEFAULT_TERPENE_PERCENT)),
                    else_=0.0,
                )
            ).label("score"),
        )
        .select_from(PurchaseItem)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(ProductTerpene, ProductTerpene.product_id == PurchaseItem.product_id)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id)
        .where(Purchase.customer_id == customer_id)
        .where(Purchase.purchased_at >= cutoff)
        .where(PurchaseItem.feedback.isnot(None))
        .group_by(Terpene.id, Terpene.name)
    )
    
    terpene_score_rows = session.exec(terpene_scores_stmt).all()
    terpene_scores_by_id = {row[0]: float(row[2]) if row[2] else 0.0 for row in terpene_score_rows}
    
    if not terpene_scores_by_id:
        # No feedback data, return empty list
        return []

    # Step 2: Get purchase history for this customer
    purchase_history_stmt = (
        select(PurchaseItem.product_id, func.count().label("count"))
        .select_from(PurchaseItem)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .where(Purchase.customer_id == customer_id)
        .group_by(PurchaseItem.product_id)
    )

    purchase_history_rows = session.exec(purchase_history_stmt).all()
    purchased_counts = {row[0]: row[1] for row in purchase_history_rows}

    # Step 2b: Get brand affinity scores (likes - dislikes per brand, within window)
    brand_affinity_stmt = (
        select(
            Product.brand,
            func.count(case((PurchaseItem.feedback == "like", 1))).label("likes"),
            func.count(case((PurchaseItem.feedback == "dislike", 1))).label("dislikes"),
        )
        .select_from(PurchaseItem)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(Product, Product.id == PurchaseItem.product_id)
        .where(Purchase.customer_id == customer_id)
        .where(Purchase.purchased_at >= cutoff)
        .where(PurchaseItem.feedback.isnot(None))
        .where(Product.brand.isnot(None))
        .group_by(Product.brand)
    )
    brand_affinity_rows = session.exec(brand_affinity_stmt).all()
    brand_scores_by_name = {
        row.brand: (row.likes - row.dislikes)
        for row in brand_affinity_rows
    }

    # Step 3: Calculate similarity score for all active products
    # Get all active products with their terpenes
    products_stmt = (
        select(Product, ProductTerpene, Terpene)
        .join(ProductTerpene, ProductTerpene.product_id == Product.id, isouter=True)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id, isouter=True)
        .where(Product.is_active == True)
        .order_by(Product.name)
    )
    
    products_rows = session.exec(products_stmt).all()
    
    # Group by product and calculate scores
    products_dict = {}
    for product, pt_link, terpene in products_rows:
        pid = product.id
        if pid not in products_dict:
            products_dict[pid] = {
                "id": str(pid),
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "score": 0.0,
                "terpenes": [],
                "purchased_count": purchased_counts.get(pid, 0),
            }
        
        if terpene and pt_link:
            terpene_percent = pt_link.percent or DEFAULT_TERPENE_PERCENT
            terpene_score = terpene_scores_by_id.get(terpene.id, 0.0)

            # Weighted score: product's terpene percent * customer's terpene preference
            products_dict[pid]["score"] += terpene_percent * terpene_score

            products_dict[pid]["terpenes"].append({
                "name": terpene.name,
                "percent": terpene_percent,
            })

    # Apply brand affinity boost/penalty
    for pid, prod in products_dict.items():
        if prod["brand"] and prod["brand"] in brand_scores_by_name:
            prod["score"] += brand_scores_by_name[prod["brand"]] * BRAND_WEIGHT

    # Convert to list and sort by score
    products_list = list(products_dict.values())
    products_list.sort(key=lambda x: x["score"], reverse=True)
    
    # Return top N
    return products_list[:limit]
