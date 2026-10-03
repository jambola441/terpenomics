To: api-info@metrc.com
Subject: NY API Proficiency Evaluation – generic.tech LLC (Terpenomics)
Attachment: Evaluation_NY_completed.xlsx

Hi,

Please find attached our completed Generic Evaluation for New York.

  Integrator:  generic.tech LLC
  Software:    Terpenomics
  Vendor key:  HDqkP7… (full keys are on the CompanyInformation tab)

48 of the 53 steps return HTTP 200. We are requesting read-only (GET) access
across the Sales dependency chain: Strains, Items, Packages, Sales, Sales
Deliveries, and GET Transfers / Wholesale, as marked on the Permissions tab.

Five steps do not return 200. In both cases the cause appears to be a facility
capability that is disabled across the NY sandbox rather than anything about
our key, and we would appreciate your guidance on how to evidence them.

1. Sales with Patient Look Up, step 4

GET /patients/v2/statuses/{patientLicenseNumber} returns 401, as do
GET /patients/v2/active and POST /patients/v2/, so there is no way to obtain a
patient number to look up. GET /facilities/v2 reports CanHaveMemberPatients
false on every dispensary available to us (AU, MED and DUAL) across two
separate sandbox tenants, which suggests there is no member patient registry
to query.

The same facilities report CanSellToExternalPatients true, and step 5 of that
tab (a receipt with SalesCustomerType "ExternalPatient") returns 200.

Is the member patient registry intentionally disabled in the NY sandbox, and
if so, how should step 4 be evidenced?

2. Transfer External Incoming, steps 1a and 1b

POST /transfers/v2/external/incoming returns 401. Steps 3 and 4 depend on the
IDs those steps create, so they are blank. Step 2 returns 200.

GET /facilities/v2 reports CanTransferFromExternalFacilities false on all 26
facilities across both tenants. We ruled out the request itself: an empty
body returns 400 with a validation message, while a fully populated body
returns 401. We tried both transfer types flagged for external incoming
shipments, shippers inside and outside our tenant, and fully populated
transporters and packages, with the same result each time.

Is this capability disabled for NY sandbox facilities? If so, can these steps
be submitted documented as 401s?

3. Sandbox writes have been failing since 15 September

Most write requests return:

  400 {"Message":"Could not load file or assembly 'System.Data.SqlClient,
  Version=0.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a'. The
  system cannot find the file specified."}

On 3 October, 9 of 10 identical POST /strains/v2/ requests returned this and
1 succeeded. It happens on every write endpoint we have tried, across
facilities and both sandbox tenants, and even with the example body from your
documentation. Reads are unaffected, and invalid bodies still get normal
validation errors, so the failure happens after a request passes validation.

Because the evaluation needs several dozen writes in a row to succeed, we have
not been able to complete a fresh run. This is why the attached evidence is
dated 6 September. We are happy to re-run once writes are working.

A few documentation notes, in case they help other NY integrators. We can send
full request and response transcripts for any of them.

- PUT /packages/v2/adjust treats Quantity as the new total, not a change. The
  documented example passes -2.0. Sending the negative of a package's quantity
  leaves the package at that negative value, and finishing it then fails as
  "not empty". Sending 0 empties it.
- The /sandbox/v2/ endpoints authenticate with the vendor key in an
  x-metrc-key header, not basic auth. The documentation says this only for
  integrator/setup.
- A lastModified range wider than 24 hours returns 400. The documentation
  does not state this limit.
- Plants are not immediately readable after a write: a growth phase change
  returns 200, but a read straight afterwards returns nothing for a few
  seconds.

Thank you,

Pablo Melana-Dayton
generic.tech LLC
(646) 260-6799
jambola441@gmail.com
