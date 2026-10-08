"""issue_session: keep other devices signed in, and never destroy an address.

Changing a user's password through the admin API deletes every session the
user has, so phone login must only write the password when the exchange fails,
not on every login. The fake below behaves that way: a grant succeeds only with
the password currently on the account, and a password change clears the
account's sessions.

find_or_create_user matches on phone alone, so the user being updated may
predate phone login entirely. Overwriting their email with the synthetic one
would silently break their email sign-in — and admin access still depends on
it for accounts that have no phone.
"""
import pytest

from services import supabase_admin

USER = "11111111-1111-1111-1111-111111111111"
PHONE = "+16462606799"


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeSupabase:
    """One account, as GoTrue keeps it. The Phone provider is off, as the
    setup guide recommends, so only the email grant can succeed."""

    def __init__(self, email, password="set-at-creation"):
        self.email = email
        self.password = password
        self.sessions = 1  # signed in on some other device
        self.updates = []
        self.grants = []

    def request(self, method, url, **kwargs):
        body = kwargs.get("json") or {}
        if method == "GET" and "/admin/users/" in url:
            return _FakeResponse(200, {"id": USER, "email": self.email})
        if method == "PUT" and "/admin/users/" in url:
            self.updates.append(body)
            if "email" in body:
                self.email = body["email"]
            if "password" in body:
                self.password = body["password"]
                self.sessions = 0  # GoTrue: UpdatePassword(tx, nil) logs out every session
            return _FakeResponse(200, {})
        if method == "POST" and "grant_type=password" in url:
            self.grants.append(body)
            if body.get("email") == self.email and body.get("password") == self.password:
                self.sessions += 1
                return _FakeResponse(200, {"access_token": "at", "refresh_token": "rt"})
            return _FakeResponse(400, {"error": "invalid_grant"})
        raise AssertionError(f"unexpected {method} {url}")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")


def _install(monkeypatch, fake):
    monkeypatch.setattr(supabase_admin, "_request", fake.request)
    return fake


def test_repeat_login_leaves_other_devices_signed_in(monkeypatch, env):
    fake = _install(monkeypatch, _FakeSupabase("16462606799@phone.invalid"))
    fake.password = supabase_admin.login_password(USER, "service-role-key")

    session = supabase_admin.issue_session(USER, PHONE)

    assert session["access_token"] == "at"
    assert fake.updates == [], "a working password must not be rewritten"
    assert fake.sessions == 2, "the other device's session must survive"


def test_first_login_sets_the_password_once_then_stops(monkeypatch, env):
    fake = _install(monkeypatch, _FakeSupabase("16462606799@phone.invalid"))

    supabase_admin.issue_session(USER, PHONE)
    assert len(fake.updates) == 1
    assert fake.updates[0]["password"] == supabase_admin.login_password(USER, "service-role-key")

    supabase_admin.issue_session(USER, PHONE)
    assert len(fake.updates) == 1, "the second login must not write the password again"
    assert fake.sessions == 2


def test_password_is_stable_per_user_and_differs_between_users():
    a = supabase_admin.login_password(USER, "k")
    assert a == supabase_admin.login_password(USER, "k")
    assert a != supabase_admin.login_password("22222222-2222-2222-2222-222222222222", "k")
    assert a != supabase_admin.login_password(USER, "another-key")


def test_existing_email_is_never_overwritten(monkeypatch, env):
    fake = _install(monkeypatch, _FakeSupabase("owner@example.com"))

    supabase_admin.issue_session(USER, PHONE)

    update = fake.updates[0]
    assert "email" not in update, "must not send an email field for an account that has one"
    assert "email_confirm" not in update
    # The fallback grant must use the address the account actually has.
    assert fake.grants[-1] == {"email": "owner@example.com", "password": update["password"]}


def test_missing_email_is_filled_with_the_synthetic_one(monkeypatch, env):
    fake = _install(monkeypatch, _FakeSupabase(None))

    supabase_admin.issue_session(USER, PHONE)

    assert fake.updates[0]["email"] == "16462606799@phone.invalid"
    assert fake.updates[0]["email_confirm"] is True


def test_refused_after_setting_the_password_is_reported(monkeypatch, env):
    class Refusing(_FakeSupabase):
        def request(self, method, url, **kwargs):
            if method == "POST" and "grant_type=password" in url:
                return _FakeResponse(400, {"error": "invalid_grant"})
            return super().request(method, url, **kwargs)

    _install(monkeypatch, Refusing("owner@example.com"))
    with pytest.raises(supabase_admin.SupabaseAdminError):
        supabase_admin.issue_session(USER, PHONE)


def test_read_failure_is_reported(monkeypatch, env):
    def fake_request(method, url, **kwargs):
        return _FakeResponse(500, {})

    monkeypatch.setattr(supabase_admin, "_request", fake_request)
    with pytest.raises(supabase_admin.SupabaseAdminError):
        supabase_admin.issue_session(USER, PHONE)
