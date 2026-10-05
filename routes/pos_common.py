"""What the admin routes (routes/admin/partners.py) and the partner portal
(routes/partner/) share about partners and their POS connections: the response
shapes, and the connection actions both may take.

Credentials are write-only: nothing here ever puts them in a response.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session

from connectors.base import PosConnector
from connectors.oauth_state import sign_state
from connectors.registry import PROVIDERS, get_connector
from connectors.store import as_utc
from connectors.sync import disconnect
from models import Partner, PartnerLocation, PartnerMember, PointsEntry, PosConnection, PosConnectionStatus, PosOrder, PosSyncRun


def connector_factory() -> Callable[[str], PosConnector]:
    """Overridable in tests, so no request ever reaches a real POS."""
    return get_connector


def iso(dt: Optional[datetime]) -> Optional[str]:
    dt = as_utc(dt)
    return dt.isoformat() if dt else None


# ----------------------------------------------------------------------
# Serializers
# ----------------------------------------------------------------------

def partner_json(p: Partner) -> dict:
    return {
        "id": str(p.id), "name": p.name, "slug": p.slug, "is_active": p.is_active,
        "logo_url": p.logo_url, "created_at": iso(p.created_at), "updated_at": iso(p.updated_at),
    }


def location_json(loc: PartnerLocation) -> dict:
    return {
        "id": str(loc.id), "partner_id": str(loc.partner_id),
        "connection_id": str(loc.connection_id) if loc.connection_id else None,
        "external_location_id": loc.external_location_id, "name": loc.name,
        "address": loc.address, "timezone": loc.timezone, "is_active": loc.is_active,
    }


def connection_json(c: PosConnection) -> dict:
    return {
        "id": str(c.id), "partner_id": str(c.partner_id), "provider": c.provider,
        "status": c.status, "external_merchant_id": c.external_merchant_id,
        "scopes": c.scopes, "has_credentials": bool(c.credentials),
        "token_expires_at": iso(c.token_expires_at), "sync_cursor": iso(c.sync_cursor),
        "syncing": c.sync_locked_at is not None, "last_synced_at": iso(c.last_synced_at),
        "last_error": c.last_error, "consecutive_failures": c.consecutive_failures,
        "created_at": iso(c.created_at), "updated_at": iso(c.updated_at),
    }


def run_json(r: PosSyncRun) -> dict:
    return {
        "id": str(r.id), "connection_id": str(r.connection_id), "status": r.status,
        "since": iso(r.since), "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
        "orders_fetched": r.orders_fetched, "orders_inserted": r.orders_inserted,
        "orders_updated": r.orders_updated, "orders_matched": r.orders_matched, "error": r.error,
    }


def member_json(m: PartnerMember) -> dict:
    return {
        "id": str(m.id), "partner_id": str(m.partner_id), "email": m.email,
        "signed_in": m.auth_user_id is not None,
        "invited_at": iso(m.invited_at), "last_login_at": iso(m.last_login_at),
    }


def points_summary_json(session: Session, customer_id: UUID, limit: int = 50) -> dict:
    """A customer's balance and recent ledger entries."""
    from connectors.points import PENDING_DAYS, balance, history, points_per_dollar
    from connectors.store import utcnow

    now = utcnow()
    bal = balance(session, customer_id, now)
    return {
        "available": bal.available,
        "pending": bal.pending,
        "points_per_dollar": points_per_dollar(),
        "pending_days": PENDING_DAYS,
        "entries": [points_entry_json(e, partner_name, now) for e, partner_name in history(session, customer_id, limit)],
    }


def points_entry_json(e: PointsEntry, partner_name: Optional[str], now: datetime) -> dict:
    return {
        "id": str(e.id), "kind": e.kind, "points": e.points,
        "partner_name": partner_name, "pos_order_id": str(e.pos_order_id) if e.pos_order_id else None,
        "eligible_cents": e.eligible_cents, "created_at": iso(e.created_at),
        "available_at": iso(e.available_at), "pending": as_utc(e.available_at) > now,
        "note": e.note,
    }


def order_json(o: PosOrder, *, for_partner: bool = False) -> dict:
    """One order. `for_partner` drops who the shopper is: a partner learns that a
    sale came from a Terpee member, never which member."""
    out = {
        "id": str(o.id), "partner_id": str(o.partner_id), "connection_id": str(o.connection_id),
        "partner_location_id": str(o.partner_location_id) if o.partner_location_id else None,
        "external_order_id": o.external_order_id, "kind": o.kind,
        "source_external_order_id": o.source_external_order_id, "state": o.state,
        "currency": o.currency, "total_cents": o.total_cents, "tax_cents": o.tax_cents,
        "tip_cents": o.tip_cents, "discount_cents": o.discount_cents, "refunded_cents": o.refunded_cents,
        "ordered_at": iso(o.ordered_at), "closed_at": iso(o.closed_at),
        "items": [
            {"name": i.name, "variation": i.variation, "quantity": i.quantity, "total_cents": i.total_cents}
            for i in o.items
        ],
    }
    if for_partner:
        out["is_member"] = o.customer_id is not None
        return out
    out.update({
        "customer_id": str(o.customer_id) if o.customer_id else None,
        "matched_via": o.matched_via, "matched_at": iso(o.matched_at),
        "has_contact": bool(o.customer_phone or o.customer_email),
        "contact_purged_at": iso(o.contact_purged_at),
    })
    return out


# ----------------------------------------------------------------------
# Connection actions
# ----------------------------------------------------------------------

def _build(factory: Callable[[str], PosConnector], provider: str) -> PosConnector:
    try:
        return factory(provider)
    except Exception as e:
        raise HTTPException(503, f"{provider} is not configured: {e}")


def authorize_url(factory: Callable[[str], PosConnector], provider: str, partner_id: UUID, origin: str) -> dict:
    """The POS consent URL. Returned as JSON rather than a redirect: the caller's
    token is a bearer header, which a browser navigation would not carry."""
    if provider not in PROVIDERS:
        raise HTTPException(404, "unknown provider")
    connector = _build(factory, provider)
    return {"authorize_url": connector.authorize_url(sign_state(partner_id, provider, origin=origin))}


def set_connection_status(session: Session, conn: PosConnection, status: str) -> dict:
    """Pause ('disabled'), resume, or re-enable after errors. A revoked connection
    has no credentials left and needs OAuth again."""
    if conn.status == PosConnectionStatus.revoked.value:
        raise HTTPException(409, "connection was disconnected; reconnect through OAuth")
    conn.status = status
    if status == "active":
        conn.consecutive_failures = 0
    conn.updated_at = datetime.now(timezone.utc)
    session.add(conn)
    session.commit()
    session.refresh(conn)
    return connection_json(conn)


def disconnect_connection(session: Session, factory: Callable[[str], PosConnector], conn: PosConnection) -> dict:
    """Revoke at the POS and drop credentials. Orders are kept."""
    if conn.status == PosConnectionStatus.revoked.value:
        return connection_json(conn)
    return connection_json(disconnect(session, _build(factory, conn.provider), conn))
