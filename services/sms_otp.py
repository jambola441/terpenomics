# services/sms_otp.py
"""SMS OTP providers for phone login.

The provider owns the code end to end: it generates, delivers and validates the
OTP, and we only ever see a reference. That is the reason this does not run
through Supabase's Send SMS Hook — that hook hands you a Supabase-generated code
to deliver verbatim, which no provider-validated OTP API can accept. See
SMS_LOGIN.md for the full rationale.

Swapping vendors means implementing SmsOtpProvider and adding a branch to
get_provider(); nothing above this module changes.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Protocol

import httpx

from services.phone import mask, split_e164

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = float(os.getenv("SMS_OTP_TIMEOUT_SECONDS", "10"))


class SmsOtpUnavailable(Exception):
    """The provider could not be reached or is misconfigured. Retryable."""


class SmsOtpRejected(Exception):
    """The provider refused this request (bad number, per-number limit hit)."""


class SmsOtpProvider(Protocol):
    name: str

    def send(self, e164: str, otp_length: int) -> str:
        """Deliver a code and return the provider's reference for it."""

    def check(self, provider_ref: str, code: str) -> bool:
        """Return True if the code is correct, False if it is not."""


# ---------------------------
# Message Central VerifyNow
# ---------------------------

class VerifyNowProvider:
    """https://cpaas.messagecentral.com — provider-generated and -validated OTP.

    Sends from Message Central's pre-registered US sender pool, so no A2P 10DLC
    brand or campaign registration is involved.
    """

    name = "verifynow"

    # Response codes worth distinguishing; everything else is treated as an
    # outage rather than a user error.
    _WRONG_CODE = {702}
    _DEAD_CHALLENGE = {505, 703, 705}
    _RATE_LIMITED = {800}

    def __init__(self, base_url: str, customer_id: str, key: str, email: str | None, country: str | None):
        self._base_url = base_url.rstrip("/")
        self._customer_id = customer_id
        self._key = key
        self._email = email
        self._country = country
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()

    # -- auth token ------------------------------------------------------

    def _fetch_token(self) -> str:
        params = {"customerId": self._customer_id, "key": self._key, "scope": "NEW"}
        if self._email:
            params["email"] = self._email
        if self._country:
            params["country"] = self._country

        try:
            resp = httpx.get(
                f"{self._base_url}/auth/v1/authentication/token",
                params=params,
                timeout=SEND_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise SmsOtpUnavailable(f"VerifyNow token request failed: {exc}") from exc

        if resp.status_code != 200:
            raise SmsOtpUnavailable(f"VerifyNow token request returned {resp.status_code}")

        try:
            body = resp.json() or {}
        except ValueError as exc:
            raise SmsOtpUnavailable("VerifyNow token response was not JSON") from exc

        token = body.get("token")
        if token:
            return token

        # The auth endpoint reports failures as HTTP 200 with an error body
        # (e.g. {"status":400,"error":"password is wrong"}), so surface that
        # text rather than the useless "no token" it would otherwise produce.
        # A wrong VERIFYNOW_KEY is the common cause: it must be the base-64
        # encoding of the account password, not a console API key.
        reason = body.get("error") or body.get("message")
        raise SmsOtpUnavailable(
            f"VerifyNow rejected our credentials: {reason}" if reason
            else "VerifyNow token response contained no token"
        )

    def _auth_header(self, force_refresh: bool = False) -> dict[str, str]:
        with self._token_lock:
            if force_refresh or not self._token or time.time() >= self._token_expires_at:
                self._token = self._fetch_token()
                # The API does not return an expiry; refresh well inside the
                # documented lifetime rather than waiting for a 401.
                self._token_expires_at = time.time() + float(os.getenv("VERIFYNOW_TOKEN_TTL_SECONDS", "1800"))
            return {"authToken": self._token}

    def _request(self, method: str, path: str, params: dict) -> dict:
        for attempt in (1, 2):
            headers = self._auth_header(force_refresh=attempt == 2)
            try:
                resp = httpx.request(
                    method,
                    f"{self._base_url}{path}",
                    params=params,
                    headers=headers,
                    timeout=SEND_TIMEOUT_SECONDS,
                )
            except httpx.HTTPError as exc:
                raise SmsOtpUnavailable(f"VerifyNow {path} failed: {exc}") from exc

            if resp.status_code in (401, 403) and attempt == 1:
                continue  # stale token — refresh once and retry
            try:
                return resp.json() or {}
            except ValueError as exc:
                raise SmsOtpUnavailable(f"VerifyNow {path} returned non-JSON body") from exc

        raise SmsOtpUnavailable(f"VerifyNow {path} rejected our auth token twice")

    # -- provider interface ----------------------------------------------

    def send(self, e164: str, otp_length: int) -> str:
        country_code, national = split_e164(e164)
        body = self._request(
            "POST",
            "/verification/v3/send",
            {
                "countryCode": country_code,
                "customerId": self._customer_id,
                "flowType": "SMS",
                "mobileNumber": national,
                "otpLength": otp_length,
            },
        )

        code = body.get("responseCode")
        data = body.get("data") or {}
        verification_id = data.get("verificationId")

        if code in self._RATE_LIMITED:
            raise SmsOtpRejected("Too many codes requested for this number. Try again later.")
        if code != 200 or not verification_id:
            logger.warning("VerifyNow send failed for %s: responseCode=%s", mask(e164), code)
            if code in (400, 511):
                raise SmsOtpRejected("That number was rejected by our SMS provider.")
            raise SmsOtpUnavailable(f"VerifyNow send returned responseCode {code}")

        return str(verification_id)

    def check(self, provider_ref: str, code: str) -> bool:
        body = self._request(
            "GET",
            "/verification/v3/validateOtp",
            {"verificationId": provider_ref, "code": code},
        )

        response_code = body.get("responseCode")
        data = body.get("data") or {}

        if response_code == 200 and data.get("verificationStatus") == "VERIFICATION_COMPLETED":
            return True
        if response_code in self._WRONG_CODE:
            return False
        if response_code in self._DEAD_CHALLENGE:
            raise SmsOtpRejected("That code has expired. Request a new one.")

        logger.warning("VerifyNow validate returned responseCode=%s", response_code)
        raise SmsOtpUnavailable(f"VerifyNow validate returned responseCode {response_code}")


# ---------------------------
# Wiring
# ---------------------------

_provider: SmsOtpProvider | None = None
_provider_lock = threading.Lock()


def get_provider() -> SmsOtpProvider:
    """Build the configured provider, or raise SmsOtpUnavailable if unset."""
    global _provider
    with _provider_lock:
        if _provider is not None:
            return _provider

        name = os.getenv("SMS_OTP_PROVIDER", "verifynow").strip().lower()
        if name != "verifynow":
            raise SmsOtpUnavailable(f"Unknown SMS_OTP_PROVIDER: {name}")

        customer_id = os.getenv("VERIFYNOW_CUSTOMER_ID")
        key = os.getenv("VERIFYNOW_KEY")
        if not customer_id or not key:
            raise SmsOtpUnavailable("SMS login is not configured (VERIFYNOW_CUSTOMER_ID / VERIFYNOW_KEY)")

        _provider = VerifyNowProvider(
            base_url=os.getenv("VERIFYNOW_BASE_URL", "https://cpaas.messagecentral.com"),
            customer_id=customer_id,
            key=key,
            email=os.getenv("VERIFYNOW_EMAIL"),
            country=os.getenv("VERIFYNOW_COUNTRY"),
        )
        return _provider


def reset_provider_cache() -> None:
    """Test hook: drop the memoized provider so env changes take effect."""
    global _provider
    with _provider_lock:
        _provider = None
