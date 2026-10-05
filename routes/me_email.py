# routes/me_email.py
"""A customer adding, changing or removing their contact email.

The email is contact information only -- sign-in is by phone -- but it is still
verified: a code goes to the new address and the address is saved only when
the code comes back, so nobody can put someone else's address on their account.
Verified addresses are what /me/link-customer may match on.

    POST   /me/email/start   {email}               -> {challenge_id, expires_in, resend_in}
    POST   /me/email/verify  {challenge_id, code}  -> the /me profile
    DELETE /me/email                               -> the /me profile
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlmodel import Session, select

from database import get_session
from models import Customer, EmailChallenge, utcnow
from routes_me import _serialize_customer, get_current_customer
from services import email_sender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/email", tags=["me"])


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


TTL_SECONDS = _int_env("EMAIL_CODE_TTL_SECONDS", 600)
RESEND_SECONDS = _int_env("EMAIL_CODE_RESEND_SECONDS", 60)
MAX_PER_HOUR = _int_env("EMAIL_CODE_MAX_PER_HOUR", 5)
MAX_ATTEMPTS = _int_env("EMAIL_CODE_MAX_ATTEMPTS", 5)

INVALID_CODE = "That code is wrong or has expired. Request a new one."


def _hash(challenge_id: UUID, code: str) -> str:
    # Salted with the challenge id so equal codes never share a hash. Guessing
    # is bounded by MAX_ATTEMPTS, not by the hash.
    return hashlib.sha256(f"{challenge_id}:{code}".encode()).hexdigest()


def _too_many(detail: str, retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(retry_after, 1))},
    )


def _enforce_send_limits(session: Session, customer_id: UUID, now: datetime) -> None:
    latest = session.exec(
        select(EmailChallenge)
        .where(EmailChallenge.customer_id == customer_id)
        .order_by(EmailChallenge.created_at.desc())
        .limit(1)
    ).first()
    if latest is not None:
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < RESEND_SECONDS:
            raise _too_many("A code was just sent. Wait a moment before requesting another.",
                            int(RESEND_SECONDS - elapsed))
    sent = session.exec(
        select(func.count()).select_from(EmailChallenge).where(
            EmailChallenge.customer_id == customer_id,
            EmailChallenge.created_at >= now - timedelta(hours=1),
        )
    ).one()
    if sent >= MAX_PER_HOUR:
        raise _too_many("Too many codes requested. Try again later.", 900)


def _email_in_use(session: Session, email: str, customer_id: UUID) -> bool:
    return session.exec(
        select(Customer.id).where(Customer.email == email, Customer.id != customer_id)
    ).first() is not None


class StartRequest(BaseModel):
    email: EmailStr


@router.post("/start")
def start_email_change(
    payload: StartRequest,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    email = str(payload.email).strip().lower()
    if email.endswith("@phone.invalid"):
        raise HTTPException(status_code=422, detail="Enter a real email address")
    if email == (customer.email or "").lower():
        raise HTTPException(status_code=409, detail="That is already your email")
    if _email_in_use(session, email, customer.id):
        raise HTTPException(status_code=409, detail="That email is on another account. Contact us if it is yours.")

    now = utcnow()
    _enforce_send_limits(session, customer.id, now)

    try:
        sender = email_sender.get_sender()
    except email_sender.EmailUnavailable:
        raise HTTPException(status_code=503, detail="Email isn't set up yet. Try again later.")

    challenge = EmailChallenge(
        customer_id=customer.id, email=email, code_hash="",
        created_at=now, expires_at=now + timedelta(seconds=TTL_SECONDS),
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge.code_hash = _hash(challenge.id, code)

    try:
        sender.send(
            email,
            f"{code} is your Terpenomics code",
            f"Your Terpenomics verification code is {code}.\n\n"
            f"Enter it in the app to add this email to your account. It expires in "
            f"{TTL_SECONDS // 60} minutes.\n\n"
            "If you didn't ask for this, you can ignore this email.\n",
        )
    except email_sender.EmailUnavailable:
        raise HTTPException(status_code=503, detail="Could not send the email right now. Try again in a minute.")

    # Recorded only once sent, so a failed send does not cost a resend slot.
    session.add(challenge)
    session.commit()
    return {"challenge_id": str(challenge.id), "expires_in": TTL_SECONDS, "resend_in": RESEND_SECONDS}


class VerifyRequest(BaseModel):
    challenge_id: UUID
    code: str


@router.post("/verify")
def verify_email_change(
    payload: VerifyRequest,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    """One generic error for every failure: wrong, expired, used, or not yours."""
    challenge = session.get(EmailChallenge, payload.challenge_id)
    now = utcnow()
    if (
        challenge is None
        or challenge.customer_id != customer.id
        or challenge.consumed_at is not None
        or challenge.expires_at <= now
        or challenge.attempts >= MAX_ATTEMPTS
    ):
        raise HTTPException(status_code=400, detail=INVALID_CODE)

    challenge.attempts += 1
    code = "".join(ch for ch in payload.code if ch.isdigit())
    if not hmac.compare_digest(challenge.code_hash, _hash(challenge.id, code)):
        session.add(challenge)
        session.commit()
        raise HTTPException(status_code=400, detail=INVALID_CODE)

    # Burned before anything else, so a replay cannot apply it twice.
    challenge.consumed_at = now
    session.add(challenge)
    if _email_in_use(session, challenge.email, customer.id):
        session.commit()
        raise HTTPException(status_code=409, detail="That email is on another account. Contact us if it is yours.")

    customer.email = challenge.email
    customer.updated_at = now
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return _serialize_customer(customer)


@router.delete("")
def remove_email(
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    customer.email = None
    customer.updated_at = utcnow()
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return _serialize_customer(customer)
