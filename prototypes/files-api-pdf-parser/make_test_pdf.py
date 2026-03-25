"""
Generate a synthetic COA-style PDF for testing.
Uses PyMuPDF (fitz) — already in requirements.txt.

Run:  python make_test_pdf.py
Output: test_coa.pdf
"""

import fitz


COA_TEXT = """\
CERTIFICATE OF ANALYSIS

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

This report is for informational purposes only.
ISO/IEC 17025:2017 Accredited Laboratory
"""


def make_test_pdf(output_path: str = "test_coa.pdf") -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text(
        (50, 60),
        COA_TEXT,
        fontsize=11,
        fontname="Courier",
        color=(0, 0, 0),
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    with open(output_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written: {output_path} ({len(pdf_bytes):,} bytes)")
    return pdf_bytes


if __name__ == "__main__":
    make_test_pdf()
