# services/email_sender.py
"""Transactional email: today, only the code that verifies a customer's email.

A customer's email is a contact address, not a way to sign in (phone is), so it
is verified with our own code rather than through Supabase Auth -- Supabase's
email change flow would also mail the placeholder @phone.invalid address that
phone logins carry. See routes/me_email.py.

Swapping vendors means another class with send() and a branch in get_sender();
nothing above this module changes.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = float(os.getenv("EMAIL_TIMEOUT_SECONDS", "10"))


class EmailUnavailable(Exception):
    """Email is not configured, or the provider could not be reached."""


class EmailSender(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class ResendSender:
    """https://resend.com -- one HTTPS call, no SDK."""

    def __init__(self, api_key: str, sender: str):
        self.api_key = api_key
        self.sender = sender

    def send(self, to: str, subject: str, text: str) -> None:
        try:
            resp = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"from": self.sender, "to": [to], "subject": subject, "text": text},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise EmailUnavailable(f"Email provider unreachable: {exc}") from exc
        if resp.status_code >= 300:
            # The body names the problem (unverified domain, bad key); the
            # address itself is not logged.
            logger.warning("Resend rejected a send: %s %s", resp.status_code, resp.text[:300])
            raise EmailUnavailable(f"Email provider returned {resp.status_code}")


def get_sender() -> EmailSender:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise EmailUnavailable("Email is not configured: set RESEND_API_KEY")
    sender = os.getenv("EMAIL_FROM", "Terpenomics <onboarding@resend.dev>")
    return ResendSender(api_key, sender)
