"""The evaluation step sequences, in the order the workbook asks for them.

Each function drives one workbook tab. Steps are labelled to match column A
('Step 1', 'Step 1a', ...) so the writer can drop each result into the right
row without any manual mapping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .client import CallRecord, MetrcClient, first, rows

ISO = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(dt: datetime) -> str:
    return dt.strftime(ISO)


def today() -> str:
    return utc_now().strftime("%Y-%m-%d")


@dataclass
class Context:
    """Carries state between steps — ids and tags a later step depends on."""

    license_number: str = ""
    plant_tags: list = field(default_factory=list)
    package_tags: list = field(default_factory=list)
    created: dict = field(default_factory=dict)
    suffix: str = field(default_factory=lambda: utc_now().strftime("%m%d-%H%M"))

    def take_plant_tag(self) -> str:
        if not self.plant_tags:
            raise RuntimeError("out of plant tags — mint more via bootstrap.mint_tags")
        return self.plant_tags.pop(0)

    def take_package_tag(self) -> str:
        if not self.package_tags:
            raise RuntimeError("out of package tags — mint more via bootstrap.mint_tags")
        return self.package_tags.pop(0)


def annotate(
    record: CallRecord,
    *,
    ids: list | None = None,
    tags: list | None = None,
    names: list | None = None,
    last_modified: str = "",
) -> CallRecord:
    """Attach the verification values a step produced to its record."""
    if ids:
        record.object_ids = list(ids)
    if tags:
        record.tags = list(tags)
    if names:
        record.names = list(names)
    if last_modified:
        record.last_modified = last_modified
    elif not record.last_modified:
        record.last_modified = stamp(utc_now())
    return record


def _lm(row: dict) -> str:
    return str(row.get("LastModified") or "")


# ---------------------------------------------------------------------------
# GET-only evaluation
# ---------------------------------------------------------------------------

def get_transfers_and_wholesale(client: MetrcClient, ctx: Context, *, window_days: int = 90) -> None:
    """The 'GET Transfers and Wholesale' tab — six read steps.

    Steps 1 and 2 require a lastModified range; the rest chain off ids
    discovered by the previous step.
    """
    sheet = "GET Transfers and Wholesale"
    end = utc_now()
    start = end - timedelta(days=window_days)
    window = {"lastModifiedStart": stamp(start), "lastModifiedEnd": stamp(end)}

    incoming = client.get(
        "/transfers/v2/incoming", params=dict(window), step="Step 1", sheet=sheet
    )
    inc_rows = rows(incoming.response_body)
    annotate(
        incoming,
        ids=[r.get("Id") for r in inc_rows[:5] if r.get("Id")],
        names=[r.get("ManifestNumber") for r in inc_rows[:5] if r.get("ManifestNumber")],
        last_modified=_lm(inc_rows[0]) if inc_rows else "",
    )

    outgoing = client.get(
        "/transfers/v2/outgoing", params=dict(window), step="Step 2", sheet=sheet
    )
    out_rows = rows(outgoing.response_body)
    annotate(
        outgoing,
        ids=[r.get("Id") for r in out_rows[:5] if r.get("Id")],
        names=[r.get("ManifestNumber") for r in out_rows[:5] if r.get("ManifestNumber")],
        last_modified=_lm(out_rows[0]) if out_rows else "",
    )

    rejected = client.get(
        "/transfers/v2/rejected", params=dict(window), step="Step 3", sheet=sheet,
        raise_on_error=False,
    )
    rej_rows = rows(rejected.response_body)
    annotate(
        rejected,
        ids=[r.get("Id") for r in rej_rows[:5] if r.get("Id")],
        last_modified=_lm(rej_rows[0]) if rej_rows else "",
    )

    # Step 4 needs a real transfer id; prefer an incoming one, fall back to outgoing.
    transfer = (inc_rows or out_rows or [None])[0]
    if not transfer:
        raise RuntimeError(
            "no transfers found in the last "
            f"{window_days} days — widen the window or ask Metrc to seed one"
        )
    transfer_id = transfer["Id"]

    # This path takes no licenseNumber, so suppress the client's auto-injection.
    deliveries = client.get(
        f"/transfers/v2/{transfer_id}/deliveries",
        license_number="",
        step="Step 4",
        sheet=sheet,
    )
    del_rows = rows(deliveries.response_body)
    annotate(
        deliveries,
        ids=[transfer_id],
        names=[str(transfer.get("ManifestNumber") or "")],
        last_modified=_lm(transfer),
    )
    if not del_rows:
        raise RuntimeError(f"transfer {transfer_id} has no deliveries to inspect")
    delivery_id = del_rows[0]["Id"]

    # NOTE: the workbook prints this as /transfers/v2/delivery/... — the real
    # v2 path is /transfers/v2/deliveries/{id}/packages.
    packages = client.get(
        f"/transfers/v2/deliveries/{delivery_id}/packages",
        license_number="",
        step="Step 5",
        sheet=sheet,
    )
    pkg_rows = rows(packages.response_body)
    annotate(
        packages,
        ids=[delivery_id],
        tags=[r.get("PackageLabel") for r in pkg_rows[:5] if r.get("PackageLabel")],
    )

    wholesale = client.get(
        f"/transfers/v2/deliveries/{delivery_id}/packages/wholesale",
        license_number="",
        step="Step 6",
        sheet=sheet,
        raise_on_error=False,
    )
    ws_rows = rows(wholesale.response_body)
    annotate(
        wholesale,
        ids=[delivery_id],
        tags=[r.get("PackageLabel") for r in ws_rows[:5] if r.get("PackageLabel")],
    )

    ctx.created["transfer_id"] = transfer_id
    ctx.created["delivery_id"] = delivery_id


def read_lab_results(client: MetrcClient, ctx: Context, *, max_packages: int = 25) -> None:
    """Read-only lab path: find a tested package, then pull its results.

    Recorded against the LabResults tab so the evidence lands somewhere, even
    though that tab's own Step 1 is a POST.
    """
    sheet = "LabResults"
    types = client.get(
        "/labtests/v2/types", license_number="", step="lab-types", sheet="_readonly",
    )
    annotate(types, names=[r.get("Name") for r in rows(types.response_body)[:10]])

    active = client.get("/packages/v2/active", step="packages-active", sheet="_readonly")
    candidates = rows(active.response_body)[:max_packages]
    tested = [p for p in candidates if p.get("LabTestingStateName") == "TestPassed"] or candidates

    if not tested:
        raise RuntimeError("no active packages found to read lab results from")

    for package in tested:
        record = client.get(
            "/labtests/v2/results",
            params={"packageId": package["Id"]},
            step="Step 1",
            sheet=sheet,
            raise_on_error=False,
        )
        result_rows = rows(record.response_body)
        annotate(
            record,
            ids=[package["Id"]],
            tags=[package.get("Label", "")],
            names=[r.get("LabTestTypeName") for r in result_rows[:10] if r.get("LabTestTypeName")],
            last_modified=_lm(package),
        )
        if record.ok and result_rows:
            ctx.created["lab_package_id"] = package["Id"]
            ctx.created["lab_package_label"] = package.get("Label", "")
            return

    raise RuntimeError(
        f"checked {len(tested)} packages, none returned lab results — "
        "ask Metrc to seed a tested package in the sandbox"
    )


# Read endpoints swept for a GET-only evaluation, grouped by the workbook tab
# whose subject matter they cover.
READ_SWEEP = [
    ("Locations", "/locations/v2/active", {}),
    ("Locations", "/locations/v2/types", {}),
    ("Strains", "/strains/v2/active", {}),
    ("Items", "/items/v2/active", {}),
    ("Items", "/items/v2/categories", {}),
    ("PlantBatches", "/plantbatches/v2/active", {"window": True}),
    ("Plants", "/plants/v2/vegetative", {"window": True}),
    ("Plants", "/plants/v2/flowering", {"window": True}),
    ("Harvest", "/harvests/v2/active", {"window": True}),
    ("Packages", "/packages/v2/active", {"window": True}),
    ("Packages", "/packages/v2/inactive", {"window": True}),
    ("Packages", "/packages/v2/types", {}),
    ("LabResults", "/labtests/v2/types", {"no_license": True}),
    ("Sales", "/sales/v2/receipts/active", {"window": True}),
    ("Sales", "/sales/v2/customertypes", {}),
    ("Sales Deliveries (NOT CA)", "/sales/v2/deliveries/active", {"window": True}),
]


def read_sweep(client: MetrcClient, ctx: Context, *, window_days: int = 90) -> list:
    """Exercise every readable area once, for a GET-only submission."""
    end = utc_now()
    start = end - timedelta(days=window_days)
    results = []
    for sheet, path, opts in READ_SWEEP:
        params = {}
        if opts.get("window"):
            params = {"lastModifiedStart": stamp(start), "lastModifiedEnd": stamp(end)}
        record = client.get(
            path,
            params=params or None,
            license_number="" if opts.get("no_license") else None,
            step=f"read {path}",
            sheet="_readonly",
            raise_on_error=False,
        )
        payload = rows(record.response_body)
        annotate(
            record,
            ids=[r.get("Id") for r in payload[:3] if isinstance(r, dict) and r.get("Id")],
            last_modified=_lm(payload[0]) if payload and isinstance(payload[0], dict) else "",
        )
        results.append((sheet, path, record.status, len(payload)))
    return results


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

def _names(payload, key: str = "Name") -> list:
    return [r.get(key) for r in rows(payload) if isinstance(r, dict) and r.get(key)]


def _pick(options: list, *preferred: str) -> str:
    """First preferred option that the facility actually offers, else the first."""
    for want in preferred:
        for option in options:
            if option and option.lower() == want.lower():
                return option
    if not options:
        raise RuntimeError("facility offers no options for a required reference field")
    return options[0]


def load_reference(client: MetrcClient) -> dict:
    """Fetch the vocabularies the write steps must draw from.

    Metrc rejects free-text values for these, so every body has to be built
    from what this facility actually offers.
    """
    def read(path, no_license=False):
        record = client.get(
            path,
            license_number="" if no_license else None,
            step=f"ref {path}",
            sheet="_reference",
            raise_on_error=False,
        )
        return record.response_body if record.ok else []

    return {
        "location_types": _names(read("/locations/v2/types")),
        "item_categories": [
            r for r in rows(read("/items/v2/categories")) if isinstance(r, dict)
        ],
        "units": _names(read("/unitsofmeasure/v2/active", no_license=True)),
        "waste_methods": _names(read("/plants/v2/waste/methods")),
        "waste_reasons": _names(read("/plants/v2/waste/reasons")),
        "harvest_waste_types": _names(read("/harvests/v2/waste/types")),
        "adjust_reasons": _names(read("/packages/v2/adjust/reasons")),
        "customer_types": _names(read("/sales/v2/customertypes")),
    }


# ---------------------------------------------------------------------------
# Write tabs
# ---------------------------------------------------------------------------

def locations_tab(client: MetrcClient, ctx: Context, ref: dict) -> None:
    sheet = "Locations"
    name = f"Terpenomics Loc {ctx.suffix}"
    loc_type = _pick(ref["location_types"], "Default")

    created = client.post(
        "/locations/v2/",
        body=[{"Name": name, "LocationTypeName": loc_type}],
        step="Step 1", sheet=sheet,
    )
    loc_id = created.object_ids[0]
    annotate(created, ids=[loc_id], names=[name])

    renamed = f"{name} (Updated)"
    updated = client.put(
        "/locations/v2/",
        body=[{"Id": loc_id, "Name": renamed, "LocationTypeName": loc_type}],
        step="Step 2", sheet=sheet,
    )
    annotate(updated, ids=[loc_id], names=[renamed])

    fetched = client.get(f"/locations/v2/{loc_id}", step="Step 3", sheet=sheet)
    row = (rows(fetched.response_body) or [{}])[0]
    annotate(fetched, ids=[loc_id], names=[row.get("Name", renamed)], last_modified=_lm(row))

    ctx.created["location_name"] = renamed
    ctx.created["location_id"] = loc_id


def strains_tab(client: MetrcClient, ctx: Context, ref: dict) -> None:
    sheet = "Strains"
    name = f"Terpenomics Strain {ctx.suffix}"

    created = client.post(
        "/strains/v2/",
        body=[{
            "Name": name, "TestingStatus": "None",
            "ThcLevel": 0.1865, "CbdLevel": 0.1075,
            "IndicaPercentage": 25.0, "SativaPercentage": 75.0,
        }],
        step="Step 1", sheet=sheet,
    )
    strain_id = created.object_ids[0]
    annotate(created, ids=[strain_id], names=[name])

    # Step 2 asks specifically for the indica/sativa split to change.
    updated = client.put(
        "/strains/v2/",
        body=[{
            "Id": strain_id, "Name": name, "TestingStatus": "None",
            "ThcLevel": 0.1865, "CbdLevel": 0.1075,
            "IndicaPercentage": 60.0, "SativaPercentage": 40.0,
        }],
        step="Step 2", sheet=sheet,
    )
    annotate(updated, ids=[strain_id], names=[name])

    fetched = client.get(f"/strains/v2/{strain_id}", step="Step 3", sheet=sheet)
    row = (rows(fetched.response_body) or [{}])[0]
    annotate(fetched, ids=[strain_id], names=[row.get("Name", name)], last_modified=_lm(row))

    ctx.created["strain_name"] = name
    ctx.created["strain_id"] = strain_id


def items_tab(client: MetrcClient, ctx: Context, ref: dict) -> None:
    sheet = "Items"
    name = f"Terpenomics Item {ctx.suffix}"
    strain = ctx.created.get("strain_name")

    categories = ref["item_categories"]
    category = next(
        (c for c in categories if c.get("Name") == "Buds"),
        categories[0] if categories else {},
    )
    category_name = category.get("Name")
    if not category_name:
        raise RuntimeError("no item categories available for this facility")

    # A category dictates its own unit-of-measure family; ignoring that is the
    # usual cause of a 400 here.
    quantity_type = category.get("QuantityType", "WeightBased")
    if quantity_type == "CountBased":
        first_unit, second_unit = "Each", "Each"
    else:
        first_unit, second_unit = "Ounces", "Grams"

    body = {"ItemCategory": category_name, "Name": name, "UnitOfMeasure": first_unit}
    if category.get("RequiresStrain") and strain:
        body["Strain"] = strain

    created = client.post("/items/v2/", body=[body], step="Step 1", sheet=sheet)
    item_id = created.object_ids[0]
    annotate(created, ids=[item_id], names=[name])

    # Step 2 asks for the unit of measure specifically to change.
    updated_body = dict(body, Id=item_id, UnitOfMeasure=second_unit)
    updated = client.put("/items/v2/", body=[updated_body], step="Step 2", sheet=sheet)
    annotate(updated, ids=[item_id], names=[name])

    fetched = client.get(f"/items/v2/{item_id}", step="Step 3", sheet=sheet)
    row = (rows(fetched.response_body) or [{}])[0]
    annotate(fetched, ids=[item_id], names=[row.get("Name", name)], last_modified=_lm(row))

    ctx.created["item_name"] = name
    ctx.created["item_id"] = item_id


def plantbatches_tab(client: MetrcClient, ctx: Context, ref: dict) -> None:
    """The open-loop PlantBatches tab (NY). Closed-loop states use a different tab."""
    sheet = "PlantBatches"
    batch_name = f"TP Batch {ctx.suffix}"
    strain = ctx.created["strain_name"]
    location = ctx.created.get("location_name")

    created = client.post(
        "/plantbatches/v2/plantings",
        body=[{
            "Name": batch_name, "Type": "Clone", "Count": 6, "Strain": strain,
            "Location": location, "Sublocation": None,
            "PatientLicenseNumber": None, "ActualDate": today(),
            "SourcePlantBatches": None,
        }],
        step="Step 1", sheet=sheet,
    )
    annotate(created, ids=created.object_ids, names=[batch_name])

    # Step 2: package 3 clones out of the batch.
    package_tag = ctx.take_package_tag()
    packaged = client.post(
        "/plantbatches/v2/packages",
        body=[{
            "Id": None, "PlantBatch": batch_name, "Count": 3,
            "Location": location, "Sublocation": None,
            "Item": ctx.created["item_name"], "Tag": package_tag,
            "PatientLicenseNumber": None, "Note": "Evaluation step",
            "IsTradeSample": False, "IsDonation": False, "ActualDate": today(),
        }],
        step="Step 2", sheet=sheet,
    )
    annotate(packaged, ids=packaged.object_ids, tags=[package_tag], names=[batch_name])

    # Step 3: move 2 plants to Vegetative. Each plant consumes a plant tag,
    # assigned sequentially from StartingTag.
    starting_tag = ctx.take_plant_tag()
    second_tag = ctx.take_plant_tag()
    phased = client.post(
        "/plantbatches/v2/growthphase",
        body=[{
            "Name": batch_name, "Count": 2, "StartingTag": starting_tag,
            "GrowthPhase": "Vegetative", "NewLocation": location,
            "NewSublocation": None, "GrowthDate": today(),
            "PatientLicenseNumber": None,
        }],
        step="Step 3", sheet=sheet,
    )
    annotate(phased, ids=phased.object_ids, tags=[starting_tag, second_tag], names=[batch_name])

    destroyed = client.delete(
        "/plantbatches/v2/",
        body=[{
            "PlantBatch": batch_name, "Count": 1,
            "WasteMethodName": _pick(ref["waste_methods"], "Compost"),
            "WasteMaterialMixed": "Soil",
            "WasteReasonName": _pick(ref["waste_reasons"], "Contamination", "Destroy"),
            "ReasonNote": "Evaluation step — destroying one immature plant.",
            "WasteWeight": 1.0, "WasteUnitOfMeasure": "Grams",
            "ActualDate": today(),
        }],
        step="Step 4", sheet=sheet,
    )
    annotate(destroyed, names=[batch_name])

    ctx.created["plant_batch_name"] = batch_name
    ctx.created["veg_plant_tags"] = [starting_tag, second_tag]


def plants_tab(client: MetrcClient, ctx: Context, ref: dict) -> None:
    sheet = "Plants"
    location = ctx.created.get("location_name")
    strain = ctx.created["strain_name"]

    flowering = client.get(
        "/plants/v2/flowering",
        params={
            "lastModifiedStart": stamp(utc_now() - timedelta(days=30)),
            "lastModifiedEnd": stamp(utc_now()),
        },
        step="discover flowering", sheet="_reference",
        raise_on_error=False,
    )
    plants = [p for p in rows(flowering.response_body) if p.get("Label")]
    if len(plants) < 3:
        raise RuntimeError(
            f"need at least 3 flowering plants, found {len(plants)}. Move a batch "
            "to Flowering via POST /plantbatches/v2/growthphase first."
        )

    moved = client.put(
        "/plants/v2/location",
        body=[{
            "Id": None, "Label": plants[0]["Label"], "Location": location,
            "Sublocation": None, "ActualDate": today(),
        }],
        step="Step 1", sheet=sheet,
    )
    annotate(moved, tags=[plants[0]["Label"]], last_modified=_lm(plants[0]))

    immature_name = f"TP Immature {ctx.suffix}"
    plant_tag = ctx.take_plant_tag()
    planted = client.post(
        "/plants/v2/plantings",
        body=[{
            "PlantLabel": plants[0]["Label"], "PlantBatchName": immature_name,
            "PlantBatchType": "Clone", "PlantCount": 3,
            "LocationName": location, "SublocationName": None,
            "StrainName": strain, "PatientLicenseNumber": None,
            "ActualDate": stamp(utc_now()),
        }],
        step="Step 2", sheet=sheet,
    )
    annotate(planted, ids=planted.object_ids, tags=[plants[0]["Label"]], names=[immature_name])

    clone_tag = ctx.take_package_tag()
    cloned = client.post(
        "/plants/v2/plantbatch/packages",
        body=[{
            "PlantLabel": plants[0]["Label"], "PackageTag": clone_tag,
            "PlantBatchType": "Clone", "Item": ctx.created["item_name"],
            "Location": location, "Sublocation": None, "Note": None,
            "IsTradeSample": False, "PatientLicenseNumber": None,
            "IsDonation": False, "Count": 3, "ActualDate": stamp(utc_now()),
        }],
        step="Step 3", sheet=sheet,
    )
    annotate(cloned, ids=cloned.object_ids, tags=[clone_tag])

    destroyed = client.delete(
        "/plants/v2/",
        body=[{
            "Id": None, "Label": plants[1]["Label"],
            "WasteMethodName": _pick(ref["waste_methods"], "Compost"),
            "WasteMaterialMixed": "Soil", "WasteWeight": 15.0,
            "WasteUnitOfMeasureName": "Grams",
            "WasteReasonName": _pick(ref["waste_reasons"], "Contamination", "Destroy"),
            "Count": 0, "ReasonNote": "Evaluation step — plant destruction.",
            "ActualDate": today(),
        }],
        step="Step 4", sheet=sheet,
    )
    annotate(destroyed, tags=[plants[1]["Label"]])

    harvest_name = f"TP Harvest {ctx.suffix}"
    manicured = client.post(
        "/plants/v2/manicure",
        body=[{
            "Plant": plants[2]["Label"], "Weight": 25.0, "UnitOfWeight": "Grams",
            "DryingLocation": location, "DryingSublocation": None,
            "HarvestName": None, "PatientLicenseNumber": None,
            "ActualDate": today(), "PlantCount": 1,
        }],
        step="Step 5", sheet=sheet,
    )
    annotate(manicured, ids=manicured.object_ids, tags=[plants[2]["Label"]])

    # Step 6: harvest the remaining plants into one named harvest. Joining an
    # existing harvest requires the exact name on the same calendar day.
    remaining = plants[2:4] if len(plants) >= 4 else plants[2:3]
    harvested = client.put(
        "/plants/v2/harvest",
        body=[{
            "Plant": p["Label"], "Weight": 100.0, "UnitOfWeight": "Grams",
            "DryingLocation": location, "DryingSublocation": None,
            "HarvestName": harvest_name, "PatientLicenseNumber": None,
            "ActualDate": today(),
        } for p in remaining],
        step="Step 6", sheet=sheet,
    )
    annotate(
        harvested,
        ids=harvested.object_ids,
        tags=[p["Label"] for p in remaining],
        names=[harvest_name],
    )
    ctx.created["harvest_name"] = harvest_name


def harvest_tab(client: MetrcClient, ctx: Context, ref: dict) -> None:
    sheet = "Harvest"
    harvest_name = ctx.created["harvest_name"]
    location = ctx.created.get("location_name")

    active = client.get(
        "/harvests/v2/active",
        params={
            "lastModifiedStart": stamp(utc_now() - timedelta(days=2)),
            "lastModifiedEnd": stamp(utc_now()),
        },
        step="discover harvest", sheet="_reference",
    )
    harvest = first(active.response_body, Name=harvest_name) or (rows(active.response_body) or [None])[0]
    if not harvest:
        raise RuntimeError(f"harvest {harvest_name!r} not found among active harvests")
    harvest_id = harvest["Id"]

    package_tag = ctx.take_package_tag()
    packaged = client.post(
        "/harvests/v2/packages",
        body=[{
            "Tag": package_tag, "Location": location, "Sublocation": None,
            "Item": ctx.created["item_name"], "UnitOfWeight": "Grams",
            "PatientLicenseNumber": None, "Note": "Evaluation step",
            "IsProductionBatch": False, "ProductionBatchNumber": None,
            "IsTradeSample": False, "IsDonation": False,
            "ProductRequiresRemediation": False, "RemediateProduct": False,
            "ActualDate": today(),
            "Ingredients": [{
                "HarvestId": harvest_id, "HarvestName": None,
                "Weight": 50.0, "UnitOfWeight": "Grams",
            }],
        }],
        step="Step 1", sheet=sheet,
    )
    annotate(packaged, ids=packaged.object_ids, tags=[package_tag], names=[harvest_name])
    ctx.created["harvest_package_tag"] = package_tag

    # Step 2 is explicit that moisture loss is NOT waste — remaining wet weight is.
    remaining = harvest.get("CurrentWeight") or 10.0
    wasted = client.post(
        "/harvests/v2/waste",
        body=[{
            "Id": harvest_id,
            "WasteType": _pick(ref["harvest_waste_types"], "Plant Material"),
            "UnitOfWeight": "Grams", "WasteWeight": float(remaining),
            "ActualDate": today(),
        }],
        step="Step 2", sheet=sheet,
    )
    annotate(wasted, ids=[harvest_id], names=[harvest_name])

    finished = client.put(
        "/harvests/v2/finish",
        body=[{"Id": harvest_id, "ActualDate": today()}],
        step="Step 3", sheet=sheet,
    )
    annotate(finished, ids=[harvest_id], names=[harvest_name])

    unfinished = client.put(
        "/harvests/v2/unfinish",
        body=[{"Id": harvest_id}],
        step="Step 4", sheet=sheet,
    )
    annotate(unfinished, ids=[harvest_id], names=[harvest_name])


def packages_tab(client: MetrcClient, ctx: Context, ref: dict) -> None:
    sheet = "Packages"
    source_tag = ctx.created.get("harvest_package_tag")
    if not source_tag:
        raise RuntimeError("no source package — run the Harvest tab first")

    new_tag = ctx.take_package_tag()
    created = client.post(
        "/packages/v2/",
        body=[{
            "Tag": new_tag, "Location": ctx.created.get("location_name"),
            "Sublocation": None, "Item": ctx.created["item_name"],
            "Quantity": 10.0, "UnitOfMeasure": "Grams",
            "PatientLicenseNumber": None, "Note": "Evaluation step",
            "IsProductionBatch": False, "ProductionBatchNumber": None,
            "IsDonation": False, "IsTradeSample": False,
            "ProductRequiresRemediation": False, "UseSameItem": True,
            "ActualDate": today(),
            "Ingredients": [{
                "Package": source_tag, "Quantity": 10.0, "UnitOfMeasure": "Grams",
            }],
        }],
        step="Step 1", sheet=sheet,
    )
    annotate(created, ids=created.object_ids, tags=[new_tag])

    # Step 2 wants a different item, so create a second one to switch to.
    alt_name = f"Terpenomics Alt Item {ctx.suffix}"
    categories = ref["item_categories"]
    category = next((c for c in categories if c.get("Name") == "Shake"), categories[0])
    alt_body = {
        "ItemCategory": category.get("Name"), "Name": alt_name,
        "UnitOfMeasure": "Grams",
    }
    if category.get("RequiresStrain"):
        alt_body["Strain"] = ctx.created["strain_name"]
    client.post("/items/v2/", body=[alt_body], step="alt item", sheet="_reference")

    reitemed = client.put(
        "/packages/v2/item",
        body=[{"Label": new_tag, "Item": alt_name}],
        step="Step 2", sheet=sheet,
    )
    annotate(reitemed, tags=[new_tag], names=[alt_name])

    # Step 3: adjust down to zero. The quantity is a delta, so it must be negative.
    adjusted = client.put(
        "/packages/v2/adjust",
        body=[{
            "Label": new_tag, "Quantity": -10.0, "UnitOfMeasure": "Grams",
            "AdjustmentReason": _pick(ref["adjust_reasons"], "Drying", "Scale Variance"),
            "AdjustmentDate": today(),
            "ReasonNote": "Evaluation step — adjusting to zero.",
        }],
        step="Step 3", sheet=sheet,
    )
    annotate(adjusted, tags=[new_tag])

    finished = client.put(
        "/packages/v2/finish",
        body=[{"Label": new_tag, "ActualDate": today()}],
        step="Step 4", sheet=sheet,
    )
    annotate(finished, tags=[new_tag])

    unfinished = client.put(
        "/packages/v2/unfinish",
        body=[{"Label": new_tag}],
        step="Step 5", sheet=sheet,
    )
    annotate(unfinished, tags=[new_tag])
    ctx.created["package_tag"] = new_tag


WRITE_TABS = [
    ("Locations", locations_tab),
    ("Strains", strains_tab),
    ("Items", items_tab),
    ("PlantBatches", plantbatches_tab),
    ("Plants", plants_tab),
    ("Harvest", harvest_tab),
    ("Packages", packages_tab),
]


def run_full(client: MetrcClient, ctx: Context, only: set | None = None) -> list:
    """Run the write tabs in dependency order, reporting per-tab outcomes."""
    ref = load_reference(client)
    results = []
    for name, fn in WRITE_TABS:
        if only and name not in only:
            continue
        try:
            fn(client, ctx, ref)
            results.append((name, "ok", ""))
        except Exception as exc:
            results.append((name, "FAIL", str(exc)))
    return results
