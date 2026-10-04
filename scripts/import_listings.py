"""
import_listings.py — Import scraped listing CSVs into the DB.

Upserts listings keyed on (dispensary_id, sku, COALESCE(variant, '')) — several
platforms reuse one SKU across weight/price tiers, so the variant is part of a
listing's identity.

Where a listing's identity comes from
-------------------------------------
Three sources, each overriding the one before it:

  1. the CSV             enrichment's answer — model, curated maps, name tokens
  2. the brand catalog   when the listing resolves to a catalog entry by a trusted
                         method (exact, jev >= AUTO, or a human's manual match), the
                         entry's subtype, strain and product_line replace the
                         extracted ones. This is what makes every store carrying a
                         product land on one identity, instead of the product_line
                         being "FJ-Mini" at one store, "FJ Mini" at another and blank
                         at a third.
  3. a human claim       verified_fields, bound to the scraped name

And one thing that is never a source: a failed enrichment. A row the model did not
answer (enrich_failed) carries fallback values; for a listing we already hold, the
stored identity is kept rather than overwritten with them. Before this, a missing API
key or one bad batch wrote "other"/NULL over good data, fleet-wide on a bad day.

The catalog columns (catalog_entry_id / _confidence / _method) are written on every
import, so new listings get matched and renamed ones get re-matched. A match a human
made (method "manual") is never overwritten.

Usage:
  python scripts/import_listings.py --csv data/scrapes/<slug>_<stamp>.csv [--dry-run]

  DATABASE_URL must be set in the environment or in .env at the project root.

Exit codes: 0 ok · 1 error · 2 no rows could be imported (unknown dispensary)
            3 the CSV had no rows (a scrape that returned nothing is a failure)
"""

import argparse
import csv
import hashlib
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verification  # noqa: E402
import attributes  # noqa: E402
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.extras import Json
except ImportError:
    print("psycopg2-binary required: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

# Insert column order. Records are dicts keyed by column name and become tuples only
# at the INSERT, so a field cannot silently land in its neighbour's slot.
COLUMNS = [
    "id", "dispensary_id", "sku", "batch_id", "price_cents", "variant", "url", "image_url",
    "in_stock", "is_active", "scraped_at", "scraped_name", "scraped_brand", "scraped_category",
    "subtype", "strain", "classification", "description", "product_line", "attributes",
    "catalog_entry_id", "catalog_match_confidence", "catalog_match_method",
    "created_at", "updated_at", "last_seen_at",
]
# Identity fields a failed enrichment must not overwrite.
IDENTITY = ("scraped_category", "subtype", "strain", "product_line")
# verification.VERIFIABLE name -> listings column. `variant` is deliberately absent:
# it is part of the upsert key, and overlaying it re-keyed the listing — a new row
# with no claims was inserted and the verified one deactivated as stale.
VERIFIED_COLUMN = {"category": "scraped_category", "subtype": "subtype",
                   "strain": "strain", "product_line": "product_line"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Import scraped listings into terpenomics DB")
    p.add_argument("--csv", required=True, help="Path to scraper CSV file")
    p.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    p.add_argument(
        "--stale-threshold", type=float,
        default=float(os.environ.get("IMPORT_STALE_THRESHOLD", "0.5")),
        help="Skip marking absent listings inactive when this scrape carries fewer "
             "than THRESHOLD x the dispensary's active listings (default 0.5, or "
             "$IMPORT_STALE_THRESHOLD). Guards a partial scrape from deactivating "
             "the rest of the menu. 0 disables the guard.",
    )
    p.add_argument("--no-catalog", action="store_true",
                   help="Skip catalog matching; leave catalog columns as they are")
    p.add_argument("--no-jev", action="store_true",
                   help="Catalog matching without the Jev tier (exact matches only)")
    return p.parse_args(argv)


def load_env(project_root: str) -> None:
    env_path = os.path.join(project_root, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key not in os.environ:
                os.environ[key] = val


def parse_bool(val) -> bool:
    return str(val).strip().upper() in ("TRUE", "1", "YES")


def parse_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _clean(row: dict, key: str):
    return (row.get(key) or "").strip() or None


def synthetic_sku(name: str) -> str:
    """A stable key for a row the platform gave no SKU.

    Rows without a SKU used to be plain INSERTs: a fresh duplicate every run, never
    marked stale. A hash of the normalised name gives them the same upsert path as
    everything else. (Production held no NULL-SKU rows when this changed, 2026-10-04,
    so there are no legacy twins to retire.)
    """
    norm = " ".join((name or "").lower().split())
    return "nosku:" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def build_record(row: dict, dispensary_id: str, now: datetime) -> dict | None:
    name = _clean(row, "name")
    if not name:
        return None
    category = _clean(row, "category")
    return {
        "id": str(uuid.uuid4()),
        "dispensary_id": dispensary_id,
        "sku": _clean(row, "sku") or synthetic_sku(name),
        "batch_id": _clean(row, "batch_id"),
        "price_cents": parse_int(row.get("price_cents")),
        "variant": _clean(row, "variant"),
        "url": _clean(row, "product_url"),
        "image_url": _clean(row, "image_url"),
        "in_stock": parse_bool(row.get("in_stock", "true")),
        "is_active": True,
        "scraped_at": _clean(row, "scraped_at"),
        "scraped_name": name,
        "scraped_brand": _clean(row, "brand"),
        "scraped_category": category,
        "subtype": _clean(row, "subtype"),
        "strain": _clean(row, "strain"),
        "classification": _clean(row, "classification"),
        "description": _clean(row, "description"),
        "product_line": _clean(row, "product_line"),
        # Per-category identity that does not fit the shared columns — merch colour
        # and flavour today. Derived from the name, so computed here rather than
        # carried through the CSV.
        "attributes": attributes.for_category(category, name) or None,
        "catalog_entry_id": None,
        "catalog_match_confidence": None,
        "catalog_match_method": None,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
        "_enrich_failed": parse_bool(row.get("enrich_failed", "")),
    }


def fetch_existing(cur, dispensary_id: str, skus: list[str]) -> dict[tuple, dict]:
    cur.execute(
        """
        SELECT sku, COALESCE(variant, '') AS variant_key, variant, in_stock, price_cents,
               image_url, scraped_name, scraped_brand, scraped_category, subtype, strain,
               url, product_line, verified_fields, catalog_entry_id,
               catalog_match_confidence, catalog_match_method, is_active
        FROM listings
        WHERE dispensary_id = %s AND sku = ANY(%s)
        """,
        (dispensary_id, skus),
    )
    cols = [d[0] for d in cur.description]
    return {(r[0], r[1]): dict(zip(cols, r)) for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------

def protect_failed_enrichment(records: list[dict], existing: dict[tuple, dict]) -> int:
    """Keep the stored identity of listings whose enrichment failed this run.

    When the failed row's (sku, variant) is not on file but exactly one active row
    with that sku is, the row adopts that row's variant: the variant column is the
    enriched one, so a row the model skipped arrives with the scraper's raw variant
    and would otherwise be inserted as a new listing while the real one is retired.
    """
    by_sku: dict[str, list[dict]] = {}
    for (sku, _), row in existing.items():
        if row["is_active"]:
            by_sku.setdefault(sku, []).append(row)
    # Keys already claimed in this batch. Adopting a stored variant that another
    # incoming row also carries would send one key twice in a single upsert (Postgres
    # refuses: "ON CONFLICT DO UPDATE command cannot affect row a second time") or
    # let one size tier's price overwrite its sibling's.
    taken = {(r["sku"], r["variant"] or "") for r in records}
    kept = 0
    for rec in records:
        if not rec["_enrich_failed"]:
            continue
        stored = existing.get((rec["sku"], rec["variant"] or ""))
        if stored is None and len(by_sku.get(rec["sku"], [])) == 1:
            candidate = by_sku[rec["sku"]][0]
            target = (rec["sku"], candidate["variant"] or "")
            if target not in taken:
                taken.discard((rec["sku"], rec["variant"] or ""))
                taken.add(target)
                rec["variant"] = candidate["variant"]
                stored = candidate
        if stored is None:
            continue
        for col in IDENTITY:
            rec[col] = stored[col]
        kept += 1
    return kept


def apply_catalog(records: list[dict], existing: dict[tuple, dict], catalogs: dict,
                  use_jev: bool, slug: str, usage) -> dict:
    """Resolve each record against its brand's catalog and overlay trusted matches."""
    import catalog_match
    import catalog_store
    from catalog_enricher import _is_masked

    stats = {"exact": 0, "jev": 0, "jev_review": 0, "manual": 0, "substring": 0,
             "token": 0, "ambiguous": 0, "none": 0, "no_catalog": 0, "overlaid": 0,
             "kept_previous": 0, "masked_strain_skipped": 0}
    by_id = catalog_store.entries_by_id(catalogs)
    by_brand: dict[str, list[int]] = {}
    for i, rec in enumerate(records):
        stored = existing.get((rec["sku"], rec["variant"] or ""))
        if stored and stored["catalog_match_method"] == "manual":
            # A human chose this entry; keep it and take identity from it.
            rec["catalog_entry_id"] = str(stored["catalog_entry_id"]) if stored["catalog_entry_id"] else None
            rec["catalog_match_confidence"] = stored["catalog_match_confidence"]
            rec["catalog_match_method"] = "manual"
            stats["manual"] += 1
            hit = by_id.get(rec["catalog_entry_id"] or "")
            if hit:
                _overlay(rec, hit[1], stats, _is_masked)
            continue
        key = catalog_store.brand_key(rec["scraped_brand"])
        if key in catalogs:
            by_brand.setdefault(key, []).append(i)
        else:
            stats["no_catalog"] += 1

    for key, idxs in by_brand.items():
        catalog = catalogs[key]
        listings = [{"id": str(i), "name": records[i]["scraped_name"],
                     "category": records[i]["scraped_category"],
                     "subtype": records[i]["subtype"],
                     "variant": records[i]["variant"]} for i in idxs]
        cache = catalog_match.AnswerCache(catalog.get("brand_slug") or key)
        decisions = catalog_match.resolve(catalog, listings, use_jev=use_jev, cache=cache,
                                          usage=usage)
        for d in decisions:
            rec = records[int(d.listing["id"])]
            # This run could not make a model decision — no key, the breaker open, or
            # the call failed. A trusted match from an earlier run on the same name is
            # kept rather than replaced by "none", or one bad morning would undo every
            # catalog identity the way a failed enrichment used to undo extraction.
            if d.method == "error" or (not use_jev and d.method != "exact"):
                stored = existing.get((rec["sku"], rec["variant"] or ""))
                kept = _keep_stored_match(rec, stored, by_id, stats, _is_masked)
                if kept or d.method == "error":
                    stats["kept_previous" if kept else "none"] += 1
                    continue
            method = d.method if d.method in stats else "none"
            stats[method] += 1
            if d.entry is None:
                continue
            rec["catalog_entry_id"] = d.entry.get("id")
            rec["catalog_match_confidence"] = d.confidence
            rec["catalog_match_method"] = d.method
            if d.method in catalog_match.OVERLAY_METHODS:
                _overlay(rec, d.entry, stats, _is_masked)
    return stats


def _keep_stored_match(rec: dict, stored: dict | None, by_id: dict, stats: dict,
                       is_masked) -> bool:
    """Carry an earlier trusted match forward when the name it was made on is unchanged
    and its entry is still active. A renamed listing is not carried: nobody — and no
    model — has looked at the new name."""
    import catalog_match
    if not stored or stored["catalog_match_method"] not in catalog_match.OVERLAY_METHODS:
        return False
    if (stored["scraped_name"] or "") != (rec["scraped_name"] or ""):
        return False
    hit = by_id.get(str(stored["catalog_entry_id"]) if stored["catalog_entry_id"] else "")
    if not hit:
        return False
    rec["catalog_entry_id"] = hit[1]["id"]
    rec["catalog_match_confidence"] = stored["catalog_match_confidence"]
    rec["catalog_match_method"] = stored["catalog_match_method"]
    _overlay(rec, hit[1], stats, is_masked)
    return True


def _overlay(rec: dict, entry: dict, stats: dict, is_masked) -> None:
    """The catalog entry is authoritative for what the product IS.

    product_line is taken as-is, including empty: the line being present at some
    stores and absent at others is the split this exists to remove, so an entry with
    no line means every listing of it has no line. subtype and strain are taken only
    when the entry has one — a catalog row without them is incomplete, not a claim
    that the product has none. A self-censored strain ("Fu*K") is never copied onto
    a listing: the catalog is authoritative about which product it is, not about how
    to spell it on our menu. Fix those once in the admin and they flow everywhere.
    """
    if entry.get("subtype"):
        rec["subtype"] = entry["subtype"]
    strain = entry.get("strain")
    if strain and is_masked(strain):
        stats["masked_strain_skipped"] += 1
    elif strain:
        rec["strain"] = strain
    rec["product_line"] = entry.get("product_line")
    stats["overlaid"] += 1


def apply_verification(records: list[dict], existing: dict[tuple, dict]) -> int:
    """Human-signed fields win over everything, bound to the incoming scraped name."""
    protected = 0
    for rec in records:
        stored = existing.get((rec["sku"], rec["variant"] or ""))
        if not stored or not stored["verified_fields"]:
            continue
        held = verification.verified_fields(
            {"verified_fields": stored["verified_fields"], "scraped_name": rec["scraped_name"]})
        touched = False
        for field, value in (held or {}).items():
            col = VERIFIED_COLUMN.get(field)
            if col:
                rec[col] = value
                touched = True
        protected += touched
    return protected


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _upsert_sql(with_catalog: bool) -> str:
    catalog = """
        catalog_entry_id = CASE WHEN listings.catalog_match_method = 'manual'
                                THEN listings.catalog_entry_id ELSE EXCLUDED.catalog_entry_id END,
        catalog_match_confidence = CASE WHEN listings.catalog_match_method = 'manual'
                                THEN listings.catalog_match_confidence ELSE EXCLUDED.catalog_match_confidence END,
        catalog_match_method = CASE WHEN listings.catalog_match_method = 'manual'
                                THEN listings.catalog_match_method ELSE EXCLUDED.catalog_match_method END,
    """ if with_catalog else ""
    return f"""
        INSERT INTO listings ({", ".join(COLUMNS)})
        VALUES %s
        ON CONFLICT (dispensary_id, sku, COALESCE(variant, ''))
        WHERE sku IS NOT NULL
        DO UPDATE SET
            in_stock         = EXCLUDED.in_stock,
            is_active        = TRUE,
            price_cents      = EXCLUDED.price_cents,
            batch_id         = EXCLUDED.batch_id,
            image_url        = EXCLUDED.image_url,
            scraped_name     = EXCLUDED.scraped_name,
            scraped_brand    = EXCLUDED.scraped_brand,
            scraped_category = EXCLUDED.scraped_category,
            subtype          = EXCLUDED.subtype,
            strain           = EXCLUDED.strain,
            classification   = EXCLUDED.classification,
            description      = EXCLUDED.description,
            product_line     = EXCLUDED.product_line,
            attributes       = EXCLUDED.attributes,
            {catalog}
            url              = EXCLUDED.url,
            scraped_at       = EXCLUDED.scraped_at,
            last_seen_at     = EXCLUDED.last_seen_at,
            updated_at       = EXCLUDED.updated_at
    """


def _as_tuple(rec: dict) -> tuple:
    return tuple(Json(rec[c]) if c == "attributes" and rec[c] else rec[c] for c in COLUMNS)


TRACKED = [("in_stock", "in_stock"), ("price_cents", "price_cents"), ("image_url", "image_url"),
           ("scraped_name", "scraped_name"), ("scraped_brand", "scraped_brand"),
           ("scraped_cat", "scraped_category"), ("subtype", "subtype"), ("strain", "strain"),
           ("url", "url"), ("product_line", "product_line")]


def print_diff(slug: str, records: list[dict], existing: dict[tuple, dict]) -> None:
    new, changed, unchanged = [], [], 0
    counts: dict[str, int] = {}
    for rec in records:
        stored = existing.get((rec["sku"], rec["variant"] or ""))
        if stored is None:
            new.append(rec)
            continue
        diffs = []
        for label, col in TRACKED:
            if rec[col] != stored[col]:
                diffs.append(f"{label}: {stored[col]!r} -> {rec[col]!r}")
                counts[label] = counts.get(label, 0) + 1
        if diffs:
            changed.append((rec, diffs))
        else:
            unchanged += 1
    print(f"\n  --- diff: {slug} ---")
    print(f"  new: {len(new)}  |  changed: {len(changed)}  |  unchanged: {unchanged}")
    if counts:
        print("  field changes: " + ", ".join(
            f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))
    for rec, diffs in changed[:10]:
        print(f"    [{rec['sku']}] {rec['scraped_name'] or ''}:  {' | '.join(diffs)}")
    print()


def main(argv=None) -> int:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env(project_root)
    args = parse_args(argv)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set", file=sys.stderr)
        return 1
    if not os.path.isfile(args.csv):
        print(f"Error: CSV not found: {args.csv}", file=sys.stderr)
        return 1

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("CSV is empty — treating as a failed scrape.", file=sys.stderr)
        return 3

    # Brand aliases at the one place every row passes through. Three of five scrapers
    # applied them and two did not, so one brand could arrive under two spellings.
    from scraper_common import apply_brand_aliases, read_scrape_meta
    apply_brand_aliases(rows)
    # The scraper's own account of how much of the menu it got. A partial scrape is
    # still imported — prices and stock refresh for what arrived — but retires nothing.
    meta = read_scrape_meta(args.csv)
    partial = bool(meta.get("partial"))
    if partial:
        print(f"  [WARN] partial scrape ({meta.get('collected')} of {meta.get('reported_total')} "
              f"products): importing what arrived, retiring nothing")

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing {len(rows)} rows from {args.csv}")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    slugs = {r["dispensary_slug"].strip() for r in rows if r.get("dispensary_slug")}
    cur.execute("SELECT id, slug FROM dispensaries WHERE slug = ANY(%s)", (list(slugs),))
    dispensary_map: dict[str, str] = {slug: str(did) for did, slug in cur.fetchall()}
    missing = slugs - set(dispensary_map)
    if missing:
        print(f"  [WARN] Dispensaries not found (rows will be skipped): {missing} — "
              f"run scripts/import_dispensaries.py", file=sys.stderr)
    if not dispensary_map:
        conn.close()
        return 2

    catalogs: dict = {}
    use_jev = False
    usage = None
    if not args.no_catalog:
        import catalog_store
        import jev
        catalogs = catalog_store.load_from_cursor(cur)
        use_jev = not args.no_jev and jev.available()
        usage = jev.Usage()
        if catalogs:
            print(f"  catalogs: {len(catalogs)} brand(s)"
                  f"{'' if use_jev else ' — Jev off, exact matches only'}")

    now = utcnow()
    total_upserted = total_skipped = 0

    for slug, dispensary_id in dispensary_map.items():
        records = []
        for row in rows:
            if (row.get("dispensary_slug") or "").strip() != slug:
                continue
            rec = build_record(row, dispensary_id, now)
            if rec is None:
                total_skipped += 1
            else:
                records.append(rec)

        # Last row wins on a duplicate key, as the upsert would require anyway.
        records = list({(r["sku"], r["variant"] or ""): r for r in records}.values())
        existing = fetch_existing(cur, dispensary_id, [r["sku"] for r in records])

        # Counted before anything is written, so a dry run predicts the real run and
        # brand-new SKUs cannot inflate the denominator of the partial-scrape guard.
        cur.execute("SELECT COUNT(*) FROM listings WHERE dispensary_id = %s "
                    "AND sku IS NOT NULL AND is_active", (dispensary_id,))
        active_before = cur.fetchone()[0]

        kept = protect_failed_enrichment(records, existing)
        if kept:
            print(f"  enrichment failed on {kept} known listing(s); kept their stored identity")
        if not args.no_catalog:
            stats = apply_catalog(records, existing, catalogs, use_jev, slug, usage)
            interesting = {k: v for k, v in stats.items() if v and k != "no_catalog"}
            if interesting:
                print("  catalog: " + ", ".join(f"{k}={v}" for k, v in interesting.items()))
            if stats["masked_strain_skipped"]:
                print("  [note] some catalog entries carry a self-censored strain; fix the "
                      "spelling in the admin catalog page and it will apply everywhere")
        protected = apply_verification(records, existing)
        if protected:
            print(f"  verified: kept {protected} human-signed row(s) from being overwritten")

        print_diff(slug, records, existing)

        if not args.dry_run and records:
            psycopg2.extras.execute_values(cur, _upsert_sql(not args.no_catalog),
                                           [_as_tuple(r) for r in records], page_size=500)

        # Stale marking — listings on file but absent from this scrape. Guarded: a
        # partial scrape (pagination break, bot wall, API change) must not retire the
        # rest of the menu.
        keys = [f"{r['sku']}|{r['variant'] or ''}" for r in records]
        if partial:
            pass   # announced above; a short scrape is not evidence a listing is gone
        elif not keys:
            if active_before:
                print(f"  [WARN] scrape carried no rows; {active_before} active listings left untouched")
        elif active_before and len(keys) < args.stale_threshold * active_before:
            print(f"  [WARN] scrape carried {len(keys)} rows vs {active_before} active "
                  f"(< {args.stale_threshold:.0%}); looks partial — skipping stale-marking")
        else:
            cur.execute(
                """
                SELECT sku, variant, scraped_name FROM listings
                WHERE dispensary_id = %s AND sku IS NOT NULL AND is_active
                  AND sku || '|' || COALESCE(variant, '') != ALL(%s)
                """,
                (dispensary_id, keys),
            )
            stale = cur.fetchall()
            if stale:
                print(f"  marking {len(stale)} stale listings inactive:")
                for sku, variant, name in stale[:5]:
                    print(f"    [{sku}|{variant or ''}] {name}")
                if len(stale) > 5:
                    print(f"    ... and {len(stale) - 5} more")
                if not args.dry_run:
                    cur.execute(
                        """
                        UPDATE listings SET is_active = FALSE, in_stock = FALSE, updated_at = %s
                        WHERE dispensary_id = %s AND sku IS NOT NULL AND is_active
                          AND sku || '|' || COALESCE(variant, '') != ALL(%s)
                        """,
                        (now, dispensary_id, keys),
                    )

        total_upserted += len(records)
        print(f"  {slug}: {len(records)} upserted")

    if not args.dry_run:
        conn.commit()
    conn.close()

    if usage is not None and (usage.requests or usage.failures):
        print("  " + usage.summary())
    print(f"\nDone. rows processed: {total_upserted}  skipped (no name): {total_skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
