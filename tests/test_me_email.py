"""Changing a customer's contact email: emailed code, verified before saved."""
import re
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import Customer, EmailChallenge, utcnow
from routes import me_email
from routes.me_email import router as me_email_router
from routes_me import router as me_router
from services import email_sender

AUTH_UID = uuid4()


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (EmailChallenge, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
        session.add(Customer(first_name="Ada", phone="+15552010001", auth_user_id=AUTH_UID))
        session.commit()
    yield


class FakeSender:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, text):
        self.sent.append((to, subject, text))

    def last_code(self):
        return re.search(r"\b(\d{6})\b", self.sent[-1][2]).group(1)


@pytest.fixture
def outbox(monkeypatch):
    sender = FakeSender()
    monkeypatch.setattr(email_sender, "get_sender", lambda: sender)
    return sender


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(me_router)
    app.include_router(me_email_router)
    app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
        user_id=str(AUTH_UID), email=None, phone="15552010001", role="authenticated", raw_claims={},
    )
    return TestClient(app)


def _start(client, email="Ada@Example.com"):
    return client.post("/me/email/start", json={"email": email})


def test_code_sets_the_email(client, outbox):
    res = _start(client)
    assert res.status_code == 200
    assert outbox.sent[0][0] == "ada@example.com"
    me = client.post("/me/email/verify", json={"challenge_id": res.json()["challenge_id"], "code": outbox.last_code()})
    assert me.status_code == 200 and me.json()["email"] == "ada@example.com"


def test_nothing_is_saved_without_the_code(client, outbox):
    res = _start(client)
    bad = client.post("/me/email/verify", json={"challenge_id": res.json()["challenge_id"], "code": "000000"
                      if outbox.last_code() != "000000" else "111111"})
    assert bad.status_code == 400
    assert client.get("/me").json()["email"] is None


def test_code_is_single_use_and_never_stored(client, outbox):
    cid = _start(client).json()["challenge_id"]
    code = outbox.last_code()
    assert client.post("/me/email/verify", json={"challenge_id": cid, "code": code}).status_code == 200
    assert client.post("/me/email/verify", json={"challenge_id": cid, "code": code}).status_code == 400
    with Session(engine) as s:
        assert code not in s.exec(select(EmailChallenge)).one().code_hash


def test_attempts_are_capped(client, outbox):
    cid = _start(client).json()["challenge_id"]
    code = outbox.last_code()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(me_email.MAX_ATTEMPTS):
        client.post("/me/email/verify", json={"challenge_id": cid, "code": wrong})
    assert client.post("/me/email/verify", json={"challenge_id": cid, "code": code}).status_code == 400


def test_expired_code_fails(client, outbox):
    cid = _start(client).json()["challenge_id"]
    with Session(engine) as s:
        ch = s.exec(select(EmailChallenge)).one()
        ch.expires_at = utcnow() - timedelta(seconds=1)
        s.add(ch)
        s.commit()
    assert client.post("/me/email/verify", json={"challenge_id": cid, "code": outbox.last_code()}).status_code == 400


def test_another_customers_challenge_is_not_usable(client, outbox):
    with Session(engine) as s:
        other = Customer(first_name="Grace", phone="+15552010002")
        s.add(other)
        s.flush()
        ch = EmailChallenge(customer_id=other.id, email="g@example.com", code_hash="",
                            expires_at=utcnow() + timedelta(minutes=5))
        ch.code_hash = me_email._hash(ch.id, "123456")
        s.add(ch)
        s.commit()
        cid = str(ch.id)
    assert client.post("/me/email/verify", json={"challenge_id": cid, "code": "123456"}).status_code == 400
    assert client.get("/me").json()["email"] is None


def test_email_on_another_account_is_refused(client, outbox):
    with Session(engine) as s:
        s.add(Customer(first_name="Grace", phone="+15552010002", email="taken@example.com"))
        s.commit()
    assert _start(client, "taken@example.com").status_code == 409
    assert outbox.sent == []


def test_resend_cooldown(client, outbox):
    assert _start(client).status_code == 200
    res = _start(client, "other@example.com")
    assert res.status_code == 429 and int(res.headers["Retry-After"]) > 0


def test_not_configured_is_a_clear_503(client, monkeypatch):
    def unavailable():
        raise email_sender.EmailUnavailable("no key")
    monkeypatch.setattr(email_sender, "get_sender", unavailable)
    res = _start(client)
    assert res.status_code == 503
    with Session(engine) as s:
        assert s.exec(select(EmailChallenge)).all() == []


def test_remove_email(client, outbox):
    cid = _start(client).json()["challenge_id"]
    client.post("/me/email/verify", json={"challenge_id": cid, "code": outbox.last_code()})
    assert client.delete("/me/email").json()["email"] is None


def test_placeholder_address_is_refused(client, outbox):
    assert _start(client, "15552010001@phone.invalid").status_code == 422


def test_resend_wire_format(monkeypatch):
    calls = []

    class Resp:
        status_code = 200
        text = "{}"

    monkeypatch.setattr(email_sender.httpx, "post", lambda url, **kw: calls.append((url, kw)) or Resp())
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "Terpenomics <codes@example.com>")
    email_sender.get_sender().send("ada@example.com", "subj", "body")
    url, kw = calls[0]
    assert url == "https://api.resend.com/emails"
    assert kw["headers"]["Authorization"] == "Bearer re_test"
    assert kw["json"] == {"from": "Terpenomics <codes@example.com>", "to": ["ada@example.com"],
                          "subject": "subj", "text": "body"}

    Resp.status_code = 403
    with pytest.raises(email_sender.EmailUnavailable):
        email_sender.get_sender().send("ada@example.com", "subj", "body")


def test_no_key_means_unavailable(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with pytest.raises(email_sender.EmailUnavailable):
        email_sender.get_sender()
