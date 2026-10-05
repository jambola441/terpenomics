-- The enrich cache in Postgres, for runs with no persistent disk (a Render cron job, a
-- sandbox): scripts/enrich_cache_db.py, used when ENRICH_CACHE=db. One row per store
-- and cache key; `entry` is the answer enrich.py would otherwise keep in
-- data/enrich_cache/<slug>.json. A non-default model's slug carries the model as a
-- suffix (enrich.py), so a comparison run never reads another model's answers.
CREATE TABLE IF NOT EXISTS enrich_cache (
  slug       text        NOT NULL,
  cache_key  text        NOT NULL,
  entry      jsonb       NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (slug, cache_key)
);

-- Kept from the anon key like every other table (0004); explicit, though the event
-- trigger would do it too.
ALTER TABLE enrich_cache ENABLE ROW LEVEL SECURITY;
