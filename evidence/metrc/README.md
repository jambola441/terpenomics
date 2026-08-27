# Metrc API Proficiency Evaluation — NY

Tooling to run the Metrc evaluation against the NY sandbox and write the
results straight into the workbook Metrc sent.

## Scope reality check

Two things in the request as scoped do not exist as Metrc describes them:

1. **There is no "read lab results only" permission tier.** The Permissions tab
   states the Labs dependency chain as: *Strains, Packages, Labs, GET Transfers
   and Wholesale*, with Items and Transfer Templates optional. Lab access does
   not come on its own.

2. **"GET only" is not a smaller evaluation.** The Permissions tab: *"Request a
   GET only Evaluation — You will be required to complete all sections of all
   tabs."* Requesting read-only reduces the permissions you receive, not the
   work required to certify. Worth confirming the exact expectation with
   api-info@metrc.com before committing to a submission, since most task sheets
   are written around POST/PUT steps a GET-only key cannot perform.

## NY applicability

From the workbook's `States` tab, NY is **open loop**, so:

| Use | Skip |
|---|---|
| `PlantBatches` | `Closed Loop States PlantBatches` |
| `LabResults` | `CA ONLY Labs` |
| `Sales with Patient Look Up` (NY Patients = YES) | `CA- SalesRetailDeliveries` (NY = NO) |
| `Sales Deliveries (NOT CA)` | |

Everything else applies: Locations, Strains, Items, Plants, Harvest, Packages,
GET Transfers and Wholesale, Transfer Templates, Transfer External Incoming.

## Authentication

Every call is HTTP basic auth where **username = vendor key** and
**password = industry user key**. Permissions come from the user key only.

The single exception is `POST /sandbox/v2/integrator/setup`, which takes the
vendor key alone in an `x-metrc-key` header — this is how you mint a user key
without a licensee partner.

## Workflow

```bash
cp .env.example .env          # fill in METRC_VENDOR_KEY
set -a; source .env; set +a

# 1. Mint an industry user key (vendor key only). 201/202 = queued, re-run.
python -m scripts.metrc.run setup-user
python -m scripts.metrc.run setup-user --user-key <key>   # look up / confirm

# 2. Find your facility and see exactly what the state granted it.
python -m scripts.metrc.run facilities

# 3. Stand up inventory: tags are created, shipped and received in one call.
python -m scripts.metrc.run bootstrap --plant-tags 25 --package-tags 25 --packages 10

# 4. Run the read-only evaluation.
python -m scripts.metrc.run get-only --window 90

# 5. Write the recorded run into the workbook.
python -m scripts.metrc.run fill --run <run-id> --out evidence/metrc/Evaluation_completed.xlsx
```

Inspect the derived cell map at any time with `python -m scripts.metrc.run map`.

## How results reach the workbook

The cell map is derived from the file, not hardcoded: the header row is found by
its `Result code` column and answer rows by the `Step N` labels in column A. A
reshuffled workbook release still works.

Per step, the runner writes result code, license, object id, last-modified, tag,
the full request URL, and minified JSON — request body for writes, response for
reads, which is what "JSON Body Or Response" means in practice.

Every call is also appended to `calls.jsonl` as it happens, so a run that dies
halfway still leaves usable evidence, and `fill` can be re-run against it.

## Known workbook errata

- The `GET Transfers and Wholesale` tab prints `GET /transfers/v2/delivery/{id}/packages`.
  The real v2 path is `/transfers/v2/**deliveries**/{id}/packages` (same for the
  `/wholesale` variant).
- `Transfer Templates` Step 2 lists the endpoint as `GE` (truncated). It should be
  `GET /transfers/v2/templates`.
