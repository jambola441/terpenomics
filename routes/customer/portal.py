from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func, case, or_
from sqlalchemy import cast, String

from database import get_session
from models import Customer, Purchase, PurchaseItem, Product, ProductTerpene, Terpene, Cannabinoid, ProductCannabinoid
from routes.admin.serializers import serialize_purchase_item

DEFAULT_TERPENE_PERCENT = 0.10
BRAND_WEIGHT = 1000

router = APIRouter()


# ---------------------------
# GET /products
# ---------------------------

@router.get("/products")
def list_portal_products(
    session: Session = Depends(get_session),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    id_stmt = select(Product.id).where(Product.is_active == True)

    if q:
        like = f"%{q.strip()}%"
        id_stmt = id_stmt.where(
            or_(
                Product.name.ilike(like),
                Product.brand.ilike(like),
                cast(Product.category, String).ilike(like),
            )
        )

    id_stmt = id_stmt.order_by(Product.name).offset(offset).limit(limit)
    product_ids = session.exec(id_stmt).all()

    if not product_ids:
        return []

    rows = session.exec(
        select(Product, ProductTerpene, Terpene)
        .join(ProductTerpene, ProductTerpene.product_id == Product.id, isouter=True)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id, isouter=True)
        .where(Product.id.in_(product_ids))
        .order_by(Product.name)
    ).all()

    by_id = {}
    for product, link, terpene in rows:
        pid = str(product.id)
        if pid not in by_id:
            by_id[pid] = {
                "id": pid,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "terpenes": [],
                "cannabinoids": [],
            }
        if terpene is not None and link is not None:
            by_id[pid]["terpenes"].append({"name": terpene.name, "percent": link.percent})

    cannab_rows = session.exec(
        select(ProductCannabinoid, Cannabinoid)
        .join(Cannabinoid, Cannabinoid.id == ProductCannabinoid.cannabinoid_id)
        .where(ProductCannabinoid.product_id.in_(product_ids))
    ).all()

    for link, c in cannab_rows:
        pid = str(link.product_id)
        if pid in by_id:
            by_id[pid]["cannabinoids"].append({"name": c.name, "family": c.family, "percent": link.percent})

    order = {str(pid): i for i, pid in enumerate(product_ids)}
    return sorted(by_id.values(), key=lambda x: order.get(x["id"], 10**9))


# ---------------------------
# GET /products/{product_id}
# ---------------------------

@router.get("/products/{product_id}")
def get_portal_product(
    product_id: UUID,
    session: Session = Depends(get_session),
):
    p = session.get(Product, product_id)
    if not p or not p.is_active:
        raise HTTPException(status_code=404, detail="product not found")

    terpene_rows = session.exec(
        select(ProductTerpene, Terpene)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id)
        .where(ProductTerpene.product_id == product_id)
    ).all()
    terpenes = [{"name": t.name, "percent": link.percent} for link, t in terpene_rows]

    cannab_rows = session.exec(
        select(ProductCannabinoid, Cannabinoid)
        .join(Cannabinoid, Cannabinoid.id == ProductCannabinoid.cannabinoid_id)
        .where(ProductCannabinoid.product_id == product_id)
    ).all()
    cannabinoids = [{"name": c.name, "family": c.family, "percent": link.percent} for link, c in cannab_rows]

    return {
        "id": str(p.id),
        "name": p.name,
        "brand": p.brand,
        "category": p.category,
        "terpenes": terpenes,
        "cannabinoids": cannabinoids,
    }


# ---------------------------
# GET /{customer_id}/purchases
# ---------------------------

@router.get("/{customer_id}/purchases")
def get_portal_purchases(
    customer_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    # Pass 1: paginated purchase IDs
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

    # Pass 2: full data for those purchase IDs
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
            items.append({
                **serialize_purchase_item(item, product.name),
                "product_category": product.category,
            })

    order = {str(pid): i for i, pid in enumerate(purchase_ids)}
    return sorted(purchases_by_id.values(), key=lambda x: order.get(x["id"], 10**9))


# ---------------------------
# POST /{customer_id}/purchase-items/{item_id}/feedback
# ---------------------------

class FeedbackUpdate(BaseModel):
    feedback: Optional[Literal["like", "dislike", "neutral"]] = None


@router.post("/{customer_id}/purchase-items/{item_id}/feedback")
def set_portal_feedback(
    customer_id: UUID,
    item_id: UUID,
    payload: FeedbackUpdate,
    session: Session = Depends(get_session),
):
    # Ownership check: item must belong to a purchase of this customer
    item = session.exec(
        select(PurchaseItem)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .where(PurchaseItem.id == item_id)
        .where(Purchase.customer_id == customer_id)
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="item not found")

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


# ---------------------------
# GET /{customer_id}/recommendations
# ---------------------------

@router.get("/{customer_id}/recommendations")
def get_portal_recommendations(
    customer_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=10, ge=1, le=50),
    window_days: int = Query(default=180, ge=1, le=3650),
):
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    # Step 1: Customer terpene preference scores
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
        return []

    # Step 2: Purchase history counts
    purchase_history_rows = session.exec(
        select(PurchaseItem.product_id, func.count().label("count"))
        .select_from(PurchaseItem)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .where(Purchase.customer_id == customer_id)
        .group_by(PurchaseItem.product_id)
    ).all()
    purchased_counts = {row[0]: row[1] for row in purchase_history_rows}

    # Step 2b: Brand affinity scores
    brand_affinity_rows = session.exec(
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
    ).all()
    brand_scores_by_name = {row.brand: (row.likes - row.dislikes) for row in brand_affinity_rows}

    # Step 3: Score all active products by terpene match
    products_rows = session.exec(
        select(Product, ProductTerpene, Terpene)
        .join(ProductTerpene, ProductTerpene.product_id == Product.id, isouter=True)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id, isouter=True)
        .where(Product.is_active == True)
        .order_by(Product.name)
    ).all()

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
            products_dict[pid]["score"] += terpene_percent * terpene_score
            products_dict[pid]["terpenes"].append({
                "name": terpene.name,
                "percent": terpene_percent,
            })

    # Apply brand affinity
    for prod in products_dict.values():
        if prod["brand"] and prod["brand"] in brand_scores_by_name:
            prod["score"] += brand_scores_by_name[prod["brand"]] * BRAND_WEIGHT

    products_list = list(products_dict.values())
    products_list.sort(key=lambda x: x["score"], reverse=True)
    return products_list[:limit]
