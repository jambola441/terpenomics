-- Pre-rolls keep no subtype (scripts/taxonomy.py, keeps_subtype). Single or pack is
-- the size's pack count, and infused is the product line where the brand names one.
-- As a subtype, infused took the slot from pack, and one product sat under two
-- subtypes at different stores: two rows in the products view, two catalog entries.
--
-- The importer drops a pre-roll's subtype from now on; this clears the ones already
-- stored. Bootstrap entries are re-proposed without one by
-- `catalog_bootstrap.py --rebuild --push --replace`. Idempotent.
UPDATE listings
SET subtype = NULL
WHERE scraped_category = 'preroll'
  AND subtype IS NOT NULL;

UPDATE brand_catalog_entries
SET subtype = NULL
WHERE category = 'preroll'
  AND subtype IS NOT NULL;
