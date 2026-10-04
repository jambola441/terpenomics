-- Production DDL for the tables the scrape -> enrich -> import -> match pipeline
-- writes, read from the live database on 2026-10-04 (pg_attribute, pg_indexes).
--
-- Not a migration: production already has all of this. It exists so tests can run
-- the importer against a real Postgres (scripts/test_import_listings.py) and so the
-- schema the pipeline depends on is written down somewhere other than in the live
-- database. Schema changes go in db/migrations/, applied by scripts/db_migrate.py.

DO $$ BEGIN
  CREATE TYPE postype AS ENUM ('none', 'alleaves', 'leaflogix');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS dispensaries (
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  name character varying(200) NOT NULL,
  slug character varying(100) NOT NULL,
  website_url character varying(500),
  location character varying(200),
  address character varying(500),
  lat double precision,
  lng double precision,
  pos_type postype NOT NULL,
  id uuid PRIMARY KEY,
  is_active boolean NOT NULL DEFAULT true,
  pos_tenant_id character varying(200),
  accepts_pickup boolean NOT NULL DEFAULT false,
  logo_url character varying(1000),
  banner_url character varying(1000)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_dispensaries_slug ON dispensaries (slug);

CREATE TABLE IF NOT EXISTS brand_catalogs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_slug text NOT NULL UNIQUE,
  brand_name text NOT NULL,
  source_url text,
  source_method text NOT NULL,
  fetched_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS brand_catalog_entries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  catalog_id uuid NOT NULL REFERENCES brand_catalogs(id) ON DELETE CASCADE,
  external_id text,
  name text NOT NULL,
  product_line text,
  category text,
  subtype text,
  strain text,
  variant text,
  attributes jsonb,
  match_terms text[],
  is_active boolean NOT NULL DEFAULT true,
  first_seen_at timestamp with time zone NOT NULL DEFAULT now(),
  last_seen_at timestamp with time zone NOT NULL DEFAULT now(),
  verified_fields jsonb,
  verified_by text,
  verified_at timestamp with time zone,
  UNIQUE (catalog_id, external_id)
);
CREATE INDEX IF NOT EXISTS brand_catalog_entries_catalog_idx
  ON brand_catalog_entries (catalog_id) WHERE is_active;

CREATE TABLE IF NOT EXISTS listings (
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  dispensary_id uuid NOT NULL REFERENCES dispensaries(id),
  sku character varying(200),
  batch_id character varying(200),
  price_cents integer,
  variant character varying(100),
  url character varying(1000),
  image_url character varying(1000),
  in_stock boolean NOT NULL,
  is_active boolean NOT NULL,
  scraped_at timestamp without time zone,
  scraped_name character varying(300),
  scraped_brand character varying(200),
  scraped_category character varying(100),
  subtype character varying(100),
  strain character varying(200),
  classification character varying(50),
  description character varying(5000),
  id uuid PRIMARY KEY,
  product_line character varying(200),
  last_seen_at timestamp with time zone,
  verified_fields jsonb,
  verified_at timestamp with time zone,
  attributes jsonb,
  catalog_entry_id uuid REFERENCES brand_catalog_entries(id),
  catalog_match_confidence real,
  catalog_match_method text
);
CREATE INDEX IF NOT EXISTS ix_listings_dispensary_id ON listings (dispensary_id);
CREATE INDEX IF NOT EXISTS listings_catalog_entry_idx
  ON listings (catalog_entry_id) WHERE catalog_entry_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS listings_verified_idx
  ON listings (verified_at) WHERE verified_fields IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS listings_dispensary_sku_variant_unique
  ON listings (dispensary_id, sku, COALESCE(variant, ''::character varying)) WHERE sku IS NOT NULL;
