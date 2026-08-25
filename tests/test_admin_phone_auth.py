"""Admin access by phone number.

Sign-in is by text now, so admin is granted on the JWT's phone claim. The
claim carries the number without a leading "+", so both sides are normalized
rather than compared as raw strings.
"""
import pytest
from fastapi import HTTPException

from auth import SupabaseAuthUser
from routes.admin.auth import require_admin


def _user(phone=None, role="authenticated", user_id="u1"):
    return SupabaseAuthUser(user_id=user_id, email=None, phone=phone, role=role, raw_claims={})


@pytest.mark.parametrize("configured", ["+16462606799", "6462606799", "646-260-6799"])
def test_phone_allowlist_accepts_however_it_is_written(monkeypatch, configured):
    monkeypatch.setenv("ADMIN_PHONES", configured)
    # The JWT claim has no leading "+".
    assert require_admin(_user(phone="16462606799")).user_id == "u1"


def test_other_numbers_are_rejected(monkeypatch):
    monkeypatch.setenv("ADMIN_PHONES", "+16462606799")
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_admin(_user(phone="15551234567"))
    assert exc.value.status_code == 403


def test_missing_phone_claim_is_rejected(monkeypatch):
    monkeypatch.setenv("ADMIN_PHONES", "+16462606799")
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    with pytest.raises(HTTPException):
        require_admin(_user(phone=None))


def test_existing_user_id_allowlist_still_works(monkeypatch):
    """Email-only admins must keep working until they have phone access."""
    monkeypatch.delenv("ADMIN_PHONES", raising=False)
    monkeypatch.setenv("ADMIN_USER_IDS", "abc-123")
    assert require_admin(_user(user_id="abc-123")).user_id == "abc-123"


def test_role_claim_still_works(monkeypatch):
    monkeypatch.delenv("ADMIN_PHONES", raising=False)
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    assert require_admin(_user(role="admin")).role == "admin"
