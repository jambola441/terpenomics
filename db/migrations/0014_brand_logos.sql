-- brand_logos: the logo a brand's tile and page show. A person picks it in the admin
-- from candidates read off the brand's own site, or uploads one
-- (routes/admin/brand_logos.py); the file goes to the photos bucket (migration 0013).
-- A brand without one keeps what it showed before: a product photo, or its initial.
--
-- Keyed by the folding catalogs use (catalog_store.brand_key: lowercase, '&' as
-- 'and', no punctuation), so "Papa & Barkley" and "Papa and Barkley" share a logo.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS brand_logos (
  brand_key  text PRIMARY KEY,
  brand_name text NOT NULL,
  logo_url   text,
  source_url text,
  site_url   text,
  chosen_by  text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
