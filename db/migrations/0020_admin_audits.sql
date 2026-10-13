-- Admin audits (routes/admin/audits.py, scripts/audits.py, scripts/audit_worker.py).
--
-- The loop: an audit run flags listings of the brands picked (scripts/data_health.py's
-- price-outlier, odd-title and price detectors) and adds a random sample of trusted
-- listings (catalog_entry_id set, catalog_match_method 'attributes' or 'manual'); each
-- is judged right / wrong / unsure, by a person or by an LLM judge (Claude, the model
-- picked per run); a wrong one gets a listing fix or a catalog proposal; a proposal is
-- measured as a dry run, approved by an admin, applied, the brand's catalog grid
-- synced and its listings re-matched; every apply is logged with before and after.
--
--   audit_runs       one row per run: brands, sample size, judge model, status,
--                    progress, token use and cost
--   audit_items      one row per listing looked at in a run: why (flags / sample),
--                    the evidence shown, the verdict, cause and proposed fix
--   audit_proposals  catalog changes waiting for, or past, an admin's call: what,
--                    why, the measured effect, the decision, the apply result
--   audit_jobs       work for the background worker (scripts/audit_worker.py):
--                    build a run, judge it, measure or apply a proposal
--   audit_log        every apply and listing fix, with what it replaced
--
-- New tables: the API's create_all makes them at startup from models.py (as for
-- review_decisions, 0017); this file has them on record and makes them where the
-- API has not started. Index names match create_all's. Written with the
-- service-role key only; RLS on (0004's trigger does it too), no policies.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS audit_runs (
  id            uuid        PRIMARY KEY,
  brands        jsonb       NOT NULL,
  sample_size   integer     NOT NULL DEFAULT 20,
  judge_model   text,
  status        varchar(16) NOT NULL DEFAULT 'queued',
  created_by    text        NOT NULL,
  created_at    timestamp   NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  finished_at   timestamp,
  total_items   integer     NOT NULL DEFAULT 0,
  judged_items  integer     NOT NULL DEFAULT 0,
  input_tokens  integer     NOT NULL DEFAULT 0,
  output_tokens integer     NOT NULL DEFAULT 0,
  cost_usd      double precision NOT NULL DEFAULT 0,
  error         text
);
CREATE INDEX IF NOT EXISTS ix_audit_runs_created_at ON audit_runs (created_at);

CREATE TABLE IF NOT EXISTS audit_items (
  id            uuid        PRIMARY KEY,
  run_id        uuid        NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
  listing_id    uuid        NOT NULL,
  brand         text        NOT NULL,
  source        varchar(16) NOT NULL,
  flags         jsonb,
  evidence      jsonb,
  verdict       varchar(16),
  cause         text,
  explanation   text,
  proposed_fix  jsonb,
  judged_by     text,
  judged_at     timestamp,
  fix           jsonb,
  created_at    timestamp   NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS ix_audit_items_run_id ON audit_items (run_id);
CREATE INDEX IF NOT EXISTS ix_audit_items_listing_id ON audit_items (listing_id);

CREATE TABLE IF NOT EXISTS audit_proposals (
  id            uuid        PRIMARY KEY,
  run_id        uuid        REFERENCES audit_runs(id) ON DELETE SET NULL,
  item_id       uuid        REFERENCES audit_items(id) ON DELETE SET NULL,
  brand         text        NOT NULL,
  kind          varchar(32) NOT NULL,
  params        jsonb       NOT NULL,
  why           text,
  status        varchar(16) NOT NULL DEFAULT 'measuring',
  measure       jsonb,
  measured_at   timestamp,
  created_by    text        NOT NULL,
  decided_by    text,
  decided_at    timestamp,
  applied_at    timestamp,
  result        jsonb,
  error         text,
  created_at    timestamp   NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS ix_audit_proposals_status ON audit_proposals (status);

CREATE TABLE IF NOT EXISTS audit_jobs (
  id            uuid        PRIMARY KEY,
  kind          varchar(32) NOT NULL,
  payload       jsonb       NOT NULL,
  status        varchar(16) NOT NULL DEFAULT 'queued',
  attempts      integer     NOT NULL DEFAULT 0,
  error         text,
  created_at    timestamp   NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  started_at    timestamp,
  finished_at   timestamp
);
CREATE INDEX IF NOT EXISTS ix_audit_jobs_status ON audit_jobs (status);

CREATE TABLE IF NOT EXISTS audit_log (
  id            uuid        PRIMARY KEY,
  actor         text        NOT NULL,
  action        varchar(32) NOT NULL,
  brand         text,
  target_kind   varchar(32) NOT NULL,
  target_id     text        NOT NULL,
  before        jsonb,
  after         jsonb,
  created_at    timestamp   NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS ix_audit_log_created_at ON audit_log (created_at);

ALTER TABLE audit_runs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_items     ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_jobs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log       ENABLE ROW LEVEL SECURITY;
