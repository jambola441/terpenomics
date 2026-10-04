-- Catalog entries learn which product they are a size of, where they came from, and
-- how many stores vouch for them.
--
--   product_key  groups an entry's sizes into one product. Lived only in the export
--                file (as product_external_id) until now, so a catalog read from the
--                database could not tell Ayrloom's 'honeycrisp' vape from its
--                'honeycrisp' beverage except by category.
--   source       how the entry was made: shopify_products_json, listings_bootstrap,
--                manual — per entry, because one catalog can mix them.
--   support      for listings_bootstrap entries, how many stores carried the product
--                when it was proposed — the strength of the consensus behind it.
ALTER TABLE brand_catalog_entries
  ADD COLUMN IF NOT EXISTS product_key text,
  ADD COLUMN IF NOT EXISTS source      text,
  ADD COLUMN IF NOT EXISTS support     integer;

CREATE INDEX IF NOT EXISTS brand_catalog_entries_product_idx
  ON brand_catalog_entries (catalog_id, product_key) WHERE is_active;
