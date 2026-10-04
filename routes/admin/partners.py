"""Partner stores and their POS connections.

CRUD only, per the thin-API rule: syncing lives in scripts/pos_sync.py. The
exceptions are the two halves of OAuth -- /start here, the callback in
routes/pos_oauth.py -- and disconnect, which has to revoke at the POS.

Credentials are write-only: no response from this module ever includes them.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, func, select

from auth import SupabaseAuthUser
from connectors.base import PosConnector
from database import get_session
from routes.pos_common import (
    authorize_url,
    connection_json as _connection,
    connector_factory,
    disconnect_connection,
    location_json as _location,
    member_json,
    order_json,
    partner_json as _partner,
    run_json as _run,
    set_connection_status,
)
from models import (
    Partner,
    PartnerLocation,
    PartnerMember,
    PosConnection,
    PosOrder,
    PosSyncRun,
)
from .auth import require_admin

router = APIRouter()


# ----------------------------------------------------------------------
# Partners
# ----------------------------------------------------------------------

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PartnerCreate(BaseModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    is_active: bool = True


class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: Optional[bool] = None


def _check_slug(session: Session, slug: str, partner_id: Optional[UUID] = None) -> None:
    if not _SLUG.match(slug):
        raise HTTPException(422, "slug must be lowercase letters, digits and hyphens")
    clash = session.exec(select(Partner).where(Partner.slug == slug)).first()
    if clash is not None and clash.id != partner_id:
        raise HTTPException(409, "slug already in use")


def _get_partner(session: Session, partner_id: UUID) -> Partner:
    partner = session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(404, "partner not found")
    return partner


@router.get("/partners")
def list_partners(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows = session.exec(select(Partner).order_by(Partner.name).offset(offset).limit(limit)).all()
    return [_partner(p) for p in rows]


@router.post("/partners", status_code=201)
def create_partner(
    payload: PartnerCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    _check_slug(session, payload.slug)
    partner = Partner(**payload.model_dump())
    session.add(partner)
    session.commit()
    session.refresh(partner)
    return _partner(partner)


@router.get("/partners/{partner_id}")
def get_partner(
    partner_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    partner = _get_partner(session, partner_id)
    locations = session.exec(
        select(PartnerLocation).where(PartnerLocation.partner_id == partner_id).order_by(PartnerLocation.name)
    ).all()
    connections = session.exec(select(PosConnection).where(PosConnection.partner_id == partner_id)).all()
    members = session.exec(
        select(PartnerMember).where(PartnerMember.partner_id == partner_id).order_by(PartnerMember.invited_at)
    ).all()
    return {
        **_partner(partner),
        "locations": [_location(loc) for loc in locations],
        "connections": [_connection(c) for c in connections],
        "members": [member_json(m) for m in members],
    }


@router.patch("/partners/{partner_id}")
def update_partner(
    partner_id: UUID,
    payload: PartnerUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    partner = _get_partner(session, partner_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("slug") is not None:
        _check_slug(session, data["slug"], partner_id)
    for key, value in data.items():
        if value is None and key in ("name", "slug", "is_active"):
            raise HTTPException(422, f"{key} cannot be null")
        setattr(partner, key, value)
    partner.updated_at = datetime.now(timezone.utc)
    session.add(partner)
    session.commit()
    session.refresh(partner)
    return _partner(partner)


# ----------------------------------------------------------------------
# Partner logins
# ----------------------------------------------------------------------
#
# Who may sign in to the partner's own dashboard at /partner. Inviting is just
# recording an email: whoever signs in with Google as that address gets in.

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MemberCreate(BaseModel):
    email: str


@router.post("/partners/{partner_id}/members", status_code=201)
def invite_member(
    partner_id: UUID,
    payload: MemberCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    _get_partner(session, partner_id)
    email = payload.email.strip().lower()
    if not _EMAIL.match(email) or email.endswith("@phone.invalid"):
        raise HTTPException(422, "enter a valid email address")
    clash = session.exec(select(PartnerMember).where(
        PartnerMember.partner_id == partner_id, PartnerMember.email == email,
    )).first()
    if clash is not None:
        raise HTTPException(409, "that email already has access")
    member = PartnerMember(partner_id=partner_id, email=email)
    session.add(member)
    session.commit()
    session.refresh(member)
    return member_json(member)


@router.delete("/partner-members/{member_id}")
def remove_member(
    member_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    member = session.get(PartnerMember, member_id)
    if member is None:
        raise HTTPException(404, "member not found")
    session.delete(member)
    session.commit()
    return {"ok": True}


# ----------------------------------------------------------------------
# Locations
# ----------------------------------------------------------------------

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


@router.patch("/partner-locations/{location_id}")
def update_location(
    location_id: UUID,
    payload: LocationUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    loc = session.get(PartnerLocation, location_id)
    if loc is None:
        raise HTTPException(404, "location not found")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in data.items():
        setattr(loc, key, value)
    loc.updated_at = datetime.now(timezone.utc)
    session.add(loc)
    session.commit()
    session.refresh(loc)
    return _location(loc)


# ----------------------------------------------------------------------
# Connections
# ----------------------------------------------------------------------

def _get_connection(session: Session, connection_id: UUID) -> PosConnection:
    conn = session.get(PosConnection, connection_id)
    if conn is None:
        raise HTTPException(404, "connection not found")
    return conn


@router.get("/pos-connections/oauth/{provider}/start")
def start_oauth(
    provider: str,
    partner_id: UUID = Query(...),
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    factory: Callable[[str], PosConnector] = Depends(connector_factory),
):
    """Return the POS consent URL for the admin UI to navigate to.

    JSON rather than a redirect: the admin's token is a bearer header, which a
    browser navigation would not carry.
    """
    _get_partner(session, partner_id)
    return authorize_url(factory, provider, partner_id, origin="admin")


@router.get("/pos-connections")
def list_connections(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    partner_id: Optional[UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    stmt = select(PosConnection).order_by(PosConnection.created_at)
    if partner_id:
        stmt = stmt.where(PosConnection.partner_id == partner_id)
    if status:
        stmt = stmt.where(PosConnection.status == status)
    return [_connection(c) for c in session.exec(stmt).all()]


@router.get("/pos-connections/{connection_id}")
def get_connection(
    connection_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    conn = _get_connection(session, connection_id)
    locations = session.exec(select(PartnerLocation).where(PartnerLocation.connection_id == connection_id)).all()
    return {**_connection(conn), "locations": [_location(loc) for loc in locations]}


class ConnectionUpdate(BaseModel):
    status: Literal["active", "disabled"]


@router.patch("/pos-connections/{connection_id}")
def update_connection(
    connection_id: UUID,
    payload: ConnectionUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Pause, resume, or re-enable after errors. A revoked connection needs OAuth again."""
    return set_connection_status(session, _get_connection(session, connection_id), payload.status)


@router.delete("/pos-connections/{connection_id}")
def delete_connection(
    connection_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    factory: Callable[[str], PosConnector] = Depends(connector_factory),
):
    """Disconnect: revoke at the POS and drop credentials. Orders are kept."""
    return disconnect_connection(session, factory, _get_connection(session, connection_id))


@router.get("/pos-connections/{connection_id}/runs")
def list_runs(
    connection_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    limit: int = Query(default=20, ge=1, le=200),
):
    _get_connection(session, connection_id)
    rows = session.exec(
        select(PosSyncRun).where(PosSyncRun.connection_id == connection_id)
        .order_by(PosSyncRun.started_at.desc()).limit(limit)
    ).all()
    return [_run(r) for r in rows]


# ----------------------------------------------------------------------
# Orders (read-only)
# ----------------------------------------------------------------------

@router.get("/pos-orders")
def list_pos_orders(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    partner_id: Optional[UUID] = Query(default=None),
    customer_id: Optional[UUID] = Query(default=None),
    unmatched: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(PosOrder)
    count = select(func.count()).select_from(PosOrder)
    filters = []
    if partner_id:
        filters.append(PosOrder.partner_id == partner_id)
    if customer_id:
        filters.append(PosOrder.customer_id == customer_id)
    if unmatched:
        filters.append(PosOrder.customer_id.is_(None))
    for f in filters:
        stmt = stmt.where(f)
        count = count.where(f)
    rows = session.exec(stmt.order_by(PosOrder.ordered_at.desc()).offset(offset).limit(limit)).all()
    return {"total": session.exec(count).one(), "items": [order_json(o) for o in rows]}
