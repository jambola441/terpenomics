-- A review decision `entry` is a transition to trusted, by review (owner decision
-- 2026-10-11): routes/admin/review.py sets the listing's catalog_entry_id to the
-- entry, catalog_match_method to 'manual' and catalog_match_confidence to 1.0, and
-- overlays the entry's identity. Undo puts the listing's previous match back, so the
-- decision keeps it:
--
--   reason           the prior catalog_match_method (already there, 0017)
--   prev_entry_id    the prior catalog_entry_id (often the matcher's suggestion)
--   prev_confidence  the prior catalog_match_confidence
--
-- create_all does not add columns to an existing table, so run this before the API
-- that maps them (models.py ReviewDecision) is deployed.
--
-- Skipped where review_decisions does not exist yet; create_all makes it from
-- models.py with these columns.
--
-- Idempotent.

DO $migration$
BEGIN
  IF to_regclass('public.review_decisions') IS NULL THEN
    RETURN;
  END IF;

  ALTER TABLE review_decisions
    ADD COLUMN IF NOT EXISTS prev_entry_id uuid REFERENCES brand_catalog_entries(id);
  ALTER TABLE review_decisions
    ADD COLUMN IF NOT EXISTS prev_confidence double precision;
END
$migration$;
