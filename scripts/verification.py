"""
verification.py — human-verified listing fields, and the rules that protect them.

A verified field is one a person has checked and signed. The pipeline must not
overwrite it: not on re-enrichment, not on import, not on an _ENRICH_VERSION bump.
Before this existed a correction survived exactly one scrape, because both
enrich() and import_listings.py rewrite the identity fields unconditionally.

Shape, stored in listings.verified_fields:

    {"strain": {"value": "Blue Dream", "by": "pablo", "at": "2026-08-27T12:00:00Z",
                "name_hash": "9f2c1a..."}}

Provenance is per field because fields are checked at different times by different
people, and a claim should record what it was checked against.

Lapsing
-------
A claim is about a (listing, scraped_name) pair, not about a listing. Dispensaries
rename products in place under the same SKU, and when that happens the row now
describes different text — text nobody read. So each claim stores a hash of the
name it was made against, and a claim whose hash no longer matches is treated as
absent rather than as truth. It is not deleted: `lapsed_fields()` surfaces it so a
reviewer can re-confirm rather than start over.

This is deliberately strict. The failure it prevents — a stale human sign-off
vouching for a product that has since become something else — is worse than asking
for a re-check, because a verified field is trusted everywhere else without question.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

# The identity fields verification can cover. Deliberately not price or stock:
# those are volatile by nature and a human claim about them would always be stale.
VERIFIABLE = ("category", "subtype", "strain", "product_line", "variant")


def name_hash(name: str | None) -> str:
    """Stable hash of a scraped name, insensitive to whitespace and case only.

    Punctuation is significant: "Blue Dream" and "Blue-Dream" may well be different
    products, and a claim should not silently carry across that difference.
    """
    normalized = re.sub(r"\s+", " ", (name or "")).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _entries(row: dict) -> dict[str, dict]:
    raw = row.get("verified_fields")
    return raw if isinstance(raw, dict) else {}


def verified_fields(row: dict) -> dict[str, Any]:
    """{field: value} for claims that still hold — the hash matches the live name.

    Callers should treat these as immovable: they are the one part of a listing the
    pipeline is not allowed to have an opinion about.
    """
    live = name_hash(row.get("scraped_name") or row.get("name"))
    return {
        field: claim.get("value")
        for field, claim in _entries(row).items()
        if isinstance(claim, dict) and claim.get("name_hash") == live
    }


def lapsed_fields(row: dict) -> dict[str, dict]:
    """Claims whose product has been renamed underneath them.

    Kept rather than dropped so a reviewer can re-confirm in one glance instead of
    redoing the work. Nothing in the pipeline should read these as verified.
    """
    live = name_hash(row.get("scraped_name") or row.get("name"))
    return {
        field: claim
        for field, claim in _entries(row).items()
        if isinstance(claim, dict) and claim.get("name_hash") != live
    }


def is_fully_verified(row: dict) -> bool:
    """True when every verifiable field carries a live claim.

    enrich() uses this to skip a row entirely — which makes verified rows free as
    well as stable, since they never reach the model.
    """
    return set(verified_fields(row)) >= set(VERIFIABLE)


def apply(row: dict) -> dict:
    """Overlay live claims onto a row, in place. Returns the row.

    Run this last, after the model and after the deterministic layer, so that a
    human answer wins over both.
    """
    for field, value in verified_fields(row).items():
        row[field] = value
    return row


def claim(fields: dict[str, Any], name: str, by: str,
          existing: dict | None = None) -> dict:
    """Build a verified_fields value: `existing` updated with `fields`.

    Merges rather than replaces, so verifying `strain` today does not silently
    withdraw a claim someone made about `variant` last week.
    """
    unknown = set(fields) - set(VERIFIABLE)
    if unknown:
        raise ValueError(f"not verifiable: {', '.join(sorted(unknown))}")
    now = datetime.now(timezone.utc).isoformat()
    h = name_hash(name)
    out = dict(existing or {})
    for field, value in fields.items():
        out[field] = {"value": value, "by": by, "at": now, "name_hash": h}
    return out
