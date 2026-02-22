# routes_me.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from auth import SupabaseAuthUser, get_current_user
from database import get_session
from models import Customer, Purchase

router = APIRouter(prefix="/me", tags=["me"])


# ---------------------------
# Helpers
# ---------------------------

def get_current_customer(
    user: SupabaseAuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Customer:
    try:
        auth_user_id = UUID(user.user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid auth user id")

    customer = session.exec(
        select(Customer).where(Customer.auth_user_id == auth_user_id)
    ).first()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not linked. Call /me/link-customer first.",
        )

    return customer


# ---------------------------
# Link customer endpoint
# ---------------------------

class LinkCustomerRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    marketing_opt_in: Optional[bool] = None


@router.post("/link-customer")
def link_customer(
    payload: LinkCustomerRequest,
    user: SupabaseAuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        auth_user_id = UUID(user.user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Supabase user_id is not a UUID")

    existing_link = session.exec(
        select(Customer).where(Customer.auth_user_id == auth_user_id)
    ).first()

    if existing_link:
        return {"customer_id": str(existing_link.id), "linked": True}

    phone = (payload.phone or user.phone or "").strip() or None
    email = (payload.email or user.email or "").strip().lower() or None

    if not phone and not email:
        raise HTTPException(status_code=400, detail="Provide phone or email")

    customer = None
    if phone:
        customer = session.exec(select(Customer).where(Customer.phone == phone)).first()
    if not customer and email:
        customer = session.exec(select(Customer).where(Customer.email == email)).first()

    if customer:
        if customer.auth_user_id and customer.auth_user_id != auth_user_id:
            raise HTTPException(status_code=409, detail="Customer already linked")

        customer.auth_user_id = auth_user_id
        if payload.name and not customer.name:
            customer.name = payload.name
        if payload.marketing_opt_in is not None:
            customer.marketing_opt_in = payload.marketing_opt_in
        customer.last_visit_at = customer.last_visit_at or datetime.utcnow()
        customer.updated_at = datetime.utcnow()

        session.add(customer)
        session.commit()
        session.refresh(customer)
        return {"customer_id": str(customer.id), "linked": True, "created": False}

    new_customer = Customer(
        name=payload.name,
        phone=phone,
        email=email,
        auth_user_id=auth_user_id,
        marketing_opt_in=bool(payload.marketing_opt_in)
        if payload.marketing_opt_in is not None
        else False,
        last_visit_at=datetime.utcnow(),
    )
    session.add(new_customer)
    session.commit()
    session.refresh(new_customer)
    return {"customer_id": str(new_customer.id), "linked": True, "created": True}


# ---------------------------
# GET /me — customer profile
# ---------------------------

@router.get("")
def get_me(customer: Customer = Depends(get_current_customer)):
    return {
        "id": str(customer.id),
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "marketing_opt_in": customer.marketing_opt_in,
    }


# ---------------------------
# GET /me/purchases
# ---------------------------

@router.get("/purchases")
def get_my_purchases(
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    purchases = session.exec(
        select(Purchase).where(Purchase.customer_id == customer.id)
    ).all()

    return [
        {
            "id": str(p.id),
            "purchased_at": p.purchased_at,
            "total_amount_cents": p.total_amount_cents,
            "source": p.source,
        }
        for p in purchases
    ]


# ---------------------------
# GET /me/preferences (placeholder)
# ---------------------------

@router.get("/preferences")
def get_preferences(customer: Customer = Depends(get_current_customer)):
    """
    Placeholder until terpene scoring is implemented.
    """
    return {
        "top_terpenes": [],
        "message": "Preference scoring not implemented yet"
    }
