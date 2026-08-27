"""VerifyNow client — request shape and responseCode handling.

The wire contract here was taken from Message Central's published API docs, so
these tests are what pins it down: if the vendor changes parameter names or
codes, this is where it should break.
"""

import httpx
import pytest

from services import sms_otp
from services.sms_otp import SmsOtpRejected, SmsOtpUnavailable, VerifyNowProvider


@pytest.fixture
def provider():
    return VerifyNowProvider(
        base_url="https://cpaas.example.test",
        customer_id="C-123",
        key="base64key",
        email="dev@example.test",
        country="US",
    )


@pytest.fixture
def calls(monkeypatch):
    """Capture outbound HTTP and serve canned responses."""
    recorded = []
    queue = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        recorded.append({"method": "GET", "url": url, "params": params or {}, "headers": {}})
        return httpx.Response(200, json={"status": 200, "token": "tok-abc"})

    def fake_request(method, url, params=None, headers=None, timeout=None, **kwargs):
        recorded.append({"method": method, "url": url, "params": params or {}, "headers": headers or {}})
        return queue.pop(0)

    monkeypatch.setattr(sms_otp.httpx, "get", fake_get)
    monkeypatch.setattr(sms_otp.httpx, "request", fake_request)
    return {"recorded": recorded, "queue": queue}


def test_send_uses_documented_parameters(provider, calls):
    calls["queue"].append(
        httpx.Response(200, json={"responseCode": 200, "data": {"verificationId": "9911"}})
    )

    assert provider.send("+15551234567", 6) == "9911"

    send_call = calls["recorded"][-1]
    assert send_call["method"] == "POST"
    assert send_call["url"].endswith("/verification/v3/send")
    assert send_call["params"] == {
        "countryCode": "1",
        "customerId": "C-123",
        "flowType": "SMS",
        "mobileNumber": "5551234567",
        "otpLength": 6,
    }
    assert send_call["headers"]["authToken"] == "tok-abc"


def test_send_surfaces_provider_rate_limit_as_user_error(provider, calls):
    calls["queue"].append(httpx.Response(200, json={"responseCode": 800, "data": {}}))
    with pytest.raises(SmsOtpRejected):
        provider.send("+15551234567", 6)


def test_send_treats_server_error_as_outage(provider, calls):
    calls["queue"].append(httpx.Response(200, json={"responseCode": 500, "data": {}}))
    with pytest.raises(SmsOtpUnavailable):
        provider.send("+15551234567", 6)


def test_check_accepts_completed_verification(provider, calls):
    calls["queue"].append(
        httpx.Response(
            200,
            json={"responseCode": 200, "data": {"verificationStatus": "VERIFICATION_COMPLETED"}},
        )
    )
    assert provider.check("9911", "123456") is True

    call = calls["recorded"][-1]
    assert call["method"] == "GET"
    assert call["url"].endswith("/verification/v3/validateOtp")
    assert call["params"] == {"verificationId": "9911", "code": "123456"}


def test_check_returns_false_for_wrong_code(provider, calls):
    calls["queue"].append(httpx.Response(200, json={"responseCode": 702, "data": {}}))
    assert provider.check("9911", "000000") is False


@pytest.mark.parametrize("code", [505, 703, 705])
def test_check_rejects_dead_challenges(provider, calls, code):
    calls["queue"].append(httpx.Response(200, json={"responseCode": code, "data": {}}))
    with pytest.raises(SmsOtpRejected):
        provider.check("9911", "123456")


def test_token_is_reused_across_calls(provider, calls):
    calls["queue"].append(
        httpx.Response(200, json={"responseCode": 200, "data": {"verificationId": "1"}})
    )
    calls["queue"].append(
        httpx.Response(200, json={"responseCode": 200, "data": {"verificationStatus": "VERIFICATION_COMPLETED"}})
    )

    provider.send("+15551234567", 6)
    provider.check("1", "123456")

    token_calls = [c for c in calls["recorded"] if "authentication/token" in c["url"]]
    assert len(token_calls) == 1


def test_stale_token_is_refreshed_once(provider, calls):
    calls["queue"].append(httpx.Response(401))
    calls["queue"].append(
        httpx.Response(200, json={"responseCode": 200, "data": {"verificationId": "77"}})
    )

    assert provider.send("+15551234567", 6) == "77"
    token_calls = [c for c in calls["recorded"] if "authentication/token" in c["url"]]
    assert len(token_calls) == 2
