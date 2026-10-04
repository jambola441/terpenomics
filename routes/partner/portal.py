"""The partner portal: a partner managing their own POS connection.

Partners can connect (OAuth), reconnect, pause/resume and disconnect, and see
their sync history and orders. They cannot rename themselves, change which
locations earn points, or manage logins -- those stay in /admin. Orders say
whether the shopper was a Terpee member, never who.

Every route is scoped by the partner id in the path and checked by
require_partner_member; a connection id from another partner is a 404.
"""
from __future__ import annotations

from typing import Callable, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, func, select

from auth import SupabaseAuthUser, get_current_user
from connectors.base import PosConnector
from database import get_session
from models import Partner, PartnerLocation, PosConnection, PosOrder, PosSyncRun
from routes.pos_common import (
    authorize_url,
    connection_json,
    connector_factory,
    disconnect_connection,
    location_json,
    order_json,
    partner_json,
    run_json,
    set_connection_status,
)

from .auth import memberships, require_partner_member, verified_email

router = APIRouter()


def _connection_of(session: Session, partner: Partner, connection_id: UUID) -> PosConnection:
    conn = session.get(PosConnection, connection_id)
    if conn is None or conn.partner_id != partner.id:
        raise HTTPException(404, "connection not found")
    return conn


@router.get("/me")
def me(
    user: SupabaseAuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """The partners this signed-in person can manage (usually one)."""
    rows = memberships(session, user)
    partners = [session.get(Partner, m.partner_id) for m in rows]
    return {
        "email": verified_email(user) or user.email,
        "partners": sorted((partner_json(p) for p in partners if p), key=lambda p: p["name"]),
    }


@router.get("/partners/{partner_id}")
def get_partner(
    partner: Partner = Depends(require_partner_member),
    session: Session = Depends(get_session),
):
    locations = session.exec(
        select(PartnerLocation).where(PartnerLocation.partner_id == partner.id).order_by(PartnerLocation.name)
    ).all()
    connections = session.exec(select(PosConnection).where(PosConnection.partner_id == partner.id)).all()
    return {
        **partner_json(partner),
        "locations": [location_json(loc) for loc in locations],
        "connections": [connection_json(c) for c in connections],
    }


@router.get("/partners/{partner_id}/oauth/{provider}/start")
def start_oauth(
    provider: str,
    partner: Partner = Depends(require_partner_member),
    factory: Callable[[str], PosConnector] = Depends(connector_factory),
):
    """Square's consent URL; after approving, the browser comes back to /partner."""
    return authorize_url(factory, provider, partner.id, origin="partner")


class ConnectionUpdate(BaseModel):
    status: Literal["active", "disabled"]


@router.patch("/partners/{partner_id}/connections/{connection_id}")
def update_connection(
    connection_id: UUID,
    payload: ConnectionUpdate,
    partner: Partner = Depends(require_partner_member),
    session: Session = Depends(get_session),
):
    return set_connection_status(session, _connection_of(session, partner, connection_id), payload.status)


@router.delete("/partners/{partner_id}/connections/{connection_id}")
def delete_connection(
    connection_id: UUID,
    partner: Partner = Depends(require_partner_member),
    session: Session = Depends(get_session),
    factory: Callable[[str], PosConnector] = Depends(connector_factory),
):
    return disconnect_connection(session, factory, _connection_of(session, partner, connection_id))


@router.get("/partners/{partner_id}/connections/{connection_id}/runs")
def list_runs(
    connection_id: UUID,
    partner: Partner = Depends(require_partner_member),
    session: Session = Depends(get_session),
    limit: int = Query(default=10, ge=1, le=50),
):
    _connection_of(session, partner, connection_id)
    rows = session.exec(
        select(PosSyncRun).where(PosSyncRun.connection_id == connection_id)
        .order_by(PosSyncRun.started_at.desc()).limit(limit)
    ).all()
    return [run_json(r) for r in rows]


@router.get("/partners/{partner_id}/orders")
def list_orders(
    partner: Partner = Depends(require_partner_member),
    session: Session = Depends(get_session),
    members_only: bool = Query(default=False),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    filters = [PosOrder.partner_id == partner.id]
    if members_only:
        filters.append(PosOrder.customer_id.is_not(None))
    stmt = select(PosOrder).where(*filters).order_by(PosOrder.ordered_at.desc()).offset(offset).limit(limit)
    total = session.exec(select(func.count()).select_from(PosOrder).where(*filters)).one()
    return {"total": total, "items": [order_json(o, for_partner=True) for o in session.exec(stmt).all()]}
