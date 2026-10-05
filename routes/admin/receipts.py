"""Admin review queue for customer receipt uploads.

A reviewer opens a pending receipt and approves it, either by picking the
synced POS order it matches (the order earns the points) or by confirming the
subtotal (before tax and tip), store and date. Or rejects it with a reason the
customer sees. Each receipt comes with what the receipt reader found (Claude's
reading, matching POS orders, flags). See connectors/receipts.py and
connectors/receipt_reader.py.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field as PydField
from sqlmodel import Session, func, select

from auth import SupabaseAuthUser
from connectors import receipt_reader, receipts as svc
from connectors.points import PENDING_DAYS, points_per_dollar
from database import get_session
from models import Customer, Partner, ReceiptSubmission
from routes.pos_common import iso
from .auth import require_admin

router = APIRouter()


def _reviewer(user: SupabaseAuthUser) -> str:
    return user.email or user.phone or user.user_id


def _summary(r: ReceiptSubmission, customer: Optional[Customer], partner: Optional[Partner],
             points: Optional[int]) -> dict:
    return {
        "id": str(r.id), "status": r.status,
        "customer_id": str(r.customer_id),
        "customer_name": customer.name if customer else None,
        "customer_phone": customer.phone if customer else None,
        "partner_id": str(r.partner_id), "partner_name": partner.name if partner else None,
        "purchased_on": r.purchased_on.isoformat() if r.purchased_on else None,
        "customer_note": r.customer_note, "subtotal_cents": r.subtotal_cents, "points": points,
        "reject_reason": r.reject_reason, "reviewed_by": r.reviewed_by,
        "reviewed_at": iso(r.reviewed_at), "created_at": iso(r.created_at),
        "image_content_type": r.image_content_type,
        "pos_order_id": str(r.pos_order_id) if r.pos_order_id else None,
        "read_status": "read" if r.read_result is not None else ("failed" if r.read_error else "pending"),
    }


def _get(session: Session, receipt_id: UUID) -> ReceiptSubmission:
    r = session.get(ReceiptSubmission, receipt_id)
    if r is None:
        raise HTTPException(404, "receipt not found")
    return r


@router.get("/receipts")
def list_receipts(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    status: Literal["pending", "approved", "rejected", "all"] = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    counts = dict(session.exec(
        select(ReceiptSubmission.status, func.count()).group_by(ReceiptSubmission.status)
    ).all())
    stmt = (
        select(ReceiptSubmission, Customer, Partner)
        .join(Customer, Customer.id == ReceiptSubmission.customer_id)
        .join(Partner, Partner.id == ReceiptSubmission.partner_id)
    )
    if status != "all":
        stmt = stmt.where(ReceiptSubmission.status == status)
    # Oldest first while reviewing, so nobody waits longest; newest first otherwise.
    order = ReceiptSubmission.created_at.asc() if status == "pending" else ReceiptSubmission.created_at.desc()
    rows = session.exec(stmt.order_by(order).offset(offset).limit(limit)).all()
    points = svc.receipt_points(session, [r for r, _, _ in rows])
    return {
        "counts": {k: counts.get(k, 0) for k in ("pending", "approved", "rejected")},
        "items": [_summary(r, c, p, points[r.id]) for r, c, p in rows],
    }


def _order_json(o) -> dict:
    tenders = (o.raw or {}).get("tenders") or []
    cards = [((t.get("card_details") or {}).get("card") or {}) for t in tenders if isinstance(t, dict)]
    return {
        "id": str(o.id), "ordered_at": iso(o.ordered_at), "total_cents": o.total_cents,
        "tax_cents": o.tax_cents, "tip_cents": o.tip_cents,
        "subtotal_cents": o.total_cents - o.tax_cents - o.tip_cents,
        "cards": [f"{c.get('card_brand') or 'CARD'} {c.get('last_4')}" for c in cards if c.get("last_4")],
    }


def _candidate_json(c: dict) -> dict:
    return {**_order_json(c["order"]), "score": c["score"], "signals": c["signals"],
            "strength": c["strength"], "claimed": c["claimed"]}


def _reading_json(session: Session, r: ReceiptSubmission) -> dict:
    rv = receipt_reader.review(session, r)
    return {
        "read": rv["read"], "read_model": rv["read_model"], "read_at": iso(rv["read_at"]),
        "read_error": rv["read_error"], "has_pos": rv["has_pos"],
        "candidates": [_candidate_json(c) for c in rv["candidates"]],
        "best_order_id": str(rv["best"]["order"].id) if rv["best"] else None,
        "flags": rv["flags"], "suggestion": rv["suggestion"],
    }


@router.get("/receipts/{receipt_id}")
def get_receipt(
    receipt_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    r = _get(session, receipt_id)
    points = svc.receipt_points(session, [r])[r.id]
    dupes = svc.possible_duplicates(session, r)
    partners = session.exec(select(Partner).order_by(Partner.name)).all()
    return {
        **_summary(r, session.get(Customer, r.customer_id), session.get(Partner, r.partner_id), points),
        "points_per_dollar": points_per_dollar(),
        "pending_days": PENDING_DAYS,
        "stale": dupes["stale"],
        "partners": [{"id": str(p.id), "name": p.name} for p in partners],
        "duplicate_receipts": [
            {"id": str(d.id), "status": d.status,
             "purchased_on": d.purchased_on.isoformat() if d.purchased_on else None,
             "subtotal_cents": d.subtotal_cents, "created_at": iso(d.created_at)}
            for d in dupes["receipts"]
        ],
        "nearby_orders": [
            {"id": str(o.id), "ordered_at": iso(o.ordered_at), "total_cents": o.total_cents,
             "subtotal_cents": o.total_cents - o.tax_cents - o.tip_cents,
             "same_customer": o.customer_id == r.customer_id, "matched": o.customer_id is not None}
            for o in dupes["orders"]
        ],
        "reading": _reading_json(session, r),
    }


@router.get("/receipts/{receipt_id}/image")
def receipt_image(
    receipt_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    r = _get(session, receipt_id)
    if not r.image:
        raise HTTPException(404, "no image")
    return Response(content=r.image, media_type=r.image_content_type,
                    headers={"Cache-Control": "private, max-age=3600"})


class ApproveBody(BaseModel):
    """Either the synced order the receipt matches, or a subtotal and date."""
    pos_order_id: Optional[UUID] = None
    subtotal_cents: Optional[int] = PydField(default=None, gt=0)
    purchased_on: Optional[date] = None
    partner_id: Optional[UUID] = None


class ReasonBody(BaseModel):
    reason: str


def _act(fn):
    try:
        return fn()
    except svc.ReceiptError as e:
        msg = str(e)
        raise HTTPException(409 if "already" in msg or "only an approved" in msg or "another customer" in msg else 422, msg)


@router.post("/receipts/{receipt_id}/approve")
def approve_receipt(
    receipt_id: UUID,
    body: ApproveBody,
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
):
    r = _get(session, receipt_id)
    if body.pos_order_id:
        _act(lambda: svc.approve_order(session, r, body.pos_order_id, _reviewer(user)))
    elif body.subtotal_cents and body.purchased_on:
        _act(lambda: svc.approve(session, r, body.subtotal_cents, body.purchased_on, body.partner_id, _reviewer(user)))
    else:
        raise HTTPException(422, "give the matching order, or the subtotal and purchase date")
    return get_receipt(receipt_id, session, user)


@router.post("/receipts/{receipt_id}/reject")
def reject_receipt(
    receipt_id: UUID,
    body: ReasonBody,
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
):
    r = _get(session, receipt_id)
    _act(lambda: svc.reject(session, r, body.reason, _reviewer(user)))
    return get_receipt(receipt_id, session, user)


@router.post("/receipts/{receipt_id}/void")
def void_receipt(
    receipt_id: UUID,
    body: ReasonBody,
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
):
    r = _get(session, receipt_id)
    _act(lambda: svc.void(session, r, body.reason, _reviewer(user)))
    return get_receipt(receipt_id, session, user)
