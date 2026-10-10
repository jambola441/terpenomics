-- Photos Terpee serves itself, from Supabase Storage.
--
-- The `photos` bucket holds store photos copied at web sizes from hosts that cannot
-- resize on request (scripts/photo_mirror.py) and, later, brand logos. It is public:
-- anyone can read a file by its URL, and nothing grants a policy on storage.objects,
-- so only the service role (the pipeline and the API) can write.
--
-- Supabase creates the storage schema; a plain Postgres (the test database) has none,
-- so the bucket is added only where the schema exists.
--
-- Idempotent.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'storage') THEN
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    VALUES ('photos', 'photos', true, 5242880,
            ARRAY['image/webp', 'image/png', 'image/jpeg', 'image/svg+xml'])
    ON CONFLICT (id) DO NOTHING;
  END IF;
END $$;

-- One row per store photo URL the pipeline has tried to copy. `url` is the copy's
-- 640px file; a 320px one sits beside it (…/320.webp). A row whose copy failed keeps
-- the reason, has no url, and is tried again after a week.
CREATE TABLE IF NOT EXISTS photo_mirrors (
  source_url  text PRIMARY KEY,
  url         text,
  bytes       integer,
  failed      text,
  mirrored_at timestamptz NOT NULL DEFAULT now()
);
