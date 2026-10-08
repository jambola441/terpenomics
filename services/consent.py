# services/consent.py
"""What sign-up asks a customer to agree to, and the record of their answers.

The wording lives here, not in the apps: GET /me hands it to the client to
display, and the client echoes back the version it showed. A version that no
longer matches means the screen is stale, and the write is refused rather than
recording agreement to words nobody saw.

Every grant or withdrawal is an append-only ConsentEvent; the columns on
Customer are only the current state. Nothing else should write either.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from fastapi import Request
from sqlmodel import Session

from models import ConsentEvent, Customer, utcnow

# Bump TERMS_VERSION whenever the Terms or Privacy Policy change materially:
# everyone whose accepted version differs is sent back through sign-up.
TERMS_VERSION = os.getenv("TERMS_VERSION", "2026-10-05")
TERMS_URL = os.getenv("TERMS_URL", "")
PRIVACY_URL = os.getenv("PRIVACY_URL", "")

AGE_VERSION = "2026-10-05"
AGE_TEXT = "I am 21 years of age or older."

# Carriers reviewing a 10DLC marketing campaign ask for exactly this: who is
# sending, what, how often, that rates apply, how to stop, and that agreeing is
# not a condition of using the service. Any change to the text needs a new
# version, so the records keep saying what each person actually saw.
MARKETING_SMS_VERSION = "2026-10-08"
MARKETING_SMS_TEXT = (
    "Text me deals and updates from Terpee at the number I signed in with. "
    "Up to 4 msgs/month. Msg & data rates may apply. Reply STOP to opt out, HELP "
    "for help. Consent is not a condition of purchase."
)

TERMS = "terms"
AGE_21 = "age_21"
MARKETING_SMS = "marketing_sms"


def disclosures() -> dict:
    """What a client must show at sign-up, with the versions to echo back."""
    return {
        "terms": {"version": TERMS_VERSION, "terms_url": TERMS_URL or None, "privacy_url": PRIVACY_URL or None},
        "age_21": {"version": AGE_VERSION, "text": AGE_TEXT},
        "marketing_sms": {"version": MARKETING_SMS_VERSION, "text": MARKETING_SMS_TEXT},
    }


def missing(customer: Customer) -> list[str]:
    """Required sign-up steps this customer has not completed, in screen order."""
    out = []
    if not (customer.first_name or "").strip():
        out.append("first_name")
    if customer.age_confirmed_at is None:
        out.append("age_21")
    if customer.terms_version != TERMS_VERSION:
        out.append("terms")
    return out


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def _user_agent(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    return (request.headers.get("user-agent") or "")[:500] or None


def record(
    session: Session,
    customer: Customer,
    kind: str,
    granted: bool,
    source: str,
    request: Optional[Request] = None,
    now: Optional[datetime] = None,
    shown: bool = True,
) -> ConsentEvent:
    """Append one event and update the matching column on the customer.

    The caller commits. Text and version are always the current ones: callers
    check the client's echoed version before getting here. `shown=False` is for
    changes made on someone's behalf (an admin), where no wording was displayed
    and none is claimed.
    """
    now = now or utcnow()
    version, text = {
        TERMS: (TERMS_VERSION, None),
        AGE_21: (AGE_VERSION, AGE_TEXT),
        MARKETING_SMS: (MARKETING_SMS_VERSION, MARKETING_SMS_TEXT),
    }[kind]
    if not shown:
        version, text = None, None

    if kind == TERMS:
        customer.terms_version = TERMS_VERSION if granted else None
        customer.terms_accepted_at = now if granted else None
    elif kind == AGE_21:
        customer.age_confirmed_at = now if granted else None
    elif kind == MARKETING_SMS:
        customer.marketing_opt_in = granted

    event = ConsentEvent(
        customer_id=customer.id,
        kind=kind,
        granted=granted,
        version=version,
        text=text,
        source=source[:64],
        phone=customer.phone if kind == MARKETING_SMS else None,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        created_at=now,
    )
    session.add(event)
    session.add(customer)
    return event
