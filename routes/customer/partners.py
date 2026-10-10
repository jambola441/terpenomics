"""Partner stores, for customers: who they are, where they are, how points work.

Partners are local businesses, not dispensaries, where a purchase earns Terpee
points. The list and each partner's page show what the business says about
itself, its stores with coordinates, phone and hours (Square sends these; a store
added by hand gets its coordinates in the admin), and the program's real numbers,
so no screen states a rule the ledger doesn't keep.

Only active partners and their active stores are shown. No sign-in: knowing
where to earn comes before having an account.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from database import get_session
from models import Partner, PartnerLocation
from routes.pos_common import program_json
from services.response_cache import cached_json

router = APIRouter()


def _location(loc: PartnerLocation) -> dict:
    return {"id": str(loc.id), "name": loc.name, "address": loc.address,
            "lat": loc.lat, "lng": loc.lng, "phone": loc.phone, "hours": loc.hours}


def _partner(p: Partner, locations: list[PartnerLocation]) -> dict:
    return {"id": str(p.id), "slug": p.slug, "name": p.name, "logo_url": p.logo_url,
            "description": p.description, "category": p.category, "website_url": p.website_url,
            "locations": [_location(loc) for loc in sorted(locations, key=lambda loc: loc.name.lower())]}


def _build(session: Session, slug: str | None = None) -> dict:
    stmt = select(Partner).where(Partner.is_active.is_(True)).order_by(Partner.name)
    if slug is not None:
        stmt = stmt.where(Partner.slug == slug)
    partners = session.exec(stmt).all()
    if slug is not None and not partners:
        raise HTTPException(404, "partner not found")
    by_partner: dict = defaultdict(list)
    if partners:
        for loc in session.exec(
            select(PartnerLocation)
            .where(PartnerLocation.partner_id.in_([p.id for p in partners]))
            .where(PartnerLocation.is_active.is_(True))
        ).all():
            by_partner[loc.partner_id].append(loc)
    shown = [_partner(p, by_partner[p.id]) for p in partners]
    if slug is not None:
        return {**shown[0], "program": program_json()}
    return {"program": program_json(), "partners": shown}


@router.get("/partners")
def list_partners(session: Session = Depends(get_session)):
    """Every partner store, with its locations, and how points work."""
    # The same for everyone and rarely changed; the admin and the partner clear it
    # when they edit (services/response_cache.py).
    return cached_json(("partners",), _build, session)


@router.get("/partners/{slug}")
def get_partner(slug: str, session: Session = Depends(get_session)):
    """One partner store: what it is, its locations, and how points work."""
    return cached_json(("partner", slug), lambda s: _build(s, slug), session)
