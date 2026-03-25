# Anthropic Files API — Uploading PDFs via SDK

> Sprint question: Should the lab report parser upload PDFs using Anthropic's Files API instead of rasterizing pages and sending base64 images sequentially?

## Current Approach (r010)

`services/lab_report_parser.py` today:

1. PyMuPDF rasterizes each PDF page → 200 DPI PNG
2. PNG → base64 string
3. One `client.messages.create` call per page, using `type: "base64", media_type: "image/png"`
4. Results merged across pages via `_merge_extractions`

**N pages = N API calls. No text layer. Image-only.**

---

## Files API Approach

### Step 1 — Upload (r002, r003)

```python
import io
import anthropic

client = anthropic.Anthropic()

# pdf_bytes is the raw bytes from the uploaded file
response = client.beta.files.upload(
    file=("report.pdf", io.BytesIO(pdf_bytes), "application/pdf"),
)
file_id = response.id  # e.g. "file_011CNha8iCJcU1wXNR6q4V8w"
```

- All file operations live under `client.beta.files` (not `client.files`)
- Upload is **free** (r012)
- Returns an object with `.id`, `.filename`, `.size_bytes`, `.created_at`

### Step 2 — Send the PDF in a message (r003, r004)

```python
response = client.beta.messages.create(
    model="claude-haiku-4-5",
    max_tokens=1024,
    betas=["files-api-2025-04-14"],   # required (r001)
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ],
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "file",
                        "file_id": file_id,
                    },
                    # optional (r015):
                    # "title": "Cannabis COA",
                    # "context": "NY OCM lab report",
                    # "citations": {"enabled": True},
                },
                {
                    "type": "text",
                    "text": (
                        "Extract all terpene data and report metadata from this lab "
                        "report. Return only the JSON object as specified."
                    ),
                },
            ],
        }
    ],
)
```

**Single call. All pages. Text + image per page.**

### Step 3 — Clean up (r011)

```python
client.beta.files.delete(file_id)
```

---

## How Native PDF Processing Works (r007)

When a PDF is sent as a `document` block (regardless of whether via `file`, `base64`, or `url` source type):

1. Anthropic extracts the **text layer** from every page
2. Anthropic renders every page as an **image**
3. Claude receives both text + image for every page in the same call

Compare to the current approach: Claude only receives a rasterized image (no text layer). Text-heavy lab reports (tables with terpene names and values) benefit significantly from the text layer — Claude can read column headers and values directly rather than OCR-ing pixels.

---

## Three Ways to Send a PDF (r009)

| Source type | When to use | Payload cost |
|---|---|---|
| `"file"` (Files API) | Repeated use, large PDFs, batch processing | Tiny (just the ID) |
| `"base64"` | One-shot, no upload step wanted | Entire PDF in request body |
| `"url"` | PDF already publicly hosted | Just the URL |

For the lab report parser, `"file"` is best: the PDF is uploaded once, referenced by ID, then deleted.

---

## Limits (r006, r008)

| Dimension | Limit |
|---|---|
| Max file size | 500 MB per file |
| Total org storage | 500 GB |
| Max PDF pages | 600 per request (100 for 200k-context models) |
| Max request payload | 32 MB |
| File retention | Indefinite until deleted |
| Platform availability | Direct Anthropic API only — **not** Bedrock, **not** Vertex AI |

---

## Cost Tradeoff (r012)

| Approach | Token cost per page |
|---|---|
| Current (rasterized image) | Image tokens only |
| Files API native PDF | Image tokens **+** text tokens (~1,500–3,000/page) |

Token cost per page is higher with native PDF, but you get: better accuracy, fewer API calls, no PyMuPDF dependency, smaller request payloads.

---

## Risks (r014, r011)

- **Beta instability**: `files-api-2025-04-14` header signals beta status; contract may change before GA
- **Rate limit**: ~100 file API requests/minute — could bottleneck batch uploads
- **ZDR**: Files API is not ZDR-eligible. Orgs with Zero Data Retention requirements cannot use this beta feature
- **Platform lock-in**: Only works on direct Anthropic API (not Bedrock/Vertex)

---

## Migration Summary (r013)

**Remove:**
- `import fitz` / PyMuPDF dependency
- `rasterize_pdf()` function
- `_extract_from_page()` per-page loop
- `_merge_extractions()` merge logic

**Add:**
- `import io`
- `client.beta.files.upload(file=("report.pdf", io.BytesIO(pdf_bytes), "application/pdf"))`
- `client.beta.messages.create(..., betas=["files-api-2025-04-14"], ...)` with a single `document` block
- `client.beta.files.delete(file_id)` after extraction

**Result:** `extract_from_pdf` goes from N API calls + PyMuPDF rendering to 1 upload + 1 message + 1 delete.

---

## File Management Methods (r011 reference)

```python
# List all uploaded files
files = client.beta.files.list()

# Get file metadata
meta = client.beta.files.retrieve_metadata(file_id)

# Delete a file
client.beta.files.delete(file_id)
```

Files cannot be downloaded — only metadata can be retrieved for user-uploaded files.
