"""The import writes no derived identity onto a listing (owner, 2026-10-12): subtype,
strain, product_line and size are inserted NULL and never updated; the shop reads a
trusted match's entry (services/shop_listings.py)."""

import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import import_listings  # noqa: E402


def test_the_upsert_sql_neither_inserts_nor_updates_identity():
    for with_catalog in (True, False):
        sql = import_listings._upsert_sql(with_catalog)
        insert = re.search(r"INSERT INTO listings \(([^)]*)\)", sql).group(1)
        for col in import_listings.NOT_WRITTEN:
            assert col not in insert.split(", ")
            assert not re.search(rf"\b{col}\s*=", sql)
    assert "scraped_category = EXCLUDED.scraped_category" in " ".join(sql.split())


def test_the_rest_path_sends_no_identity_columns():
    sent = []

    class FakeDb:
        def insert(self, table, rows):
            sent.extend(rows)

        def upsert(self, table, rows, on_conflict):
            sent.extend(rows)

    store = import_listings.RestStore.__new__(import_listings.RestStore)
    store.db = FakeDb()
    now = datetime.now(timezone.utc)
    rec = import_listings.build_record({"name": "MFNY Skunk Mini Preroll", "sku": "s1", "brand": "MFNY",
                                        "category": "pre-rolls", "product_line": "Mini",
                                        "strain": "Skunk"}, "d1", now)
    stored = {**rec, "id": "x", "variant": None, "created_at": now.isoformat(), "reading": None,
              "url": None, "catalog_entry_id": None, "catalog_match_confidence": None,
              "catalog_match_method": None}
    store.upsert([rec], {}, True)
    store.upsert([rec], {("s1", ""): stored}, True)
    assert len(sent) == 2
    for row in sent:
        assert not set(row) & set(import_listings.NOT_WRITTEN)
        assert row["scraped_name"] == "MFNY Skunk Mini Preroll"
