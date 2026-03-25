"""
Challenge for p006: tests whether the old approach actually makes N calls for N pages.

The old parser has early-exit logic (services/lab_report_parser.py:342):
    for page_b64 in pages[1:]:
        if result.terpenes and result.cannabinoids and result.confidence >= 3:
            break

For a typical well-formatted COA (confidence=5 on page 1), the loop never fires.
Old = 1 API call even on a 3-page PDF.

Usage:
    python challenge_p006.py
"""

import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from make_multipage_pdf import make_multipage_pdf
from services.lab_report_parser import rasterize_pdf, _make_client, _extract_from_page, _merge_extractions
from parser_files_api import extract_from_pdf as new_extract, COAExtraction


def old_extract_instrumented(pdf_bytes: bytes):
    """Old pipeline with call counting injected."""
    client = _make_client()
    pages = rasterize_pdf(pdf_bytes)
    call_count = 0

    result = _extract_from_page(client, pages[0])
    call_count += 1
    early_exit = False

    for page_b64 in pages[1:]:
        if result.terpenes and result.cannabinoids and result.confidence >= 3:
            early_exit = True
            break
        page_result = _extract_from_page(client, page_b64)
        call_count += 1
        result = _merge_extractions(result, page_result)

    return result, call_count, early_exit


# --- Generate 3-page PDF ---
print("=== Generating 3-page test COA ===")
pdf_bytes = make_multipage_pdf("test_coa_3page.pdf")
print(f"PDF: {len(pdf_bytes):,} bytes, 3 pages")

print(f"\nPages after rasterize: {len(rasterize_pdf(pdf_bytes))}")

# --- Old approach (instrumented) ---
print("\n=== OLD: rasterize + per-page (instrumented) ===")
t0 = time.perf_counter()
old_result, old_calls, early_exit = old_extract_instrumented(pdf_bytes)
old_elapsed = time.perf_counter() - t0

print(f"  API calls made    : {old_calls} of 3 pages")
print(f"  Early exit fired  : {early_exit}")
print(f"  Confidence p1     : {old_result.confidence}")
print(f"  Terpenes found    : {len(old_result.terpenes)}")
print(f"  Cannabinoids found: {len(old_result.cannabinoids)}")
print(f"  Elapsed           : {old_elapsed:.2f}s")

# --- New approach ---
print("\n=== NEW: Files API single-call ===")
t0 = time.perf_counter()
new_result = new_extract(pdf_bytes)
new_elapsed = time.perf_counter() - t0

print(f"  API calls made    : 3 (upload + message + delete)")
print(f"  Terpenes found    : {len(new_result.terpenes)}")
print(f"  Cannabinoids found: {len(new_result.cannabinoids)}")
print(f"  Elapsed           : {new_elapsed:.2f}s")

# --- Verdict ---
print("\n=== CHALLENGE VERDICT ===")
print(f"p006 claim: 'old makes N calls for N pages → latency crossover at N>1'")
print(f"Reality   : old made {old_calls} call(s) for a {len(rasterize_pdf(pdf_bytes))}-page PDF (early_exit={early_exit})")
if early_exit and old_calls == 1:
    print("CHALLENGED: Early exit fired on page 1. Old = 1 call even on 3-page PDF.")
    print(f"  Old latency: {old_elapsed:.2f}s   New latency: {new_elapsed:.2f}s")
    if old_elapsed < new_elapsed:
        print(f"  Old is STILL faster by {new_elapsed - old_elapsed:.2f}s on 3-page COA.")
    else:
        print(f"  New is faster by {old_elapsed - new_elapsed:.2f}s on 3-page COA.")
else:
    print(f"NOT challenged: Old made {old_calls} calls as expected (no early exit).")

results = {
    "pdf_pages": 3,
    "pdf_bytes": len(pdf_bytes),
    "old": {"elapsed_s": round(old_elapsed, 2), "api_calls": old_calls, "early_exit": early_exit,
            "terpenes": len(old_result.terpenes), "cannabinoids": len(old_result.cannabinoids),
            "confidence": old_result.confidence},
    "new": {"elapsed_s": round(new_elapsed, 2), "api_calls": 3,
            "terpenes": len(new_result.terpenes), "cannabinoids": len(new_result.cannabinoids),
            "confidence": new_result.confidence},
}
with open("results_challenge_p006.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nResults saved to results_challenge_p006.json")
