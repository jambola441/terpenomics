from datetime import datetime, timezone
from typing import Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlmodel import Session, select, or_

from database import engine, get_session
from models import (
    Customer, Dispensary, Listing, ListingTerpene, ListingCannabinoid,
    Terpene, Cannabinoid, Purchase, PurchaseItem,
)
from routes.admin.serializers import serialize_purchase_item

router = APIRouter()


# ---------------------------
# GET /dispensaries
# ---------------------------

@router.get("/dispensaries")
def list_portal_dispensaries(session: Session = Depends(get_session)):
    dispensaries = session.exec(
        select(Dispensary)
        .where(Dispensary.is_active == True)  # noqa: E712
        .order_by(Dispensary.name)
    ).all()
    return [
        {
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
        for d in dispensaries
    ]


# ---------------------------
# GET /brands
# ---------------------------

@router.get("/brands")
def list_portal_brands(limit: int = 24, session: Session = Depends(get_session)):
    rows = session.exec(
        select(
            Listing.scraped_brand,
            func.count(Listing.id).label("cnt"),
            func.min(Listing.image_url).label("image_url"),
        )
        .where(Listing.scraped_brand.isnot(None))
        .where(Listing.scraped_brand != "")
        .group_by(Listing.scraped_brand)
        .order_by(func.count(Listing.id).desc())
        .limit(limit)
    ).all()
    return [{"name": r.scraped_brand, "listing_count": r.cnt, "image_url": r.image_url} for r in rows]


# ---------------------------
# GET /brands/{brand_name}
# ---------------------------

@router.get("/brands/{brand_name}")
def get_portal_brand(
    brand_name: str,
    session: Session = Depends(get_session),
    in_stock: bool = Query(default=True),
):
    stmt = (
        select(Listing, Dispensary)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
        .where(Listing.scraped_brand == brand_name)
        .where(Listing.is_active == True)  # noqa: E712
        .where(Dispensary.is_active == True)  # noqa: E712
    )
    if in_stock:
        stmt = stmt.where(Listing.in_stock == True)  # noqa: E712
    stmt = stmt.order_by(Listing.scraped_category, Listing.scraped_name)

    rows = session.exec(stmt).all()
    if not rows:
        raise HTTPException(status_code=404, detail="brand not found")

    # Group listings into products by the 6-tuple identity (brand is fixed here).
    # Each product carries its per-dispensary offerings so the client can compute
    # the closest/cheapest options against the user's location.
    products: dict[tuple, dict] = {}
    brand_image = None
    dispensary_ids = set()

    for listing, dispensary in rows:
        if brand_image is None and listing.image_url:
            brand_image = listing.image_url
        dispensary_ids.add(str(dispensary.id))

        key = (
            listing.scraped_category,
            listing.subtype,
            listing.product_line,
            listing.strain,
            listing.variant,
        )
        product = products.get(key)
        if product is None:
            name = (
                listing.strain
                or listing.product_line
                or listing.scraped_name
                or listing.scraped_category
                or "—"
            )
            product = {
                "key": "|".join("" if k is None else str(k) for k in key),
                "name": name,
                "category": listing.scraped_category,
                "subtype": listing.subtype,
                "product_line": listing.product_line,
                "strain": listing.strain,
                "variant": listing.variant,
                "image_url": listing.image_url,
                "offerings": [],
            }
            products[key] = product

        if product["image_url"] is None and listing.image_url:
            product["image_url"] = listing.image_url

        product["offerings"].append({
            "listing_id": str(listing.id),
            "dispensary_id": str(dispensary.id),
            "dispensary_name": dispensary.name,
            "dispensary_slug": dispensary.slug,
            "lat": dispensary.lat,
            "lng": dispensary.lng,
            "price_cents": listing.price_cents,
            "in_stock": listing.in_stock,
            "url": listing.url,
        })

    product_list = []
    for product in products.values():
        prices = [o["price_cents"] for o in product["offerings"] if o["price_cents"] is not None]
        product["min_price_cents"] = min(prices) if prices else None
        product["dispensary_count"] = len({o["dispensary_id"] for o in product["offerings"]})
        product_list.append(product)

    product_list.sort(key=lambda p: ((p["category"] or ""), p["name"].lower()))

    return {
        "name": brand_name,
        "image_url": brand_image,
        "product_count": len(product_list),
        "dispensary_count": len(dispensary_ids),
        "products": product_list,
    }


# ---------------------------
# GET /categories
# ---------------------------

@router.get("/categories")
def list_portal_categories(session: Session = Depends(get_session)):
    rows = session.exec(
        select(
            Listing.scraped_category,
            func.count(Listing.id).label("cnt"),
            func.min(Listing.image_url).label("image_url"),
        )
        .where(Listing.scraped_category.isnot(None))
        .group_by(Listing.scraped_category)
        .order_by(func.count(Listing.id).desc())
    ).all()
    return [{"name": r.scraped_category, "listing_count": r.cnt, "image_url": r.image_url} for r in rows]


# ---------------------------
# GET /dispensaries/{id}/filter-options
# ---------------------------

@router.get("/dispensaries/{dispensary_id}/filter-options")
def get_dispensary_filter_options(
    dispensary_id: UUID,
    session: Session = Depends(get_session),
):
    brands = session.exec(
        select(Listing.scraped_brand)
        .where(Listing.dispensary_id == dispensary_id)
        .where(Listing.is_active == True)  # noqa: E712
        .where(Listing.in_stock == True)  # noqa: E712
        .where(Listing.scraped_brand.isnot(None))
        .distinct()
        .order_by(Listing.scraped_brand)
    ).all()

    variants = session.exec(
        select(Listing.variant)
        .where(Listing.dispensary_id == dispensary_id)
        .where(Listing.is_active == True)  # noqa: E712
        .where(Listing.in_stock == True)  # noqa: E712
        .where(Listing.variant.isnot(None))
        .where(Listing.variant != "")
        .distinct()
        .order_by(Listing.variant)
    ).all()

    return {
        "brands": [b for b in brands if b],
        "variants": [v for v in variants if v],
    }


# ---------------------------
# GET /dispensaries/{id}/listings
# ---------------------------

@router.get("/dispensaries/{dispensary_id}/listings")
def get_dispensary_listings(
    dispensary_id: UUID,
    session: Session = Depends(get_session),
    category: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    variant: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    in_stock: Optional[bool] = Query(default=True),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    dispensary = session.get(Dispensary, dispensary_id)
    if not dispensary:
        raise HTTPException(status_code=404, detail="dispensary not found")

    stmt = (
        select(Listing.id)
        .where(Listing.dispensary_id == dispensary_id)
        .where(Listing.is_active == True)  # noqa: E712
    )
    if in_stock:
        stmt = stmt.where(Listing.in_stock == True)  # noqa: E712
    if category:
        stmt = stmt.where(Listing.scraped_category == category)
    if brand:
        stmt = stmt.where(Listing.scraped_brand == brand)
    if variant:
        stmt = stmt.where(Listing.variant == variant)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Listing.scraped_name.ilike(like),
                Listing.scraped_brand.ilike(like),
            )
        )

    stmt = stmt.order_by(Listing.scraped_name).offset(offset).limit(limit)
    listing_ids = session.exec(stmt).all()

    if not listing_ids:
        return []

    listings = session.exec(
        select(Listing).where(Listing.id.in_(listing_ids)).order_by(Listing.scraped_name)
    ).all()

    terpene_map: dict[str, list] = {}
    for link, t in session.exec(
        select(ListingTerpene, Terpene)
        .join(Terpene, Terpene.id == ListingTerpene.terpene_id)
        .where(ListingTerpene.listing_id.in_(listing_ids))
    ).all():
        lid = str(link.listing_id)
        terpene_map.setdefault(lid, []).append({"name": t.name, "percent": link.percent})

    cannabinoid_map: dict[str, list] = {}
    for link, c in session.exec(
        select(ListingCannabinoid, Cannabinoid)
        .join(Cannabinoid, Cannabinoid.id == ListingCannabinoid.cannabinoid_id)
        .where(ListingCannabinoid.listing_id.in_(listing_ids))
    ).all():
        lid = str(link.listing_id)
        cannabinoid_map.setdefault(lid, []).append({"name": c.name, "family": c.family, "percent": link.percent})

    result = []
    for listing in listings:
        lid = str(listing.id)
        result.append({
            "id": lid,
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
            "terpenes": terpene_map.get(lid, []),
            "cannabinoids": cannabinoid_map.get(lid, []),
        })

    return result


# ---------------------------
# GET /dispensaries/{id}/listings/{listing_id}
# ---------------------------

@router.get("/dispensaries/{dispensary_id}/listings/{listing_id}")
def get_dispensary_listing(
    dispensary_id: UUID,
    listing_id: UUID,
    session: Session = Depends(get_session),
):
    dispensary = session.get(Dispensary, dispensary_id)
    if not dispensary:
        raise HTTPException(status_code=404, detail="dispensary not found")

    listing = session.exec(
        select(Listing)
        .where(Listing.id == listing_id)
        .where(Listing.dispensary_id == dispensary_id)
        .where(Listing.is_active == True)  # noqa: E712
    ).first()
    if not listing:
        raise HTTPException(status_code=404, detail="listing not found")

    terpenes = []
    for link, t in session.exec(
        select(ListingTerpene, Terpene)
        .join(Terpene, Terpene.id == ListingTerpene.terpene_id)
        .where(ListingTerpene.listing_id == listing_id)
    ).all():
        terpenes.append({"name": t.name, "percent": link.percent})

    cannabinoids = []
    for link, c in session.exec(
        select(ListingCannabinoid, Cannabinoid)
        .join(Cannabinoid, Cannabinoid.id == ListingCannabinoid.cannabinoid_id)
        .where(ListingCannabinoid.listing_id == listing_id)
    ).all():
        cannabinoids.append({"name": c.name, "family": c.family, "percent": link.percent})

    return {
        "id": str(listing.id),
        "dispensary_id": str(dispensary.id),
        "dispensary_name": dispensary.name,
        "dispensary_slug": dispensary.slug,
        "scraped_name": listing.scraped_name,
        "scraped_brand": listing.scraped_brand,
        "scraped_category": listing.scraped_category,
        "subtype": listing.subtype,
        "strain": listing.strain,
        "product_line": listing.product_line,
        "classification": listing.classification,
        "price_cents": listing.price_cents,
        "variant": listing.variant,
        "url": listing.url,
        "image_url": listing.image_url,
        "in_stock": listing.in_stock,
        "description": listing.description,
        "terpenes": terpenes,
        "cannabinoids": cannabinoids,
    }


# ---------------------------
# GET /products
# ---------------------------

@router.get("/products")
def list_portal_products(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    conditions = ["1=1"]
    params: dict = {}

    if q:
        conditions.append(
            "(brand ILIKE :q OR category ILIKE :q OR strain ILIKE :q)"
        )
        params["q"] = f"%{q.strip()}%"
    if category:
        conditions.append("category = :category")
        params["category"] = category
    if brand:
        conditions.append("brand ILIKE :brand")
        params["brand"] = f"%{brand.strip()}%"

    where = " AND ".join(conditions)
    sql = text(f"""
        SELECT brand, category, subtype, strain, variant,
               listing_count, dispensary_count,
               min_price_cents, max_price_cents,
               any_in_stock
        FROM products
        WHERE {where}
        ORDER BY brand, category, subtype, strain, variant
        LIMIT :limit OFFSET :offset
    """)
    params["limit"] = limit
    params["offset"] = offset

    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    return [dict(r) for r in rows]


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
            items.append({
                **serialize_purchase_item(item, listing),
                "product_category": listing.scraped_category,
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
    # Recommendations engine not yet implemented for listing-level terpene data
    return []
