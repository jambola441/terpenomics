from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from auth import SupabaseAuthUser
from database import get_session
from models import Dispensary, Listing
from .auth import require_admin

router = APIRouter()


class ListingCreate(BaseModel):
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
    product_line: Optional[str] = None
    strain: Optional[str] = None


def _serialize(listing: Listing, dispensary: Dispensary) -> dict:
    return {
        "id":               str(listing.id),
        "dispensary_id":    str(listing.dispensary_id),
        "dispensary_name":  dispensary.name,
        "dispensary_slug":  dispensary.slug,
        "scraped_name":     listing.scraped_name,
        "scraped_brand":    listing.scraped_brand,
        "scraped_category": listing.scraped_category,
        "subtype":          listing.subtype,
        "strain":           listing.strain,
        "product_line":     listing.product_line,
        "price_cents":      listing.price_cents,
        "variant":          listing.variant,
        "sku":              listing.sku,
        "url":              listing.url,
        "image_url":        listing.image_url,
        "in_stock":         listing.in_stock,
        "is_active":        listing.is_active,
        "classification":   listing.classification,
        "description":      listing.description,
        "scraped_at":       listing.scraped_at.isoformat() if listing.scraped_at else None,
        "created_at":       listing.created_at.isoformat(),
        "updated_at":       listing.updated_at.isoformat(),
    }


@router.get("/listings/filter-options")
def get_listing_filter_options(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    dispensaries = session.exec(text(
        "SELECT DISTINCT d.id, d.name FROM dispensaries d"
        " JOIN listings l ON l.dispensary_id = d.id"
        " ORDER BY d.name"
    )).all()
    brands = session.exec(text(
        "SELECT DISTINCT scraped_brand FROM listings"
        " WHERE scraped_brand IS NOT NULL ORDER BY scraped_brand"
    )).all()
    classifications = session.exec(text(
        "SELECT DISTINCT classification FROM listings"
        " WHERE classification IS NOT NULL ORDER BY classification"
    )).all()
    subtypes = session.exec(text(
        "SELECT DISTINCT subtype FROM listings"
        " WHERE subtype IS NOT NULL ORDER BY subtype"
    )).all()
    return {
        "dispensaries":    [{"id": str(r[0]), "name": r[1]} for r in dispensaries],
        "brands":          [r[0] for r in brands],
        "classifications": [r[0] for r in classifications],
        "subtypes":        [r[0] for r in subtypes],
    }


@router.get("/listings")
def list_listings(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    dispensary_id: Optional[UUID] = Query(default=None),
    category: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    subtype: Optional[str] = Query(default=None),
    classification: Optional[str] = Query(default=None),
    in_stock: Optional[bool] = Query(default=None),
    sort: Optional[str] = Query(default=None),
    order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Listing, Dispensary)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            Listing.scraped_name.ilike(like) | Listing.scraped_brand.ilike(like)
        )
    if dispensary_id:
        stmt = stmt.where(Listing.dispensary_id == dispensary_id)
    if category:
        stmt = stmt.where(Listing.scraped_category == category)
    if brand:
        stmt = stmt.where(Listing.scraped_brand == brand)
    if subtype:
        stmt = stmt.where(Listing.subtype == subtype)
    if classification:
        stmt = stmt.where(Listing.classification == classification)
    if in_stock is not None:
        stmt = stmt.where(Listing.in_stock == in_stock)

    _sort_cols = {
        "name":         Listing.scraped_name,
        "brand":        Listing.scraped_brand,
        "category":     Listing.scraped_category,
        "subtype":      Listing.subtype,
        "product_line": Listing.product_line,
        "strain":       Listing.strain,
        "dispensary":   Dispensary.name,
        "price":        Listing.price_cents,
        "scraped_at":   Listing.scraped_at,
    }
    col = _sort_cols.get(sort or "")
    if col is not None:
        stmt = stmt.order_by(col.asc() if order == "asc" else col.desc())
    else:
        stmt = stmt.order_by(Listing.created_at.desc())

    stmt = stmt.offset(offset).limit(limit)
    return [_serialize(l, d) for l, d in session.exec(stmt).all()]


@router.post("/listings")
def create_listing(
    payload: ListingCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    dispensary = session.get(Dispensary, payload.dispensary_id)
    if not dispensary:
        raise HTTPException(status_code=404, detail="dispensary not found")

    listing = Listing(
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
    return _serialize(listing, dispensary)


@router.get("/listings/{listing_id}")
def get_listing(
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
    return _serialize(*row)


@router.post("/listings/{listing_id}")
def update_listing(
    listing_id: UUID,
    payload: ListingUpdate,
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
    if payload.product_line is not None:
        listing.product_line = payload.product_line.strip() or None
    if payload.strain is not None:
        listing.strain = payload.strain.strip() or None

    listing.updated_at = datetime.now(timezone.utc)
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return _serialize(listing, dispensary)
