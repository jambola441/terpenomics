# CheckWeedNY Bulk Sync — Prototype

Walks all active products in the database, looks each one up in the
CheckWeedNY COA API, and writes terpene data to `product_terpenes`.

## Requirements

```
pip install requests sqlmodel psycopg2-binary
```

Plus the usual project env vars (`DATABASE_URL` or `SUPABASE_DB_*`).

## Usage

```bash
# Dry run — see what would happen (no DB writes)
python sync.py

# Dry run for a single brand
python sync.py --brand "Ayrloom"

# Actually write terpenes to DB
python sync.py --write

# Write, but skip products that already have terpenes
python sync.py --write --skip-existing

# Sync a single product
python sync.py --write --product-id <uuid>

# Lower the confidence threshold (default 0.7)
python sync.py --write --min-confidence 0.5
```

## Lookup strategy

1. **Batch lookup** (`?batch=<batch_id>`): If the product has a linked `LabReport`
   with a `batch_id`, use that as the primary lookup key. Returns exactly 1 result.
2. **Brand + product name** (`?brand=<brand>&product=<name>`): Falls back to
   substring search. Picks the hit with the highest `parse_confidence` that has terpenes.

## Write conditions

A product's terpenes are written **only** when:
- `parse_confidence >= 0.7` (configurable via `--min-confidence`)
- `terpene_count > 0`

## Output statuses

| Status | Meaning |
|---|---|
| `written` | Terpenes written to DB |
| `dry_run` | Would be written — re-run with `--write` |
| `skipped` | Already has terpenes (with `--skip-existing`) |
| `not_found` | No matching COA in CheckWeedNY |
| `low_confidence` | Found but `parse_confidence < 0.7` |
| `no_terpenes` | Found but `terpene_count = 0` |
| `error` | API or DB error |

## Terpene name normalization

The API uses different compound names than our canonical list (x007 risk).
`sync.py` includes a normalization map that converts API names → canonical
names before writing. Example: `"Caryophyllene"` → `"β-Caryophyllene"`.

Any unmapped name is written as-is — which is safe (no validation errors)
but may create duplicates if the same compound appears under two names across
API-sourced and Claude-sourced records.
