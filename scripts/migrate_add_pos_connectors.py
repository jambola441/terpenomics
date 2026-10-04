#!/usr/bin/env python3
"""
migrate_add_pos_connectors.py — Partner stores and the POS connector tables.

Partners are non-dispensary businesses (cafés, shops) whose customers earn Terpee
points for buying there. Their orders are pulled from the partner's own POS --
Square first -- by scripts/pos_sync.py and land in pos_orders. See
POS_CONNECTORS.md for the design.

Why partners are not dispensaries: a dispensary row carries a menu, listings and
pickup, none of which a partner has. Why partner orders are not purchases:
`purchases` feeds the recommendation engine, and a coffee receipt must not move
anyone's strain recommendations.

Tables:
  partners            the business
  pos_connections     one OAuth grant to one POS merchant account
  partner_locations   the business's stores, as the POS knows them
  pos_orders          every order the POS reports, matched to a customer or not
  pos_order_items     its lines
  pos_customer_links  POS customer id -> Terpee customer, once known
  pos_sync_runs       one row per sync, for the admin UI
  partner_members     who may sign in to a partner's /partner dashboard

Idempotent — safe to re-run.

Usage:
  python scripts/migrate_add_pos_connectors.py            # show the SQL, change nothing
  python scripts/migrate_add_pos_connectors.py --run
"""

import argparse
import os
import sys

DDL = """
CREATE TABLE IF NOT EXISTS partners (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  slug       text NOT NULL UNIQUE,
  is_active  boolean NOT NULL DEFAULT true,
  logo_url   text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pos_connections (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id           uuid NOT NULL REFERENCES partners(id),
  provider             text NOT NULL,
  status               text NOT NULL DEFAULT 'active',
  external_merchant_id text NOT NULL,
  credentials          text,          -- Fernet token, see connectors/crypto.py
  scopes               text,
  token_expires_at     timestamptz,
  sync_cursor          timestamptz,
  sync_locked_at       timestamptz,   -- lease held by a running sync
  last_synced_at       timestamptz,
  last_error           text,
  consecutive_failures integer NOT NULL DEFAULT 0,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pos_connections_provider_merchant_key UNIQUE (provider, external_merchant_id)
);
CREATE INDEX IF NOT EXISTS ix_pos_connections_partner_id ON pos_connections (partner_id);

CREATE TABLE IF NOT EXISTS partner_locations (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id           uuid NOT NULL REFERENCES partners(id),
  connection_id        uuid REFERENCES pos_connections(id),
  external_location_id text,
  name                 text NOT NULL,
  address              text,
  timezone             text,
  is_active            boolean NOT NULL DEFAULT true,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT partner_locations_connection_location_key UNIQUE (connection_id, external_location_id)
);
CREATE INDEX IF NOT EXISTS ix_partner_locations_partner_id ON partner_locations (partner_id);
CREATE INDEX IF NOT EXISTS ix_partner_locations_connection_id ON partner_locations (connection_id);

CREATE TABLE IF NOT EXISTS pos_orders (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  connection_id            uuid NOT NULL REFERENCES pos_connections(id),
  partner_id               uuid NOT NULL REFERENCES partners(id),
  partner_location_id      uuid REFERENCES partner_locations(id),
  external_order_id        text NOT NULL,
  external_location_id     text,
  kind                     text NOT NULL DEFAULT 'sale',
  source_external_order_id text,
  state                    text NOT NULL,
  currency                 text NOT NULL DEFAULT 'USD',
  total_cents              integer NOT NULL DEFAULT 0,
  tax_cents                integer NOT NULL DEFAULT 0,
  tip_cents                integer NOT NULL DEFAULT 0,
  discount_cents           integer NOT NULL DEFAULT 0,
  refunded_cents           integer NOT NULL DEFAULT 0,
  external_customer_id     text,
  customer_phone           text,
  customer_email           text,
  customer_id              uuid REFERENCES customers(id),
  matched_via              text,
  matched_at               timestamptz,
  contact_purged_at        timestamptz,
  ordered_at               timestamptz NOT NULL,
  closed_at                timestamptz,
  external_updated_at      timestamptz NOT NULL,
  raw                      jsonb,
  first_seen_at            timestamptz NOT NULL DEFAULT now(),
  last_synced_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pos_orders_connection_order_key UNIQUE (connection_id, external_order_id)
);
CREATE INDEX IF NOT EXISTS ix_pos_orders_connection_id ON pos_orders (connection_id);
CREATE INDEX IF NOT EXISTS ix_pos_orders_partner_id ON pos_orders (partner_id);
CREATE INDEX IF NOT EXISTS ix_pos_orders_partner_location_id ON pos_orders (partner_location_id);
CREATE INDEX IF NOT EXISTS ix_pos_orders_customer_id ON pos_orders (customer_id);
CREATE INDEX IF NOT EXISTS ix_pos_orders_customer_phone ON pos_orders (customer_phone);
CREATE INDEX IF NOT EXISTS ix_pos_orders_source_external_order_id ON pos_orders (source_external_order_id);
-- Matching and the claim-window purge only ever look at unmatched orders.
CREATE INDEX IF NOT EXISTS pos_orders_unmatched_idx ON pos_orders (ordered_at) WHERE customer_id IS NULL;

CREATE TABLE IF NOT EXISTS pos_order_items (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id         uuid NOT NULL REFERENCES pos_orders(id) ON DELETE CASCADE,
  external_line_id text,
  external_sku     text,
  name             text NOT NULL,
  variation        text,
  quantity         text NOT NULL DEFAULT '1',
  total_cents      integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_pos_order_items_order_id ON pos_order_items (order_id);

CREATE TABLE IF NOT EXISTS pos_customer_links (
  connection_id        uuid NOT NULL REFERENCES pos_connections(id),
  external_customer_id text NOT NULL,
  customer_id          uuid NOT NULL REFERENCES customers(id),
  linked_via           text NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (connection_id, external_customer_id)
);
CREATE INDEX IF NOT EXISTS ix_pos_customer_links_customer_id ON pos_customer_links (customer_id);

CREATE TABLE IF NOT EXISTS pos_sync_runs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  connection_id   uuid NOT NULL REFERENCES pos_connections(id),
  status          text NOT NULL DEFAULT 'running',
  since           timestamptz,
  started_at      timestamptz NOT NULL DEFAULT now(),
  finished_at     timestamptz,
  orders_fetched  integer NOT NULL DEFAULT 0,
  orders_inserted integer NOT NULL DEFAULT 0,
  orders_updated  integer NOT NULL DEFAULT 0,
  orders_matched  integer NOT NULL DEFAULT 0,
  error           text
);
CREATE INDEX IF NOT EXISTS ix_pos_sync_runs_connection_id ON pos_sync_runs (connection_id);
CREATE INDEX IF NOT EXISTS ix_pos_sync_runs_started_at ON pos_sync_runs (started_at);

-- Partner logins. An admin invites an email; whoever signs in with Google as that
-- address gets in, and their Supabase user id is recorded on first sign-in.
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
"""

TABLES = (
    "partners", "pos_connections", "partner_locations", "pos_orders",
    "pos_order_items", "pos_customer_links", "pos_sync_runs", "partner_members",
)


def load_env(root: str) -> None:
    path = os.path.join(root, ".env")
    if not os.path.isfile(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description="Add partner + POS connector tables")
    ap.add_argument("--run", action="store_true", help="Execute (default: print only)")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env(root)

    if not args.run:
        print("-- DDL that WOULD be executed (nothing has run):")
        print(DDL)
        print("-- Pass --run to apply, or paste the above into the SQL editor.")
        return

    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2-binary required: pip install psycopg2-binary")

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()

    cur.execute(
        """
        SELECT table_name, count(*) FROM information_schema.columns
        WHERE table_name = ANY(%s) GROUP BY 1 ORDER BY 1
        """,
        (list(TABLES),),
    )
    for name, cols in cur.fetchall():
        print(f"  {name}: {cols} columns")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
