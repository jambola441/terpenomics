-- Brand reading examples in the database (until now data/reading_examples.json only).
--
-- scripts/catalog_reading.py shows a question a few of the brand's own listings with
-- their answers (brand_examples). In a file, a new example needed a commit and a
-- deploy; in this table an approved add-example / remove-example proposal
-- (routes/admin/audits.py, scripts/audits.py) counts from the next read on.
--
--   brand_slug  the catalog's brand_slug (the file's top-level key)
--   position    order within the brand, as in the file
--   listing     a store listing's title
--   size_field  the store's size field, where the example is about size
--   entry       catalog_fix's selector naming one entry: {category, strain, size, ...}
--   is_active   false: taken out (remove-example); kept for the record
--
-- Filled once by scripts/import_reading_examples.py --write. catalog_reading reads it
-- when READING_EXAMPLES is db (or auto, with the Supabase service key set) and falls
-- back to the file when the table is empty or cannot be read.
--
-- Not mapped by models.py, so create_all does not make it: run this before the import.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS reading_examples (
  id          uuid      PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_slug  text      NOT NULL,
  position    integer   NOT NULL DEFAULT 0,
  listing     text      NOT NULL,
  size_field  text,
  entry       jsonb     NOT NULL,
  is_active   boolean   NOT NULL DEFAULT true,
  source      text,
  created_at  timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS ix_reading_examples_brand_slug ON reading_examples (brand_slug);

ALTER TABLE reading_examples ENABLE ROW LEVEL SECURITY;
