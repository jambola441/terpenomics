#!/usr/bin/env python3
"""
backfill_customer_phone_e164.py — respell customers.phone as E.164.

customers.phone grew up in several spellings: SMS logins wrote the number the
way the Supabase JWT carries it ("16462606799"), admins typed whatever they
liked, and POS orders carry E.164 ("+16462606799"). Matching works around this
today (connectors/matching.py looks up two spellings), but any spelling outside
those two silently matches nothing. Every write path now stores E.164; this
brings the existing rows in line.

It only PATCHes `phone`, and only on rows whose value actually changes. It
leaves alone, and reports, any number that does not parse and any two rows that
would end up with the same number — those need a person to decide.

Writes over PostgREST because the Postgres wire protocol is unreachable from some
sandboxes (see DB_ACCESS.md).

    python scripts/backfill_customer_phone_e164.py         # report, change nothing
    python scripts/backfill_customer_phone_e164.py --run
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import db_http  # noqa: E402
from services.phone import mask, to_e164  # noqa: E402


def plan(rows: list[dict]) -> tuple[list[tuple[str, str, str]], list[str], list[list[str]]]:
    """Split rows into (id, old, new) changes, unparseable ids, and collisions.

    A collision is two or more rows normalizing to one number; none of them is
    changed, since the unique index would reject all but one anyway.
    """
    by_number: dict[str, list[dict]] = defaultdict(list)
    unparseable: list[str] = []
    for r in rows:
        e164 = to_e164(r["phone"])
        if e164 is None:
            unparseable.append(r["id"])
        else:
            by_number[e164].append(r)

    changes, collisions = [], []
    for e164, group in by_number.items():
        if len(group) > 1:
            collisions.append([r["id"] for r in group])
            continue
        r = group[0]
        if r["phone"] != e164:
            changes.append((r["id"], r["phone"], e164))
    return changes, unparseable, collisions


def main() -> int:
    ap = argparse.ArgumentParser(description="Respell customers.phone as E.164")
    ap.add_argument("--run", action="store_true", help="write the changes (default: report only)")
    args = ap.parse_args()

    rows = db_http.select_all("customers", "select=id,phone&phone=not.is.null")
    changes, unparseable, collisions = plan(rows)

    print(f"{len(rows)} customers with a phone; {len(changes)} to respell")
    for cid, old, new in changes:
        print(f"  {cid}  {mask(old)} -> {mask(new)}")
    for cid in unparseable:
        print(f"  UNPARSEABLE  {cid}  (left as is)")
    for ids in collisions:
        print(f"  COLLISION    {', '.join(ids)}  (same number; left as is)")

    if not args.run:
        print("report only; pass --run to write")
        return 0

    for cid, _old, new in changes:
        db_http.update("customers", f"id=eq.{cid}", {"phone": new})
    print(f"respelled {len(changes)}")
    return 1 if unparseable or collisions else 0


if __name__ == "__main__":
    sys.exit(main())
