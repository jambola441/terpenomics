# Reaching the database from a sandbox

## The symptom

A script that touches the database hangs, then dies:

```
$ python scripts/migrate.py
  ... (long pause) ...
  OperationalError: connection to server at "aws-0-us-west-2.pooler.supabase.com",
  port 5432 failed: timeout expired
```

Nothing is wrong with the script, the credentials, or the database.

## Why

Claude Code on the web — and most hardened CI runners — route all outbound
traffic through an HTTPS proxy that only speaks `CONNECT` to port 443. The
Postgres wire protocol on 5432 is not HTTP, so there is nothing for that proxy
to forward. The connection is not refused, it is dropped, which is why the
failure looks like a hang rather than an error.

This is an egress policy, not a configuration bug. There is no client-side
setting, no `sslmode`, and no pooler port (6543 included) that changes it.
Tunnelling around it is also not the answer: the policy is what keeps a
sandboxed agent from opening arbitrary sockets.

## What works instead

Supabase serves the same database over HTTPS. `scripts/db_http.py` wraps both
available paths. Start with:

```
python scripts/db_http.py check
```

### 1. PostgREST — row CRUD, no setup

Uses `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`, which the app already
sets. Covers select / insert / update / upsert / delete against any table,
including filters and embedded joins:

```
python scripts/db_http.py select listings "select=strain,price_cents,dispensaries(name)&in_stock=is.true&limit=5"
python scripts/db_http.py update listings "id=eq.<uuid>" '{"in_stock": false}'
```

`update` and `delete` refuse to run without a filter, so a missed `WHERE`
cannot quietly rewrite a whole table.

From Python:

```python
from scripts.db_http import select, upsert
rows = select("dispensaries", "select=id,slug&is_active=is.true")
upsert("terpenes", [{"name": "myrcene"}], on_conflict="name")
```

Note that the service-role key bypasses row-level security. It is the same key
the API server runs with; treat a sandbox that holds it as production-adjacent.

### 2. Management API — arbitrary SQL and DDL

Needed for the `migrate.py` class of work: `CREATE VIEW`, `DROP TABLE`, window
functions, anything PostgREST cannot express. Requires one extra credential —
a personal access token from https://supabase.com/dashboard/account/tokens —
exposed as `SUPABASE_ACCESS_TOKEN`:

```
python scripts/db_http.py sql "SELECT scraped_category, count(*) FROM listings GROUP BY 1 ORDER BY 2 DESC"
python scripts/db_http.py sql - < some_migration.sql
```

This token is account-wide and can drop the database. Scope the environments
that carry it accordingly.

One trap if you write your own client against this endpoint: Cloudflare fronts
`api.supabase.com` and blocks urllib's default `Python-urllib/3.x` agent with a
403 whose entire body is `error code: 1010`. That is indistinguishable at a
glance from a rejected token — but curl succeeds against the same credential.
Send a named `User-Agent` and it goes through.

### 3. Run the script where 5432 is reachable

The right home for the long batch jobs — `enrich.py`, `import_listings.py`,
`scrape.py`. They are chatty enough that a per-statement HTTP round trip would
dominate their runtime, and `enrich.py` additionally needs the cache disk
described in `SCRAPERS.md`. Render already has both the network path and the
environment variables, so run them there (one-off job, or the
`terpenomics-scraper` worker) and read the logs rather than re-plumbing them
through HTTPS.

## Picking between them

| Work | Path |
| --- | --- |
| Inspect data, fix a few rows, backfill a column | PostgREST (1) |
| Schema change, view, migration, reporting query | Management API (2) |
| Scrape, enrich, full import | Run on Render (3) |
