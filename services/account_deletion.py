# services/account_deletion.py
"""Deleting a customer's account, as the customer asks from the app.

Apple requires in-app deletion for any app that creates accounts, and the
Privacy Policy promises it. "Deleted" here means nothing left identifies the
person, not that every row is gone:

- The login is deleted outright (the Supabase user, our phone identity rows and
  any outstanding SMS challenges), so the number can sign up again as new.
- The customer row is kept but scrubbed -- name, phone, email and the link to
  the login are cleared -- because purchases, orders and the points ledger
  reference it and are business records. Unspent points are forfeited.
- Open pickup orders are cancelled so no store holds product for nobody.
- Receipt photos and notes are erased; POS customer links are removed and the
  contact details on matched POS orders purged, so a later order at a partner
  can no longer be matched back to this person.
- Consent events stay: they record what someone agreed to and, if they were
  receiving marketing texts, that they withdrew -- which is what keeps a
  recycled number from being texted on old consent.

The Supabase user goes first. If that fails nothing has changed and the
customer can retry; if it succeeds and the database step then fails, the
login is already gone and an admin finishes the rest with this function.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from sqlmodel import Session, delete, select

from models import (
    Customer,
    EmailChallenge,
    Order,
    OrderStatus,
    PhoneAuthChallenge,
    PhoneAuthIdentity,
    PosCustomerLink,
    PosOrder,
    PreferredDispensary,
    ReceiptStatus,
    ReceiptSubmission,
    utcnow,
)
from services import consent, supabase_admin

OPEN_ORDER_STATES = (OrderStatus.submitted, OrderStatus.ready)


def delete_account(session: Session, customer: Customer, request: Optional[Request] = None) -> None:
    """Delete the login and scrub the customer. Commits."""
    if customer.auth_user_id is not None:
        supabase_admin.delete_user(customer.auth_user_id)
    scrub(session, customer, request)
    session.commit()


def scrub(session: Session, customer: Customer, request: Optional[Request] = None) -> None:
    """Everything after the Supabase user: the database half. Does not commit."""
    now = utcnow()
    now_tz = datetime.now(timezone.utc)
    phone = customer.phone

    if customer.marketing_opt_in:
        consent.record(session, customer, consent.MARKETING_SMS, False, "account_deleted", request, now=now)

    for order in session.exec(
        select(Order).where(Order.customer_id == customer.id, Order.status.in_(OPEN_ORDER_STATES))
    ).all():
        order.status = OrderStatus.cancelled
        order.cancelled_at = now
        order.updated_at = now
        session.add(order)

    for receipt in session.exec(select(ReceiptSubmission).where(ReceiptSubmission.customer_id == customer.id)).all():
        receipt.image = None
        receipt.customer_note = None
        receipt.read_result = None
        if receipt.status == ReceiptStatus.pending.value:
            receipt.status = ReceiptStatus.rejected.value
            receipt.reject_reason = "Account deleted"
        session.add(receipt)

    for order in session.exec(select(PosOrder).where(PosOrder.customer_id == customer.id)).all():
        order.customer_phone = None
        order.customer_email = None
        order.external_customer_id = None
        order.contact_purged_at = order.contact_purged_at or now_tz
        session.add(order)

    session.exec(delete(PosCustomerLink).where(PosCustomerLink.customer_id == customer.id))
    session.exec(delete(PreferredDispensary).where(PreferredDispensary.customer_id == customer.id))
    session.exec(delete(EmailChallenge).where(EmailChallenge.customer_id == customer.id))
    if customer.auth_user_id is not None:
        session.exec(delete(PhoneAuthIdentity).where(PhoneAuthIdentity.auth_user_id == customer.auth_user_id))
    if phone:
        session.exec(delete(PhoneAuthChallenge).where(PhoneAuthChallenge.phone == phone))

    customer.name = None
    customer.first_name = None
    customer.last_name = None
    customer.phone = None
    customer.email = None
    customer.auth_user_id = None
    customer.marketing_opt_in = False
    customer.deleted_at = now
    customer.updated_at = now
    session.add(customer)
