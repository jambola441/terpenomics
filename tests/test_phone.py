"""E.164 normalization — the format Supabase and every SMS provider require."""

import pytest

from services.phone import mask, split_e164, to_e164


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("(555) 123-4567", "+15551234567"),
        ("5551234567", "+15551234567"),
        ("15551234567", "+15551234567"),
        ("+1 555 123 4567", "+15551234567"),
        ("+1-555-123-4567", "+15551234567"),
        ("  5551234567  ", "+15551234567"),
        ("+44 7700 900123", "+447700900123"),
    ],
)
def test_to_e164_accepts_real_numbers(raw, expected):
    assert to_e164(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "abc", "555123", "123", "+1", "+12"])
def test_to_e164_rejects_junk(raw):
    assert to_e164(raw) is None


def test_split_e164_separates_country_from_national():
    assert split_e164("+15551234567") == ("1", "5551234567")
    assert split_e164("+447700900123") == ("44", "7700900123")


def test_mask_hides_the_middle():
    masked = mask("+15551234567")
    assert masked.startswith("+1555")
    assert masked.endswith("4567")
    assert "123" not in masked[5:-4]
