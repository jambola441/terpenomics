"""The only code that writes partner locations and partner orders.

Upserts are keyed on the POS's own ids, so re-reading an order -- the sync
overlap, a manual re-run, a later refund -- rewrites one row rather than adding
another. Matching state is never touched here; matching.py owns it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from sqlmodel import Session, select

from models import PartnerLocation, PosConnection, PosOrder, PosOrderItem

from .base import ExternalLocation, NormalizedOrder


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands timestamptz back naive; Postgres does not. Treat naive as UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def import_locations(
    session: Session, connection: PosConnection, locations: Iterable[ExternalLocation]
) -> dict[str, UUID]:
    """Upsert the POS's locations; return external id -> partner_locations.id.

    Name, address and timezone follow the POS. `is_active` is taken from the POS
    only when a location is first seen: after that it is an admin's decision and
    a sync must not undo it.
    """
    existing = {
        loc.external_location_id: loc
        for loc in session.exec(
            select(PartnerLocation).where(PartnerLocation.connection_id == connection.id)
        ).all()
    }
    now = utcnow()
    for ext in locations:
        row = existing.get(ext.external_id)
        if row is None:
            row = PartnerLocation(
                partner_id=connection.partner_id,
                connection_id=connection.id,
                external_location_id=ext.external_id,
                name=ext.name,
                is_active=ext.is_active,
            )
            existing[ext.external_id] = row
        row.name = ext.name
        row.address = ext.address
        row.timezone = ext.timezone
        row.updated_at = now
        session.add(row)
    session.flush()
    return {ext_id: row.id for ext_id, row in existing.items()}


def upsert_orders(
    session: Session,
    connection: PosConnection,
    orders: Iterable[NormalizedOrder],
    location_ids: dict[str, UUID],
) -> tuple[list[PosOrder], int, int]:
    """Write a batch of orders. Returns (rows touched, inserted, updated)."""
    batch = list(orders)
    if not batch:
        return [], 0, 0

    ext_ids = [o.external_order_id for o in batch]
    existing = {
        row.external_order_id: row
        for row in session.exec(
            select(PosOrder).where(
                PosOrder.connection_id == connection.id,
                PosOrder.external_order_id.in_(ext_ids),
            )
        ).all()
    }

    now = utcnow()
    touched: list[PosOrder] = []
    inserted = updated = 0
    for o in batch:
        row = existing.get(o.external_order_id)
        if row is None:
            row = PosOrder(
                connection_id=connection.id,
                partner_id=connection.partner_id,
                external_order_id=o.external_order_id,
                state=o.state,
                ordered_at=o.ordered_at,
                external_updated_at=o.external_updated_at,
            )
            existing[o.external_order_id] = row
            inserted += 1
        else:
            updated += 1

        row.partner_location_id = location_ids.get(o.external_location_id) if o.external_location_id else None
        row.external_location_id = o.external_location_id
        row.kind = o.kind
        row.source_external_order_id = o.source_external_order_id
        row.state = o.state
        row.currency = o.currency
        row.total_cents = o.total_cents
        row.tax_cents = o.tax_cents
        row.tip_cents = o.tip_cents
        row.discount_cents = o.discount_cents
        row.refunded_cents = o.refunded_cents
        row.ordered_at = o.ordered_at
        row.closed_at = o.closed_at
        row.external_updated_at = o.external_updated_at
        row.last_synced_at = now

        # Past the claim window, an unmatched order's contact details were
        # deliberately dropped. A later refund re-fetches the order; it must not
        # bring them back.
        if row.contact_purged_at is not None and row.customer_id is None:
            row.external_customer_id = row.customer_phone = row.customer_email = None
            row.raw = None
        else:
            row.external_customer_id = o.external_customer_id
            row.customer_phone = o.customer_phone
            row.customer_email = o.customer_email
            row.raw = o.raw

        row.items.clear()
        for line in o.lines:
            row.items.append(PosOrderItem(
                external_line_id=line.external_line_id,
                external_sku=line.external_sku,
                name=line.name,
                variation=line.variation,
                quantity=line.quantity,
                total_cents=line.total_cents,
            ))
        session.add(row)
        touched.append(row)

    session.flush()
    return touched, inserted, updated
