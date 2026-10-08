-- listings.reading: the listing's own reading of what it is, as enrichment and the
-- rule files gave it (category, subtype, strain, product_line, size), saved before
-- the catalog overlay replaces those columns with the matched entry's. The matcher
-- joins on it (catalog_match.CatalogIndex.join), so a re-match reads what the store
-- wrote, never the last match's answer.
--
-- Filled at import (import_listings.record_reading); listings imported before this
-- get theirs from scripts/backfill_reading.py.
--
-- Idempotent.

ALTER TABLE listings ADD COLUMN IF NOT EXISTS reading jsonb;
