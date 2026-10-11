-- The review queue's `category` decision (owner decision 2026-10-11): a listing whose
-- category or subtype Jev was unsure of at enrichment, and that the catalog did not
-- settle, is in the queue with catalog_match_method 'review_category'
-- (scripts/import_listings.py mark_unsure_category). The reviewer picks its category
-- and subtype; routes/admin/review.py writes them to the listing and adds them to its
-- verified_fields, so every later import keeps them. The decision keeps both the
-- choice and what it replaced, for undo:
--
--   category, subtype            the reviewer's choice
--   prev_category, prev_subtype  the listing's scraped_category and subtype before
--   prev_verified                the listing's verified_fields before
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

  ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS category      text;
  ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS subtype       text;
  ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS prev_category text;
  ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS prev_subtype  text;
  ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS prev_verified jsonb;
END
$migration$;
