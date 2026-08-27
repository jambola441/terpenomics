# services/phone.py
"""E.164 normalization, mirroring ui/my-app/src/utils/phone.ts.

Kept deliberately small: the product is US-first, so this handles NANP properly
and accepts any explicitly international "+..." input. If we ever go
multi-country in earnest, swap this for the phonenumbers package.
"""
from __future__ import annotations

import os
import re

DEFAULT_COUNTRY_CODE = re.sub(r"\D", "", os.getenv("SMS_DEFAULT_COUNTRY_CODE", "1")) or "1"

# Longest-prefix match when splitting E.164 back into (country, national).
# Extend via SMS_COUNTRY_CODES if you start sending outside these.
_DEFAULT_COUNTRY_CODES = "1,7,20,27,30,31,33,34,39,44,49,52,55,61,64,81,82,86,91"
KNOWN_COUNTRY_CODES = sorted(
    (c for c in re.split(r"[,\s]+", os.getenv("SMS_COUNTRY_CODES", _DEFAULT_COUNTRY_CODES)) if c),
    key=len,
    reverse=True,
)


def to_e164(raw: str | None, country_code: str = DEFAULT_COUNTRY_CODE) -> str | None:
    """Normalize user input to E.164, or None if it cannot be a valid number."""
    value = (raw or "").strip()
    if not value:
        return None

    if value.startswith("+"):
        digits = re.sub(r"\D", "", value[1:])
        return f"+{digits}" if 8 <= len(digits) <= 15 else None

    digits = re.sub(r"\D", "", value)
    if not digits:
        return None

    if country_code == "1":
        # NANP: 10 digits, or 11 with the leading country code.
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return f"+1{digits}" if len(digits) == 10 else None

    digits = digits.lstrip("0")
    if not digits.startswith(country_code):
        digits = country_code + digits
    return f"+{digits}" if 8 <= len(digits) <= 15 else None


def split_e164(e164: str) -> tuple[str, str]:
    """Split "+15551234567" into ("1", "5551234567").

    Providers like VerifyNow take the country code and the national number as
    separate parameters rather than a single E.164 string.
    """
    digits = e164.lstrip("+")
    for code in KNOWN_COUNTRY_CODES:
        if digits.startswith(code) and len(digits) > len(code):
            return code, digits[len(code):]
    # Unknown country code: fall back to the configured default rather than
    # guessing a split that would silently misroute the message.
    if digits.startswith(DEFAULT_COUNTRY_CODE):
        return DEFAULT_COUNTRY_CODE, digits[len(DEFAULT_COUNTRY_CODE):]
    raise ValueError(f"Cannot determine country code for {e164}; set SMS_COUNTRY_CODES")


def mask(e164: str) -> str:
    """Log-safe rendering: +1555***4567."""
    return f"{e164[:5]}***{e164[-4:]}" if len(e164) > 9 else "***"
