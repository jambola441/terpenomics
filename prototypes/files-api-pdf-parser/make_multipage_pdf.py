"""
Generate a 3-page synthetic COA PDF for testing the early-exit behaviour.
Page 1: full terpene + cannabinoid table (confidence 5 expected)
Page 2: QA/methodology boilerplate
Page 3: lab accreditation info

Run: python make_multipage_pdf.py
Output: test_coa_3page.pdf
"""

import fitz


PAGE1 = """\
CERTIFICATE OF ANALYSIS — PAGE 1 OF 3

Lab Name: Green Leaf Analytics LLC
Lab License: OCM-NY-LAB-0042
Test Date: 2024-11-15
Batch ID: GLX-2024-8813
Product Name: Blue Dream — Flower
Overall Result: PASS

TERPENE PROFILE
--------------------------------------------
Terpene                  %w/w
--------------------------------------------
Myrcene                  0.4210
Limonene                 0.3180
beta-Caryophyllene       0.2950
Linalool                 0.1870
alpha-Pinene             0.0940
beta-Pinene              0.0710
Humulene                 0.0680
Ocimene                  0.0540
Terpinolene              0.0320
Bisabolol                0.0210
--------------------------------------------
TOTAL TERPENES           1.5610 %

CANNABINOID PANEL
--------------------------------------------
Cannabinoid              %w/w
--------------------------------------------
THCa                     22.4500
D9-THC                    0.3100
THCV                      0.1200
CBD                       0.0800
CBDa                      0.0400
CBG                       0.1500
CBN                       0.0300
CBC                       0.0600
--------------------------------------------
"""

PAGE2 = """\
CERTIFICATE OF ANALYSIS — PAGE 2 OF 3
QUALITY ASSURANCE & METHODOLOGY

Sample Preparation:
  - Homogenized and extracted per SOP-CHEM-001
  - All reagents ACS grade or higher

Analytical Methods:
  - Terpenes: GC-FID per USP <203>
  - Cannabinoids: HPLC-UV per USP <561>
  - Pesticides: LC-MS/MS per AOAC 2007.01

QC Results:
  - Method blanks: All below LOQ
  - Matrix spike recovery: 85-115% for all analytes
  - Lab duplicate RPD: < 20% for all analytes
  - Calibration R²: > 0.999 for all methods

Sample chain of custody verified.
This page contains no terpene or cannabinoid data.
"""

PAGE3 = """\
CERTIFICATE OF ANALYSIS — PAGE 3 OF 3
LABORATORY ACCREDITATION

Green Leaf Analytics LLC is accredited by
A2LA (American Association for Laboratory Accreditation)
Certificate #: 5823.01
Scope: Cannabis testing per ISO/IEC 17025:2017

This report shall not be reproduced except in full
without written approval of the laboratory.

Results apply to the sample as received.

Authorized Signatory: Dr. Jane Smith, PhD
Title: Laboratory Director
Signature date: 2024-11-15

--- END OF REPORT ---
This page contains no terpene or cannabinoid data.
"""


def make_multipage_pdf(output_path: str = "test_coa_3page.pdf") -> bytes:
    doc = fitz.open()
    for i, text in enumerate([PAGE1, PAGE2, PAGE3], 1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 60), text, fontsize=10, fontname="Courier", color=(0, 0, 0))
    pdf_bytes = doc.tobytes()
    doc.close()
    with open(output_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written: {output_path} ({len(pdf_bytes):,} bytes, 3 pages)")
    return pdf_bytes


if __name__ == "__main__":
    make_multipage_pdf()
