#!/usr/bin/env python3
"""
pos_sync.py — Pull partner orders from their POS into pos_orders.

Runs every connection that is `active`, then the global passes:
  * re-match unmatched orders still inside the claim window (a shopper who
    signed up after buying gets matched now)
  * purge contact details from orders unclaimed past the window
  * reconcile Terpee points with the orders (connectors/points.py)

Scheduled as a Render cron job (see scripts/render.yaml); safe to run by hand at
the same time, since a connection that is already syncing is skipped.

Usage:
  python scripts/pos_sync.py                     # all active connections
  python scripts/pos_sync.py --connection <id>   # one connection
  python scripts/pos_sync.py --no-global         # skip re-match + purge

Exit status is 1 if any connection failed, so the cron run shows red.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from uuid import UUID

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlmodel import Session  # noqa: E402

from connectors.matching import purge_expired_contacts, rematch_window  # noqa: E402
from connectors.points import reconcile_points  # noqa: E402
from connectors.registry import get_connector  # noqa: E402
from connectors.sync import active_connections, sync_connection  # noqa: E402
from database import engine  # noqa: E402
from models import PosConnection  # noqa: E402

log = logging.getLogger("pos-sync")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync partner POS orders")
    ap.add_argument("--connection", type=UUID, help="sync only this connection id")
    ap.add_argument("--no-global", action="store_true", help="skip the re-match, purge and points passes")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    failed = 0
    with Session(engine) as session:
        if args.connection:
            conn = session.get(PosConnection, args.connection)
            if conn is None:
                log.error("no connection %s", args.connection)
                return 1
            connections = [conn]
        else:
            connections = active_connections(session)

        connectors = {}
        for conn in connections:
            try:
                connector = connectors.get(conn.provider) or get_connector(conn.provider)
                connectors[conn.provider] = connector
            except Exception as e:
                log.error("connection %s: cannot build %s connector: %s", conn.id, conn.provider, e)
                failed += 1
                continue

            run = sync_connection(session, connector, conn)
            if run is None:
                log.info("connection %s: skipped (%s)", conn.id, conn.status)
            elif run.status == "ok":
                log.info(
                    "connection %s: fetched %d, new %d, updated %d, matched %d",
                    conn.id, run.orders_fetched, run.orders_inserted, run.orders_updated, run.orders_matched,
                )
            else:
                failed += 1
                log.error("connection %s: %s", conn.id, run.error)

        if not args.no_global:
            matched = rematch_window(session)
            purged = purge_expired_contacts(session)
            session.commit()
            log.info("re-matched %d order(s) inside the claim window; purged contacts on %d", matched, purged)
            entries = reconcile_points(session)
            session.commit()
            log.info("points: wrote %d ledger entr%s", entries, "y" if entries == 1 else "ies")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
