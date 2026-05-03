from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import SupabaseAuthUser
from database import get_session
from models import Dispensary, Listing, Product, ProductCategory
from services.matching import score_candidates
from .auth import require_admin

router = APIRouter()


def _category_from_listing(listing: Listing) -> ProductCategory:
    try:
        return ProductCategory(listing.scraped_category)
    except (ValueError, TypeError):
        return ProductCategory.other


class ListingCreate(BaseModel):
    product_id: Optional[UUID] = None
    dispensary_id: UUID
    price_cents: Optional[int] = None
    variant: Optional[str] = None
    sku: Optional[str] = None
    url: Optional[str] = None
    in_stock: bool = True
    is_active: bool = True


class ListingUpdate(BaseModel):
    price_cents: Optional[int] = None
    variant: Optional[str] = None
    sku: Optional[str] = None
    url: Optional[str] = None
    in_stock: Optional[bool] = None
    is_active: Optional[bool] = None


class MatchPayload(BaseModel):
    product_id: Optional[UUID] = None  # None = create new product from scraped data


class BulkCreateProductsPayload(BaseModel):
    listing_ids: list[UUID]


def _serialize(listing: Listing, product: Optional[Product], dispensary: Dispensary) -> dict:
    return {
        "id":               str(listing.id),
        "product_id":       str(listing.product_id) if listing.product_id else None,
        "product_name":     product.name if product else None,
        "product_brand":    product.brand if product else None,
        "dispensary_id":    str(listing.dispensary_id),
        "dispensary_name":  dispensary.name,
        "dispensary_slug":  dispensary.slug,
        "scraped_name":     listing.scraped_name,
        "scraped_name_raw": listing.scraped_name_raw,
        "scraped_brand":    listing.scraped_brand,
        "scraped_category": listing.scraped_category,
        "price_cents":      listing.price_cents,
        "variant":          listing.variant,
        "sku":              listing.sku,
        "url":              listing.url,
        "in_stock":         listing.in_stock,
        "is_active":        listing.is_active,
        "scraped_at":       listing.scraped_at.isoformat() if listing.scraped_at else None,
        "created_at":       listing.created_at.isoformat(),
        "updated_at":       listing.updated_at.isoformat(),
    }


@router.get("/listings")
def list_listings(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    product_id: Optional[UUID] = Query(default=None),
    dispensary_id: Optional[UUID] = Query(default=None),
    matched: Optional[bool] = Query(default=None, description="Filter by whether product_id is set"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Listing, Product, Dispensary)
        .outerjoin(Product, Product.id == Listing.product_id)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            Listing.scraped_name.ilike(like) | Listing.scraped_brand.ilike(like)
        )
    if product_id:
        stmt = stmt.where(Listing.product_id == product_id)
    if dispensary_id:
        stmt = stmt.where(Listing.dispensary_id == dispensary_id)
    if matched is True:
        stmt = stmt.where(Listing.product_id.is_not(None))
    elif matched is False:
        stmt = stmt.where(Listing.product_id.is_(None))

    stmt = stmt.order_by(Listing.created_at.desc()).offset(offset).limit(limit)
    return [_serialize(l, p, d) for l, p, d in session.exec(stmt).all()]


@router.get("/listings/unmatched")
def list_unmatched_listings(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    dispensary_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return unmatched listings with scored product candidates for each."""
    stmt = (
        select(Listing, Dispensary)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
        .where(Listing.product_id.is_(None))
    )
    if dispensary_id:
        stmt = stmt.where(Listing.dispensary_id == dispensary_id)
    stmt = stmt.order_by(Listing.created_at.desc()).offset(offset).limit(limit)

    rows = session.exec(stmt).all()
    if not rows:
        return []

    # Load all products and brand aliases once for this request
    all_products = session.exec(select(Product)).all()
    from sqlalchemy import text
    aliases_rows = session.exec(text("SELECT alias, canonical_brand FROM brand_aliases")).all()  # type: ignore[arg-type]
    brand_aliases = {a: c for a, c in aliases_rows}

    # Batch load dispensary slugs for every product (used to annotate candidates)
    disp_rows = session.exec(
        select(Listing.product_id, Dispensary.slug, Listing.url)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
        .where(Listing.product_id.is_not(None))
        .distinct()
    ).all()
    product_dispensaries: dict = {}
    for pid, slug, url in disp_rows:
        product_dispensaries.setdefault(str(pid), []).append({"slug": slug, "url": url})

    result = []
    for listing, dispensary in rows:
        candidates = score_candidates(
            scraped_name=listing.scraped_name or "",
            scraped_brand=listing.scraped_brand or "",
            scraped_variant=listing.variant or "",
            scraped_category=listing.scraped_category or "",
            products=all_products,
            brand_aliases=brand_aliases,
            top_n=5,
        )
        result.append({
            **_serialize(listing, None, dispensary),
            "candidates": [
                {
                    "product_id":        str(c["product"].id),
                    "product_name":      c["product"].name,
                    "product_brand":     c["product"].brand,
                    "product_variant":   c["product"].variant,
                    "product_category":  c["product"].category.value,
                    "score":             c["score"],
                    "match_basis":       c["basis"],
                    "dispensary_slugs":  product_dispensaries.get(str(c["product"].id), []),
                }
                for c in candidates
            ],
        })

    return result


@router.post("/listings/{listing_id}/match")
def match_listing(
    listing_id: UUID,
    payload: MatchPayload,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """
    Assign a product to a listing.
    If product_id is provided: link to existing product.
    If product_id is None: create a new product from scraped_name/scraped_brand and link it.
    """
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="listing not found")

    dispensary = session.get(Dispensary, listing.dispensary_id)

    if payload.product_id:
        product = session.get(Product, payload.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="product not found")
    else:
        if not listing.scraped_name:
            raise HTTPException(status_code=400, detail="no scraped_name to create product from")
        now = datetime.now(timezone.utc)
        product = Product(
            id=uuid4(),
            name=listing.scraped_name,
            brand=listing.scraped_brand or None,
            variant=listing.variant or None,
            category=_category_from_listing(listing),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(product)
        session.flush()

    listing.product_id = product.id
    listing.updated_at = datetime.now(timezone.utc)
    session.add(listing)
    session.commit()
    session.refresh(listing)

    return _serialize(listing, product, dispensary)


@router.post("/listings/bulk-create-products")
def bulk_create_products(
    payload: BulkCreateProductsPayload,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Create a new product from scraped data for each listing ID and link them."""
    if not payload.listing_ids:
        return {"created": 0, "errors": []}

    now = datetime.now(timezone.utc)
    created = 0
    errors = []

    for lid in payload.listing_ids:
        listing = session.get(Listing, lid)
        if not listing:
            errors.append({"listing_id": str(lid), "error": "not found"})
            continue
        if listing.product_id:
            errors.append({"listing_id": str(lid), "error": "already matched"})
            continue
        if not listing.scraped_name:
            errors.append({"listing_id": str(lid), "error": "no scraped_name"})
            continue

        product = Product(
            id=uuid4(),
            name=listing.scraped_name,
            brand=listing.scraped_brand or None,
            variant=listing.variant or None,
            category=_category_from_listing(listing),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(product)
        session.flush()

        listing.product_id = product.id
        listing.updated_at = now
        session.add(listing)
        created += 1

    session.commit()
    return {"created": created, "errors": errors}


@router.post("/listings")
def create_listing(
    payload: ListingCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    product = session.get(Product, payload.product_id) if payload.product_id else None
    if payload.product_id and not product:
        raise HTTPException(status_code=404, detail="product not found")

    dispensary = session.get(Dispensary, payload.dispensary_id)
    if not dispensary:
        raise HTTPException(status_code=404, detail="dispensary not found")

    listing = Listing(
        product_id=payload.product_id,
        dispensary_id=payload.dispensary_id,
        price_cents=payload.price_cents,
        variant=payload.variant.strip() if payload.variant else None,
        sku=payload.sku.strip() if payload.sku else None,
        url=payload.url,
        in_stock=payload.in_stock,
        is_active=payload.is_active,
    )
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return _serialize(listing, product, dispensary)


@router.get("/listings/{listing_id}")
def get_listing(
    listing_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    row = session.exec(
        select(Listing, Product, Dispensary)
        .outerjoin(Product, Product.id == Listing.product_id)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
        .where(Listing.id == listing_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="listing not found")
    return _serialize(*row)


@router.post("/listings/{listing_id}/unmatch")
def unmatch_listing(
    listing_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    row = session.exec(
        select(Listing, Dispensary)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
        .where(Listing.id == listing_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="listing not found")

    listing, dispensary = row
    listing.product_id = None
    listing.updated_at = datetime.now(timezone.utc)
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return _serialize(listing, None, dispensary)


@router.post("/listings/{listing_id}")
def update_listing(
    listing_id: UUID,
    payload: ListingUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    row = session.exec(
        select(Listing, Product, Dispensary)
        .outerjoin(Product, Product.id == Listing.product_id)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
        .where(Listing.id == listing_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="listing not found")

    listing, product, dispensary = row

    if payload.price_cents is not None:
        listing.price_cents = payload.price_cents
    if payload.variant is not None:
        listing.variant = payload.variant.strip() if payload.variant else None
    if payload.sku is not None:
        listing.sku = payload.sku.strip() if payload.sku else None
    if payload.url is not None:
        listing.url = payload.url
    if payload.in_stock is not None:
        listing.in_stock = payload.in_stock
    if payload.is_active is not None:
        listing.is_active = payload.is_active

    session.add(listing)
    session.commit()
    session.refresh(listing)
    return _serialize(listing, product, dispensary)
