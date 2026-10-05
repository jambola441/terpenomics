# Partner POS connectors

Partner stores are non-dispensary businesses. When a Terpee customer buys
something at a partner, they earn Terpee points. This module pulls the partners'
orders out of their point-of-sale system (Square first) and works out which
customer each order belongs to. The points ledger, which comes later, reads from
what this module stores.

```
Square ──OAuth──▶ pos_connections ──scripts/pos_sync.py (cron, 15 min)──▶ pos_orders ──▶ points ledger (next)
                                                                              ▲
                                       phone match / POS-customer link / receipt claim
```

## Decisions

| Decision | Why |
|---|---|
| Partners are their own table, not `dispensaries` | Partners have no menu, listings or pickup. |
| Partner orders are `pos_orders`, never `purchases` | `purchases` feeds cannabis recommendations, and a coffee receipt shouldn't change those. |
| Polling is the source of truth | A missed webhook can't lose an order. Webhooks can be added later to cut latency. |
| Upsert on the POS's own order id | Re-reading an order (the sync overlap, a re-run, a later refund) rewrites the same row instead of adding one. |
| 7-day backfill on first connect | Product decision. `sync.BACKFILL_DAYS`. |
| 30-day claim window | Unmatched orders are re-matched for 30 days, so someone who signs up after buying still gets the points. After 30 days their contact details are purged. `matching.CLAIM_WINDOW_DAYS`. |
| Matching = phone, or uploaded receipt | Product decision. A match that carries a POS customer id also writes a `pos_customer_links` row, so that shopper's later orders match automatically. |
| Credentials encrypted at rest | `POS_CREDENTIALS_KEY` (Fernet; a comma-separated list allows key rotation). |
| API is CRUD only, plus OAuth and disconnect | Follows the thin-API rule: syncing lives in the script. OAuth has to be HTTP, and disconnect has to call the POS to revoke. |

## Tables

Created by `scripts/migrate_add_pos_connectors.py` (idempotent; prints the SQL
without `--run`).

- `partners`: the business.
- `pos_connections`: one OAuth grant to one POS merchant account. Holds:
  - `status`: `active`, `error`, `disabled` or `revoked`
  - `sync_cursor`: the newest POS `updated_at` already ingested
  - `sync_locked_at`: a lease that stops two syncs of the same connection running at once
  - `consecutive_failures` and `last_error`
- `partner_locations`: the partner's stores, imported from the POS. Name and
  address follow the POS. `is_active` is the admin's to change; the sync never
  overrides it.
- `pos_orders`:
  - Unique on `(connection_id, external_order_id)`.
  - `kind` is `sale` or `return`. A Square itemized return is its own order, and
    its `source_external_order_id` points at the sale it returns.
  - `refunded_cents` holds refunds recorded on the order itself.
  - Matching fields: `customer_id`, `matched_via` (`link`, `phone`, `receipt` or
    `sale`), `matched_at`.
  - `raw` keeps the provider's payload.
- `pos_order_items`: replaced wholesale whenever the order is re-fetched.
- `pos_customer_links`: maps a POS customer id to a Terpee customer.
- `pos_sync_runs`: one row per sync, with counts and the error if it failed.

## Code

```
connectors/
  base.py         PosConnector protocol; NormalizedOrder (cents, UTC, E.164)
  square.py       Square: OAuth, Locations, SearchOrders, Customers bulk-retrieve
  registry.py     provider name -> connector configured from env
  crypto.py       credential encryption
  oauth_state.py  signed, expiring OAuth `state`
  store.py        the only writer of pos_orders / partner_locations
  matching.py     link -> phone matching, rematch_window, purge, claim_order
  sync.py         complete_oauth, disconnect, sync_connection
scripts/pos_sync.py              cron entry point
routes/admin/partners.py         admin CRUD + OAuth start + disconnect
routes/pos_oauth.py              OAuth callback (unauthenticated; trusts the signed state)
tests/test_pos_connectors.py
```

To add a provider: write a class that satisfies `PosConnector`, register it in
`registry.py`, and add its name to `PROVIDERS`. Nothing downstream changes.

## How a sync runs

1. Claim the lease. If another run holds it (and the lease is under 30 minutes
   old), skip this connection.
2. Refresh the access token if it expires within 7 days. Square tokens last 30
   days, and the refresh token doesn't expire.
3. Re-import locations, in case the partner opened a store.
4. Fetch every order updated since `cursor − 10 min`. Orders are written in
   committed batches of 200 and matched to customers as each batch lands.
5. Only if the whole run succeeds, advance the cursor to the newest update seen.
   A crash halfway through just re-reads from the old cursor, and the upsert
   absorbs the repeats.
6. On failure:
   - An auth failure sets the connection to `error` immediately, because the
     partner has to reconnect.
   - Any other failure counts toward 5 consecutive failures, after which the
     connection is set to `error`.
   - An admin re-enables it with `PATCH {"status": "active"}`.

After all connections are done, the script runs two global passes: re-matching
unmatched orders inside the claim window, and purging contacts on orders past it.

## Setup

1. Create the Square app at developer.squareup.com. Set its OAuth redirect URL
   (Sandbox and Production tabs separately) to either the API's
   `<API base>/pos/oauth/square/callback` or the admin site's
   `https://terpenomics.generic.tech/pos/oauth/square/callback`. The admin-site
   page (`ui/my-app/src/PosOAuthForward.tsx`) just forwards to the API's callback.
2. Set these on the web service and the cron job (see `.env.example`):
   - `POS_CREDENTIALS_KEY`: must be the same value on both
   - `SQUARE_APPLICATION_ID`, `SQUARE_APPLICATION_SECRET`, `SQUARE_ENVIRONMENT`
   - `POS_OAUTH_RETURN_URL`: web service only
3. Run `python scripts/migrate_add_pos_connectors.py --run`.
4. Create the `terpenomics-pos-sync` cron job (see `scripts/render.yaml`).
5. Connect a partner from the admin UI: **Admin → Partner Stores → + Add
   partner**, then **Connect Square** on the partner's page and approve with
   the partner's Square account. Set `POS_OAUTH_RETURN_URL` to
   `<admin UI>/admin/partners` so Square's redirect lands back there.

## API

| Endpoint | |
|---|---|
| `GET/POST /admin/partners`, `GET/PATCH /admin/partners/{id}` | partners; GET by id includes locations and connections |
| `PATCH /admin/partner-locations/{id}` | rename or deactivate a store |
| `GET /admin/pos-connections/oauth/{provider}/start?partner_id=` | returns `authorize_url` |
| `GET /pos/oauth/{provider}/callback` | POS redirects here; redirects on to `POS_OAUTH_RETURN_URL` |
| `GET /admin/pos-connections[?partner_id&status]`, `GET /admin/pos-connections/{id}` | credentials are never returned |
| `PATCH /admin/pos-connections/{id}` `{"status": "active" \| "disabled"}` | pause, resume, or re-enable after errors |
| `DELETE /admin/pos-connections/{id}` | revoke at the POS and drop credentials; orders are kept |
| `GET /admin/pos-connections/{id}/runs` | sync history |
| `GET /admin/pos-orders[?partner_id&customer_id&unmatched]` | read-only; contact details are not exposed |

## Partner portal (`/partner`)

Partners manage their own connection. An admin adds the person's Google email
under **Partner logins** on the partner's admin page; that person signs in at
`https://terpenomics.generic.tech/partner` with Google and can connect,
reconnect, pause/resume or disconnect Square, and see sync history and orders.

- **Access** (`routes/partner/auth.py`): a `partner_members` row grants access to
  whoever signs in with that email, and binds to their Supabase user id on first
  sign-in, so a later change to the Google address keeps working and a new
  holder of the old address does not get in. SMS-login placeholder emails
  (`…@phone.invalid`) and unverified emails never match. A partner that isn't
  yours returns the same 404 as one that doesn't exist.
- **Privacy**: partner order responses carry `is_member` only, never the customer,
  how they matched, or contact details (`order_json(for_partner=True)`).
- **Stays admin-only**: renaming, which locations earn points, and managing logins.
- **OAuth return**: the signed state records where the connect started
  (`admin` or `partner`), and the callback sends the browser back there. The
  partner page is `POS_PARTNER_RETURN_URL`, defaulting to `/partner` on the
  `POS_OAUTH_RETURN_URL` host.

## Terpee points (`connectors/points.py`)

Partner orders turn into points at the end of every sync (`reconcile_points`).

- **What earns:** completed sales matched to a customer. The amount is the
  order total minus tax and tip. A refund or return removes its share in
  proportion: refunding half the order removes half the points.
- **Rate:** 1 point per $1, rounded down (`POINTS_PER_DOLLAR`).
- **Pending:** points are pending for 7 days after the purchase, then
  available. A refund inside that window lands as pending too, so it cancels
  the points before anyone can spend them. A refund after that takes the
  points back immediately.
- **Fixed at first earn:** the rate, and whether the partner and location earn
  at all, are read when an order first earns. Changing a setting later never
  rewrites past earnings.
- **Ledger:** `points_ledger` is append-only. Each run works out what every
  order should be worth, compares that with what is already recorded, and
  writes only the difference (`earn`, `refund` or `adjust`). Re-running
  writes nothing.
- **Where it shows:** customers see their balance and history under
  **You → Points** in the portal (`GET /me/points`). Admin shows each
  customer's ledger on the customer page (`GET /admin/customers/{id}/points`)
  and the points next to each matched order on the partner page.
- **Not built:** redeeming points.

## Receipt uploads (`connectors/receipts.py`)

For partner purchases the sync can't match: the shopper didn't give their
phone number, or the partner's POS isn't connected.

- **Customer** (portal → You → Points → Upload a receipt): picks the store and
  purchase date and takes a photo. The browser shrinks the photo to about
  1600px JPEG before upload. The customer sees each receipt as In review,
  +N points, or Not approved with the reason.
- **Reviewer** (`/admin/receipts`): the queue is oldest first. The reviewer
  sees the photo, enters the subtotal before tax and tip, confirms or corrects
  the store and date, and approves it, or rejects it with a reason. The next
  pending receipt opens automatically.
- **Duplicate flags (not blocks):** the same customer's other receipts at that
  store within 2 days; synced orders at that store around the date,
  highlighted when already matched to this customer; purchase dates over 30
  days old.
- **Points:** the subtotal × `POINTS_PER_DOLLAR`, rounded down, pending until
  7 days after the purchase date. Recorded as one `points_ledger` entry of
  kind `receipt` with no `pos_order_id`, so `reconcile_points` never touches
  it. Voiding an approved receipt appends the opposite entry.
- **Limits:** 10 MB per image; JPEG, PNG, WebP or HEIC; at most 10 receipts
  awaiting review per customer. Images are stored in the row, as lab-report
  PDFs are.

## Not built yet

- **Square webhooks** (`order.updated`), to cut latency. Polling stays as the backstop.
- **Unconfirmed: how Square reports a refund on the original sale.** Square's
  docs don't say whether the original sale order is edited when it's refunded, so
  both possible shapes are captured. Confirm against a sandbox refund before the
  ledger relies on either.
