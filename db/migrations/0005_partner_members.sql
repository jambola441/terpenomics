-- Partner logins: who may sign in to a partner's /partner dashboard.
--
-- An admin invites an email address; whoever signs in with Google as that address
-- gets in, and their Supabase user id is recorded on first sign-in. RLS is turned on
-- by the ensure_rls event trigger from 0004 (the API connects as postgres and
-- bypasses it). The API's create_all also creates this table on startup; this file is
-- the record of its shape. Idempotent.

CREATE TABLE IF NOT EXISTS partner_members (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id    uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  email         text NOT NULL,           -- lower-cased
  auth_user_id  uuid,
  invited_at    timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz,
  CONSTRAINT partner_members_partner_email_key UNIQUE (partner_id, email)
);
CREATE INDEX IF NOT EXISTS ix_partner_members_partner_id ON partner_members (partner_id);
CREATE INDEX IF NOT EXISTS ix_partner_members_email ON partner_members (email);
CREATE INDEX IF NOT EXISTS ix_partner_members_auth_user_id ON partner_members (auth_user_id);
ALTER TABLE partner_members ENABLE ROW LEVEL SECURITY;
