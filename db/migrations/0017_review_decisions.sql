-- The catalog review queue's decisions, one row per call a reviewer makes on a
-- listing the matcher left for review (catalog_match_method review_unsure,
-- review_missing or review_near; scripts/catalog_match.py review_reason).
--
-- A decision entry makes the listing a manual match to entry_id (trusted, by
-- review; since 2026-10-11, see 0018). Every other decision is recorded only: it
-- never changes the listing's match or the catalog. Catalog issues are fixed in
-- the catalog, and these rows are what the catalog-fix proposals are drawn up from. routes/admin/review.py writes them; models.py
-- (ReviewDecision) maps onto this table.
--
--   decision  entry    the listing is entry_id (one of the candidates offered)
--             none     none of the candidates offered
--             missing  the catalog lacks this product, or this size of it
--             skip     passed over; still counts as decided, undo brings it back
--   reason    the listing's catalog_match_method when the call was made
--
-- A new table, so the API's create_all makes it at startup and this needs no run
-- before deploy. This file exists so the table is on record with the rest, and
-- for databases where the API has not started yet. Index names match the ones
-- create_all gives (models.py), so the two never make a second copy.
--
-- RLS: the ensure_rls event trigger (0004) turns it on for any new public
-- table; it is set here as well so the table never depends on the trigger.
--
-- Skipped where listings or brand_catalog_entries does not exist yet; create_all
-- makes it from models.py.
--
-- Idempotent.

DO $migration$
BEGIN
  IF to_regclass('public.listings') IS NULL
     OR to_regclass('public.brand_catalog_entries') IS NULL THEN
    RETURN;
  END IF;

  CREATE TABLE IF NOT EXISTS review_decisions (
    id          uuid        PRIMARY KEY,
    listing_id  uuid        NOT NULL REFERENCES listings(id),
    reviewer    text        NOT NULL,
    decision    varchar(16) NOT NULL,
    entry_id    uuid        REFERENCES brand_catalog_entries(id),
    note        text,
    reason      varchar(32),
    created_at  timestamp   NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
  );

  -- The queue's "not decided yet" test, and a reviewer's undo and pace.
  CREATE INDEX IF NOT EXISTS ix_review_decisions_listing_id
    ON review_decisions (listing_id);
  CREATE INDEX IF NOT EXISTS review_decisions_reviewer_created_at
    ON review_decisions (reviewer, created_at);

  ALTER TABLE review_decisions ENABLE ROW LEVEL SECURITY;
END
$migration$;
