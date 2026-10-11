#!/usr/bin/env python3
"""
apply_review_decisions.py — One-off: apply the review queue's existing `entry` decisions.

Until 2026-10-11 a review decision `entry` was recorded only. It is now a transition
to trusted, by review (routes/admin/review.py make_manual). This applies the ones
recorded before that change: for each decision `entry` whose listing is still in the
review queue (catalog_match_method in models.REVIEW_REASONS), the listing gets

    catalog_entry_id = the decision's entry, catalog_match_method = 'manual',
    catalog_match_confidence = 1.0

and the decision keeps the match it replaces (prev_entry_id, prev_confidence; the
method is already its `reason`), so undo can put it back. Identity is not overlaid
here: the next import keeps the manual match and overlays the entry onto the listing
(import_listings.apply_catalog).

Needs db/migrations/0018 applied before --write (prev_entry_id / prev_confidence).

Usage:
    python scripts/apply_review_decisions.py                    # dry run, DATABASE_URL
    python scripts/apply_review_decisions.py --via-http         # dry run over HTTPS
    python scripts/apply_review_decisions.py --write [--via-http]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# models.REVIEW_REASONS, kept here so this runs without the API's dependencies.
REVIEW_REASONS = ("review_unsure", "review_missing", "review_near")


def plan(decisions: list[dict], listings: dict[str, dict]) -> list[dict]:
    """The changes to make: one per `entry` decision whose listing is still in review.
    decisions: review_decisions rows; listings: id -> listings row."""
    out = []
    for d in decisions:
        if d.get("decision") != "entry" or not d.get("entry_id"):
            continue
        listing = listings.get(str(d["listing_id"]))
        if listing is None or listing.get("catalog_match_method") not in REVIEW_REASONS:
            continue
        out.append({
            "decision_id": str(d["id"]), "listing_id": str(d["listing_id"]),
            "entry_id": str(d["entry_id"]),
            "prev_method": listing.get("catalog_match_method"),
            "prev_entry_id": str(listing["catalog_entry_id"]) if listing.get("catalog_entry_id") else None,
            "prev_confidence": listing.get("catalog_match_confidence"),
            "name": listing.get("scraped_name"), "brand": listing.get("scraped_brand"),
        })
    return out


class HttpDb:
    def __init__(self):
        import db_http
        self.h = db_http

    def decisions(self) -> list[dict]:
        return self.h.select_all("review_decisions", "select=id,listing_id,decision,entry_id,reason&decision=eq.entry")

    def listings(self, ids: list[str]) -> dict[str, dict]:
        out = {}
        cols = "id,scraped_name,scraped_brand,catalog_entry_id,catalog_match_method,catalog_match_confidence"
        for i in range(0, len(ids), 100):
            chunk = ",".join(ids[i:i + 100])
            for r in self.h.select("listings", f"select={cols}&id=in.({chunk})"):
                out[str(r["id"])] = r
        return out

    def apply(self, c: dict) -> None:
        self.h.update("review_decisions", f"id=eq.{c['decision_id']}",
                      {"prev_entry_id": c["prev_entry_id"], "prev_confidence": c["prev_confidence"]})
        self.h.update("listings", f"id=eq.{c['listing_id']}&catalog_match_method=eq.{c['prev_method']}",
                      {"catalog_entry_id": c["entry_id"], "catalog_match_method": "manual",
                       "catalog_match_confidence": 1.0})

    def commit(self) -> None:
        pass


class PgDb:
    def __init__(self):
        import psycopg2
        import psycopg2.extras
        import db_http  # noqa: F401  (loads .env)
        self.conn = psycopg2.connect(os.environ["DATABASE_URL"])
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def decisions(self) -> list[dict]:
        self.cur.execute("SELECT id, listing_id, decision, entry_id, reason FROM review_decisions "
                         "WHERE decision = 'entry'")
        return [dict(r) for r in self.cur.fetchall()]

    def listings(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        self.cur.execute("SELECT id, scraped_name, scraped_brand, catalog_entry_id, catalog_match_method, "
                         "catalog_match_confidence FROM listings WHERE id::text = ANY(%s)", (ids,))
        return {str(r["id"]): dict(r) for r in self.cur.fetchall()}

    def apply(self, c: dict) -> None:
        self.cur.execute("UPDATE review_decisions SET prev_entry_id = %s, prev_confidence = %s WHERE id = %s",
                         (c["prev_entry_id"], c["prev_confidence"], c["decision_id"]))
        self.cur.execute("UPDATE listings SET catalog_entry_id = %s, catalog_match_method = 'manual', "
                         "catalog_match_confidence = 1.0 WHERE id = %s AND catalog_match_method = %s",
                         (c["entry_id"], c["listing_id"], c["prev_method"]))

    def commit(self) -> None:
        self.conn.commit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("--write", action="store_true", help="Apply the changes (default: dry run)")
    ap.add_argument("--via-http", action="store_true", help="Use Supabase's REST API instead of DATABASE_URL")
    args = ap.parse_args(argv)

    db = HttpDb() if args.via_http else PgDb()
    decisions = db.decisions()
    listings = db.listings(sorted({str(d["listing_id"]) for d in decisions}))
    changes = plan(decisions, listings)

    print(f"entry decisions: {len(decisions)}; listing still in review: {len(changes)}")
    print("  by prior method:", dict(Counter(c["prev_method"] for c in changes)))
    print("  prior entry same as chosen:", sum(c["prev_entry_id"] == c["entry_id"] for c in changes))
    for c in changes[:20]:
        print(f"  {c['listing_id']}  {c['prev_method']:<15} -> manual {c['entry_id']}  "
              f"{c['brand']} | {c['name']}")
    if len(changes) > 20:
        print(f"  ... and {len(changes) - 20} more")
    if not args.write:
        print("dry run; --write to apply")
        return 0
    for c in changes:
        db.apply(c)
    db.commit()
    print(f"applied {len(changes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
