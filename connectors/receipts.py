"""Receipt uploads: a customer's photo, a person's reading of it, the points.

The POS sync awards points on its own when it can match an order to a customer.
Receipts cover what it can't: a shopper who didn't give their phone number, or
a partner whose POS isn't connected. A reviewer reads the subtotal (before tax
and tip) off the photo, and that amount earns points by the same rules as a
synced order:

  * POINTS_PER_DOLLAR (1 point per $1), rounded down
  * pending for PENDING_DAYS after the purchase date, then available

Approving writes one points_ledger entry of kind "receipt" with no pos_order_id,
so reconcile_points leaves it alone. Voiding an approved receipt appends the
opposite entry; nothing is ever edited or deleted.

When the partner's POS is connected, the receipt can instead be approved by
picking the synced order it shows (approve_order). The order is claimed for the
customer and earns through reconcile_points from the POS's own amounts, so
refunds and returns adjust it like any matched order, and one sale can't earn
twice. connectors/receipt_reader.py suggests which order that is.

Duplicates are flagged for the reviewer, not blocked: the same customer's other
receipts at the same store around the same date, and synced orders from that
store around the date, especially ones already matched to this customer.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select

from models import Partner, PointsEntry, PosCustomerLink, PosOrder, ReceiptStatus, ReceiptSubmission

from .matching import ClaimError, claim_order
from .points import PENDING_DAYS, points_by_order, points_for, points_per_dollar, reconcile_points
from .receipt_reader import image_hash
from .store import as_utc, utcnow

MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
MAX_PENDING_PER_CUSTOMER = 10
# Receipts older than this are flagged to the reviewer (the same window the
# POS matching allows); they are not refused.
CLAIM_WINDOW_DAYS = 30
DUPLICATE_DAYS = 2


class ReceiptError(ValueError):
    pass


def submit(
    session: Session, customer_id: UUID, partner_id: UUID, image: bytes, content_type: str,
    purchased_on: Optional[date], note: Optional[str], now: Optional[datetime] = None,
) -> ReceiptSubmission:
    now = now or utcnow()
    if not image:
        raise ReceiptError("the photo is empty")
    if len(image) > MAX_IMAGE_BYTES:
        raise ReceiptError("the photo is too large (10 MB max)")
    if content_type not in IMAGE_TYPES:
        raise ReceiptError("upload a photo (JPEG, PNG, WebP or HEIC)")
    partner = session.get(Partner, partner_id)
    if partner is None or not partner.is_active:
        raise ReceiptError("that store isn't a Terpee partner")
    if purchased_on and purchased_on > (now + timedelta(days=1)).date():
        raise ReceiptError("the purchase date is in the future")
    pending = session.exec(select(ReceiptSubmission.id).where(
        ReceiptSubmission.customer_id == customer_id,
        ReceiptSubmission.status == ReceiptStatus.pending.value,
    )).all()
    if len(pending) >= MAX_PENDING_PER_CUSTOMER:
        raise ReceiptError("you have too many receipts waiting for review; try again once they're checked")

    receipt = ReceiptSubmission(
        customer_id=customer_id, partner_id=partner_id, image=image, image_sha256=image_hash(image),
        image_content_type=content_type, purchased_on=purchased_on,
        customer_note=(note or "").strip()[:500] or None, created_at=now,
    )
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt


def _purchase_instant(day: date) -> datetime:
    # Noon UTC, so the pending window doesn't hinge on the shopper's timezone.
    return datetime.combine(day, time(12, 0), tzinfo=timezone.utc)


def approve(
    session: Session, receipt: ReceiptSubmission, subtotal_cents: int, purchased_on: date,
    partner_id: Optional[UUID], reviewer: str, now: Optional[datetime] = None,
) -> ReceiptSubmission:
    now = now or utcnow()
    if receipt.status != ReceiptStatus.pending.value:
        raise ReceiptError(f"this receipt is already {receipt.status}")
    if subtotal_cents <= 0:
        raise ReceiptError("the subtotal must be more than $0")
    if subtotal_cents > 1_000_000:
        raise ReceiptError("that subtotal looks wrong (over $10,000)")
    if purchased_on > (now + timedelta(days=1)).date():
        raise ReceiptError("the purchase date is in the future")
    if partner_id and partner_id != receipt.partner_id:
        if session.get(Partner, partner_id) is None:
            raise ReceiptError("store not found")
        receipt.partner_id = partner_id

    rate = points_per_dollar()
    entry = PointsEntry(
        customer_id=receipt.customer_id, partner_id=receipt.partner_id, pos_order_id=None,
        kind="receipt", points=points_for(subtotal_cents, rate), eligible_cents=subtotal_cents,
        points_per_dollar=rate,
        # Same rule as synced orders: available a week after the purchase, so
        # a receipt uploaded late can be spendable as soon as it's approved.
        available_at=_purchase_instant(purchased_on) + timedelta(days=PENDING_DAYS),
        created_at=now, note=f"receipt {receipt.id}",
    )
    session.add(entry)
    session.flush()

    receipt.status = ReceiptStatus.approved.value
    receipt.subtotal_cents = subtotal_cents
    receipt.purchased_on = purchased_on
    receipt.points_entry_id = entry.id
    receipt.reviewed_by = reviewer
    receipt.reviewed_at = now
    receipt.reject_reason = None
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt


def approve_order(
    session: Session, receipt: ReceiptSubmission, order_id: UUID, reviewer: str, now: Optional[datetime] = None,
) -> ReceiptSubmission:
    """Approve by claiming the synced order the receipt shows. Points come from
    the order (reconcile_points), not from a typed subtotal."""
    now = now or utcnow()
    if receipt.status != ReceiptStatus.pending.value:
        raise ReceiptError(f"this receipt is already {receipt.status}")
    order = session.get(PosOrder, order_id)
    if order is None or order.partner_id != receipt.partner_id:
        raise ReceiptError("that order isn't from this receipt's store")
    if order.state != "completed":
        raise ReceiptError("only completed sales earn points")
    if order.customer_id == receipt.customer_id:
        raise ReceiptError("this sale already earned points for this customer")
    taken = session.exec(select(ReceiptSubmission.id).where(
        ReceiptSubmission.pos_order_id == order.id, ReceiptSubmission.id != receipt.id,
        ReceiptSubmission.status == ReceiptStatus.approved.value,
    )).first()
    if taken:
        raise ReceiptError("another receipt was already approved for this sale")
    try:
        claim_order(session, order, receipt.customer_id, now=now, via="receipt")
    except ClaimError as e:
        raise ReceiptError(str(e)) from e

    receipt.status = ReceiptStatus.approved.value
    receipt.pos_order_id = order.id
    receipt.subtotal_cents = order.total_cents - order.tax_cents - order.tip_cents
    receipt.purchased_on = receipt.purchased_on or as_utc(order.ordered_at).date()
    receipt.reviewed_by = reviewer
    receipt.reviewed_at = now
    receipt.reject_reason = None
    session.add(receipt)
    session.flush()
    reconcile_points(session, now=now, order_ids=[order.id])
    session.commit()
    session.refresh(receipt)
    return receipt


def receipt_points(session: Session, receipts: list[ReceiptSubmission]) -> dict[UUID, Optional[int]]:
    """Points each receipt earned: its own ledger entry, or its order's."""
    by_order = points_by_order(session, [r.pos_order_id for r in receipts if r.pos_order_id])
    entry_ids = [r.points_entry_id for r in receipts if r.points_entry_id]
    entries = {e.id: e.points for e in session.exec(select(PointsEntry).where(PointsEntry.id.in_(entry_ids))).all()} if entry_ids else {}
    out: dict[UUID, Optional[int]] = {}
    for r in receipts:
        if r.pos_order_id:
            out[r.id] = by_order.get(r.pos_order_id, 0)
        elif r.points_entry_id:
            out[r.id] = entries.get(r.points_entry_id)
        else:
            out[r.id] = None
    return out


def reject(session: Session, receipt: ReceiptSubmission, reason: str, reviewer: str,
           now: Optional[datetime] = None) -> ReceiptSubmission:
    now = now or utcnow()
    if receipt.status != ReceiptStatus.pending.value:
        raise ReceiptError(f"this receipt is already {receipt.status}")
    reason = (reason or "").strip()
    if not reason:
        raise ReceiptError("give the customer a reason")
    receipt.status = ReceiptStatus.rejected.value
    receipt.reject_reason = reason[:500]
    receipt.reviewed_by = reviewer
    receipt.reviewed_at = now
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt


def void(session: Session, receipt: ReceiptSubmission, reason: str, reviewer: str,
         now: Optional[datetime] = None) -> ReceiptSubmission:
    """Undo an approval (a mistake, or a duplicate found later): take the points
    back with an opposite entry and mark the receipt rejected."""
    now = now or utcnow()
    if receipt.status != ReceiptStatus.approved.value:
        raise ReceiptError("only an approved receipt can be voided")
    reason = (reason or "").strip()
    if not reason:
        raise ReceiptError("say why it's being voided")
    if receipt.pos_order_id:
        _unclaim(session, receipt, now)
    earned = session.get(PointsEntry, receipt.points_entry_id) if receipt.points_entry_id else None
    if earned is not None and earned.points:
        session.add(PointsEntry(
            customer_id=earned.customer_id, partner_id=earned.partner_id, pos_order_id=None,
            kind="adjust", points=-earned.points, eligible_cents=0,
            points_per_dollar=earned.points_per_dollar,
            # Lands with the points it cancels, like a refund on a synced order.
            available_at=max(now, as_utc(earned.available_at)),
            created_at=now, note=f"receipt {receipt.id} voided: {reason[:200]}",
        ))
    receipt.status = ReceiptStatus.rejected.value
    receipt.reject_reason = reason[:500]
    receipt.reviewed_by = reviewer
    receipt.reviewed_at = now
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt


def _unclaim(session: Session, receipt: ReceiptSubmission, now: datetime) -> None:
    """Give back an order this receipt claimed. reconcile_points then takes its
    points back, because an order whose customer was removed nets to zero."""
    order = session.get(PosOrder, receipt.pos_order_id)
    if order is None or order.customer_id != receipt.customer_id or order.matched_via != "receipt":
        return
    if order.external_customer_id:
        link = session.get(PosCustomerLink, (order.connection_id, order.external_customer_id))
        if link is not None and link.customer_id == receipt.customer_id and link.linked_via == "receipt":
            session.delete(link)
    order.customer_id = None
    order.matched_via = None
    order.matched_at = None
    session.add(order)
    session.flush()
    reconcile_points(session, now=now, order_ids=[order.id])


def possible_duplicates(session: Session, receipt: ReceiptSubmission) -> dict:
    """What a reviewer should look at before approving."""
    day = receipt.purchased_on or as_utc(receipt.created_at).date()
    lo, hi = day - timedelta(days=DUPLICATE_DAYS), day + timedelta(days=DUPLICATE_DAYS)

    receipts = session.exec(select(ReceiptSubmission).where(
        ReceiptSubmission.customer_id == receipt.customer_id,
        ReceiptSubmission.partner_id == receipt.partner_id,
        ReceiptSubmission.id != receipt.id,
        ReceiptSubmission.status != ReceiptStatus.rejected.value,
    )).all()
    receipts = [r for r in receipts if lo <= (r.purchased_on or as_utc(r.created_at).date()) <= hi]

    start, end = _purchase_instant(lo) - timedelta(hours=12), _purchase_instant(hi) + timedelta(hours=12)
    orders = session.exec(select(PosOrder).where(
        PosOrder.partner_id == receipt.partner_id,
        PosOrder.kind == "sale",
        PosOrder.state == "completed",
        PosOrder.ordered_at >= start,
        PosOrder.ordered_at <= end,
    ).order_by(PosOrder.ordered_at)).all()

    return {
        "receipts": receipts,
        "orders": orders,
        "stale": (utcnow().date() - day).days > CLAIM_WINDOW_DAYS,
    }
