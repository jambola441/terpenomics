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
