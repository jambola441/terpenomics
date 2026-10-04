"""Connect a partner, sync a connection, disconnect it.

scripts/pos_sync.py is the scheduled entry point; the OAuth callback calls
complete_oauth. Each function commits its own work, because a sync is long and
its progress should survive a crash partway through.

Sync, per connection:
  1. claim the lease (a second concurrent run skips instead of racing)
  2. refresh the access token if it expires within REFRESH_MARGIN
  3. refresh the location list (a partner may have opened a store)
  4. read every order updated since cursor - OVERLAP, in committed batches,
     matching each batch to customers as it lands
  5. on success only, advance the cursor to the newest update seen

Failures are recorded on the run and the connection rather than raised. An auth
failure means the partner revoked us or the grant is broken, so the connection
goes straight to `error`; anything else counts toward MAX_FAILURES.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import or_, update
from sqlmodel import Session, select

from models import Partner, PosConnection, PosConnectionStatus, PosSyncRun

from .base import AuthError, PosConnector
from .crypto import decrypt_credentials, encrypt_credentials
from .matching import match_orders
from .store import as_utc, import_locations, upsert_orders, utcnow

log = logging.getLogger("connectors.sync")

BACKFILL_DAYS = 7
OVERLAP = timedelta(minutes=10)
REFRESH_MARGIN = timedelta(days=7)
LEASE_TIMEOUT = timedelta(minutes=30)
MAX_FAILURES = 5
BATCH_SIZE = 200


class ConnectError(ValueError):
    pass


# ----------------------------------------------------------------------
# Connect / disconnect
# ----------------------------------------------------------------------

def complete_oauth(
    session: Session, connector: PosConnector, partner_id: UUID, code: str, now: Optional[datetime] = None
) -> PosConnection:
    """Finish the OAuth round-trip: store the grant and import locations.

    Reconnecting the same merchant (after a revoke, or to fix an `error`) reuses
    its row, so order history and the sync cursor carry over. A merchant already
    connected to a *different* partner is refused: its orders would otherwise
    start earning points under the wrong business.
    """
    now = now or utcnow()
    partner = session.get(Partner, partner_id)
    if partner is None:
        raise ConnectError("partner not found")

    grant = connector.exchange_code(code)

    connection = session.exec(select(PosConnection).where(
        PosConnection.provider == connector.provider,
        PosConnection.external_merchant_id == grant.merchant_id,
    )).first()
    if connection is not None and connection.partner_id != partner_id:
        raise ConnectError("this POS account is already connected to another partner")

    if connection is None:
        connection = PosConnection(
            partner_id=partner_id,
            provider=connector.provider,
            external_merchant_id=grant.merchant_id,
            # First connect: pull the last BACKFILL_DAYS of orders.
            sync_cursor=now - timedelta(days=BACKFILL_DAYS),
        )

    connection.credentials = encrypt_credentials(grant.credentials)
    connection.token_expires_at = grant.expires_at
    connection.scopes = grant.scopes
    connection.status = PosConnectionStatus.active.value
    connection.consecutive_failures = 0
    connection.last_error = None
    connection.updated_at = now
    session.add(connection)
    session.flush()

    import_locations(session, connection, connector.list_locations(grant.credentials))
    session.commit()
    session.refresh(connection)
    return connection


def disconnect(session: Session, connector: PosConnector, connection: PosConnection) -> PosConnection:
    """Revoke at the POS, forget the credentials, keep the orders."""
    if connection.credentials:
        try:
            connector.revoke(decrypt_credentials(connection.credentials))
        except Exception as e:  # the grant may already be dead; we forget it either way
            log.warning("revoke failed for connection %s: %s", connection.id, e)
    connection.credentials = None
    connection.token_expires_at = None
    connection.status = PosConnectionStatus.revoked.value
    connection.updated_at = utcnow()
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return connection


# ----------------------------------------------------------------------
# Sync
# ----------------------------------------------------------------------

def _claim(session: Session, connection_id: UUID, now: datetime) -> bool:
    result = session.execute(
        update(PosConnection)
        .where(
            PosConnection.id == connection_id,
            or_(PosConnection.sync_locked_at.is_(None), PosConnection.sync_locked_at < now - LEASE_TIMEOUT),
        )
        .values(sync_locked_at=now)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return result.rowcount == 1


def _ensure_fresh_token(session: Session, connector: PosConnector, connection: PosConnection,
                        credentials: dict, now: datetime) -> dict:
    expires = as_utc(connection.token_expires_at)
    if expires is not None and expires > now + REFRESH_MARGIN:
        return credentials
    grant = connector.refresh(credentials)
    connection.credentials = encrypt_credentials(grant.credentials)
    connection.token_expires_at = grant.expires_at
    session.add(connection)
    session.commit()
    log.info("refreshed token for connection %s (expires %s)", connection.id, grant.expires_at)
    return grant.credentials


def sync_connection(
    session: Session, connector: PosConnector, connection: PosConnection, now: Optional[datetime] = None
) -> Optional[PosSyncRun]:
    """One sync of one connection. Returns the run, or None if another run holds the lease."""
    now = now or utcnow()
    if connection.status != PosConnectionStatus.active.value or not connection.credentials:
        return None
    if not _claim(session, connection.id, now):
        log.info("connection %s is already syncing; skipping", connection.id)
        return None
    session.refresh(connection)

    cursor = as_utc(connection.sync_cursor) or now - timedelta(days=BACKFILL_DAYS)
    since = cursor - OVERLAP
    run = PosSyncRun(connection_id=connection.id, since=since, started_at=now)
    session.add(run)
    session.commit()

    newest = cursor
    try:
        credentials = _ensure_fresh_token(session, connector, connection, decrypt_credentials(connection.credentials), now)
        location_ids = import_locations(session, connection, connector.list_locations(credentials))
        session.commit()

        external_location_ids = sorted(location_ids)
        batch = []

        def flush_batch():
            nonlocal batch
            rows, inserted, updated = upsert_orders(session, connection, batch, location_ids)
            run.orders_inserted += inserted
            run.orders_updated += updated
            run.orders_matched += match_orders(session, rows, now)
            session.add(run)
            session.commit()
            batch = []

        if external_location_ids:
            for order in connector.fetch_orders(credentials, external_location_ids, since):
                run.orders_fetched += 1
                updated_at = as_utc(order.external_updated_at)
                if updated_at > newest:
                    newest = updated_at
                batch.append(order)
                if len(batch) >= BATCH_SIZE:
                    flush_batch()
            if batch:
                flush_batch()

        connection.sync_cursor = newest
        connection.last_synced_at = utcnow()
        connection.consecutive_failures = 0
        connection.last_error = None
        run.status = "ok"
    except Exception as e:
        session.rollback()
        session.refresh(connection)
        session.refresh(run)
        message = f"{type(e).__name__}: {e}"
        log.error("sync failed for connection %s: %s", connection.id, message)
        connection.consecutive_failures += 1
        connection.last_error = message
        if isinstance(e, AuthError) or connection.consecutive_failures >= MAX_FAILURES:
            connection.status = PosConnectionStatus.error.value
        run.status = "error"
        run.error = message
    finally:
        connection.sync_locked_at = None
        connection.updated_at = utcnow()
        run.finished_at = utcnow()
        session.add(connection)
        session.add(run)
        session.commit()
    session.refresh(run)
    return run


def active_connections(session: Session) -> list[PosConnection]:
    return list(session.exec(
        select(PosConnection).where(PosConnection.status == PosConnectionStatus.active.value)
    ).all())
