-- Lab reports (certificates of analysis) that brands publish, kept by Terpee.
--
-- scripts/coa_crawl.py finds a brand's reports by a recipe (data/coa_sources/), reads
-- each with scripts/coa_read.py, copies the PDF to the `coas` bucket and records it
-- here. A report is the lab's word on ONE lot, so it is kept per lot; it reaches a
-- product through coa_report_entries, and a listing through the listing's catalog
-- entry ("a recent tested lot of this product") or, exactly, through the listing's
-- batch_id being the report's lot or Metrc tag.
--
-- lab_reports (models.py) is the older, per-listing table with the PDF in the row;
-- it is empty and left alone.
--
-- `coas` is public, like `photos`: brands publish these reports themselves and NY
-- labels must link to them (9 NYCRR 128.5(b)(10)). Only the service role writes.
--
-- Not mapped by models.py, so create_all does not make it.
--
-- Idempotent.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'storage') THEN
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    VALUES ('coas', 'coas', true, 26214400, ARRAY['application/pdf'])
    ON CONFLICT (id) DO NOTHING;
  END IF;
END $$;

-- One row per report the brand publishes, keyed by where the brand publishes it.
--   source_url      the brand's own URL for the PDF
--   sha256          the PDF's content hash; the bucket path is coas/<brand>/<sha256>.pdf
--   file_url        Terpee's public copy
--   lot             the lot as the brand names it (link or report); report_lot is the lab's
--   metrc_tag       the tested package's Metrc tag; source_package its source package
--   category        our category for the product tested (flower, vaporizers, edible...),
--                   or null when neither the report nor the recipe says
--   catalog_strain  the brand catalog strain the report names (normalized), or null
--   cannabinoids    {canonical name: percent}; terpenes likewise
--   reader_version  coa_read.VERSION that read it; a newer reader re-reads from the copy
--   error           why it could not be read (the row is kept so it is not re-fetched)
CREATE TABLE IF NOT EXISTS coa_reports (
  id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  catalog_id         uuid        NOT NULL REFERENCES brand_catalogs(id) ON DELETE CASCADE,
  source_url         text        NOT NULL UNIQUE,
  sha256             text,
  storage_path       text,
  file_url           text,
  bytes              integer,
  link_text          text,
  lab                text,
  producer_license   text,
  lot                text,
  report_lot         text,
  metrc_tag          text,
  source_package     text,
  product_name       text,
  sample_type        text,
  category           text,
  strain             text,
  catalog_strain     text,
  test_date          text,
  total_thc          numeric,
  total_cbd          numeric,
  total_cannabinoids numeric,
  total_terpenes     numeric,
  cannabinoids       jsonb,
  terpenes           jsonb,
  reader_version     integer,
  error              text,
  fetched_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS coa_reports_catalog ON coa_reports (catalog_id);
CREATE INDEX IF NOT EXISTS coa_reports_metrc_tag ON coa_reports (metrc_tag) WHERE metrc_tag IS NOT NULL;
CREATE INDEX IF NOT EXISTS coa_reports_lot ON coa_reports (lot) WHERE lot IS NOT NULL;

-- Which catalog entries a report is for. Rebuilt per brand on every push.
--   method  'strain_category': the entry's strain and category are the report's
--           'strain': the brand has one category, so the strain alone decides
CREATE TABLE IF NOT EXISTS coa_report_entries (
  report_id  uuid NOT NULL REFERENCES coa_reports(id) ON DELETE CASCADE,
  entry_id   uuid NOT NULL REFERENCES brand_catalog_entries(id) ON DELETE CASCADE,
  method     text NOT NULL,
  PRIMARY KEY (report_id, entry_id)
);
CREATE INDEX IF NOT EXISTS coa_report_entries_entry ON coa_report_entries (entry_id);

-- Row-level security on, no policies: like every other table (0004), only the service
-- role reads or writes; the API serves what the app sees.
ALTER TABLE coa_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE coa_report_entries ENABLE ROW LEVEL SECURITY;
