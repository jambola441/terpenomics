-- Columns production already has but no checked-in DDL created: verified_fields and
-- verified_at came from migrate_add_verification.py, attributes was added by hand.
-- A no-op on production; on a fresh database it makes the schema match.
ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS verified_fields jsonb,
  ADD COLUMN IF NOT EXISTS verified_at     timestamptz,
  ADD COLUMN IF NOT EXISTS attributes      jsonb;

CREATE INDEX IF NOT EXISTS listings_verified_idx
  ON listings (verified_at) WHERE verified_fields IS NOT NULL;
