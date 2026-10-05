-- Sign-up: what a customer is asked for after their first verified login.
--
-- customers gains the current state (first/last name, 21+ confirmation, which
-- terms version they accepted, when they first finished sign-up); consent_events
-- keeps the history behind it, with the exact wording each person was shown.
-- models.py (Customer, ConsentEvent) maps onto these. Timestamps are naive UTC,
-- like the rest of customers.
--
-- Run this before deploying the code that reads these columns: create_all at
-- startup creates missing tables but never adds columns to an existing one.
--
-- Existing marketing_opt_in = true rows have no record of what anyone agreed to,
-- so they are not treated as consent: the flag is cleared (with a consent_events
-- row saying so) and those customers are asked again at sign-up.
--
-- Idempotent.

ALTER TABLE customers ADD COLUMN IF NOT EXISTS first_name        varchar(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_name         varchar(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS age_confirmed_at  timestamp;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS terms_version     varchar(32);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS terms_accepted_at timestamp;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS onboarded_at      timestamp;

CREATE TABLE IF NOT EXISTS consent_events (
  id          uuid PRIMARY KEY,
  customer_id uuid NOT NULL REFERENCES customers(id),
  kind        varchar(32) NOT NULL,
  granted     boolean NOT NULL,
  version     varchar(32),
  text        text,
  source      varchar(64) NOT NULL,
  phone       varchar(32),
  ip          varchar(64),
  user_agent  varchar(500),
  created_at  timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS ix_consent_events_customer_id ON consent_events (customer_id);
CREATE INDEX IF NOT EXISTS ix_consent_events_kind        ON consent_events (kind);
CREATE INDEX IF NOT EXISTS ix_consent_events_created_at  ON consent_events (created_at);

INSERT INTO consent_events (id, customer_id, kind, granted, source, phone, text)
SELECT gen_random_uuid(), c.id, 'marketing_sms', false, 'migration', c.phone,
       'Cleared by 0008_customer_signup: opt-in predates consent records.'
FROM customers c
WHERE c.marketing_opt_in
  AND NOT EXISTS (
    SELECT 1 FROM consent_events e
    WHERE e.customer_id = c.id AND e.kind = 'marketing_sms' AND e.granted
  );

UPDATE customers c
SET marketing_opt_in = false
WHERE c.marketing_opt_in
  AND NOT EXISTS (
    SELECT 1 FROM consent_events e
    WHERE e.customer_id = c.id AND e.kind = 'marketing_sms' AND e.granted
  );
