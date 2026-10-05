"""Who may use the partner portal (/partner/*).

A partner login is a `partner_members` row an admin created with an email
address. Signing in with Google as that address is what grants access: Supabase
only issues a Google session for a verified email. On first sign-in the row is
bound to the Supabase user id, and from then on the id is what counts, so the
person keeps access even if the Google account's address later changes.

Accounts created by SMS login carry a placeholder email (<digits>@phone.invalid,
see services/supabase_admin.py); those never match.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlmodel import Session, and_, or_, select

from auth import SupabaseAuthUser, get_current_user, verified_email
from connectors.store import as_utc
from database import get_session
from models import Partner, PartnerMember

# How often a request refreshes last_login_at; every request would be a write.
_LOGIN_TOUCH = timedelta(hours=1)


def memberships(session: Session, user: SupabaseAuthUser) -> list[PartnerMember]:
    """Every partner login this user holds, binding unclaimed invites to them."""
    email = verified_email(user)
    try:
        uid = UUID(user.user_id)
    except ValueError:
        return []
    clauses = [PartnerMember.auth_user_id == uid]
    if email:
        clauses.append(and_(PartnerMember.auth_user_id.is_(None), PartnerMember.email == email))
    rows = list(session.exec(select(PartnerMember).where(or_(*clauses))).all())

    now = datetime.now(timezone.utc)
    changed = False
    for m in rows:
        last = as_utc(m.last_login_at)
        if m.auth_user_id is None or last is None or now - last > _LOGIN_TOUCH:
            m.auth_user_id = m.auth_user_id or uid
            m.last_login_at = now
            session.add(m)
            changed = True
    if changed:
        session.commit()
    return rows


def require_partner_member(
    partner_id: UUID,
    user: SupabaseAuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Partner:
    """The partner named in the path, if the caller holds a login for it.

    Not-a-member and no-such-partner answer the same 404, so the portal cannot be
    used to discover which partners exist.
    """
    if not any(m.partner_id == partner_id for m in memberships(session, user)):
        raise HTTPException(404, "partner not found")
    partner = session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(404, "partner not found")
    return partner
