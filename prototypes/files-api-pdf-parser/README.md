# Files API PDF Parser — Prototype

Replacement for `services/lab_report_parser.py` that uses the Anthropic Files API
instead of PyMuPDF rasterization + per-page base64 image calls.

## Quick start

```bash
# Dry run (no API key needed) — validates structure + measures payloads
python compare.py --dry-run

# Live run (needs ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
python compare.py

# Run against a real COA PDF
python compare.py /path/to/real_coa.pdf
```

## Files

| File | Purpose |
|---|---|
| `parser_files_api.py` | The new implementation — drop-in replacement for `extract_from_pdf` |
| `compare.py` | Side-by-side test: old vs new approach |
| `make_test_pdf.py` | Generates a synthetic COA PDF for testing |
| `results.json` | Dry-run results (payload sizes, structural validation) |
| `demo.html` | Visual explainer for stakeholders |

## What changed

```
REMOVED:
  import fitz  (PyMuPDF)
  rasterize_pdf()
  _extract_from_page()
  _merge_extractions()

ADDED:
  import io
  client.beta.files.upload(file=("report.pdf", io.BytesIO(pdf_bytes), "application/pdf"))
  client.beta.messages.create(..., betas=["files-api-2025-04-14"], ...)
  client.beta.files.delete(file_id)
```

## Key measurements (dry-run on 1-page synthetic COA)

| Metric | Old | New |
|---|---|---|
| Message payload | 197,132 bytes (base64 PNG) | ~200 bytes (file_id) |
| API calls | 1 per page | 3 always (upload+msg+delete) |
| PyMuPDF required | Yes | No |
| Text layer | No | Yes |

For a 3-page COA: old = 3 API calls + 591 KB payload; new = 3 API calls + 4.4 KB payload.
