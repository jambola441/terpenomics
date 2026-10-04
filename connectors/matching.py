"""Attach partner orders to Terpee customers.

Three ways an order finds its customer, strongest first:

  link     the POS customer profile on the order was matched before
  phone    the profile's phone number is a Terpee customer's login number
  receipt  the customer uploaded the receipt and claimed it (claim_order)

A return order with none of those inherits the customer of the sale it returns
(matched_via "sale"), so a refund can always be clawed back from the right person.

Every successful match that carries a POS customer id writes a link, so one
receipt claim makes all of that shopper's later orders match on their own.

Unmatched orders are retried for CLAIM_WINDOW_DAYS -- a shopper who signs up a
week after buying still gets the points -- and after that their contact
details are purged. A match is never overwritten by these functions.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional
from uuid import UUID

from sqlmodel import Session, or_, select

from models import Customer, PosCustomerLink, PosOrder

from .store import as_utc, utcnow

CLAIM_WINDOW_DAYS = 30


class ClaimError(ValueError):
    pass


def _record_match(
    session: Session, order: PosOrder, customer_id: UUID, via: str, now: datetime,
    linked: Optional[set] = None,
) -> None:
    """Set the match, and write the POS-customer link if there is not one yet.

    `linked` carries the links already written in this batch: they are pending,
    not yet visible to session.get, and a second insert would collide.
    """
    order.customer_id = customer_id
    order.matched_via = via
    order.matched_at = now
    session.add(order)
    if order.external_customer_id:
        key = (order.connection_id, order.external_customer_id)
        if linked is not None and key in linked:
            return
        if linked is not None:
            linked.add(key)
        link = session.get(PosCustomerLink, key)
        if link is None:
            session.add(PosCustomerLink(
                connection_id=order.connection_id,
                external_customer_id=order.external_customer_id,
                customer_id=customer_id,
                linked_via=via,
            ))


def match_orders(session: Session, orders: Iterable[PosOrder], now: Optional[datetime] = None) -> int:
    """Try link, then phone, on each unmatched order. Returns how many matched."""
    now = now or utcnow()
    pending = [o for o in orders if o.customer_id is None and o.contact_purged_at is None]
    if not pending:
        return 0

    link_keys = {(o.connection_id, o.external_customer_id) for o in pending if o.external_customer_id}
    links: dict[tuple, UUID] = {}
    if link_keys:
        conn_ids = {k[0] for k in link_keys}
        for link in session.exec(select(PosCustomerLink).where(PosCustomerLink.connection_id.in_(conn_ids))).all():
            links[(link.connection_id, link.external_customer_id)] = link.customer_id

    phones = {o.customer_phone for o in pending if o.customer_phone}
    by_phone: dict[str, UUID] = {}
    if phones:
        for c in session.exec(select(Customer).where(Customer.phone.in_(phones))).all():
            by_phone[c.phone] = c.id

    matched = 0
    linked: set = set(links)
    for order in pending:
        key = (order.connection_id, order.external_customer_id)
        if order.external_customer_id and key in links:
            _record_match(session, order, links[key], "link", now, linked)
        elif order.customer_phone and order.customer_phone in by_phone:
            _record_match(session, order, by_phone[order.customer_phone], "phone", now, linked)
            if order.external_customer_id:
                links[key] = by_phone[order.customer_phone]
        else:
            continue
        matched += 1

    # A return belongs to whoever made the sale, whether or not the return
    # itself carries contact details.
    for order in pending:
        if order.customer_id is None and order.kind == "return" and order.source_external_order_id:
            sale = session.exec(select(PosOrder).where(
                PosOrder.connection_id == order.connection_id,
                PosOrder.external_order_id == order.source_external_order_id,
            )).first()
            if sale is not None and sale.customer_id is not None:
                _record_match(session, order, sale.customer_id, "sale", now, linked)
                matched += 1

    session.flush()
    return matched


def rematch_window(session: Session, now: Optional[datetime] = None) -> int:
    """Retry every unmatched order still inside the claim window."""
    now = now or utcnow()
    since = now - timedelta(days=CLAIM_WINDOW_DAYS)
    orders = session.exec(select(PosOrder).where(
        PosOrder.customer_id.is_(None),
        PosOrder.contact_purged_at.is_(None),
        PosOrder.ordered_at >= since,
        or_(PosOrder.customer_phone.is_not(None), PosOrder.external_customer_id.is_not(None),
            PosOrder.kind == "return"),
    )).all()
    return match_orders(session, orders, now)


def purge_expired_contacts(session: Session, now: Optional[datetime] = None) -> int:
    """Drop contact details from orders nobody claimed within the window."""
    now = now or utcnow()
    cutoff = now - timedelta(days=CLAIM_WINDOW_DAYS)
    orders = session.exec(select(PosOrder).where(
        PosOrder.customer_id.is_(None),
        PosOrder.contact_purged_at.is_(None),
        PosOrder.ordered_at < cutoff,
    )).all()
    for order in orders:
        order.customer_phone = order.customer_email = order.external_customer_id = None
        order.raw = None
        order.contact_purged_at = now
        session.add(order)
    session.flush()
    return len(orders)


def claim_order(
    session: Session, order: PosOrder, customer_id: UUID, now: Optional[datetime] = None, via: str = "receipt"
) -> PosOrder:
    """Give an order to a customer who proved they made it (an uploaded receipt).

    Deciding *which* order a receipt is -- reading it, matching store, time and
    total -- is the receipt flow's job. This is the write it ends in, and it
    enforces the rules that hold however the order was found.
    """
    now = now or utcnow()
    if order.customer_id is not None:
        if order.customer_id == customer_id:
            return order
        raise ClaimError("order already belongs to another customer")
    if order.kind != "sale":
        raise ClaimError("only sales can be claimed")
    if order.contact_purged_at is not None or as_utc(order.ordered_at) < now - timedelta(days=CLAIM_WINDOW_DAYS):
        raise ClaimError(f"orders can only be claimed within {CLAIM_WINDOW_DAYS} days")
    _record_match(session, order, customer_id, via, now)
    session.flush()
    return order
