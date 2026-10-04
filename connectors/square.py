"""Square: OAuth code flow, Locations, Orders search, Customers bulk-retrieve.

Env:
  SQUARE_APPLICATION_ID       the app's client id (Developer Console)
  SQUARE_APPLICATION_SECRET   the app's OAuth secret
  SQUARE_ENVIRONMENT          "production" (default) or "sandbox"
  SQUARE_API_VERSION          Square-Version header; pinned so a Square release
                              cannot change response shapes under us

Facts this relies on (developer.squareup.com, checked 2026-10):
  * Code-flow access tokens last 30 days; the refresh token does not expire
    until revoked. The token response carries `expires_at` (RFC 3339) and
    `merchant_id`.
  * SearchOrders takes at most 10 location ids and 1000 results per page. When
    sorting by a timestamp, the sort field must match the date_time_filter field
    -- hence UPDATED_AT for both.
  * An itemized return is its own order whose `returns[].source_order_id` names
    the sale. Whether the sale itself is also edited is not documented, so both
    shapes are captured: `refunds` on any order -> refunded_cents, and return
    orders -> kind="return" with the source id.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional
from urllib.parse import urlencode

import httpx

from services.phone import to_e164

from .base import (
    AuthError,
    ConnectorError,
    ExternalLocation,
    NormalizedLine,
    NormalizedOrder,
    OAuthGrant,
)

log = logging.getLogger("connectors.square")

DEFAULT_API_VERSION = "2026-09-16"
SCOPES = "MERCHANT_PROFILE_READ ORDERS_READ CUSTOMERS_READ"

BASE_URLS = {
    "production": "https://connect.squareup.com",
    "sandbox": "https://connect.squareupsandbox.com",
}

MAX_LOCATIONS_PER_SEARCH = 10
PAGE_LIMIT = 500
MAX_CUSTOMERS_PER_LOOKUP = 100
MAX_ATTEMPTS = 4

# Refunds that did not happen. PENDING counts as refunded: for points it is
# safer to hold back early than to claw back late.
_DEAD_REFUND_STATUSES = {"REJECTED", "FAILED"}


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _cents(money: Optional[dict]) -> int:
    return int((money or {}).get("amount") or 0)


def _chunks(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


class SquareConnector:
    provider = "square"

    def __init__(
        self,
        application_id: str,
        application_secret: str,
        environment: str = "production",
        api_version: str = DEFAULT_API_VERSION,
        transport: Optional[httpx.BaseTransport] = None,
        sleep=time.sleep,
    ):
        if environment not in BASE_URLS:
            raise ValueError(f"SQUARE_ENVIRONMENT must be one of {sorted(BASE_URLS)}")
        self.application_id = application_id
        self.application_secret = application_secret
        self.environment = environment
        self.api_version = api_version
        self.base_url = BASE_URLS[environment]
        self._sleep = sleep
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0, transport=transport)

    @classmethod
    def from_env(cls) -> "SquareConnector":
        app_id = os.getenv("SQUARE_APPLICATION_ID")
        secret = os.getenv("SQUARE_APPLICATION_SECRET")
        if not app_id or not secret:
            raise ConnectorError("SQUARE_APPLICATION_ID and SQUARE_APPLICATION_SECRET must be set")
        return cls(
            app_id,
            secret,
            environment=os.getenv("SQUARE_ENVIRONMENT", "production"),
            api_version=os.getenv("SQUARE_API_VERSION", DEFAULT_API_VERSION),
        )

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, *, token: Optional[str] = None,
                 headers: Optional[dict] = None, json: Optional[dict] = None) -> dict:
        hdrs = {"Square-Version": self.api_version, "Accept": "application/json"}
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        hdrs.update(headers or {})

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self._client.request(method, path, headers=hdrs, json=json)
            except httpx.HTTPError as e:
                if attempt == MAX_ATTEMPTS:
                    raise ConnectorError(f"{method} {path}: {e}") from e
                self._sleep(2 ** attempt)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == MAX_ATTEMPTS:
                    raise ConnectorError(f"{method} {path}: HTTP {resp.status_code} after {attempt} attempts")
                retry_after = resp.headers.get("Retry-After")
                self._sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt)
                continue

            body = resp.json() if resp.content else {}
            if resp.status_code in (401, 403):
                raise AuthError(f"{method} {path}: {self._error_text(body) or resp.status_code}")
            if resp.status_code >= 400:
                raise ConnectorError(f"{method} {path}: HTTP {resp.status_code} {self._error_text(body)}")
            return body
        raise AssertionError("unreachable")

    @staticmethod
    def _error_text(body: dict) -> str:
        errors = body.get("errors") or []
        if errors:
            return "; ".join(f"{e.get('code')}: {e.get('detail')}" for e in errors)
        return body.get("message") or body.get("error_description") or body.get("error") or ""

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    def authorize_url(self, state: str) -> str:
        params = {"client_id": self.application_id, "scope": SCOPES, "state": state}
        # `session=false` forces the seller to sign in fresh rather than reusing
        # whatever Square account the browser has open. Sandbox rejects it.
        if self.environment == "production":
            params["session"] = "false"
        return f"{self.base_url}/oauth2/authorize?{urlencode(params)}"

    def _grant(self, body: dict, previous: Optional[dict] = None) -> OAuthGrant:
        if not body.get("access_token"):
            raise AuthError("Square token response had no access_token")
        refresh_token = body.get("refresh_token") or (previous or {}).get("refresh_token")
        merchant_id = body.get("merchant_id") or (previous or {}).get("merchant_id")
        if not merchant_id:
            raise ConnectorError("Square token response had no merchant_id")
        return OAuthGrant(
            merchant_id=merchant_id,
            credentials={
                "access_token": body["access_token"],
                "refresh_token": refresh_token,
                "merchant_id": merchant_id,
            },
            expires_at=parse_ts(body.get("expires_at")),
            scopes=SCOPES,
        )

    def _token(self, payload: dict) -> dict:
        try:
            return self._request("POST", "/oauth2/token", json={
                "client_id": self.application_id,
                "client_secret": self.application_secret,
                **payload,
            })
        except ConnectorError as e:
            # A 400 here is a bad or used code / revoked refresh token, which no
            # retry will fix.
            if "HTTP 400" in str(e):
                raise AuthError(str(e)) from e
            raise

    def exchange_code(self, code: str) -> OAuthGrant:
        return self._grant(self._token({"grant_type": "authorization_code", "code": code}))

    def refresh(self, credentials: dict) -> OAuthGrant:
        if not credentials.get("refresh_token"):
            raise AuthError("no refresh token stored; the partner must reconnect")
        body = self._token({"grant_type": "refresh_token", "refresh_token": credentials["refresh_token"]})
        return self._grant(body, previous=credentials)

    def revoke(self, credentials: dict) -> None:
        self._request(
            "POST", "/oauth2/revoke",
            headers={"Authorization": f"Client {self.application_secret}"},
            json={"client_id": self.application_id, "access_token": credentials["access_token"]},
        )

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def list_locations(self, credentials: dict) -> list[ExternalLocation]:
        body = self._request("GET", "/v2/locations", token=credentials["access_token"])
        out = []
        for loc in body.get("locations") or []:
            addr = loc.get("address") or {}
            parts = [addr.get("address_line_1"), addr.get("locality"),
                     addr.get("administrative_district_level_1"), addr.get("postal_code")]
            out.append(ExternalLocation(
                external_id=loc["id"],
                name=loc.get("name") or loc.get("business_name") or loc["id"],
                address=", ".join(p for p in parts if p) or None,
                timezone=loc.get("timezone"),
                is_active=loc.get("status", "ACTIVE") == "ACTIVE",
            ))
        return out

    def fetch_orders(self, credentials: dict, location_ids: list[str], since: datetime) -> Iterator[NormalizedOrder]:
        token = credentials["access_token"]
        contacts: dict[str, dict] = {}

        # One stream per chunk of ten locations, each oldest-update first. The
        # ordering restarts at each chunk, which is why sync.py only advances its
        # cursor once a whole run has succeeded.
        for chunk in _chunks(sorted(location_ids), MAX_LOCATIONS_PER_SEARCH):
            cursor = None
            while True:
                body = {
                    "location_ids": chunk,
                    "limit": PAGE_LIMIT,
                    "query": {
                        "filter": {"date_time_filter": {"updated_at": {"start_at": _iso(since)}}},
                        "sort": {"sort_field": "UPDATED_AT", "sort_order": "ASC"},
                    },
                }
                if cursor:
                    body["cursor"] = cursor
                page = self._request("POST", "/v2/orders/search", token=token, json=body)
                orders = [o for o in page.get("orders") or [] if o.get("state") != "DRAFT"]

                wanted = {cid for o in orders if (cid := self._customer_id(o)) and cid not in contacts}
                contacts.update(self._lookup_customers(token, sorted(wanted)))

                for order in orders:
                    yield self.normalize(order, contacts)

                cursor = page.get("cursor")
                if not cursor:
                    break

    def _lookup_customers(self, token: str, customer_ids: list[str]) -> dict[str, dict]:
        found: dict[str, dict] = {}
        for chunk in _chunks(customer_ids, MAX_CUSTOMERS_PER_LOOKUP):
            body = self._request("POST", "/v2/customers/bulk-retrieve", token=token,
                                 json={"customer_ids": chunk})
            for cid, result in (body.get("responses") or {}).items():
                customer = (result or {}).get("customer")
                # A per-id error (deleted profile) is not a failed sync: the order
                # just arrives without contact details.
                found[cid] = customer or {}
        for cid in customer_ids:
            found.setdefault(cid, {})
        return found

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _customer_id(order: dict) -> Optional[str]:
        if order.get("customer_id"):
            return order["customer_id"]
        for tender in order.get("tenders") or []:
            if tender.get("customer_id"):
                return tender["customer_id"]
        return None

    @classmethod
    def normalize(cls, order: dict, contacts: Optional[dict[str, dict]] = None) -> NormalizedOrder:
        contacts = contacts or {}
        state = {"OPEN": "open", "COMPLETED": "completed", "CANCELED": "canceled"}.get(order.get("state"), "open")

        returns = order.get("returns") or []
        is_return = bool(returns) and not order.get("line_items")
        if is_return:
            kind = "return"
            source_id = next((r.get("source_order_id") for r in returns if r.get("source_order_id")), None)
            total_cents = _cents((order.get("return_amounts") or {}).get("total_money"))
            tax_cents = _cents((order.get("return_amounts") or {}).get("tax_money"))
            tip_cents = _cents((order.get("return_amounts") or {}).get("tip_money"))
            discount_cents = _cents((order.get("return_amounts") or {}).get("discount_money"))
            currency = ((order.get("return_amounts") or {}).get("total_money") or {}).get("currency")
            lines = [
                NormalizedLine(
                    name=li.get("name") or "Item",
                    quantity=str(li.get("quantity") or "1"),
                    total_cents=_cents(li.get("total_money")),
                    external_line_id=li.get("uid"),
                    external_sku=li.get("catalog_object_id"),
                    variation=li.get("variation_name"),
                )
                for r in returns for li in r.get("return_line_items") or []
            ]
        else:
            kind = "sale"
            source_id = None
            total_cents = _cents(order.get("total_money"))
            tax_cents = _cents(order.get("total_tax_money"))
            tip_cents = _cents(order.get("total_tip_money"))
            discount_cents = _cents(order.get("total_discount_money"))
            currency = (order.get("total_money") or {}).get("currency")
            lines = [
                NormalizedLine(
                    name=li.get("name") or "Custom amount",
                    quantity=str(li.get("quantity") or "1"),
                    total_cents=_cents(li.get("total_money")),
                    external_line_id=li.get("uid"),
                    external_sku=li.get("catalog_object_id"),
                    variation=li.get("variation_name"),
                )
                for li in order.get("line_items") or []
            ]

        refunded_cents = sum(
            _cents(r.get("amount_money"))
            for r in order.get("refunds") or []
            if r.get("status") not in _DEAD_REFUND_STATUSES
        )

        customer_id = cls._customer_id(order)
        customer = contacts.get(customer_id, {}) if customer_id else {}
        email = (customer.get("email_address") or "").strip().lower() or None

        created = parse_ts(order.get("created_at"))
        updated = parse_ts(order.get("updated_at")) or created
        return NormalizedOrder(
            external_order_id=order["id"],
            external_location_id=order.get("location_id"),
            kind=kind,
            source_external_order_id=source_id,
            state=state,
            currency=currency or "USD",
            total_cents=total_cents,
            tax_cents=tax_cents,
            tip_cents=tip_cents,
            discount_cents=discount_cents,
            refunded_cents=refunded_cents,
            external_customer_id=customer_id,
            customer_phone=to_e164(customer.get("phone_number")),
            customer_email=email,
            ordered_at=created,
            closed_at=parse_ts(order.get("closed_at")),
            external_updated_at=updated,
            lines=lines,
            raw=order,
        )
