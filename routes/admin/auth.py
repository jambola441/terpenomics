import os

from fastapi import Depends, HTTPException, status

from auth import SupabaseAuthUser, get_current_user
from services.phone import to_e164


def _admin_phones() -> set[str]:
    """E.164 numbers allowed into /admin, from ADMIN_PHONES.

    Normalized on read so the env var can be written however is convenient
    ("646-260-6799", "+16462606799", "6462606799") and still match the JWT.
    """
    raw = os.getenv("ADMIN_PHONES", "")
    numbers = set()
    for part in raw.replace(";", ",").split(","):
        e164 = to_e164(part.strip())
        if e164:
            numbers.add(e164)
    return numbers


def require_admin(user: SupabaseAuthUser = Depends(get_current_user)) -> SupabaseAuthUser:
    """
    Admin check, in order of preference:
    - phone number allowlist (ADMIN_PHONES) — the phone-login path
    - Supabase JWT claim `role` == "admin"
    - user id allowlist (ADMIN_USER_IDS) — the original email-login path

    The phone claim is the one that survives an account being recreated, so it
    is the preferred way to grant admin now that sign-in is by text.
    """
    # Option A: phone allowlist. The JWT carries the number without a leading
    # "+", so normalize both sides rather than comparing raw strings.
    phones = _admin_phones()
    if phones:
        claimed = to_e164(user.phone) if user.phone else None
        if claimed and claimed in phones:
            return user

    # Option B: claim-based
    if user.role == "admin":
        return user

    # Option C: user id allowlist
    allowlist = {
        x.strip() for x in (os.getenv("ADMIN_USER_IDS", "")).split(",") if x.strip()
    }
    if allowlist and user.user_id in allowlist:
        return user

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
