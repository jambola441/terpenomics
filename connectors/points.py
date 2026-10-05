"""Terpee points from partner orders.

The rules:

  * Only completed sales matched to a customer earn.
  * The eligible amount is the order total minus tax and tip. A refund or return
    removes its share in proportion: refunding half of a $20 order removes half
    of what it earned.
  * 1 point per $1 of eligible spend (POINTS_PER_DOLLAR), rounded down.
  * Points are pending for PENDING_DAYS after the purchase, then usable, so a
    refund inside that window cancels them before they can be spent.
  * Rules that could change later (the rate, and whether the partner and
    location earn at all) are read when an order first earns. After that the
    order keeps them, so changing a setting never rewrites past earnings. Only
    the order's own amounts (refunds, returns) move it afterwards.

The ledger (points_ledger) is append-only. reconcile_points works out what each
order should be worth now, compares that with what is already recorded for it,
and appends the difference. Running it twice changes nothing; running it after
a refund syncs writes exactly one negative entry.
"""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional
from uuid import UUID

from sqlmodel import Session, func, or_, select

from models import Partner, PartnerLocation, PointsEntry, PosOrder

from .store import as_utc, utcnow

PENDING_DAYS = 7


def points_per_dollar() -> int:
    try:
        return max(0, int(os.getenv("POINTS_PER_DOLLAR", "1")))
    except ValueError:
        return 1


def eligible_cents(sale: PosOrder, returns: Iterable[PosOrder] = ()) -> int:
    """Total minus tax and tip, less the share refunded or returned."""
    if sale.kind != "sale" or sale.state != "completed" or sale.total_cents <= 0:
        return 0
    net = sale.total_cents - sale.tax_cents - sale.tip_cents
    if net <= 0:
        return 0
    returned = sum(r.total_cents for r in returns if r.state == "completed")
    kept = max(0, sale.total_cents - sale.refunded_cents - returned)
    return net * kept // sale.total_cents


def points_for(cents: int, rate: int) -> int:
    return cents * rate // 100


def _purchase_time(sale: PosOrder) -> datetime:
    return as_utc(sale.closed_at) or as_utc(sale.ordered_at)


def reconcile_points(
    session: Session, now: Optional[datetime] = None, order_ids: Optional[Iterable[UUID]] = None
) -> int:
    """Bring the ledger in line with partner orders. Returns entries written.

    Looks at every sale that has a customer or already has ledger entries (an
    order whose customer was removed must have its points taken back), or just
    `order_ids` when given.
    """
    now = now or utcnow()
    has_entries = select(PointsEntry.pos_order_id).where(PointsEntry.pos_order_id.is_not(None))
    stmt = select(PosOrder).where(
        PosOrder.kind == "sale",
        or_(PosOrder.customer_id.is_not(None), PosOrder.id.in_(has_entries)),
    )
    if order_ids is not None:
        ids = list(order_ids)
        if not ids:
            return 0
        stmt = stmt.where(PosOrder.id.in_(ids))
    sales = list(session.exec(stmt).all())
    if not sales:
        return 0

    # Returns that point at these sales.
    returns: dict[tuple, list[PosOrder]] = defaultdict(list)
    for r in session.exec(select(PosOrder).where(
        PosOrder.kind == "return",
        PosOrder.connection_id.in_({s.connection_id for s in sales}),
        PosOrder.source_external_order_id.in_({s.external_order_id for s in sales}),
    )).all():
        returns[(r.connection_id, r.source_external_order_id)].append(r)

    entries: dict[UUID, list[PointsEntry]] = defaultdict(list)
    for e in session.exec(select(PointsEntry).where(
        PointsEntry.pos_order_id.in_([s.id for s in sales])
    ).order_by(PointsEntry.created_at)).all():
        entries[e.pos_order_id].append(e)

    location_active = {
        loc.id: loc.is_active for loc in session.exec(select(PartnerLocation).where(
            PartnerLocation.id.in_({s.partner_location_id for s in sales if s.partner_location_id})
        )).all()
    }
    partner_active = {
        p.id: p.is_active for p in session.exec(select(Partner).where(
            Partner.id.in_({s.partner_id for s in sales})
        )).all()
    }

    written = 0
    for sale in sales:
        recorded = entries.get(sale.id, [])
        if recorded:
            rate = recorded[0].points_per_dollar
        else:
            # Not earned yet: this is when the earn rules apply.
            if not partner_active.get(sale.partner_id, False):
                continue
            if sale.partner_location_id and not location_active.get(sale.partner_location_id, True):
                continue
            rate = points_per_dollar()

        sale_returns = returns.get((sale.connection_id, sale.external_order_id), [])
        cents = eligible_cents(sale, sale_returns)
        target = {sale.customer_id: points_for(cents, rate)} if sale.customer_id else {}

        held: dict[UUID, int] = defaultdict(int)
        latest_earn_available: dict[UUID, datetime] = {}
        for e in recorded:
            held[e.customer_id] += e.points
            if e.points > 0:
                at = as_utc(e.available_at)
                if e.customer_id not in latest_earn_available or at > latest_earn_available[e.customer_id]:
                    latest_earn_available[e.customer_id] = at

        for customer_id in set(held) | set(target):
            diff = target.get(customer_id, 0) - held.get(customer_id, 0)
            if diff == 0:
                continue
            if diff > 0:
                kind = "earn" if customer_id not in held else "adjust"
                available_at = _purchase_time(sale) + timedelta(days=PENDING_DAYS)
            else:
                refunded = sale.refunded_cents > 0 or any(r.state == "completed" for r in sale_returns)
                kind = "refund" if refunded and customer_id in target else "adjust"
                # A take-back lands with the points it cancels: while those are
                # still pending, so is the take-back, and the available balance
                # never dips below zero for points nobody could spend yet.
                pending_until = latest_earn_available.get(customer_id)
                available_at = max(now, pending_until) if pending_until else now
            session.add(PointsEntry(
                customer_id=customer_id,
                pos_order_id=sale.id,
                partner_id=sale.partner_id,
                kind=kind,
                points=diff,
                eligible_cents=cents if customer_id in target else 0,
                points_per_dollar=rate,
                available_at=available_at,
                created_at=now,
            ))
            written += 1

    session.flush()
    return written


@dataclass
class Balance:
    available: int
    pending: int

    @property
    def total(self) -> int:
        return self.available + self.pending


def balance(session: Session, customer_id: UUID, now: Optional[datetime] = None) -> Balance:
    now = now or utcnow()
    rows = session.exec(select(PointsEntry.points, PointsEntry.available_at).where(
        PointsEntry.customer_id == customer_id
    )).all()
    available = sum(p for p, at in rows if as_utc(at) <= now)
    pending = sum(p for p, at in rows if as_utc(at) > now)
    return Balance(available=available, pending=pending)


def history(session: Session, customer_id: UUID, limit: int = 50) -> list[tuple[PointsEntry, Optional[str]]]:
    """Newest entries first, each with its partner's name."""
    rows = session.exec(
        select(PointsEntry, Partner.name)
        .join(Partner, Partner.id == PointsEntry.partner_id, isouter=True)
        .where(PointsEntry.customer_id == customer_id)
        .order_by(PointsEntry.created_at.desc())
        .limit(limit)
    ).all()
    return [(e, name) for e, name in rows]


def points_by_order(session: Session, order_ids: Iterable[UUID]) -> dict[UUID, int]:
    ids = list(order_ids)
    if not ids:
        return {}
    rows = session.exec(
        select(PointsEntry.pos_order_id, func.sum(PointsEntry.points))
        .where(PointsEntry.pos_order_id.in_(ids))
        .group_by(PointsEntry.pos_order_id)
    ).all()
    return {oid: int(total) for oid, total in rows}
