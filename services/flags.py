"""Feature flags: which unreleased parts of the portal each customer sees.

Every flag resolves per customer, in this order:

  1. the customer's own override, a row in customer_flags (on or off);
  2. else the global default, from the PORTAL_FLAGS environment variable;
  3. else off.

PORTAL_FLAGS is a comma-separated list, read on every resolve so a change takes
effect when the API restarts with it:

  lines                 on for everyone
  lines_grouped:25%     on for a stable quarter of customers. The share is picked
                        by hashing the flag with the customer id, so each person
                        keeps the same answer from visit to visit, and each flag
                        picks a different quarter.

Names PORTAL_FLAGS lists that are not in FLAGS are ignored, so retiring a flag
never breaks a deploy.

Flags decide what the apps draw. They must never shape what the shared catalogue
answers contain (services/response_cache.py): those are one copy for every
shopper, and a per-customer answer there would hand one person's flags to all.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from functools import lru_cache
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select

from models import CustomerFlag

# Every flag, with what it turns on. `built` is false for a flag reserved for
# work that has not landed yet: it resolves like any other, and the admin page
# shows it as not built rather than offering a switch that does nothing.
FLAGS: dict[str, dict] = {
    "lines": {
        "built": True,
        "about": "Line filter on brand pages, lines in search, the product page's "
                 "breadcrumb and its More in this line row.",
    },
    "lines_grouped": {
        "built": True,
        "about": "Brand pages laid out as one shelf per product line, for categories that "
                 "pass the grouping rule (components/LineShelves.tsx). Needs `lines`.",
    },
    "line_page": {"built": False, "about": "Line page, Compare, route strip, flavours not on NYC shelves."},
    "browse_views": {"built": False, "about": "List and Map views on brand and category pages."},
    "price_per_unit": {"built": False, "about": "Price per mg or gram: sort, filter and column."},
    "trip_planner": {"built": False, "about": "One-trip planner and flavour flight."},
    "personal": {"built": False, "about": "Tried and not tried, line history, Buy again."},
    "alerts": {"built": False, "about": "Restock and new-flavour alerts."},
    "line_passport": {"built": False, "about": "Line passport: private tasting notes, one stamp per flavour."},
    "line_passport_rewards": {
        "built": False,
        "about": "Points for passport progress. Rewards for how much someone buys "
                 "may clash with NY cannabis advertising rules: off until checked.",
    },
    "labs_status_board": {"built": False, "about": "Service Status board per line."},
    "labs_line_map": {"built": False, "about": "Line Map: lines as routes, flavours as stations."},
    "labs_field_note": {"built": False, "about": "Field Note: a summary of the brand written from the data."},
    "labs_cart_hint": {"built": False, "about": "Cart row: more from this line at this store."},
    "labs_home_rails": {"built": False, "about": "Home rails for lines you buy."},
}

_ENTRY = re.compile(r"^([a-z0-9_]+)(?::(\d{1,3})%)?$")


@lru_cache(maxsize=8)
def _defaults(raw: str) -> dict[str, int]:
    """PORTAL_FLAGS as {flag: percent on}. Malformed or unknown entries are skipped."""
    out: dict[str, int] = {}
    for part in raw.split(","):
        m = _ENTRY.match(part.strip().lower())
        if not m or m.group(1) not in FLAGS:
            continue
        out[m.group(1)] = min(int(m.group(2)), 100) if m.group(2) else 100
    return out


def defaults() -> dict[str, int]:
    return _defaults(os.getenv("PORTAL_FLAGS", ""))


def _in_rollout(flag: str, customer_id: UUID, percent: int) -> bool:
    if percent >= 100:
        return True
    if percent <= 0:
        return False
    digest = hashlib.sha256(f"{flag}:{customer_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 100 < percent


def _overrides(session: Session, customer_id: UUID) -> dict[str, bool]:
    rows = session.exec(select(CustomerFlag).where(CustomerFlag.customer_id == customer_id)).all()
    return {row.flag: row.enabled for row in rows}


def explain(session: Session, customer_id: UUID) -> list[dict]:
    """Each flag's answer for this customer, and where the answer came from."""
    overrides = _overrides(session, customer_id)
    rollout = defaults()
    out = []
    for name, meta in FLAGS.items():
        percent = rollout.get(name, 0)
        override = overrides.get(name)
        if override is not None:
            enabled, source = override, "override"
        else:
            enabled = _in_rollout(name, customer_id, percent)
            source = "default" if percent in (0, 100) else "rollout"
        out.append({
            "flag": name,
            "enabled": enabled,
            "source": source,
            "override": override,
            "default_percent": percent,
            "built": meta["built"],
            "about": meta["about"],
        })
    return out


def resolve(session: Session, customer_id: UUID) -> dict[str, bool]:
    """{flag: on?} for every flag: what GET /me hands the apps."""
    return {row["flag"]: row["enabled"] for row in explain(session, customer_id)}


def set_override(session: Session, customer_id: UUID, flag: str, enabled: Optional[bool]) -> None:
    """Force a flag on or off for one customer; None goes back to the default.

    Raises KeyError for a flag that does not exist. Commits.
    """
    if flag not in FLAGS:
        raise KeyError(flag)
    row = session.get(CustomerFlag, (customer_id, flag))
    if enabled is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(CustomerFlag(customer_id=customer_id, flag=flag, enabled=enabled))
    else:
        row.enabled = enabled
        row.updated_at = datetime.utcnow()
        session.add(row)
    session.commit()
