# services/supabase_admin.py
"""Server-side Supabase user management and session minting.

Phone login is validated by the SMS provider, not by Supabase, so Supabase never
issues the session on its own. Once the provider confirms the code we find or
create the matching Supabase user with the service-role key, rotate a
server-held password onto it, and exchange that password for a real session that
the browser can adopt. The password is generated here, never returned to the
client, and replaced on every login, so a leaked one is useless by the next
sign-in.

Everything downstream (auth.py, /me, admin routes) keeps verifying ordinary
Supabase JWTs via JWKS — this module does not mint tokens itself.
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Any
from uuid import UUID

import httpx

from services.phone import mask

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = float(os.getenv("SUPABASE_ADMIN_TIMEOUT_SECONDS", "10"))
# Cold-start fallback only: the local phone_auth_identities table is the normal
# lookup path. Bounded so a large user base cannot turn this into a full scan.
MAX_SCAN_PAGES = int(os.getenv("SUPABASE_ADMIN_SCAN_PAGES", "5"))
SCAN_PAGE_SIZE = 200


class SupabaseAdminError(Exception):
    """A Supabase admin or token call failed."""


def _config() -> tuple[str, str, str]:
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_SERVICE_ROLE_KEY", service_key),
            ("SUPABASE_ANON_KEY", anon_key),
        )
        if not value
    ]
    if missing:
        raise SupabaseAdminError("SMS login is not configured: missing " + ", ".join(missing))
    return url.rstrip("/"), service_key, anon_key


def _admin_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def synthetic_email(e164: str) -> str:
    """A never-deliverable address so the user has an email-based login path.

    .invalid is reserved by RFC 2606 and can never resolve, so this cannot
    collide with or shadow a real address.
    """
    return f"{e164.lstrip('+')}@phone.invalid"


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    try:
        return httpx.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
    except httpx.HTTPError as exc:
        raise SupabaseAdminError(f"Supabase request failed: {exc}") from exc


def _find_user_id_by_phone(base_url: str, service_key: str, e164: str) -> UUID | None:
    headers = _admin_headers(service_key)
    wanted = e164.lstrip("+")

    def matches(user: dict[str, Any]) -> bool:
        return (user.get("phone") or "").lstrip("+") == wanted

    # GoTrue's filter is a substring search across email/phone; treat it as a
    # hint and still confirm the match ourselves.
    resp = _request(
        "GET",
        f"{base_url}/auth/v1/admin/users",
        headers=headers,
        params={"page": 1, "per_page": SCAN_PAGE_SIZE, "filter": wanted},
    )
    if resp.status_code == 200:
        for user in (resp.json() or {}).get("users", []):
            if matches(user):
                return UUID(user["id"])

    for page in range(1, MAX_SCAN_PAGES + 1):
        resp = _request(
            "GET",
            f"{base_url}/auth/v1/admin/users",
            headers=headers,
            params={"page": page, "per_page": SCAN_PAGE_SIZE},
        )
        if resp.status_code != 200:
            raise SupabaseAdminError(f"Listing Supabase users returned {resp.status_code}")
        users = (resp.json() or {}).get("users", [])
        for user in users:
            if matches(user):
                return UUID(user["id"])
        if len(users) < SCAN_PAGE_SIZE:
            return None

    logger.warning("Gave up scanning Supabase users for %s after %d pages", mask(e164), MAX_SCAN_PAGES)
    return None


def find_or_create_user(e164: str, known_user_id: UUID | None = None) -> UUID:
    """Return the Supabase user id for this phone number, creating it if needed.

    `known_user_id` comes from our local phone_auth_identities mapping and skips
    the lookup entirely on repeat logins.
    """
    base_url, service_key, _ = _config()

    if known_user_id is not None:
        return known_user_id

    resp = _request(
        "POST",
        f"{base_url}/auth/v1/admin/users",
        headers=_admin_headers(service_key),
        json={
            "phone": e164,
            "phone_confirm": True,
            "email": synthetic_email(e164),
            "email_confirm": True,
            "password": secrets.token_urlsafe(48),
            "user_metadata": {"phone_login": True},
        },
    )

    if resp.status_code in (200, 201):
        return UUID((resp.json() or {})["id"])

    # 422 = already registered. Fall through to a lookup.
    if resp.status_code in (400, 422):
        existing = _find_user_id_by_phone(base_url, service_key, e164)
        if existing is not None:
            return existing

    raise SupabaseAdminError(
        f"Could not create or locate a Supabase user for {mask(e164)} "
        f"(status {resp.status_code})"
    )


def _current_email(base_url: str, service_key: str, user_id: UUID) -> str | None:
    """The address already on the account, or None if it has none."""
    resp = _request(
        "GET",
        f"{base_url}/auth/v1/admin/users/{user_id}",
        headers=_admin_headers(service_key),
    )
    if resp.status_code != 200:
        raise SupabaseAdminError(f"Reading the Supabase user returned {resp.status_code}")
    return (resp.json() or {}).get("email") or None


def issue_session(user_id: UUID, e164: str) -> dict[str, Any]:
    """Rotate a fresh password onto the user and exchange it for a session."""
    base_url, service_key, anon_key = _config()
    password = secrets.token_urlsafe(48)

    # Never overwrite an address the account already has. find_or_create_user
    # matches on phone alone, so the user we are about to update may predate
    # phone login entirely — clobbering their email with the synthetic one
    # would silently destroy their email sign-in, and with it any admin access
    # that depends on it. Only fill in an address when there is none.
    existing_email = _current_email(base_url, service_key, user_id)
    email = existing_email or synthetic_email(e164)

    update: dict[str, Any] = {
        "password": password,
        "phone": e164,
        "phone_confirm": True,
    }
    if existing_email is None:
        update["email"] = email
        update["email_confirm"] = True

    resp = _request(
        "PUT",
        f"{base_url}/auth/v1/admin/users/{user_id}",
        headers=_admin_headers(service_key),
        json=update,
    )
    if resp.status_code != 200:
        raise SupabaseAdminError(f"Rotating the login password returned {resp.status_code}")

    token_headers = {"apikey": anon_key, "Content-Type": "application/json"}
    token_url = f"{base_url}/auth/v1/token?grant_type=password"

    # Prefer the phone grant; fall back to the synthetic email so this keeps
    # working with the dashboard's Phone provider switched off (we do not use
    # Supabase's own SMS, so there is no reason for it to be on).
    for payload in ({"phone": e164, "password": password}, {"email": email, "password": password}):
        resp = _request("POST", token_url, headers=token_headers, json=payload)
        if resp.status_code == 200:
            session = resp.json() or {}
            if session.get("access_token"):
                return session

    raise SupabaseAdminError(
        f"Supabase refused to issue a session for {mask(e164)} (status {resp.status_code})"
    )
