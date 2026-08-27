# routes/auth_sms.py
"""Phone login: provider-validated SMS OTP, exchanged for a Supabase session.

Flow:
    POST /auth/sms/start   {phone}                 -> {challenge_id, expires_in}
    POST /auth/sms/verify  {challenge_id, code}    -> Supabase session tokens

The browser hands the returned tokens to supabase.auth.setSession(), after which
every existing authenticated route works unchanged — the JWT is an ordinary
Supabase one, verified through JWKS by auth.py.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session, select, func

from database import get_session
from models import PhoneAuthChallenge, PhoneAuthIdentity, utcnow
from services import sms_otp, supabase_admin
from services.phone import mask, to_e164

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sms", tags=["auth-sms"])


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


RESEND_SECONDS      = _int_env("SMS_OTP_RESEND_SECONDS", 60)
CHALLENGE_TTL       = _int_env("SMS_OTP_TTL_SECONDS", 300)
MAX_ATTEMPTS        = _int_env("SMS_OTP_MAX_ATTEMPTS", 5)
MAX_PER_PHONE_HOUR  = _int_env("SMS_OTP_MAX_PER_PHONE_PER_HOUR", 5)
MAX_PER_IP_HOUR     = _int_env("SMS_OTP_MAX_PER_IP_PER_HOUR", 20)
OTP_LENGTH          = _int_env("SMS_OTP_LENGTH", 6)


class StartRequest(BaseModel):
    phone: str = PydanticField(min_length=3, max_length=32)


class StartResponse(BaseModel):
    challenge_id: str
    expires_in: int
    resend_in: int


class VerifyRequest(BaseModel):
    challenge_id: str
    code: str = PydanticField(min_length=3, max_length=12)


class VerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: Optional[int] = None
    user_id: str


def _client_ip(request: Request) -> Optional[str]:
    # Render and most PaaS proxies set X-Forwarded-For; the first hop is the
    # client. Only meaningful when the app is actually behind a trusted proxy,
    # which is why this is used for rate limiting and nothing else.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def _too_many(detail: str, retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(retry_after, 1))},
    )


def _enforce_send_limits(session: Session, phone: str, ip: Optional[str]) -> None:
    now = utcnow()
    hour_ago = now - timedelta(hours=1)

    latest = session.exec(
        select(PhoneAuthChallenge)
        .where(PhoneAuthChallenge.phone == phone)
        .order_by(PhoneAuthChallenge.created_at.desc())
        .limit(1)
    ).first()
    if latest is not None:
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < RESEND_SECONDS:
            raise _too_many(
                "A code was just sent. Wait a moment before requesting another.",
                int(RESEND_SECONDS - elapsed),
            )

    per_phone = session.exec(
        select(func.count())
        .select_from(PhoneAuthChallenge)
        .where(PhoneAuthChallenge.phone == phone, PhoneAuthChallenge.created_at >= hour_ago)
    ).one()
    if per_phone >= MAX_PER_PHONE_HOUR:
        raise _too_many("Too many codes requested for this number. Try again later.", 900)

    if ip:
        per_ip = session.exec(
            select(func.count())
            .select_from(PhoneAuthChallenge)
            .where(PhoneAuthChallenge.request_ip == ip, PhoneAuthChallenge.created_at >= hour_ago)
        ).one()
        if per_ip >= MAX_PER_IP_HOUR:
            raise _too_many("Too many sign-in attempts. Try again later.", 900)


@router.post("/start", response_model=StartResponse)
def start_sms_login(
    payload: StartRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    phone = to_e164(payload.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Enter a valid mobile number.")

    try:
        provider = sms_otp.get_provider()
    except sms_otp.SmsOtpUnavailable as exc:
        logger.error("SMS login unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="SMS sign-in is not available right now.")

    ip = _client_ip(request)
    _enforce_send_limits(session, phone, ip)

    try:
        provider_ref = provider.send(phone, OTP_LENGTH)
    except sms_otp.SmsOtpRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except sms_otp.SmsOtpUnavailable as exc:
        logger.error("SMS send failed for %s: %s", mask(phone), exc)
        raise HTTPException(status_code=502, detail="We couldn't send a code just now. Try again shortly.")

    now = utcnow()
    challenge = PhoneAuthChallenge(
        phone=phone,
        provider=provider.name,
        provider_ref=provider_ref,
        created_at=now,
        expires_at=now + timedelta(seconds=CHALLENGE_TTL),
        request_ip=ip,
    )
    session.add(challenge)
    session.commit()
    session.refresh(challenge)

    logger.info("Sent login code to %s", mask(phone))
    return StartResponse(
        challenge_id=str(challenge.id),
        expires_in=CHALLENGE_TTL,
        resend_in=RESEND_SECONDS,
    )


@router.post("/verify", response_model=VerifyResponse)
def verify_sms_login(
    payload: VerifyRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    # One generic failure for every bad-challenge case, so this endpoint can't
    # be used to probe which numbers or challenge ids exist.
    invalid = HTTPException(status_code=400, detail="That code is incorrect or has expired.")

    try:
        challenge_id = UUID(payload.challenge_id)
    except ValueError:
        raise invalid

    challenge = session.get(PhoneAuthChallenge, challenge_id)

    if challenge is None or challenge.consumed_at is not None:
        raise invalid
    if challenge.expires_at <= utcnow():
        raise invalid
    if challenge.attempts >= MAX_ATTEMPTS:
        raise invalid

    challenge.attempts += 1
    session.add(challenge)
    session.commit()

    try:
        provider = sms_otp.get_provider()
        accepted = provider.check(challenge.provider_ref, payload.code.strip())
    except sms_otp.SmsOtpRejected:
        raise invalid
    except sms_otp.SmsOtpUnavailable as exc:
        logger.error("SMS validation failed for %s: %s", mask(challenge.phone), exc)
        raise HTTPException(status_code=502, detail="We couldn't check that code just now. Try again shortly.")

    if not accepted:
        raise invalid

    # Burn the challenge before minting anything, so a replay of this exact
    # request cannot produce a second session.
    challenge.consumed_at = utcnow()
    session.add(challenge)
    session.commit()

    identity = session.get(PhoneAuthIdentity, challenge.phone)

    try:
        user_id = supabase_admin.find_or_create_user(
            challenge.phone,
            known_user_id=identity.auth_user_id if identity else None,
        )
        supabase_session = supabase_admin.issue_session(user_id, challenge.phone)
    except supabase_admin.SupabaseAdminError as exc:
        logger.error("Session minting failed for %s: %s", mask(challenge.phone), exc)
        raise HTTPException(status_code=502, detail="Signed in, but we couldn't start your session. Try again.")

    now = utcnow()
    if identity is None:
        session.add(
            PhoneAuthIdentity(phone=challenge.phone, auth_user_id=user_id, last_login_at=now)
        )
    else:
        identity.auth_user_id = user_id
        identity.last_login_at = now
        identity.updated_at = now
        session.add(identity)
    session.commit()

    response.headers["Cache-Control"] = "no-store"
    logger.info("Phone login succeeded for %s", mask(challenge.phone))

    return VerifyResponse(
        access_token=supabase_session["access_token"],
        refresh_token=supabase_session.get("refresh_token", ""),
        token_type=supabase_session.get("token_type", "bearer"),
        expires_in=supabase_session.get("expires_in"),
        user_id=str(user_id),
    )
