To: api-info@metrc.com
Subject: NY API Proficiency Evaluation – generic.tech LLC (Terpenomics)
Attachment: Evaluation_NY_completed.xlsx

Hi,

Please find attached our completed Generic Evaluation for New York for
generic.tech LLC (software: Terpenomics). We are requesting read-only (GET)
access, as marked on the Permissions tab.

All results are from sandbox runs on 6 September 2026. 48 of the 53 steps
return HTTP 200. We have not been able to re-run since then because most
sandbox writes have returned a "Could not load file or assembly
'System.Data.SqlClient'" error from 15 September through today.

The five remaining steps appear to be blocked by facility settings in the NY
sandbox:

- Sales with Patient Look Up, step 4: every dispensary reports
  CanHaveMemberPatients = false, so there are no patients to look up.
- Transfer External Incoming, steps 1a and 1b: every facility reports
  CanTransferFromExternalFacilities = false, so these return 401. Steps 3
  and 4 depend on them and are blank.

Could you let us know how you'd like these steps evidenced?

Thank you,

Pablo Melana-Dayton
generic.tech LLC
(646) 260-6799
jambola441@gmail.com
