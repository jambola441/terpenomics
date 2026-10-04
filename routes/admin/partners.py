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
from connectors.oauth_state import sign_state
from connectors.registry import PROVIDERS, get_connector
from connectors.store import as_utc
from connectors.sync import disconnect
from database import get_session
from models import (
    Partner,
    PartnerLocation,
    PosConnection,
    PosConnectionStatus,
    PosOrder,
    PosSyncRun,
)
from .auth import require_admin

router = APIRouter()


def connector_factory() -> Callable[[str], PosConnector]:
    """Overridable in tests, so no request ever reaches a real POS."""
    return get_connector


def _iso(dt: Optional[datetime]) -> Optional[str]:
    dt = as_utc(dt)
    return dt.isoformat() if dt else None


# ----------------------------------------------------------------------
# Serializers
# ----------------------------------------------------------------------

def _partner(p: Partner) -> dict:
    return {
        "id": str(p.id), "name": p.name, "slug": p.slug, "is_active": p.is_active,
        "logo_url": p.logo_url, "created_at": _iso(p.created_at), "updated_at": _iso(p.updated_at),
    }


def _location(loc: PartnerLocation) -> dict:
    return {
        "id": str(loc.id), "partner_id": str(loc.partner_id),
        "connection_id": str(loc.connection_id) if loc.connection_id else None,
        "external_location_id": loc.external_location_id, "name": loc.name,
        "address": loc.address, "timezone": loc.timezone, "is_active": loc.is_active,
    }


def _connection(c: PosConnection) -> dict:
    return {
        "id": str(c.id), "partner_id": str(c.partner_id), "provider": c.provider,
        "status": c.status, "external_merchant_id": c.external_merchant_id,
        "scopes": c.scopes, "has_credentials": bool(c.credentials),
        "token_expires_at": _iso(c.token_expires_at), "sync_cursor": _iso(c.sync_cursor),
        "syncing": c.sync_locked_at is not None, "last_synced_at": _iso(c.last_synced_at),
        "last_error": c.last_error, "consecutive_failures": c.consecutive_failures,
        "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at),
    }


def _run(r: PosSyncRun) -> dict:
    return {
        "id": str(r.id), "connection_id": str(r.connection_id), "status": r.status,
        "since": _iso(r.since), "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at),
        "orders_fetched": r.orders_fetched, "orders_inserted": r.orders_inserted,
        "orders_updated": r.orders_updated, "orders_matched": r.orders_matched, "error": r.error,
    }


def _order(o: PosOrder) -> dict:
    return {
        "id": str(o.id), "partner_id": str(o.partner_id), "connection_id": str(o.connection_id),
        "partner_location_id": str(o.partner_location_id) if o.partner_location_id else None,
        "external_order_id": o.external_order_id, "kind": o.kind,
        "source_external_order_id": o.source_external_order_id, "state": o.state,
        "currency": o.currency, "total_cents": o.total_cents, "tax_cents": o.tax_cents,
        "tip_cents": o.tip_cents, "discount_cents": o.discount_cents, "refunded_cents": o.refunded_cents,
        "customer_id": str(o.customer_id) if o.customer_id else None,
        "matched_via": o.matched_via, "matched_at": _iso(o.matched_at),
        "has_contact": bool(o.customer_phone or o.customer_email),
        "contact_purged_at": _iso(o.contact_purged_at),
        "ordered_at": _iso(o.ordered_at), "closed_at": _iso(o.closed_at),
        "items": [
            {"name": i.name, "variation": i.variation, "quantity": i.quantity, "total_cents": i.total_cents}
            for i in o.items
        ],
    }


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
    return {
        **_partner(partner),
        "locations": [_location(loc) for loc in locations],
        "connections": [_connection(c) for c in connections],
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
    if provider not in PROVIDERS:
        raise HTTPException(404, "unknown provider")
    _get_partner(session, partner_id)
    try:
        connector = factory(provider)
    except Exception as e:
        raise HTTPException(503, f"{provider} is not configured: {e}")
    return {"authorize_url": connector.authorize_url(sign_state(partner_id, provider))}


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
    conn = _get_connection(session, connection_id)
    if conn.status == PosConnectionStatus.revoked.value:
        raise HTTPException(409, "connection was disconnected; reconnect through OAuth")
    conn.status = payload.status
    if payload.status == "active":
        conn.consecutive_failures = 0
    conn.updated_at = datetime.now(timezone.utc)
    session.add(conn)
    session.commit()
    session.refresh(conn)
    return _connection(conn)


@router.delete("/pos-connections/{connection_id}")
def delete_connection(
    connection_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    factory: Callable[[str], PosConnector] = Depends(connector_factory),
):
    """Disconnect: revoke at the POS and drop credentials. Orders are kept."""
    conn = _get_connection(session, connection_id)
    if conn.status == PosConnectionStatus.revoked.value:
        return _connection(conn)
    try:
        connector = factory(conn.provider)
    except Exception as e:
        raise HTTPException(503, f"{conn.provider} is not configured: {e}")
    return _connection(disconnect(session, connector, conn))


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
    return {"total": session.exec(count).one(), "items": [_order(o) for o in rows]}
