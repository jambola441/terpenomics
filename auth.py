# auth.py (backend fix: verify Supabase RS256 JWTs via JWKS, NOT publishable/service keys)
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json 
import os 
import jwt
from fastapi import HTTPException, Request as FastAPIRequest, status

SUPABASE_URL = os.getenv("SUPABASE_URL")  # https://<project-ref>.supabase.co
if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is required")

SUPABASE_JWT_AUD = os.getenv("SUPABASE_JWT_AUD", "authenticated")
SUPABASE_JWT_ISSUER = os.getenv("SUPABASE_JWT_ISSUER") or f"{SUPABASE_URL.rstrip('/')}/auth/v1"
JWKS_URL = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"

_JWKS_CACHE: Dict[str, Any] = {"jwks": None, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = int(os.getenv("SUPABASE_JWKS_TTL_SECONDS", "3600"))
ALLOWED_ALGS = {"RS256", "ES256"}


def _fetch_jwks():
    req = Request(JWKS_URL, method="GET")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_jwks() -> Dict[str, Any]:
    now = time.time()
    if _JWKS_CACHE["jwks"] and (now - _JWKS_CACHE["fetched_at"] < _JWKS_TTL_SECONDS):
        return _JWKS_CACHE["jwks"]
    jwks = _fetch_jwks()
    _JWKS_CACHE["jwks"] = jwks
    _JWKS_CACHE["fetched_at"] = now
    return jwks

def _public_key_for_kid_and_alg(kid: str, alg: str):
    jwks = _get_jwks()
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            if alg == "RS256":
                return jwt.algorithms.RSAAlgorithm.from_jwk(k)
            if alg == "ES256":
                return jwt.algorithms.ECAlgorithm.from_jwk(k)
            break

    # retry once on rotation
    _JWKS_CACHE["jwks"] = None
    jwks = _get_jwks()
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            if alg == "RS256":
                return jwt.algorithms.RSAAlgorithm.from_jwk(k)
            if alg == "ES256":
                return jwt.algorithms.ECAlgorithm.from_jwk(k)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No matching JWKS key")


@dataclass(frozen=True)
class SupabaseAuthUser:
    user_id: str
    email: Optional[str]
    phone: Optional[str]
    role: Optional[str]
    raw_claims: Dict[str, Any]


def verify_supabase_jwt(token: str) -> SupabaseAuthUser:
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        kid = header.get("kid")

        if alg not in ALLOWED_ALGS:
            raise HTTPException(status_code=401, detail=f"Unexpected JWT alg: {alg}")
        if not kid:
            raise HTTPException(status_code=401, detail="JWT kid missing")

        public_key = _public_key_for_kid_and_alg(kid, alg)

        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=[alg],
            audience=SUPABASE_JWT_AUD,
            issuer=SUPABASE_JWT_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )

        return SupabaseAuthUser(
            user_id=str(claims.get("sub")),
            email=claims.get("email"),
            phone=claims.get("phone"),
            role=claims.get("role"),
            raw_claims=claims,
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(request: FastAPIRequest) -> SupabaseAuthUser:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    return verify_supabase_jwt(token)
