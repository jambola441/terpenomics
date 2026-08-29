**To:** api-info@metrc.com
**Subject:** NY sandbox — two endpoints returning 401 across two tenants, and a docs correction

Hi,

We're completing the Generic Evaluation for NY (integrator: Terpenomics). 48 of
53 steps return 200. Two endpoints return 401 for us, and we'd like to confirm
whether that's expected before we submit.

**1. `GET /patients/v2/...` returns 401**

Affects "Sales with Patient Look Up" step 4, which asks us to verify a patient's
`FlowerOuncesAvailable` via `GET /patients/v2/statuses/{patientLicenseNumber}`.

`GET /patients/v2/active` also returns 401, so we can't retrieve a valid patient
number to query. We see this at all three dispensary types — AU, MED and DUAL —
and on two independent sandbox tenants (`-30301` and `-13402`).

**2. `POST /transfers/v2/external/incoming` returns 401**

Affects "Transfer External Incoming" steps 1a/1b, and 3/4 which depend on the
ids those create. Step 2 (`GET /transfers/v2/incoming`) succeeds at 200.

An empty request body returns 400 ("The request body must not be an empty
array"), while a fully populated body returns 401 — so the route is reachable
and the authorization check happens after validation. Tried with
`TransferTypeName` values of both "Beginning Inventory" and "External Hemp
Transfer" (the two flagged `ForExternalIncomingShipments` by
`GET /transfers/v2/types`), and with shipper licenses both inside and outside
our own tenant. Same result on both tenants.

Our questions:

- Are these two disabled in the NY sandbox generally, or is it a permission we
  should request on our sandbox user?
- If they are disabled, how should the evaluation cover those steps? We're happy
  to submit them documented as 401 with the request/response evidence if that's
  acceptable.

**3. A documentation correction, offered in case it's useful**

`PUT /packages/v2/adjust` treats `Quantity` as the package's **new total**, not
a delta. The example in the docs passes `-2.0`, which reads as a delta. Sending
the negative of a package's current quantity leaves it at that negative value,
and `PUT /packages/v2/finish` then rejects it with "cannot be Finished because
it's not empty". Sending `0` empties the package and finish returns 200. We
verified this by reading the package between each call:

    read 10.0 -> adjust -10.0 -> read -10.0 -> adjust +10.0 -> read 10.0
    read 10.0 -> adjust 0     -> read 0.0   -> finish 200

A few smaller things we hit that aren't in the docs, in case they're worth a
note for other NY integrators:

- All `/sandbox/v2/*` endpoints authenticate with the vendor key in an
  `x-metrc-key` header rather than basic auth. The docs mention this only for
  `integrator/setup`; basic auth returns 401 on the other three.
- A `lastModified` range wider than 24 hours returns 400 ("Last Modified range
  cannot exceed 24 hours"). Omitting the range entirely is accepted.
- `GET /sales/v2/customertypes` returns a plain array of strings, where
  neighbouring vocabulary endpoints return objects with a `Name`.
- `POST /sales/v2/deliveries` requires `DriverEmployeeId`, which the example
  shows but the field list doesn't mark as required.

Happy to send full request/response transcripts for any of the above.

Thanks,
Terpenomics
