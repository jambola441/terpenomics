# services/bitpay.py
#
# Minimal BitPay integration for crypto checkout.
#
# Configuration (env vars, loaded via database._load_dotenv from .env):
#   BITPAY_TOKEN            — merchant API token (pos/merchant facade).
#                             TODO(owner): create at Settings → API Tokens in the
#                             BitPay dashboard and set here. Until it is set,
#                             crypto checkout returns 503 and in-store payment
#                             still works.
#   BITPAY_API_BASE         — default "https://test.bitpay.com" (sandbox).
#                             Set to "https://bitpay.com" for production.
#   BITPAY_NOTIFICATION_URL — public URL of the IPN webhook, i.e.
#                             "<api-origin>/customer/orders/bitpay/ipn".
#                             Optional: without it, order status is updated by
#                             the frontend polling the refresh-payment endpoint.
#
# BitPay invoice API reference: https://developer.bitpay.com/reference/invoices

import os
from typing import Any, Optional

import requests

BITPAY_API_BASE = os.getenv("BITPAY_API_BASE", "https://test.bitpay.com").rstrip("/")
BITPAY_TOKEN = os.getenv("BITPAY_TOKEN")
BITPAY_NOTIFICATION_URL = os.getenv("BITPAY_NOTIFICATION_URL")

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Accept-Version": "2.0.0",
}

# BitPay invoice statuses:
#   new → paid (tx seen) → confirmed (enough confirmations) → complete (settled)
#   expired (15-min window passed), invalid (paid but rejected)
PAID_STATUSES = {"paid", "confirmed", "complete"}
DEAD_STATUSES = {"expired", "invalid"}


class BitPayError(Exception):
    pass


class BitPayNotConfigured(BitPayError):
    pass


def is_configured() -> bool:
    return bool(BITPAY_TOKEN)


def create_invoice(
    *,
    price_cents: int,
    order_id: str,
    buyer_email: Optional[str] = None,
    redirect_url: Optional[str] = None,
) -> dict[str, Any]:
    """Create a hosted BitPay invoice; returns {"id", "url", "status"}."""
    if not BITPAY_TOKEN:
        raise BitPayNotConfigured("BITPAY_TOKEN is not set")

    payload: dict[str, Any] = {
        "token": BITPAY_TOKEN,
        "price": round(price_cents / 100.0, 2),
        "currency": "USD",
        "orderId": order_id,
        "extendedNotifications": True,
    }
    if BITPAY_NOTIFICATION_URL:
        payload["notificationURL"] = BITPAY_NOTIFICATION_URL
    if redirect_url:
        payload["redirectURL"] = redirect_url
    if buyer_email:
        payload["buyer"] = {"email": buyer_email}

    try:
        resp = requests.post(
            f"{BITPAY_API_BASE}/invoices", json=payload, headers=_HEADERS, timeout=20
        )
    except requests.RequestException as e:
        raise BitPayError(f"BitPay request failed: {e}") from e

    if resp.status_code >= 400:
        raise BitPayError(f"BitPay invoice creation failed ({resp.status_code}): {resp.text[:500]}")

    data = resp.json().get("data") or {}
    if not data.get("id") or not data.get("url"):
        raise BitPayError(f"Unexpected BitPay response: {resp.text[:500]}")
    return {"id": data["id"], "url": data["url"], "status": data.get("status", "new")}


def get_invoice(invoice_id: str) -> dict[str, Any]:
    """Fetch an invoice from BitPay. Used to verify IPNs and for polling —
    never trust status carried in an IPN body."""
    if not BITPAY_TOKEN:
        raise BitPayNotConfigured("BITPAY_TOKEN is not set")

    try:
        resp = requests.get(
            f"{BITPAY_API_BASE}/invoices/{invoice_id}",
            params={"token": BITPAY_TOKEN},
            headers=_HEADERS,
            timeout=20,
        )
    except requests.RequestException as e:
        raise BitPayError(f"BitPay request failed: {e}") from e

    if resp.status_code >= 400:
        raise BitPayError(f"BitPay invoice fetch failed ({resp.status_code}): {resp.text[:500]}")

    data = resp.json().get("data") or {}
    if not data.get("id"):
        raise BitPayError(f"Unexpected BitPay response: {resp.text[:500]}")
    return data
