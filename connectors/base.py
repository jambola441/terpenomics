"""The connector protocol and the provider-neutral shapes it produces.

A connector knows one POS's API and nothing about our database. It turns that
POS's orders into `NormalizedOrder`s -- integer cents, UTC datetimes, E.164 phone
numbers -- and store.py writes those. Adding a provider means writing one class
that satisfies `PosConnector`; nothing downstream changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Optional, Protocol


class ConnectorError(Exception):
    """The POS call failed. Retrying later may work."""


class AuthError(ConnectorError):
    """The POS rejected our credentials. Retrying will not help; the partner has to reconnect."""


@dataclass
class OAuthGrant:
    """What a code exchange or token refresh returns."""
    merchant_id: str
    credentials: dict              # opaque to everyone but the connector; stored encrypted
    expires_at: Optional[datetime]
    scopes: Optional[str] = None


@dataclass
class ExternalLocation:
    external_id: str
    name: str
    address: Optional[str] = None
    timezone: Optional[str] = None
    is_active: bool = True


@dataclass
class NormalizedLine:
    name: str
    quantity: str = "1"
    total_cents: int = 0
    external_line_id: Optional[str] = None
    external_sku: Optional[str] = None
    variation: Optional[str] = None


@dataclass
class NormalizedOrder:
    external_order_id: str
    state: str                     # PosOrderState value
    ordered_at: datetime
    external_updated_at: datetime
    kind: str = "sale"             # PosOrderKind value
    external_location_id: Optional[str] = None
    source_external_order_id: Optional[str] = None
    currency: str = "USD"
    total_cents: int = 0
    tax_cents: int = 0
    tip_cents: int = 0
    discount_cents: int = 0
    refunded_cents: int = 0
    external_customer_id: Optional[str] = None
    customer_phone: Optional[str] = None   # E.164
    customer_email: Optional[str] = None
    closed_at: Optional[datetime] = None
    lines: list[NormalizedLine] = field(default_factory=list)
    raw: Optional[dict] = None


class PosConnector(Protocol):
    provider: str

    def authorize_url(self, state: str) -> str:
        """Where to send the partner to grant access."""

    def exchange_code(self, code: str) -> OAuthGrant:
        """Trade the OAuth callback's code for credentials."""

    def refresh(self, credentials: dict) -> OAuthGrant:
        """Get a fresh access token."""

    def revoke(self, credentials: dict) -> None:
        """Give the grant back."""

    def list_locations(self, credentials: dict) -> list[ExternalLocation]:
        ...

    def fetch_orders(
        self, credentials: dict, location_ids: list[str], since: datetime
    ) -> Iterator[NormalizedOrder]:
        """Every order updated at or after `since`.

        Drafts and other not-yet-real orders are the connector's to drop. The
        sync advances its cursor to the newest `external_updated_at` only after
        the whole iteration succeeds, so ordering is not part of the contract.
        """
