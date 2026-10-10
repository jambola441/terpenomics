-- What customers are told about a partner store: what it is, where it is, when
-- it's open. Shown on the partners list and each partner's page, and puts the
-- locations on the map.
--
-- partners: a one- or two-sentence description, a short kind of business
-- ("Café"), and its website. Edited in the admin; the description and website
-- also by the partner at /partner. The POS sync fills them when they're blank.
--
-- partner_locations: coordinates, phone and opening hours. Square sends all
-- three with each location (connectors/square.py); a location added by hand,
-- for a partner without a POS, gets its coordinates from an address lookup in
-- the admin. `hours` is a list of {"day": "MON", "open": "09:00", "close": "17:00"}.
--
-- The partner tables come from scripts/migrate_add_pos_connectors.py, not
-- db/schema/pipeline.sql, so a database built from the pipeline schema alone
-- (the scripts' test database) has none to change.
--
-- Idempotent.

DO $$
BEGIN
  IF to_regclass('public.partners') IS NOT NULL THEN
    ALTER TABLE partners ADD COLUMN IF NOT EXISTS description text;
    ALTER TABLE partners ADD COLUMN IF NOT EXISTS category    text;
    ALTER TABLE partners ADD COLUMN IF NOT EXISTS website_url text;
  END IF;
  IF to_regclass('public.partner_locations') IS NOT NULL THEN
    ALTER TABLE partner_locations ADD COLUMN IF NOT EXISTS lat   double precision;
    ALTER TABLE partner_locations ADD COLUMN IF NOT EXISTS lng   double precision;
    ALTER TABLE partner_locations ADD COLUMN IF NOT EXISTS phone text;
    ALTER TABLE partner_locations ADD COLUMN IF NOT EXISTS hours jsonb;
  END IF;
END $$;
