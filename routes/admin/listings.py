from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import SupabaseAuthUser
from database import get_session
from models import Dispensary, Listing, Product
from .auth import require_admin

router = APIRouter()


class ListingCreate(BaseModel):
    product_id: UUID
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


def _serialize(listing: Listing, product: Product, dispensary: Dispensary) -> dict:
    return {
        "id": str(listing.id),
        "product_id": str(listing.product_id),
        "product_name": product.name,
        "product_brand": product.brand,
        "dispensary_id": str(listing.dispensary_id),
        "dispensary_name": dispensary.name,
        "dispensary_slug": dispensary.slug,
        "price_cents": listing.price_cents,
        "variant": listing.variant,
        "sku": listing.sku,
        "url": listing.url,
        "in_stock": listing.in_stock,
        "is_active": listing.is_active,
        "scraped_at": listing.scraped_at.isoformat() if listing.scraped_at else None,
        "created_at": listing.created_at.isoformat(),
        "updated_at": listing.updated_at.isoformat(),
    }


@router.get("/listings")
def list_listings(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    product_id: Optional[UUID] = Query(default=None),
    dispensary_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Listing, Product, Dispensary)
        .join(Product, Product.id == Listing.product_id)
        .join(Dispensary, Dispensary.id == Listing.dispensary_id)
    )
    if product_id:
        stmt = stmt.where(Listing.product_id == product_id)
    if dispensary_id:
        stmt = stmt.where(Listing.dispensary_id == dispensary_id)
    stmt = stmt.order_by(Listing.created_at.desc()).offset(offset).limit(limit)

    return [_serialize(l, p, d) for l, p, d in session.exec(stmt).all()]


@router.post("/listings")
def create_listing(
    payload: ListingCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    product = session.get(Product, payload.product_id)
    if not product:
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
        .join(Product, Product.id == Listing.product_id)
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
        select(Listing, Product, Dispensary)
        .join(Product, Product.id == Listing.product_id)
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
