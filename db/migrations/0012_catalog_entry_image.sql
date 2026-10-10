-- brand_catalog_entries.image_url: the brand's own photo of the product, read off
-- its site by scripts/storefront.py. Shopify, WooCommerce and WordPress sources carry
-- one; an html or json recipe names one with source.fields.image. A push refreshes it
-- (a site's photo is metadata, not a curated field) and never blanks one the site
-- stopped sending.
--
-- A listing whose match to the entry is trusted shows this photo in place of the
-- store's (services/listing_photos.py): the same product looked different at every
-- store, 2.5 photos per matched product on 2026-10-09.
--
-- Idempotent.

ALTER TABLE brand_catalog_entries ADD COLUMN IF NOT EXISTS image_url text;
