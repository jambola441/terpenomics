#!/usr/bin/env python3
"""
import_listings_rest.py — import_listings.py over Supabase PostgREST (HTTPS).

Same semantics as import_listings.py, different transport. Use this only when the
Postgres wire protocol is unreachable — a sandbox or CI network that allows 443 but
blocks 5432. Everywhere else prefer `scripts/scrape.py`, which calls the psycopg2
importer directly.

Why it cannot simply reuse the SQL: the listings upsert targets a partial expression
index, `ON CONFLICT (dispensary_id, sku, COALESCE(variant,'')) WHERE sku IS NOT
NULL`. PostgREST's `on_conflict=` accepts plain column names only, so the conflict
target is unreachable over REST. Instead this reads each dispensary's existing rows,
resolves the same `(sku, COALESCE(variant,''))` key client-side, and writes back:

  new rows          POST (plain insert, fresh uuid)
  existing rows     POST with Prefer: resolution=merge-duplicates & on_conflict=id
                    — the primary key IS a plain column, so this route works
  absent rows       PATCH is_active=false, subject to --stale-threshold

The updated column set matches the DO UPDATE clause in import_listings.py, so a row
written by either path ends up the same.

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (service role — it bypasses RLS).

KNOWN LIVE ISSUE — read before running
--------------------------------------
The production DB still enforces `listings_dispensary_sku_unique` on
(dispensary_id, sku), WITHOUT variant, so any row whose SKU already exists for
that dispensary under a different variant is rejected. A 2026-08-25 run of this
script had 924 rows rejected across 22 stores for exactly that reason. They are
real products sold across weight tiers, not duplicates.

The cause is simply that migrate_listing_variant_key.py has never run against
this database. Verified against the catalogue:

    pg_constraint on listings   -> only listings_pkey and the dispensary FK
    pg_indexes   on listings    -> listings_dispensary_sku_unique still present,
                                   listings_dispensary_sku_variant_unique absent

Neither of the migration's first two statements is reflected, and the old index
is a plain UNIQUE INDEX (not constraint-backed), so its `DROP INDEX IF EXISTS`
would have worked had it run. Fix by running the migration where 5432 is
reachable:

    python scripts/migrate_listing_variant_key.py --run

then re-run this import — it is idempotent, keyed on (sku, COALESCE(variant,'')),
so a re-run updates what already landed rather than duplicating it.

Usage
-----
  python scripts/import_listings_rest.py --csv 'data/scrapes/*.csv' --dry-run
  python scripts/import_listings_rest.py --csv 'data/scrapes/*.csv'
"""

import argparse
import csv
import glob
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("httpx required: pip install httpx")

ROOT = Path(__file__).parent.parent
PAGE = 1000          # PostgREST default max rows per response
WRITE_CHUNK = 500    # rows per write request

# Exactly the columns import_listings.py's ON CONFLICT DO UPDATE sets.
UPDATED = ["in_stock", "is_active", "price_cents", "batch_id", "image_url",
           "scraped_name", "scraped_brand", "scraped_category", "subtype", "strain",
           "classification", "description", "product_line", "url", "scraped_at",
           "last_seen_at", "updated_at"]

# The subset import_listings.py diffs for its change report. scraped_at, last_seen_at
# and updated_at are deliberately absent: they move on every scrape, so including them
# would mark every matched row "changed" and make the report useless. Matched rows are
# still written in full — this list only decides what counts as a real change.
TRACKED = ["in_stock", "price_cents", "image_url", "scraped_name", "scraped_brand",
           "scraped_category", "subtype", "strain", "url", "product_line"]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def parse_bool(v) -> bool:
    return str(v).strip().lower() in ("true", "t", "1", "yes", "y")


def clean(v):
    s = (v or "").strip()
    return s or None


class Rest:
    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1"
        self.h = {"apikey": key, "Authorization": f"Bearer {key}",
                  "Content-Type": "application/json"}
        self.client = httpx.Client(timeout=120)

    def get_all(self, path: str, params: dict) -> list[dict]:
        """Page through a select until PostgREST stops returning full pages."""
        out, offset = [], 0
        while True:
            h = {**self.h, "Range-Unit": "items", "Range": f"{offset}-{offset + PAGE - 1}"}
            r = self.client.get(f"{self.base}/{path}", params=params, headers=h)
            r.raise_for_status()
            batch = r.json()
            out.extend(batch)
            if len(batch) < PAGE:
                return out
            offset += PAGE

    def write(self, path: str, rows: list[dict], upsert_on: str | None = None) -> list[dict]:
        """Write rows; returns the ones rejected by a unique violation.

        The live DB still carries listings_dispensary_sku_unique on
        (dispensary_id, sku) — the variant-key migration's DROP INDEX could not
        remove it because it backs a CONSTRAINT. So a store selling one SKU across
        several weight tiers has rows that cannot coexist. Rather than abort the
        whole import, a rejected chunk is retried row by row and the losers are
        returned for the caller to report."""
        h = dict(self.h)
        params = {}
        if upsert_on:
            h["Prefer"] = "resolution=merge-duplicates,return=minimal"
            params["on_conflict"] = upsert_on
        else:
            h["Prefer"] = "return=minimal"
        rejected: list[dict] = []

        def post(payload):
            for attempt in range(3):
                r = self.client.post(f"{self.base}/{path}", params=params,
                                     headers=h, content=json.dumps(payload))
                if r.status_code < 300:
                    return None
                if r.status_code >= 500 and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return r
            return None

        for i in range(0, len(rows), WRITE_CHUNK):
            chunk = rows[i:i + WRITE_CHUNK]
            r = post(chunk)
            if r is None:
                continue
            if r.status_code != 409:
                raise RuntimeError(f"{r.status_code} {r.text[:400]}")
            for row in chunk:                     # isolate the offenders
                rr = post([row])
                if rr is None:
                    continue
                if rr.status_code == 409:
                    rejected.append(row)
                else:
                    raise RuntimeError(f"{rr.status_code} {rr.text[:400]}")
        return rejected

    def patch_ids(self, path: str, ids: list[str], payload: dict) -> None:
        h = {**self.h, "Prefer": "return=minimal"}
        for i in range(0, len(ids), WRITE_CHUNK):
            chunk = ids[i:i + WRITE_CHUNK]
            params = {"id": f"in.({','.join(chunk)})"}
            r = self.client.patch(f"{self.base}/{path}", params=params,
                                  headers=h, content=json.dumps(payload))
            if r.status_code >= 300:
                raise RuntimeError(f"{r.status_code} {r.text[:400]}")


def newest_csv_per_store(patterns: list[str]) -> dict[str, Path]:
    paths: list[str] = []
    for pat in patterns:
        paths.extend(sorted(glob.glob(pat)))
    best: dict[str, Path] = {}
    for p in paths:
        path = Path(p)
        with path.open(newline="", encoding="utf-8") as fh:
            head = next(csv.DictReader(fh), None)
        if not head:
            continue
        slug = head.get("dispensary_slug") or path.stem
        if slug not in best or str(path) > str(best[slug]):
            best[slug] = path
    return dict(sorted(best.items()))


def main() -> None:
    ap = argparse.ArgumentParser(description="Import scraped listings via Supabase REST")
    ap.add_argument("--csv", action="append", default=[], help="glob of CSVs (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="report the diff, write nothing")
    ap.add_argument("--stale-threshold", type=float, default=0.5,
                    help="skip deactivating absent listings when this scrape carries fewer "
                         "than THRESHOLD x the dispensary's active listings (0 disables)")
    args = ap.parse_args()
    if not args.csv:
        ap.error("give --csv GLOB (repeatable)")

    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    rest = Rest(url, key)

    disp = {d["slug"]: d["id"] for d in
            rest.get_all("dispensaries", {"select": "id,slug"})}
    stores = newest_csv_per_store(args.csv)
    print(f"{len(stores)} CSV(s); {len(disp)} dispensaries in DB; "
          f"{'DRY RUN' if args.dry_run else 'WRITING'}\n")

    tot = {"new": 0, "upd": 0, "same": 0, "deact": 0, "skipped": 0, "rejected": 0}
    blocked: list[tuple] = []
    for slug, path in stores.items():
        did = disp.get(slug)
        if not did:
            print(f"[skip] {slug}: not in dispensaries table")
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

        existing = rest.get_all("listings", {
            # created_at comes along because the update path is an upsert
            # (INSERT ... ON CONFLICT); omitting it would send NULL into a NOT NULL
            # column via the INSERT half and clobber the row's original timestamp.
            "select": "id,created_at,sku,variant,is_active," + ",".join(TRACKED),
            "dispensary_id": f"eq.{did}"})
        by_key = {(e["sku"] or "", (e.get("variant") or "").strip()): e for e in existing}
        active_before = sum(1 for e in existing if e["is_active"])

        now = utcnow()
        inserts, updates, seen_keys, unchanged, dupes = [], [], set(), 0, 0
        pending: dict[tuple, dict] = {}   # key -> record, last row wins
        for r in rows:
            name = clean(r.get("name"))
            if not name:
                tot["skipped"] += 1
                continue
            sku, variant = clean(r.get("sku")), clean(r.get("variant"))
            rec = {
                "dispensary_id": did, "sku": sku, "batch_id": clean(r.get("batch_id")),
                "price_cents": parse_int(r.get("price_cents")), "variant": variant,
                "url": clean(r.get("product_url")), "image_url": clean(r.get("image_url")),
                "in_stock": parse_bool(r.get("in_stock", "true")), "is_active": True,
                "scraped_at": clean(r.get("scraped_at")), "scraped_name": name,
                "scraped_brand": clean(r.get("brand")),
                "scraped_category": clean(r.get("category")),
                "subtype": clean(r.get("subtype")), "strain": clean(r.get("strain")),
                "classification": clean(r.get("classification")),
                "description": clean(r.get("description")),
                "product_line": clean(r.get("product_line")),
                "updated_at": now, "last_seen_at": now,
            }
            if not sku:                      # no SKU -> plain insert, matches the psycopg2 path
                inserts.append({**rec, "id": str(uuid.uuid4()), "created_at": now})
                continue
            key = (sku, variant or "")
            if key in seen_keys:
                # Same (sku, variant) twice in one scrape — the unique index would
                # reject the batch. import_listings.py dedupes with last-row-wins;
                # match that by replacing the pending record for this key.
                dupes += 1
                pending.pop(key, None)
            seen_keys.add(key)
            prev = by_key.get(key)
            if prev is None:
                pending[key] = {**rec, "id": str(uuid.uuid4()), "created_at": now}
                continue
            else:
                # Every matched row is written (freshness columns must move), but only
                # a TRACKED difference is reported as a change.
                pending[key] = {**rec, "id": prev["id"],
                                "created_at": prev["created_at"]}
                if not any(prev.get(c) != rec.get(c) for c in TRACKED):
                    unchanged += 1

        # Split the deduped records into inserts (fresh uuid) and updates (existing id).
        existing_ids = {e["id"] for e in existing}
        for rec in pending.values():
            (updates if rec["id"] in existing_ids else inserts).append(rec)
        if dupes:
            print(f"  [dedupe] {slug}: {dupes} duplicate (sku,variant) row(s) collapsed")

        # Deactivate rows absent from this scrape, with the same partial-scrape guard.
        absent = [e["id"] for k, e in by_key.items() if e["is_active"] and k not in seen_keys]
        guard = args.stale_threshold > 0 and active_before and \
            len(rows) < args.stale_threshold * active_before
        if guard:
            print(f"  [guard] {slug}: scrape has {len(rows)} rows vs {active_before} active "
                  f"(< {args.stale_threshold:g}x) — NOT deactivating {len(absent)}")
            absent = []

        unchanged = min(unchanged, len(updates))
        changed = len(updates) - unchanged
        print(f"{slug:38s} rows={len(rows):5d}  new={len(inserts):5d} "
              f"changed={changed:5d} same={unchanged:5d} deact={len(absent):5d}")
        tot["new"] += len(inserts); tot["upd"] += changed
        tot["same"] += unchanged; tot["deact"] += len(absent)

        if not args.dry_run:
            rej = []
            if inserts:
                rej += rest.write("listings", inserts)
            if updates:
                rej += rest.write("listings", updates, upsert_on="id")
            if absent:
                rest.patch_ids("listings", absent,
                               {"is_active": False, "updated_at": now})
            if rej:
                tot["rejected"] += len(rej)
                blocked.extend((slug, r.get("sku"), r.get("variant"),
                                r.get("scraped_name")) for r in rej)
                print(f"  [blocked] {slug}: {len(rej)} row(s) rejected by "
                      f"listings_dispensary_sku_unique")

    print(f"\n{'would ' if args.dry_run else ''}insert={tot['new']:,} "
          f"update={tot['upd']:,} unchanged={tot['same']:,} "
          f"deactivate={tot['deact']:,} skipped(no name)={tot['skipped']}")
    if blocked:
        print(f"\n{len(blocked)} row(s) REJECTED by listings_dispensary_sku_unique "
              f"— the pre-migration (dispensary_id, sku) key. These are real products "
              f"sharing one SKU across weight tiers and cannot land until the "
              f"constraint is dropped:")
        for slug, sku, variant, name in blocked[:15]:
            print(f"    {slug:32s} sku={sku} variant={variant!r} {(name or '')[:40]}")
        if len(blocked) > 15:
            print(f"    ... and {len(blocked) - 15} more")


if __name__ == "__main__":
    main()
