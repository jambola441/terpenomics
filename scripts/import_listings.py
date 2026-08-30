"""
import_listings.py — Import scraped listing CSVs into the DB.

Upserts listings keyed on (dispensary_id, sku, COALESCE(variant, '')) — several
platforms reuse one SKU across weight/price tiers, so the variant is part of a
listing's identity. On conflict, updates volatile fields (in_stock, price_cents,
image_url, url, scraped_at, subtype, strain, scraped_name, scraped_brand,
scraped_category, description).

Usage:
  python scripts/import_listings.py \\
    --csv prototypes/alleaves-scraper/brooklynorganicbuds_listings.csv \\
    [--dry-run]

  DATABASE_URL must be set in the environment or in .env at the project root.
"""

import argparse
import csv
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verification  # noqa: E402
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2-binary required: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_args():
    p = argparse.ArgumentParser(description="Import scraped listings into terpenomics DB")
    p.add_argument("--csv", required=True, help="Path to scraper CSV file")
    p.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    p.add_argument(
        "--stale-threshold", type=float, default=0.5,
        help="Skip marking absent listings inactive when this scrape carries fewer "
             "than THRESHOLD × the dispensary's currently-active listings (default 0.5). "
             "Guards a partial scrape from deactivating the rest of the menu. 0 disables.",
    )
    return p.parse_args()


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


def parse_bool(val: str) -> bool:
    return str(val).strip().upper() in ("TRUE", "1", "YES")


def parse_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def parse_float(val):
    try:
        v = float(val)
        return v if v else None
    except (ValueError, TypeError):
        return None


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env(project_root)

    args = parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.csv):
        print(f"Error: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSV is empty.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing {len(rows)} rows from {args.csv}")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # Resolve dispensary slugs
    slugs = {r["dispensary_slug"].strip() for r in rows if r.get("dispensary_slug")}
    cur.execute("SELECT id, slug FROM dispensaries WHERE slug = ANY(%s)", (list(slugs),))
    dispensary_map: dict[str, str] = {slug: str(did) for did, slug in cur.fetchall()}
    missing = slugs - set(dispensary_map)
    if missing:
        print(f"  [WARN] Dispensaries not found (rows will be skipped): {missing}")

    now = utcnow()
    total_inserted = 0
    total_skipped  = 0

    for slug, dispensary_id in dispensary_map.items():
        disp_rows = [r for r in rows if r.get("dispensary_slug", "").strip() == slug]

        to_upsert: list[tuple] = []
        no_sku_insert: list[tuple] = []

        for row in disp_rows:
            sku              = (row.get("sku")          or "").strip() or None
            batch_id         = (row.get("batch_id")     or "").strip() or None
            scraped_name     = (row.get("name")         or "").strip() or None
            scraped_brand    = (row.get("brand")        or "").strip() or None
            scraped_category = (row.get("category")     or "").strip() or None
            subtype          = (row.get("subtype")      or "").strip() or None
            strain           = (row.get("strain")       or "").strip() or None
            product_line     = (row.get("product_line") or "").strip() or None
            price_cents      = parse_int(row.get("price_cents"))
            variant          = (row.get("variant")      or "").strip() or None
            url              = (row.get("product_url")  or "").strip() or None
            image_url        = (row.get("image_url")    or "").strip() or None
            in_stock         = parse_bool(row.get("in_stock", "true"))
            scraped_at       = (row.get("scraped_at")   or "").strip() or None
            classification   = (row.get("classification") or "").strip() or None
            description      = (row.get("description")  or "").strip() or None

            if not scraped_name:
                total_skipped += 1
                continue

            record = (
                str(uuid.uuid4()),  # 0:  id
                dispensary_id,      # 1:  dispensary_id
                sku,                # 2:  sku
                batch_id,           # 3:  batch_id
                price_cents,        # 4:  price_cents
                variant,            # 5:  variant
                url,                # 6:  url
                image_url,          # 7:  image_url
                in_stock,           # 8:  in_stock
                True,               # 9:  is_active
                scraped_at,         # 10: scraped_at
                scraped_name,       # 11: scraped_name
                scraped_brand,      # 12: scraped_brand
                scraped_category,   # 13: scraped_category
                subtype,            # 14: subtype
                strain,             # 15: strain
                classification,     # 16: classification
                description,        # 17: description
                product_line,       # 18: product_line
                now,                # 19: created_at
                now,                # 20: updated_at
                now,                # 21: last_seen_at
            )

            if sku:
                to_upsert.append(record)
            else:
                no_sku_insert.append(record)

        # --- Diff summary ---
        if to_upsert:
            skus = [r[2] for r in to_upsert]
            cur.execute(
                """
                SELECT sku, in_stock, price_cents, image_url,
                       scraped_name, scraped_brand, scraped_category,
                       subtype, strain, url, product_line, COALESCE(variant, ''),
                       verified_fields
                FROM listings
                WHERE dispensary_id = %s AND sku = ANY(%s)
                """,
                (dispensary_id, skus),
            )
            existing: dict[tuple, tuple] = {(row[0], row[11]): row for row in cur.fetchall()}

            # Overlay human-verified fields onto the records about to be written.
            # Doing it here rather than in the upsert's DO UPDATE keeps one
            # implementation of the name hash — a CASE expression would need the
            # same normalisation in SQL, and the two drifting apart would silently
            # either drop protection or freeze stale values.
            #
            # A claim is about a (listing, scraped_name) pair. verified_fields()
            # compares the stored hash against the INCOMING name, so a renamed
            # product lapses and the scraped value takes over, which is the
            # behaviour we want: nobody has read the new name.
            VERIFIED_IDX = {"subtype": 14, "strain": 15, "product_line": 18, "variant": 5}
            protected = 0
            for pos, rec in enumerate(to_upsert):
                db_row = existing.get((rec[2], rec[5] or ""))
                if not db_row or not db_row[12]:
                    continue
                held = verification.verified_fields(
                    {"verified_fields": db_row[12], "scraped_name": rec[11]})
                if not held:
                    continue
                as_list = list(rec)
                for field, value in held.items():
                    idx = VERIFIED_IDX.get(field)
                    if idx is not None:
                        as_list[idx] = value
                to_upsert[pos] = tuple(as_list)
                protected += 1
            if protected:
                print(f"  verified: kept {protected} human-signed row(s) from being overwritten")

            TRACKED = [
                # (label, record_idx, existing_col_idx)
                ("in_stock",       8,  1),
                ("price_cents",    4,  2),
                ("image_url",      7,  3),
                ("scraped_name",  11,  4),
                ("scraped_brand", 12,  5),
                ("scraped_cat",   13,  6),
                ("subtype",       14,  7),
                ("strain",        15,  8),
                ("url",            6,  9),
                ("product_line",  18, 10),
            ]

            new_skus, changed, unchanged = [], [], []
            field_change_counts: dict[str, int] = {}

            for rec in to_upsert:
                sku_val = rec[2]
                key = (sku_val, rec[5] or "")
                if key not in existing:
                    new_skus.append(sku_val)
                    continue
                db_row = existing[key]
                diffs = []
                for label, ri, di in TRACKED:
                    nv, ov = rec[ri], db_row[di]
                    if nv != ov:
                        diffs.append(f"{label}: {ov!r} → {nv!r}")
                        field_change_counts[label] = field_change_counts.get(label, 0) + 1
                if diffs:
                    changed.append((rec, diffs))
                else:
                    unchanged.append(sku_val)

            print(f"\n  --- diff: {slug} ---")
            print(f"  new: {len(new_skus)}  |  changed: {len(changed)}  |  unchanged: {len(unchanged)}  |  no-SKU: {len(no_sku_insert)}")
            if field_change_counts:
                print("  field changes: " + ", ".join(
                    f"{k}={v}" for k, v in sorted(field_change_counts.items(), key=lambda x: -x[1])
                ))
            if changed:
                print(f"  sample changes (first {min(10, len(changed))}):")
                for rec, diffs in changed[:10]:
                    print(f"    [{rec[2]}] {rec[11] or ''}:  {' | '.join(diffs)}")
            print()

        if not args.dry_run:
            if to_upsert:
                # Deduplicate by (sku, variant) — last row wins (avoids CardinalityViolation)
                seen: dict[tuple, tuple] = {}
                for rec in to_upsert:
                    seen[(rec[2], rec[5] or "")] = rec
                to_upsert = list(seen.values())

                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO listings
                        (id, dispensary_id, sku, batch_id, price_cents, variant, url, image_url,
                         in_stock, is_active, scraped_at,
                         scraped_name, scraped_brand, scraped_category,
                         subtype, strain, classification, description, product_line,
                         created_at, updated_at, last_seen_at)
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
                        url              = EXCLUDED.url,
                        scraped_at       = EXCLUDED.scraped_at,
                        last_seen_at     = EXCLUDED.last_seen_at,
                        updated_at       = EXCLUDED.updated_at
                    """,
                    to_upsert,
                )

            if no_sku_insert:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO listings
                        (id, dispensary_id, sku, batch_id, price_cents, variant, url, image_url,
                         in_stock, is_active, scraped_at,
                         scraped_name, scraped_brand, scraped_category,
                         subtype, strain, classification, description, product_line,
                         created_at, updated_at, last_seen_at)
                    VALUES %s
                    """,
                    no_sku_insert,
                )

        # Mark stale listings inactive — (sku, variant) rows present in DB but absent
        # from this scrape. Guarded: a partial scrape (pagination break, platform API
        # change) must not deactivate the rest of the menu, so we skip the step when
        # this scrape carries suspiciously few rows vs. what's currently active.
        upserted_keys = [f"{rec[2]}|{rec[5] or ''}" for rec in to_upsert if rec[2]]
        cur.execute(
            """
            SELECT COUNT(*) FROM listings
            WHERE dispensary_id = %s AND sku IS NOT NULL AND is_active = TRUE
            """,
            (dispensary_id,),
        )
        active_count = cur.fetchone()[0]

        if not upserted_keys:
            if active_count:
                print(f"  [WARN] scrape carried no SKU'd rows; skipping stale-marking "
                      f"({active_count} active listings left untouched)")
        elif active_count and len(upserted_keys) < args.stale_threshold * active_count:
            print(f"  [WARN] scrape carried {len(upserted_keys)} rows vs {active_count} active "
                  f"(< {args.stale_threshold:.0%}); looks partial — skipping stale-marking")
        else:
            cur.execute(
                """
                SELECT sku, variant, scraped_name FROM listings
                WHERE dispensary_id = %s AND sku IS NOT NULL AND is_active = TRUE
                  AND sku || '|' || COALESCE(variant, '') != ALL(%s)
                """,
                (dispensary_id, upserted_keys),
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
                        WHERE dispensary_id = %s AND sku IS NOT NULL
                          AND sku || '|' || COALESCE(variant, '') != ALL(%s)
                        """,
                        (now, dispensary_id, upserted_keys),
                    )

        total_inserted += len(to_upsert) + len(no_sku_insert)
        print(f"  {slug}: {len(to_upsert)} upserted, {len(no_sku_insert)} inserted (no SKU), "
              f"{len(disp_rows) - len(to_upsert) - len(no_sku_insert)} skipped")

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\nDone. rows processed: {total_inserted}  skipped (no name): {total_skipped}")


if __name__ == "__main__":
    main()
