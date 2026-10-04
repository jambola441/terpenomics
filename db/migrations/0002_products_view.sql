-- The products view exactly as it runs in production (pg_get_viewdef, 2026-10-04).
-- Until now its only checked-in definition was in scripts/migrate.py, a destructive
-- reset script, and that copy had drifted: production groups on `attributes` too.
-- A no-op on production.
CREATE OR REPLACE VIEW products AS
 SELECT scraped_brand AS brand,
    scraped_category AS category,
    subtype,
    product_line,
    strain,
    variant,
    count(*) AS listing_count,
    count(DISTINCT dispensary_id) AS dispensary_count,
    min(price_cents) FILTER (WHERE in_stock = true) AS min_price_cents,
    max(price_cents) FILTER (WHERE in_stock = true) AS max_price_cents,
    bool_or(in_stock) AS any_in_stock,
    attributes
   FROM listings
  WHERE is_active = true
  GROUP BY scraped_brand, scraped_category, subtype, product_line, strain, variant, attributes;
