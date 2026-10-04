-- Row-level security on every table in the public schema, now and for tables added later.
--
-- Supabase serves the public schema over its REST API to anyone holding the anon key,
-- and that key ships in the web and mobile apps by design. RLS is what limits it. With
-- RLS on and no policies, the anon and authenticated roles see no rows and can write
-- none. Nothing in this repo reads tables as those roles: both apps use Supabase only
-- for login, the API connects as postgres, and the pipeline's REST calls use the
-- service-role key. Both of those roles bypass RLS.
--
-- Tables are also created outside this directory: by the API's create_all at startup
-- (database.py) and by the scripts/migrate_add_*.py scripts. So an event trigger turns
-- RLS on for every new public table as it is created. This is Supabase's documented
-- recipe (supabase.com/docs/guides/database/postgres/row-level-security, "Auto-enable
-- RLS for new tables").
--
-- Applied to production on 2026-10-04. Idempotent. To undo: DROP EVENT TRIGGER
-- ensure_rls, then run the first block with DISABLE in place of ENABLE.

DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.rls_auto_enable()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT * FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table', 'partitioned table')
      AND schema_name = 'public'
  LOOP
    BEGIN
      EXECUTE format('ALTER TABLE IF EXISTS %s ENABLE ROW LEVEL SECURITY', cmd.object_identity);
    EXCEPTION WHEN OTHERS THEN
      -- Never fail the CREATE TABLE itself; say so loudly instead.
      RAISE WARNING 'rls_auto_enable: could not enable RLS on %: %', cmd.object_identity, SQLERRM;
    END;
  END LOOP;
END;
$$;

DROP EVENT TRIGGER IF EXISTS ensure_rls;
CREATE EVENT TRIGGER ensure_rls ON ddl_command_end
  WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
  EXECUTE FUNCTION public.rls_auto_enable();

-- The function exists only for the trigger; nobody should reach it over the REST API.
-- (anon and authenticated exist only on Supabase, not in a plain test database.)
REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM PUBLIC;
DO $$
DECLARE r text;
BEGIN
  FOR r IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated') LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM %I', r);
  END LOOP;
END $$;
