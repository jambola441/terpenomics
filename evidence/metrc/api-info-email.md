**To:** api-info@metrc.com
**Subject:** NY API evaluation — two facility capabilities disabled in the sandbox

Hi,

Attached is our completed Generic Evaluation for New York (integrator:
Terpenomics, vendor key HDqkP7…). 48 of the 53 steps return HTTP 200.

Five steps do not, and in both cases we believe the cause is a facility
capability that is switched off across the NY sandbox rather than anything
about our key. We would like your guidance on how to evidence those steps
before we treat the evaluation as complete.

---

**1. Member patients — "Sales with Patient Look Up", step 4**

`GET /patients/v2/statuses/{patientLicenseNumber}` returns 401. So do
`GET /patients/v2/active` and `POST /patients/v2/`, which means there is no
route to obtain a valid patient number to query in the first place.

`GET /facilities/v2` reports `CanHaveMemberPatients: false` and
`TotalMemberPatientsAllowed: null` on every dispensary available to us — AU,
MED and DUAL — across two independent sandbox tenants (`…-30301` and
`…-13402`). That reads to us as the facilities having no member patient
registry at all, which would explain the 401 on all three routes.

The same facilities report `CanSellToExternalPatients: true`, and step 5 of
that tab succeeds: we posted a receipt with `SalesCustomerType` of
`ExternalPatient` and received a 200. So the external-patient half of the tab
is demonstrated; only the member-patient lookup in step 4 is not.

Is the member patient registry intentionally disabled in the NY sandbox? If
so, how would you like step 4 evidenced?

**2. External incoming transfers — "Transfer External Incoming", steps 1a/1b**

`POST /transfers/v2/external/incoming` returns 401. Steps 3 and 4 depend on
the ids those steps create, so they are blank. Step 2 of that tab,
`GET /transfers/v2/incoming`, returns 200.

`GET /facilities/v2` reports `CanTransferFromExternalFacilities: false` on all
26 facilities across both tenants.

We ruled out the request itself: an empty array returns
`400 "The request body must not be an empty array"`, while a fully populated
body returns 401, so authorization is being refused after validation is
reached. We tried both transfer types flagged `ForExternalIncomingShipments`
by `GET /transfers/v2/types` ("Beginning Inventory" and "External Hemp
Transfer"), shipper licenses inside and outside our own tenant, populated
`Transporters` and `Packages` arrays, and item names valid at the receiving
facility. Same result each time, on both tenants.

Is this capability disabled for NY sandbox facilities? If it is, we would
appreciate confirmation that those steps can be submitted documented as 401s.

**3. The NY sandbox is currently rejecting writes**

Since 15 September, `POST /strains/v2/` has returned:

    400 {"Message":"Could not load file or assembly 'System.Data.SqlClient,
    Version=0.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a'.
    The system cannot find the file specified."}

It persists across retries and was still occurring on 17 September. Reads are
unaffected — `GET /strains/v2/active`, `/facilities/v2` and the rest all return
200 — and `POST /locations/v2/` succeeded on a retry, so it may be intermittent
across instances rather than total.

Flagging it in case it is not already known. It is why the attached evidence is
dated 6 September rather than this week; we are happy to re-run once writes are
healthy.

---

**Documentation notes**

Offered in case they are useful to your team or to other NY integrators. Happy
to provide full request/response transcripts for any of them.

*`PUT /packages/v2/adjust` treats `Quantity` as the new total, not a delta.*
The documented example passes `-2.0`, which reads as an adjustment amount.
Sending the negative of a package's current quantity sets the package to that
negative value, and `PUT /packages/v2/finish` then rejects it with "cannot be
Finished because it's not empty". Sending `0` empties the package and finish
returns 200. Reading the package between calls:

    read 10.0 -> adjust -10.0 -> read -10.0 -> adjust +10.0 -> read 10.0
    read 10.0 -> adjust  0    -> read   0.0 -> finish 200

*The `/sandbox/v2/` endpoints use a different authentication scheme.* All four
authenticate with the vendor key in an `x-metrc-key` header rather than basic
auth. The documentation mentions this only for `integrator/setup`; basic auth
returns 401 on `tagtypes`, `facility/tags` and `packages/create`.

*A `lastModified` range wider than 24 hours returns 400* ("Last Modified range
cannot exceed 24 hours") on plant batches, plants, harvests, packages and
transfers. Omitting the range entirely is accepted and returns everything. The
"Requesting Large Amounts of Data" section describes chronological paging but
does not state the cap.

*Plants are not read-after-write consistent.* `POST
/plantbatches/v2/growthphase` returns 200, but `GET /plants/v2/flowering`
issued immediately afterwards returns no rows; the plants appear a few seconds
later. Worth a note for integrators who read back after a write.

*Smaller items.* `GET /sales/v2/customertypes` returns a plain array of
strings where neighbouring vocabulary endpoints return objects with a `Name`.
`POST /sales/v2/deliveries` requires `DriverEmployeeId` and rejects duplicate
package labels across a delivery's transactions. NY publishes no plant waste
methods, so `WasteMethodName` is necessarily null, and the only delivery
return reason is "Unable to Deliver" rather than the documented "Spoilage".

Thanks very much,

Terpenomics
