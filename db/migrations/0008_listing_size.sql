-- listings.size: the size product pages group on.
--
-- `variant` is the store's own size, kept as typed: it is part of the row's key
-- (dispensary, sku, variant), and orders, purchases and lab reports hang off the row.
-- So a store's typo made a product of its own: Camino's 100mg 20-pack listed as 50mg,
-- Ayrloom's 150mg drops as 600mg (150mg THC + 450mg CBD). The importer now writes
-- `size`: the store's size, or the catalog's when the store mistyped it
-- (scripts/import_listings.py, assign_sizes). A row not re-imported since reads its
-- `variant` (COALESCE). The view keeps its column name, so its readers are unchanged.
-- Idempotent.
ALTER TABLE listings ADD COLUMN IF NOT EXISTS size varchar(100);

CREATE OR REPLACE VIEW products AS
 SELECT scraped_brand AS brand,
    scraped_category AS category,
    subtype,
    product_line,
    strain,
    COALESCE(size, variant)::varchar(100) AS variant,
    count(*) AS listing_count,
    count(DISTINCT dispensary_id) AS dispensary_count,
    min(price_cents) FILTER (WHERE in_stock = true) AS min_price_cents,
    max(price_cents) FILTER (WHERE in_stock = true) AS max_price_cents,
    bool_or(in_stock) AS any_in_stock,
    attributes
   FROM listings
  WHERE is_active = true
  GROUP BY scraped_brand, scraped_category, subtype, product_line, strain,
    COALESCE(size, variant)::varchar(100), attributes;
