-- reset_listings.sql — wipe listings (and the orders that reference them),
-- then re-establish the variant-aware listing key.
--
-- DESTRUCTIVE AND IRREVERSIBLE. Run in the Supabase SQL editor, or from a shell
-- where 5432 is reachable:
--
--     psql "$DATABASE_URL" -f scripts/reset_listings.sql
--
-- What it does NOT touch: dispensaries, brand_aliases, customers,
-- phone_auth_identities, phone_auth_challenges. Those survive.
--
-- Verified state before writing this (2026-08-26):
--     listings              27165
--     orders                    1   <- a real order, 2026-08-26 00:09 UTC
--     order_items               1   <- references listing 7d7180fd-…, at
--                                      brooklyn-organic-buds ("Apple & Bananas
--                                      | Premium Flower", sku 1450)
--     listing_terpenes          0
--     listing_cannabinoids      0
--     purchase_items            0
--
-- order_items -> listings has no ON DELETE CASCADE, so that one order is what
-- blocks a plain DELETE FROM listings. Steps 1-2 remove it deliberately.

BEGIN;

-- 1. the order that references a listing
DELETE FROM order_items;
DELETE FROM orders;

-- 2. every listing
DELETE FROM listings;

-- 3. the migration that has never actually run against this database.
--    Checked directly: listings_dispensary_sku_unique is a plain UNIQUE INDEX
--    (not constraint-backed — pg_constraint holds only the pkey and the
--    dispensary FK), and listings_dispensary_sku_variant_unique does not exist.
--    Without this, a re-import still rejects rows that share a SKU across weight
--    tiers — 924 of them in the 2026-08-25 run. Clearing the table alone does
--    NOT fix that; the index is what rejects them.
DROP INDEX IF EXISTS listings_dispensary_sku_unique;

CREATE UNIQUE INDEX IF NOT EXISTS listings_dispensary_sku_variant_unique
  ON listings (dispensary_id, sku, COALESCE(variant, ''))
  WHERE sku IS NOT NULL;

ALTER TABLE listings ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP;

COMMIT;

-- Confirm:
--   SELECT count(*) FROM listings;                    -- 0
--   SELECT indexname FROM pg_indexes
--    WHERE tablename='listings' ORDER BY indexname;   -- variant_unique present,
--                                                     -- sku_unique gone
--
-- Then re-populate from a machine where 5432 is reachable:
--   python scripts/scrape.py --all --parallel
--
-- Note step 3 covers the same ground as migrate_listing_variant_key.py steps
-- 1-3. Its step 4 (clearing ~10,265 synthetic batch_ids) is intentionally
-- omitted here — DELETE FROM listings makes it moot.
