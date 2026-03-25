"""
Side-by-side comparison: Files API approach vs current base64-image approach.

Usage:
    # Run full comparison (needs ANTHROPIC_API_KEY):
    python compare.py

    # Dry run — validates code paths without making API calls:
    python compare.py --dry-run

    # Use a real PDF:
    python compare.py path/to/real_coa.pdf
"""

import argparse
import json
import sys
import time
import os

# ---------------------------------------------------------------------------
# Parse args early so dry-run works without API key
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("pdf", nargs="?", help="Path to a PDF to test with")
parser.add_argument("--dry-run", action="store_true", help="Skip API calls, validate structure only")
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Generate test PDF
# ---------------------------------------------------------------------------
from make_test_pdf import make_test_pdf

print("=== Generating test PDF ===")
pdf_bytes = make_test_pdf("test_coa.pdf")
if args.pdf:
    with open(args.pdf, "rb") as f:
        pdf_bytes = f.read()
    print(f"Using provided PDF: {args.pdf} ({len(pdf_bytes):,} bytes)")

# ---------------------------------------------------------------------------
# Dry run: validate imports, structure, and payload diff
# ---------------------------------------------------------------------------
if args.dry_run:
    print("\n=== DRY RUN — validating code paths ===")

    # Validate new parser imports cleanly
    from parser_files_api import extract_from_pdf, COAExtraction
    print("[OK] parser_files_api imports OK")

    # Validate old parser imports cleanly
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    from services.lab_report_parser import rasterize_pdf, extract_from_pdf as old_extract
    print("[OK] services.lab_report_parser imports OK")

    # Show what the new code would send
    import io
    print("\n--- New approach: what would be uploaded ---")
    print(f"  Upload payload size : {len(pdf_bytes):,} bytes (the raw PDF)")
    print(f"  Message payload     : ~200 bytes (just the file_id + text prompt)")
    print(f"  Total API calls     : 3 (upload + message + delete)")

    # Show what the old code sends
    print("\n--- Old approach: what is actually sent ---")
    pages = rasterize_pdf(pdf_bytes)
    import base64
    total_b64 = sum(len(p) for p in pages)
    print(f"  Pages rasterized    : {len(pages)}")
    for i, p in enumerate(pages):
        print(f"    Page {i+1} b64 size  : {len(p):,} bytes ({len(p)*3//4:,} raw bytes PNG)")
    print(f"  Total b64 bytes sent: {total_b64:,} bytes across {len(pages)} API calls")
    print(f"  Total API calls     : {len(pages)} (one per page)")

    # Payload ratio
    new_payload = len(pdf_bytes)
    old_payload = total_b64
    print(f"\n  Payload reduction   : {old_payload:,} → {new_payload:,} bytes "
          f"({(1 - new_payload/old_payload)*100:.0f}% smaller in message body)")

    print("\n[DRY RUN PASSED] Structure valid. Run without --dry-run to make API calls.")
    sys.exit(0)

# ---------------------------------------------------------------------------
# Live run
# ---------------------------------------------------------------------------
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY not set. Use --dry-run to test without API calls.")
    sys.exit(1)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from services.lab_report_parser import extract_from_pdf as old_extract, rasterize_pdf
from parser_files_api import extract_from_pdf as new_extract

results = {}

# --- Old approach ---
print("\n=== OLD: rasterize + per-page image calls ===")
t0 = time.perf_counter()
old_result = old_extract(pdf_bytes)
old_elapsed = time.perf_counter() - t0
results["old"] = {
    "elapsed_s": round(old_elapsed, 2),
    "terpenes": len(old_result.terpenes),
    "cannabinoids": len(old_result.cannabinoids),
    "confidence": old_result.confidence,
    "total_terpenes": old_result.total_terpenes,
    "lab_name": old_result.lab_name,
    "pass_fail": old_result.pass_fail,
}
print(json.dumps(results["old"], indent=2))

# --- New approach ---
print("\n=== NEW: Files API single-call ===")
t0 = time.perf_counter()
new_result = new_extract(pdf_bytes)
new_elapsed = time.perf_counter() - t0
results["new"] = {
    "elapsed_s": round(new_elapsed, 2),
    "terpenes": len(new_result.terpenes),
    "cannabinoids": len(new_result.cannabinoids),
    "confidence": new_result.confidence,
    "total_terpenes": new_result.total_terpenes,
    "lab_name": new_result.lab_name,
    "pass_fail": new_result.pass_fail,
}
print(json.dumps(results["new"], indent=2))

# --- Summary ---
print("\n=== COMPARISON ===")
print(f"{'Metric':<25} {'Old':>10} {'New':>10}")
print("-" * 47)
for k in ["elapsed_s", "terpenes", "cannabinoids", "confidence"]:
    print(f"{k:<25} {str(results['old'][k]):>10} {str(results['new'][k]):>10}")

old_pages = len(rasterize_pdf(pdf_bytes))
print(f"\nAPI calls (old)  : {old_pages} (one per page)")
print(f"API calls (new)  : 3 (upload + message + delete)")
print(f"Latency delta    : {results['new']['elapsed_s'] - results['old']['elapsed_s']:+.2f}s")

# Save results for demo.html
with open("results.json", "w") as f:
    json.dump({"old": results["old"], "new": results["new"],
               "old_api_calls": old_pages, "pdf_bytes": len(pdf_bytes)}, f, indent=2)
print("\nResults saved to results.json")
