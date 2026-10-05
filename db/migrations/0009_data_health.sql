-- The daily audit's memory (scripts/data_health.py, the /audit-terpee-listings skill).
--
--   data_health_snapshots   one row per saved report: its numbers, and each finding's
--                           evidence, so the next report can say what changed and
--                           which findings are new.
--   data_health_dismissals  findings judged not a problem. A report leaves one out
--                           until its evidence grows past what it was when dismissed.
--
-- Written with the service-role key only; RLS is on for new tables (0004), with no
-- policies, so the public keys see nothing.

CREATE TABLE IF NOT EXISTS data_health_snapshots (
  taken_at timestamptz PRIMARY KEY DEFAULT now(),
  metrics  jsonb NOT NULL,
  findings jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS data_health_dismissals (
  finding_key  text PRIMARY KEY,
  reason       text NOT NULL,
  evidence     integer NOT NULL,
  dismissed_at timestamptz NOT NULL DEFAULT now()
);
