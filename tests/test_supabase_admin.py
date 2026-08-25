"""issue_session must never destroy an address the account already has.

find_or_create_user matches on phone alone, so the user being updated may
predate phone login entirely. Overwriting their email with the synthetic one
would silently break their email sign-in — and admin access still depends on
it for accounts that have no phone.
"""
import httpx
import pytest

from services import supabase_admin


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _install(monkeypatch, existing_email, recorder):
    def fake_request(method, url, **kwargs):
        if method == "GET" and "/admin/users/" in url:
            return _FakeResponse(200, {"id": "u1", "email": existing_email})
        if method == "PUT" and "/admin/users/" in url:
            recorder["update"] = kwargs.get("json")
            return _FakeResponse(200, {})
        if method == "POST" and "grant_type=password" in url:
            recorder.setdefault("grants", []).append(kwargs.get("json"))
            return _FakeResponse(200, {"access_token": "at", "refresh_token": "rt"})
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(supabase_admin, "_request", fake_request)


def test_existing_email_is_never_overwritten(monkeypatch):
    rec = {}
    _install(monkeypatch, "owner@example.com", rec)

    supabase_admin.issue_session("11111111-1111-1111-1111-111111111111", "+16462606799")

    assert "email" not in rec["update"], "must not send an email field for an account that has one"
    assert "email_confirm" not in rec["update"]
    assert rec["update"]["password"]
    # The fallback grant must use the address the account actually has.
    assert rec["grants"][0] == {"phone": "+16462606799", "password": rec["update"]["password"]}


def test_missing_email_is_filled_with_the_synthetic_one(monkeypatch):
    rec = {}
    _install(monkeypatch, None, rec)

    supabase_admin.issue_session("11111111-1111-1111-1111-111111111111", "+16462606799")

    assert rec["update"]["email"] == "16462606799@phone.invalid"
    assert rec["update"]["email_confirm"] is True


def test_read_failure_is_reported(monkeypatch):
    def fake_request(method, url, **kwargs):
        return _FakeResponse(500, {})

    monkeypatch.setattr(supabase_admin, "_request", fake_request)
    with pytest.raises(supabase_admin.SupabaseAdminError):
        supabase_admin.issue_session("11111111-1111-1111-1111-111111111111", "+16462606799")
