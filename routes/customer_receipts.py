"""Customer side of receipt uploads (/me/receipts) and the partner list to pick from.

See connectors/receipts.py for the rules. A customer uploads a photo and sees
its status; a person in /admin/receipts reads the subtotal and approves it.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from connectors import receipts as svc
from database import get_session
from models import Customer, Partner, ReceiptSubmission
from routes.pos_common import iso
from routes_me import get_current_customer

router = APIRouter(prefix="/me", tags=["me"])


def receipt_json(r: ReceiptSubmission, partner_name: Optional[str], points: Optional[int]) -> dict:
    return {
        "id": str(r.id), "partner_id": str(r.partner_id), "partner_name": partner_name,
        "status": r.status, "purchased_on": r.purchased_on.isoformat() if r.purchased_on else None,
        "customer_note": r.customer_note, "subtotal_cents": r.subtotal_cents, "points": points,
        "reject_reason": r.reject_reason, "created_at": iso(r.created_at), "reviewed_at": iso(r.reviewed_at),
    }


@router.get("/partners")
def list_partners(
    _: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    """Stores where purchases earn Terpee points (to pick when uploading a receipt)."""
    rows = session.exec(select(Partner).where(Partner.is_active.is_(True)).order_by(Partner.name)).all()
    return [{"id": str(p.id), "name": p.name, "logo_url": p.logo_url} for p in rows]


@router.post("/receipts", status_code=201)
async def upload_receipt(
    partner_id: UUID = Form(...),
    purchased_on: Optional[date] = Form(default=None),
    note: Optional[str] = Form(default=None),
    image: UploadFile = File(...),
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    data = await image.read(svc.MAX_IMAGE_BYTES + 1)
    try:
        r = svc.submit(session, customer.id, partner_id, data, image.content_type or "", purchased_on, note)
    except svc.ReceiptError as e:
        raise HTTPException(422, str(e))
    partner = session.get(Partner, r.partner_id)
    return receipt_json(r, partner.name if partner else None, None)


@router.get("/receipts")
def my_receipts(
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(ReceiptSubmission, Partner.name)
        .join(Partner, Partner.id == ReceiptSubmission.partner_id)
        .where(ReceiptSubmission.customer_id == customer.id)
        .order_by(ReceiptSubmission.created_at.desc())
        .limit(50)
    ).all()
    points = svc.receipt_points(session, [r for r, _ in rows])
    return [receipt_json(r, name, points[r.id]) for r, name in rows]
