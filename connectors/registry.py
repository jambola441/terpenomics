"""Provider name -> a connector configured from the environment."""
from __future__ import annotations

from .base import ConnectorError, PosConnector

PROVIDERS = ("square",)


def get_connector(provider: str) -> PosConnector:
    if provider == "square":
        from .square import SquareConnector
        return SquareConnector.from_env()
    raise ConnectorError(f"unknown POS provider {provider!r}")
