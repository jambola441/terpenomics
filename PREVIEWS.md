# PR Previews on Render

Every pull request gets its own live copy of the app, so a change can be
reviewed from a phone by tapping a link in the GitHub PR — no laptop, no local
checkout, and nothing deployed to production until the PR is merged.

```
PR #42 opened
  ├── terpenomics-ui-pr-42.onrender.com   ← the UI, built from the PR branch
  └── terpenomics-pr-42.onrender.com      ← the API, built from the PR branch
                                             pointed at the PREVIEW database
```

Render deletes both automatically when the PR is merged or closed.

## The workflow

1. Claude opens a PR.
2. Render posts the preview links as a deployment status on the PR. On the
   GitHub mobile app they appear under the PR's checks.
3. Tap the **UI** preview link. It figures out on its own that it is a preview
   and talks to the matching API preview — see *How the UI finds its API* below.
4. A yellow **PR PREVIEW** pill sits in the bottom-right corner. If you don't
   see it, you are on production.

Login works normally: auth is Supabase email OTP against the production
Supabase project, and admin access is a JWT claim, not a database row. Only the
*data* is different in a preview.

## One-time setup

### 1. Create the preview database

A second, free Supabase project holding throwaway data.

1. Supabase → **New project** → name it something like `terpenomics-preview`.
2. Copy its Postgres connection string (Project Settings → Database → URI, the
   **session pooler** string).
3. Build the schema. `create_db_and_tables()` runs on API startup and creates
   the tables, but *not* the `products` view that the admin screens read, so
   run the migration once against the new database:

   ```bash
   DATABASE_URL='<preview connection string>' python scripts/migrate.py --run
   ```

4. Load reference data:

   ```bash
   DATABASE_URL='<preview connection string>' python scripts/import_dispensaries.py
   ```

5. Give it some listings — either scrape into it, or import a CSV you already
   have:

   ```bash
   DATABASE_URL='<preview connection string>' python scripts/import_listings.py \
     --csv prototypes/alleaves-scraper/<store>_listings.csv
   ```

   For realistic data instead, `pg_dump` production and restore into the
   preview project.

Re-run step 3 whenever the preview data gets too mangled to be useful — it
drops and rebuilds everything. That is the point of a preview database: you can
wreck it.

### 2. Tell the API about it

In the Render dashboard, on the **`terpenomics`** service (the production one)
→ **Environment**, add:

| Key                    | Value                                |
| ---------------------- | ------------------------------------ |
| `PREVIEW_DATABASE_URL` | the preview project's connection URI |

Production ignores this variable entirely. Previews inherit it and use it
instead of `DATABASE_URL` — see *Why previews can't touch production data*.

### 3. Turn on previews

For **each** of the two services, in the Render dashboard → the service →
**Settings → Previews**:

| Service          | Generation  | Why                                                          |
| ---------------- | ----------- | ------------------------------------------------------------ |
| `terpenomics-ui` | Automatic   | Static site — previews are free, so every PR can have one.    |
| `terpenomics`    | Automatic   | Billed at the base service's rate, prorated by the second.    |

Pick **Manual** on the API instead if you'd rather previews only spin up for
PRs you label `render-preview` (or title `[render preview]`). Manual costs less
and means backend PRs get a preview only when you ask for one.

Do **not** enable previews on `terpenomics-scraper`. A preview of the worker
would start scraping on its own schedule for no reason.

## Why previews can't touch production data

Render preview instances copy every environment variable from their base
service, `DATABASE_URL` included. Left alone, a preview of an un-reviewed
branch would read and write real products, customers and purchases.

`database.py` closes that hole. Render sets `IS_PULL_REQUEST=true` on preview
instances only, so:

- **On a preview**, `DATABASE_URL` is ignored and `PREVIEW_DATABASE_URL` is
  used instead.
- **If `PREVIEW_DATABASE_URL` is missing**, the preview refuses to boot. A
  preview that fails loudly beats one that quietly edits production.
- **In production**, `IS_PULL_REQUEST` is absent, so none of this runs.

Escape hatch: set `PREVIEW_ALLOW_PROD_DB=true` on a specific preview instance
to deliberately point it at production — for reproducing a bug that only shows
up with real data. Set it on the *preview*, never on the base service.

Covered by `tests/test_preview_db.py`.

## How the UI finds its API

`VITE_API_BASE_URL` is baked in at build time, and previews inherit it — so a
preview UI would point at the production API. `src/api/base.ts` resolves the
API at runtime instead, first match wins:

1. **`?api=<url>`** in the address bar — pins this browser to any API.
   `?api=reset` clears it.
2. A previously pinned override, remembered in `localStorage`.
3. **The hostname.** On `<anything>-pr-42.onrender.com`, it uses
   `https://terpenomics-pr-42.onrender.com`. This is what makes previews work
   with no configuration.
4. `VITE_API_BASE_URL` from the build.
5. The hardcoded dev fallback.

The service name in step 3 is `terpenomics`; override it with
`VITE_PREVIEW_API_SERVICE` if the API service is ever renamed.

`?api=` is the useful one on a phone. Open the production UI, append
`?api=https://terpenomics-pr-42.onrender.com`, and you get the polished
production frontend against a PR's backend — handy for a backend-only PR. The
pill turns red (**CUSTOM API**) whenever an override is active; tap it to see
the target or clear it.

## Cost

- UI previews: free. Static sites don't bill for previews.
- API previews: the base service's rate, prorated by the second. A Starter
  preview alive for two days is well under a dollar.
- The preview Supabase project: free tier.

Previews are deleted when their PR is merged or closed, so cost tracks how long
PRs stay open. If they pile up, switch the API to **Manual** generation.

## Known limits

- **Preview URLs are always `*.onrender.com`.** Render does not support custom
  domains on preview instances, so per-PR URLs can't live under your own
  domain. If you want one stable, memorable address, see below.
- **The scraper worker is not previewed.** A PR that only changes
  `scripts/scrape*.py` has nothing to look at; run it locally against the
  preview database instead.
- **Auth is shared with production.** Previews use the production Supabase
  project for login. Your session and admin claim carry over; the data does
  not.

### If you want a real subdomain instead

Render can't give each PR a custom domain, but it can give one long-lived
service a custom one. Create a second web service and a second static site off
a fixed `staging` branch, attach `preview.yourdomain.com` to the static site,
and merge whichever PR branch you want to look at into `staging`. You get one
bookmarkable address, at the cost of one PR at a time and an extra always-on
service. Per-PR previews are the better fit for reviewing Claude's PRs; this is
the option if you specifically want a stable subdomain to hand to someone else.
