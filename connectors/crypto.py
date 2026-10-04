"""Encryption for stored POS credentials.

An OAuth access token reads a partner's whole order history and customer list,
so it is never stored in the clear. POS_CREDENTIALS_KEY holds one or more Fernet
keys, comma-separated: the first encrypts, all of them decrypt. To rotate, put a
new key first, re-save every connection, then drop the old key.

Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import json
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class CredentialsKeyError(RuntimeError):
    pass


def _fernet() -> MultiFernet:
    raw = os.getenv("POS_CREDENTIALS_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise CredentialsKeyError("POS_CREDENTIALS_KEY is not set")
    try:
        return MultiFernet([Fernet(k) for k in keys])
    except ValueError as e:
        raise CredentialsKeyError(f"POS_CREDENTIALS_KEY is not a valid Fernet key: {e}") from e


def encrypt_credentials(credentials: dict) -> str:
    return _fernet().encrypt(json.dumps(credentials).encode()).decode()


def decrypt_credentials(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken as e:
        raise CredentialsKeyError("stored credentials do not decrypt with POS_CREDENTIALS_KEY") from e
