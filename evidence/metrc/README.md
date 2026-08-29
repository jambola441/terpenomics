# Metrc API Proficiency Evaluation — NY

Tooling to run the Metrc evaluation against the NY sandbox and write the
results straight into the workbook Metrc sent.

## Status of this evaluation

**48 of 53 steps return HTTP 200.** Every tab NY requires is populated from
live sandbox calls.

Two permissions are not granted on the current key, and both need Metrc to
enable them before the evaluation can be submitted complete:

| Blocked | Steps | Evidence |
|---|---|---|
| Patients | Sales with Patient Look Up, step 4 | `GET /patients/v2/active` 401s at every dispensary, so it is the permission and not a bad patient number |
| External incoming transfers | Transfer External Incoming, steps 1a/1b (and 3/4, which depend on their ids) | `POST /transfers/v2/external/incoming` 401s with any populated body, while an empty array returns 400 — the route is reachable, the action is not |

Step 2 of Transfer External Incoming is an ordinary read and passes at 200.

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

## Credentials

Keys live in `metrc.env` (git-ignored) and are read from the environment. The
workbook's CompanyInformation tab asks for both API keys, so a completed
workbook contains live credentials — `evidence/metrc/Evaluation_*.xlsx` and
`company.json` are git-ignored for that reason. Copy `company.example.json` to
`company.json` for the contact fields; leave the key fields out, the runner
fills them from the environment at fill time.

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

## What the live NY sandbox actually does

Findings from a real run that the published documentation does not state.

**All `/sandbox/v2/*` endpoints authenticate with the vendor key alone**, in an
`x-metrc-key` header — not the basic auth every other endpoint uses. The docs
mention this only for `integrator/setup`; basic auth returns 401 on all four.

**A `lastModified` range wider than 24 hours is rejected** with
`400 Last Modified range cannot exceed 24 hours`. This applies to plant
batches, plants, harvests, packages and transfers. Omitting the range entirely
is allowed and returns everything, paginated — so a window is only worth
sending when a step specifically calls for a date search. The docs' "Requesting
Large Amounts of Data" section describes chronological paging but never states
the cap.

**Tag types are state-specific.** NY offers `Cannabis package` and
`Cannabis plant`, with `TagInventoryType` values of `CannabisPackage` and
`CannabisPlant` — not the `Marijuana Package` / `Package` in the doc examples.
Match case-insensitively and partially.

**Incoming and outgoing transfers live at different facilities.** A cultivator
has outgoing, a processor has incoming; no single facility has both. The GET
Transfers tab therefore spans facilities, which is exactly why the workbook
gives every step its own "License Facility" column.

**`GET /labtests/v2/types` returns over 10,000 rows in NY.** Anything that
walks that list needs to expect it.

**`PUT /packages/v2/adjust` sets the quantity, it does not adjust by it.** The
documented example passes `-2.0` as if it were a delta. In NY, sending the
negative of the current quantity leaves the package at that negative value, and
step 4 then refuses it: "cannot be Finished because it's not empty". Send `0`
to empty a package.

**Item categories declare their own requirements** through `Requires*` flags,
and they differ per facility. A cultivator's "Bud/Flower - Bulk" needs only a
strain; a dispensary's "Bud/Flower - Each" also demands a brand, a THC percent,
a unit weight and an expiration date. Build the body from the flags.

**`ProductCategoryType` decides what a package may contain.** Packaging clones
needs an item that is both `Plants`-typed and count-based, or the call fails
with "the selected Item must be of Plant type".

**`GET /sales/v2/customertypes` returns a plain array of strings**, not objects
with a `Name`, unlike every neighbouring vocabulary.

**Vocabularies are state-specific and some are empty.** NY publishes no plant
waste methods at all (the field is nullable), one delivery return reason
("Unable to Deliver", not the documented "Spoilage"), and no transfer type
called "Transfer" — outgoing templates need one flagged `ForLicensedShipments`.

**`POST /sales/v2/deliveries` requires `DriverEmployeeId`** and rejects
duplicate package labels across a delivery's transactions.

**`POST /sandbox/v2/packages/create` only sees weight-based items by default.**
A dispensary restricted to finished goods has none, so pass
`FilterBy: "Name"` to reach its count-based items.

## Known workbook errata

- The `GET Transfers and Wholesale` tab prints `GET /transfers/v2/delivery/{id}/packages`.
  The real v2 path is `/transfers/v2/**deliveries**/{id}/packages` (same for the
  `/wholesale` variant).
- `Transfer Templates` Step 2 lists the endpoint as `GE` (truncated). It should be
  `GET /transfers/v2/templates`.
