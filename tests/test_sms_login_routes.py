"""/auth/sms/start and /auth/sms/verify.

The SMS provider and Supabase are both stubbed: what is under test is our own
challenge lifecycle, rate limiting and abuse handling.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from database import engine
from models import PhoneAuthChallenge, PhoneAuthIdentity, utcnow
from routes.auth_sms import router
from services import sms_otp, supabase_admin

PHONE = "(555) 201-0001"


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.sent = []
        self.accepts = "123456"
        self.raise_on_send = None

    def send(self, e164, otp_length):
        if self.raise_on_send:
            raise self.raise_on_send
        self.sent.append((e164, otp_length))
        return f"ref-{len(self.sent)}"

    def check(self, provider_ref, code):
        return code == self.accepts


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (PhoneAuthChallenge, PhoneAuthIdentity):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(sms_otp, "get_provider", lambda: fake)
    return fake


@pytest.fixture
def supabase(monkeypatch):
    state = {"user_id": uuid4(), "sessions": 0}

    def find_or_create_user(e164, known_user_id=None):
        return known_user_id or state["user_id"]

    def issue_session(user_id, e164):
        state["sessions"] += 1
        return {
            "access_token": f"access-{state['sessions']}",
            "refresh_token": f"refresh-{state['sessions']}",
            "token_type": "bearer",
            "expires_in": 3600,
        }

    monkeypatch.setattr(supabase_admin, "find_or_create_user", find_or_create_user)
    monkeypatch.setattr(supabase_admin, "issue_session", issue_session)
    return state


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def start(client, phone=PHONE):
    return client.post("/auth/sms/start", json={"phone": phone})


# ---------------------------
# start
# ---------------------------

def test_start_normalizes_to_e164_before_sending(client, provider):
    resp = start(client)
    assert resp.status_code == 200
    assert provider.sent == [("+15552010001", 6)]
    UUID(resp.json()["challenge_id"])  # a real uuid, not an echo of the phone


def test_start_rejects_an_unusable_number(client, provider):
    resp = start(client, phone="555")
    assert resp.status_code == 400
    assert provider.sent == []


def test_start_enforces_the_resend_cooldown(client, provider):
    assert start(client).status_code == 200
    resp = start(client)
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0
    assert len(provider.sent) == 1


def test_start_caps_sends_per_number_per_hour(client, provider):
    now = utcnow()
    with Session(engine) as session:
        for minutes in (55, 40, 25, 10, 5):
            session.add(
                PhoneAuthChallenge(
                    phone="+15552010001",
                    provider="fake",
                    provider_ref="old",
                    created_at=now - timedelta(minutes=minutes),
                    expires_at=now - timedelta(minutes=minutes - 5),
                )
            )
        session.commit()

    resp = start(client)
    assert resp.status_code == 429
    assert provider.sent == []


def test_start_reports_provider_outage_as_502(client, provider):
    provider.raise_on_send = sms_otp.SmsOtpUnavailable("boom")
    assert start(client).status_code == 502


def test_start_is_503_when_sms_login_is_unconfigured(client, monkeypatch):
    def unconfigured():
        raise sms_otp.SmsOtpUnavailable("not configured")

    monkeypatch.setattr(sms_otp, "get_provider", unconfigured)
    assert start(client).status_code == 503


# ---------------------------
# verify
# ---------------------------

def test_verify_returns_a_session_and_records_the_identity(client, provider, supabase):
    challenge_id = start(client).json()["challenge_id"]

    resp = client.post("/auth/sms/verify", json={"challenge_id": challenge_id, "code": "123456"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["access_token"] == "access-1"
    assert body["refresh_token"] == "refresh-1"
    assert body["user_id"] == str(supabase["user_id"])
    assert resp.headers["cache-control"] == "no-store"

    with Session(engine) as session:
        identity = session.get(PhoneAuthIdentity, "+15552010001")
        assert identity is not None
        assert identity.auth_user_id == supabase["user_id"]


def test_verify_rejects_the_wrong_code(client, provider, supabase):
    challenge_id = start(client).json()["challenge_id"]
    resp = client.post("/auth/sms/verify", json={"challenge_id": challenge_id, "code": "000000"})
    assert resp.status_code == 400
    assert supabase["sessions"] == 0


def test_verify_locks_out_after_repeated_wrong_codes(client, provider, supabase):
    challenge_id = start(client).json()["challenge_id"]
    for _ in range(5):
        client.post("/auth/sms/verify", json={"challenge_id": challenge_id, "code": "000000"})

    # Even the correct code is refused once the attempt budget is spent.
    resp = client.post("/auth/sms/verify", json={"challenge_id": challenge_id, "code": "123456"})
    assert resp.status_code == 400
    assert supabase["sessions"] == 0


def test_a_challenge_cannot_be_replayed(client, provider, supabase):
    challenge_id = start(client).json()["challenge_id"]
    first = client.post("/auth/sms/verify", json={"challenge_id": challenge_id, "code": "123456"})
    assert first.status_code == 200

    replay = client.post("/auth/sms/verify", json={"challenge_id": challenge_id, "code": "123456"})
    assert replay.status_code == 400
    assert supabase["sessions"] == 1


def test_verify_rejects_an_expired_challenge(client, provider, supabase):
    challenge_id = start(client).json()["challenge_id"]
    with Session(engine) as session:
        challenge = session.get(PhoneAuthChallenge, UUID(challenge_id))
        challenge.expires_at = utcnow() - timedelta(seconds=1)
        session.add(challenge)
        session.commit()

    resp = client.post("/auth/sms/verify", json={"challenge_id": challenge_id, "code": "123456"})
    assert resp.status_code == 400
    assert supabase["sessions"] == 0


def test_verify_rejects_an_unknown_challenge_id(client, provider, supabase):
    resp = client.post("/auth/sms/verify", json={"challenge_id": str(uuid4()), "code": "123456"})
    assert resp.status_code == 400


def test_verify_rejects_a_malformed_challenge_id(client, provider, supabase):
    resp = client.post("/auth/sms/verify", json={"challenge_id": "not-a-uuid", "code": "123456"})
    assert resp.status_code == 400


def test_returning_user_keeps_the_same_supabase_user(client, provider, supabase):
    first = start(client).json()["challenge_id"]
    client.post("/auth/sms/verify", json={"challenge_id": first, "code": "123456"})

    # Bypass the resend cooldown the way a later sign-in would.
    with Session(engine) as session:
        challenge = session.get(PhoneAuthChallenge, UUID(first))
        challenge.created_at = utcnow() - timedelta(minutes=10)
        session.add(challenge)
        session.commit()

    second = start(client).json()["challenge_id"]
    resp = client.post("/auth/sms/verify", json={"challenge_id": second, "code": "123456"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(supabase["user_id"])

    with Session(engine) as session:
        identities = session.exec(select(PhoneAuthIdentity)).all()
        assert len(identities) == 1
