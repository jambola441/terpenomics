from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, or_

from auth import SupabaseAuthUser
from database import get_session
from models import Dispensary, PosType
from .auth import require_admin

router = APIRouter()


class DispensaryCreate(BaseModel):
    name: str
    slug: str
    website_url: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    is_active: bool = True
    pos_type: PosType = PosType.none
    pos_tenant_id: Optional[str] = None


class DispensaryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    website_url: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    is_active: Optional[bool] = None
    pos_type: Optional[PosType] = None
    pos_tenant_id: Optional[str] = None


def _serialize(d: Dispensary) -> dict:
    return {
        "id": str(d.id),
        "name": d.name,
        "slug": d.slug,
        "website_url": d.website_url,
        "location": d.location,
        "address": d.address,
        "lat": d.lat,
        "lng": d.lng,
        "is_active": d.is_active,
        "pos_type": d.pos_type,
        "pos_tenant_id": d.pos_tenant_id,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }


@router.get("/dispensaries")
def list_dispensaries(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Dispensary)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Dispensary.name.ilike(like),
                Dispensary.slug.ilike(like),
                Dispensary.location.ilike(like),
            )
        )
    stmt = stmt.order_by(Dispensary.name).offset(offset).limit(limit)
    return [_serialize(d) for d in session.exec(stmt).all()]


@router.post("/dispensaries")
def create_dispensary(
    payload: DispensaryCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    existing = session.exec(select(Dispensary).where(Dispensary.slug == payload.slug.strip())).first()
    if existing:
        raise HTTPException(status_code=409, detail="slug already in use")

    d = Dispensary(
        name=payload.name.strip(),
        slug=payload.slug.strip(),
        website_url=payload.website_url,
        location=payload.location,
        address=payload.address,
        lat=payload.lat,
        lng=payload.lng,
        is_active=payload.is_active,
        pos_type=payload.pos_type,
        pos_tenant_id=payload.pos_tenant_id,
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return _serialize(d)


@router.get("/dispensaries/{dispensary_id}")
def get_dispensary(
    dispensary_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    d = session.get(Dispensary, dispensary_id)
    if not d:
        raise HTTPException(status_code=404, detail="dispensary not found")
    return _serialize(d)


@router.post("/dispensaries/{dispensary_id}")
def update_dispensary(
    dispensary_id: UUID,
    payload: DispensaryUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    d = session.get(Dispensary, dispensary_id)
    if not d:
        raise HTTPException(status_code=404, detail="dispensary not found")

    if payload.name is not None:
        d.name = payload.name.strip()
    if payload.slug is not None:
        new_slug = payload.slug.strip()
        conflict = session.exec(
            select(Dispensary).where(Dispensary.slug == new_slug, Dispensary.id != dispensary_id)
        ).first()
        if conflict:
            raise HTTPException(status_code=409, detail="slug already in use")
        d.slug = new_slug
    if payload.website_url is not None:
        d.website_url = payload.website_url
    if payload.location is not None:
        d.location = payload.location
    if payload.address is not None:
        d.address = payload.address
    if payload.lat is not None:
        d.lat = payload.lat
    if payload.lng is not None:
        d.lng = payload.lng
    if payload.is_active is not None:
        d.is_active = payload.is_active
    if payload.pos_type is not None:
        d.pos_type = payload.pos_type
    if payload.pos_tenant_id is not None:
        d.pos_tenant_id = payload.pos_tenant_id

    session.add(d)
    session.commit()
    session.refresh(d)
    return _serialize(d)
