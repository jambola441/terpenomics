#!/usr/bin/env python3
"""
import_reading_examples.py — Copy data/reading_examples.json into the reading_examples
table (db/migrations/0021), once.

From then on catalog_reading reads the table (READING_EXAMPLES=db, or auto with the
Supabase service key set) and the admin audits' add-example / remove-example proposals
change it; the file stays as the fallback for an empty or unreachable table, and is no
longer edited.

  python scripts/import_reading_examples.py            # dry run: what would be inserted
  python scripts/import_reading_examples.py --write    # insert (refused if the table has rows)
  python scripts/import_reading_examples.py --write --replace   # deactivate what is there first

Over Supabase's REST API (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_reading  # noqa: E402

TABLE = "reading_examples"


def rows_from_file(data: dict) -> list[dict]:
    """The file's {brand_slug: [example, ...]} as table rows, in the file's order."""
    rows = []
    for slug, examples in data.items():
        for i, ex in enumerate(examples):
            rows.append({"id": str(uuid.uuid4()), "brand_slug": slug, "position": i,
                         "listing": ex["listing"], "size_field": ex.get("size_field"),
                         "entry": ex.get("entry") or {}, "is_active": True, "source": "file import"})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="insert the rows (else print what would be)")
    ap.add_argument("--replace", action="store_true", help="deactivate the table's active rows first")
    args = ap.parse_args(argv)

    rows = rows_from_file(catalog_reading.examples_from_file())
    brands = len({r["brand_slug"] for r in rows})
    print(f"{len(rows)} example(s) for {brands} brand(s) in {catalog_reading.EXAMPLES_PATH.name}")
    if not args.write:
        print("(dry run; --write inserts them)")
        return 0
    import db_http
    held = db_http.select(TABLE, "select=id&is_active=is.true&limit=1")
    if held and not args.replace:
        print("refused: the table already has active examples (--replace deactivates them first)",
              file=sys.stderr)
        return 2
    if held:
        db_http.update(TABLE, "is_active=is.true", {"is_active": False})
    for i in range(0, len(rows), 200):
        db_http.insert(TABLE, rows[i:i + 200])
    print(f"inserted {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
