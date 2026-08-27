"""Sandbox self-service bootstrap.

Metrc's sandbox exposes four endpoints that let an integrator stand up their
own test environment without a licensee partner:

    POST /sandbox/v2/integrator/setup   mint an industry user key (vendor key only)
    GET  /sandbox/v2/tagtypes           discover valid tag types
    POST /sandbox/v2/facility/tags      mint plant/package tags, instantly received
    POST /sandbox/v2/packages/create    create opening-balance packages

Together these solve the cold-start problem the workbook's 'Closed Loop
Environment' tab describes: you need tags before you can make a plant batch,
and inventory before you can make a package.
"""
from __future__ import annotations

from .client import MetrcClient, rows

PLANT_TAG_TYPES = ("Cannabis Plant", "Marijuana Plant")
PACKAGE_TAG_TYPES = ("Cannabis Package", "Marijuana Package")


def request_user_key(client: MetrcClient, user_key: str = "") -> dict:
    """Create or look up the sandbox industry user key.

    Called bare, this queues creation and Metrc emails the key to the contact
    on file. Called with an existing key, it echoes the key back once creation
    has completed.

    Returns a dict describing what happened; it does not raise on the
    non-200 statuses, because 201/202/204 are all expected here.
    """
    params = {"userKey": user_key} if user_key else None
    record = client.post(
        "/sandbox/v2/integrator/setup",
        params=params,
        license_number="",
        vendor_only=True,
        step="bootstrap",
        sheet="_bootstrap",
        raise_on_error=False,
    )
    meanings = {
        200: "user key returned in the response body (or sent to the email on file)",
        201: "user queued for creation — call again shortly",
        202: "user creation in process — call again shortly",
        204: "user key not found",
    }
    return {
        "status": record.status,
        "meaning": meanings.get(record.status or 0, "unexpected status"),
        "body": record.response_body,
        "record": record,
    }


def list_facilities(client: MetrcClient) -> list:
    """GET /facilities/v2 — the docs' recommended first call.

    Reveals which facilities the user key can reach and, crucially, the exact
    permission set the state has granted each one.
    """
    record = client.get(
        "/facilities/v2/",
        license_number="",
        step="facilities",
        sheet="_bootstrap",
    )
    return rows(record.response_body)


def facility_permissions(facility: dict) -> dict:
    """Flatten a facility's FacilityType block into name -> bool."""
    ftype = facility.get("FacilityType") or {}
    return {k: v for k, v in ftype.items() if isinstance(v, bool)}


def tag_types(client: MetrcClient) -> list:
    record = client.get("/sandbox/v2/tagtypes", step="bootstrap", sheet="_bootstrap")
    return rows(record.response_body)


def _pick_tag_type(available: list, preferred: tuple, inventory_type: str) -> str:
    names = [t.get("Name", "") for t in available]
    for want in preferred:
        if want in names:
            return want
    for t in available:
        if t.get("TagInventoryType") == inventory_type:
            return t.get("Name", "")
    raise RuntimeError(
        f"no {inventory_type} tag type available; sandbox offers: {names}"
    )


def mint_tags(client: MetrcClient, tag_type: str, count: int) -> list:
    """Generate tags and return their labels. Max 1000 per request."""
    if not 1 <= count <= 1000:
        raise ValueError("count must be between 1 and 1000")
    record = client.post(
        "/sandbox/v2/facility/tags",
        body={"TagType": tag_type, "Count": count},
        step="bootstrap",
        sheet="_bootstrap",
    )
    payload = record.response_body or {}
    labels = payload.get("Labels") if isinstance(payload, dict) else None
    return list(labels or [])


def mint_opening_packages(
    client: MetrcClient,
    count: int = 10,
    filter_by: str | None = None,
    filter_value: str | None = None,
) -> list:
    """Create opening-balance packages so there is inventory to work with."""
    if count > 100:
        raise ValueError("Metrc caps opening-balance packages at 100 per call")
    body: dict = {"Count": count}
    if filter_by:
        if not filter_value:
            raise ValueError("filter_value is required when filter_by is set")
        body["FilterBy"] = filter_by
        body["FilterValue"] = filter_value
    record = client.post(
        "/sandbox/v2/packages/create",
        body=body,
        step="bootstrap",
        sheet="_bootstrap",
    )
    return record.object_ids


def prepare_environment(
    client: MetrcClient,
    *,
    plant_tags: int = 25,
    package_tags: int = 25,
    opening_packages: int = 10,
) -> dict:
    """One call that leaves the sandbox ready to run the evaluation."""
    available = tag_types(client)
    plant_type = _pick_tag_type(available, PLANT_TAG_TYPES, "Plant")
    package_type = _pick_tag_type(available, PACKAGE_TAG_TYPES, "Package")
    return {
        "tag_types": [t.get("Name") for t in available],
        "plant_tag_type": plant_type,
        "package_tag_type": package_type,
        "plant_tags": mint_tags(client, plant_type, plant_tags),
        "package_tags": mint_tags(client, package_type, package_tags),
        "opening_package_ids": mint_opening_packages(client, opening_packages),
    }
