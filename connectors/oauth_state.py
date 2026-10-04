"""The OAuth `state` parameter: which partner a callback belongs to, tamper-proof.

The callback is an unauthenticated browser redirect from the POS, so it cannot
carry an admin token. Instead the admin-only /start endpoint signs the partner
id into `state`, and the callback trusts only a state that verifies and has not
expired. Stateless: nothing to store or clean up.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional
from uuid import UUID

STATE_TTL_SECONDS = 15 * 60


class InvalidState(ValueError):
    pass


def _secret() -> bytes:
    explicit = os.getenv("POS_OAUTH_STATE_SECRET")
    if explicit:
        return explicit.encode()
    key = os.getenv("POS_CREDENTIALS_KEY")
    if not key:
        raise InvalidState("POS_OAUTH_STATE_SECRET (or POS_CREDENTIALS_KEY) is not set")
    # Derived rather than reused, so the signing key is never the encryption key.
    return hmac.new(key.encode(), b"pos-oauth-state", hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# Where the connect flow started, so the callback can send the browser back there.
ORIGINS = ("admin", "partner")


def sign_state(partner_id: UUID, provider: str, now: Optional[float] = None, origin: str = "admin") -> str:
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {ORIGINS}")
    now = time.time() if now is None else now
    payload = {
        "p": str(partner_id),
        "v": provider,
        "e": int(now) + STATE_TTL_SECONDS,
        "n": secrets.token_urlsafe(8),
        "o": origin,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_state(state: str, provider: str, now: Optional[float] = None) -> UUID:
    """Return the partner id the state was issued for, or raise InvalidState."""
    return read_state(state, provider, now)[0]


def read_state(state: str, provider: str, now: Optional[float] = None) -> tuple[UUID, str]:
    """Return (partner id, origin) for a valid state, or raise InvalidState."""
    now = time.time() if now is None else now
    try:
        body, sig = state.split(".", 1)
    except ValueError:
        raise InvalidState("malformed state")
    expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise InvalidState("bad signature")
    try:
        payload = json.loads(_unb64(body))
        partner_id = UUID(payload["p"])
    except (ValueError, KeyError, TypeError):
        raise InvalidState("malformed state")
    if payload.get("v") != provider:
        raise InvalidState("state was issued for another provider")
    if payload.get("e", 0) < now:
        raise InvalidState("state expired")
    origin = payload.get("o", "admin")
    return partner_id, origin if origin in ORIGINS else "admin"
