from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlmodel import Session, select

from auth import SupabaseAuthUser
from database import engine, get_session
from models import Dispensary, Listing
from .auth import require_admin

router = APIRouter()

_NULL = "__null__"


def _tuple_filter(stmt, brand, category, subtype, product_line, strain, variant):
    """Apply exact-match tuple filters, treating __null__ as IS NULL."""
    if brand == _NULL:
        stmt = stmt.where(Listing.scraped_brand.is_(None))
    elif brand is not None:
        stmt = stmt.where(Listing.scraped_brand == brand)

    if category is not None:
        stmt = stmt.where(Listing.scraped_category == category)

    if subtype == _NULL:
        stmt = stmt.where(Listing.subtype.is_(None))
    elif subtype is not None:
        stmt = stmt.where(Listing.subtype == subtype)

    if product_line == _NULL:
        stmt = stmt.where(Listing.product_line.is_(None))
    elif product_line is not None:
        stmt = stmt.where(Listing.product_line == product_line)

    if strain == _NULL:
        stmt = stmt.where(Listing.strain.is_(None))
    elif strain is not None:
        stmt = stmt.where(Listing.strain == strain)

    if variant == _NULL:
        stmt = stmt.where(Listing.variant.is_(None))
    elif variant is not None:
        stmt = stmt.where(Listing.variant == variant)

    return stmt


@router.get("/products")
def list_products(
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    in_stock: Optional[bool] = Query(default=None),
    sort: Optional[str] = Query(default=None),
    order: str = Query(default="asc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    conditions = ["1=1"]
    params: dict = {}

    if q:
        conditions.append(
            "(brand ILIKE :q OR category ILIKE :q OR strain ILIKE :q OR subtype ILIKE :q)"
        )
        params["q"] = f"%{q.strip()}%"
    if brand:
        conditions.append("brand ILIKE :brand")
        params["brand"] = f"%{brand.strip()}%"
    if category:
        conditions.append("category = :category")
        params["category"] = category
    if in_stock is not None:
        conditions.append("any_in_stock = :in_stock")
        params["in_stock"] = in_stock

    _sort_cols = {
        "brand":        "brand",
        "category":     "category",
        "subtype":      "subtype",
        "product_line": "product_line",
        "strain":       "strain",
        "stores":       "dispensary_count",
        "listings":     "listing_count",
        "price":        "min_price_cents",
    }
    sort_col = _sort_cols.get(sort or "", None)
    sort_dir = "ASC" if order == "asc" else "DESC"
    order_clause = f"{sort_col} {sort_dir} NULLS LAST" if sort_col else "brand, category, subtype, strain, variant"

    where = " AND ".join(conditions)
    sql = text(f"""
        SELECT brand, category, subtype, product_line, strain, variant,
               listing_count, dispensary_count,
               min_price_cents, max_price_cents,
               any_in_stock
        FROM products
        WHERE {where}
        ORDER BY {order_clause}
        LIMIT :limit OFFSET :offset
    """)
    params["limit"] = limit
    params["offset"] = offset

    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    return [dict(r) for r in rows]


@router.get("/products/detail")
def get_product_detail(
    _: SupabaseAuthUser = Depends(require_admin),
    session: Session = Depends(get_session),
    brand: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    subtype: Optional[str] = Query(default=None),
    product_line: Optional[str] = Query(default=None),
    strain: Optional[str] = Query(default=None),
    variant: Optional[str] = Query(default=None),
):
    if category is None:
        raise HTTPException(status_code=400, detail="category is required")

    # Fetch the matching VIEW row
    view_conditions = ["category = :category"]
    view_params: dict = {"category": category}

    if brand == _NULL:
        view_conditions.append("brand IS NULL")
    elif brand is not None:
        view_conditions.append("brand = :brand")
        view_params["brand"] = brand

    if subtype == _NULL:
        view_conditions.append("subtype IS NULL")
    elif subtype is not None:
        view_conditions.append("subtype = :subtype")
        view_params["subtype"] = subtype

    if product_line == _NULL:
        view_conditions.append("product_line IS NULL")
    elif product_line is not None:
        view_conditions.append("product_line = :product_line")
        view_params["product_line"] = product_line

    if strain == _NULL:
        view_conditions.append("strain IS NULL")
    elif strain is not None:
        view_conditions.append("strain = :strain")
        view_params["strain"] = strain

    if variant == _NULL:
        view_conditions.append("variant IS NULL")
    elif variant is not None:
        view_conditions.append("variant = :variant")
        view_params["variant"] = variant

    where = " AND ".join(view_conditions)
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT * FROM products WHERE {where}"),
            view_params,
        ).mappings().first()

        # Fallback: product_line=__null__ (IS NULL) found nothing — the listing that
        # generated this URL has product_line=null but no product group with
        # product_line=null exists for this combo (all siblings have a value set).
        # Relax the product_line constraint and use whatever value the found row has.
        if not row and product_line == _NULL:
            fallback_conditions = [c for c in view_conditions if "product_line" not in c]
            fallback_params = {k: v for k, v in view_params.items() if k != "product_line"}
            row = conn.execute(
                text("SELECT * FROM products WHERE " + " AND ".join(fallback_conditions)),
                fallback_params,
            ).mappings().first()
            if row:
                product_line = row["product_line"]  # use actual value for listings query

    if not row:
        raise HTTPException(status_code=404, detail="product not found")

    product = dict(row)

    # Fetch all matching listings with dispensary name
    stmt = (
        select(Listing, Dispensary)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
        .where(Listing.is_active == True)  # noqa: E712
    )
    stmt = _tuple_filter(stmt, brand, category, subtype, product_line, strain, variant)
    stmt = stmt.order_by(Dispensary.name, Listing.price_cents)

    listings = []
    for listing, dispensary in session.exec(stmt).all():
        listings.append({
            "id":               str(listing.id),
            "dispensary_id":    str(listing.dispensary_id),
            "dispensary_name":  dispensary.name,
            "dispensary_slug":  dispensary.slug,
            "scraped_name":     listing.scraped_name,
            "price_cents":      listing.price_cents,
            "variant":          listing.variant,
            "sku":              listing.sku,
            "url":              listing.url,
            "image_url":        listing.image_url,
            "in_stock":         listing.in_stock,
            "classification":   listing.classification,
            "scraped_at":       listing.scraped_at.isoformat() if listing.scraped_at else None,
        })

    return {"product": product, "listings": listings}


@router.get("/products/brands")
def list_brands(
    _: SupabaseAuthUser = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(Listing.scraped_brand)
        .where(Listing.scraped_brand.isnot(None))
        .where(Listing.is_active == True)  # noqa: E712
        .distinct()
        .order_by(Listing.scraped_brand)
    ).all()
    return [r for r in rows if r]
