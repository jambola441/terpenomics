-- Feature flags a customer is opted into or out of, one row per override.
--
-- services/flags.py resolves each flag as: this customer's row if there is one,
-- else the global default from PORTAL_FLAGS. models.py (CustomerFlag) maps onto
-- this table.
--
-- A table rather than a column on customers on purpose: the API's create_all
-- makes a missing table at startup but never adds a column, so this needs no
-- run before deploy. This file exists so the table is on record with the rest,
-- and for databases where the API has not started yet.
--
-- RLS: the ensure_rls event trigger (0004) turns it on for any new public
-- table; it is set here as well so the table never depends on the trigger.
--
-- Skipped where customers does not exist yet (a fresh database built from
-- db/schema/pipeline.sql, as in CI); create_all makes both from models.py.
--
-- Idempotent.

DO $migration$
BEGIN
  IF to_regclass('public.customers') IS NULL THEN
    RETURN;
  END IF;

  CREATE TABLE IF NOT EXISTS customer_flags (
    customer_id uuid        NOT NULL REFERENCES customers(id),
    flag        varchar(64) NOT NULL,
    enabled     boolean     NOT NULL,
    updated_at  timestamp   NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    PRIMARY KEY (customer_id, flag)
  );

  ALTER TABLE customer_flags ENABLE ROW LEVEL SECURITY;
END
$migration$;
