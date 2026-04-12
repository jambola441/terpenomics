# Decision Brief: Lab Report Parser — Files API Migration & CheckWeedNY Integration

**Date**: 2026-04-12 | **Audience**: engineers | **Phase**: Compiled

---

## Executive Summary

Migrate the COA lab report parser to use the Anthropic Files API (upload + single `document` block) instead of per-page base64 image batching — this has shipped as a working prototype with extraction parity confirmed. In parallel, integrate the CheckWeedNY API as a "lookup first" layer: use `?batch=<batch_id>` as the primary key, falling back to `?brand=&product=`, and skip Claude entirely for records with `parse_confidence >= 0.7` and `terpene_count > 0`. A bulk-sync script prototype exists to backfill existing products. Two open risks — terpene name normalization and the 28% confidence miss rate on flowers — require attention before production rollout.

---

## Recommendation

### 1. Ship the Files API migration (ready now)

Replace `services/lab_report_parser.py` with the Files API approach (r013):

1. Remove PyMuPDF rasterization entirely (`rasterize_pdf`, `_extract_from_page`, `_merge_extraction` — ~60 lines removed, p003)
2. Upload raw PDF bytes via `client.beta.files.upload(file=("report.pdf", BytesIO(pdf_bytes), "application/pdf"))` (r002)
3. Send ONE `client.beta.messages.create` call with a `document` block, `source.type = "file"`, `file_id = upload.id` (r003, r016)
4. Delete the file in the `finally` block (r002)
5. Retain all Pydantic models unchanged (p001)

**Caveats**:
- Add `betas=["files-api-2025-04-14"]` to the messages call (r001, r016)
- Files API is beta — not eligible for ZDR (r011), ~100 req/min rate limit (r004)
- 1-page latency is ~0.9s worse (6.01s vs 5.08s, p006); crossover to faster occurs at 2+ pages where the old approach fires an early exit (x001, x002)

### 2. Integrate CheckWeedNY as a lookup-first layer

Before invoking the Claude parser, attempt a CheckWeedNY lookup:

```
1. If product has a LabReport with batch_id:
      GET /v1/coas?batch=<batch_id>
      → 1 exact result (x004)

2. Else if product.brand is set:
      GET /v1/coas?brand=<brand>&product=<name>
      → pick highest parse_confidence with terpene_count > 0

3. If found AND parse_confidence >= 0.7 AND terpene_count > 0:
      GET /v1/coas/<id>   → terpenes[{compound, value_pct}]
      → map to ProductTerpene, skip Claude entirely

4. If found but terpene_count = 0 AND pdf_url is set:
      Download pdf_url → run through Files API parser
      → saves user from uploading manually

5. Miss / low confidence → existing upload+parse flow unchanged
```

Auth: `X-API-Key` header (r019). All filter params (`?batch=`, `?brand=`, `?product=`, `?lab=`) are partial, case-insensitive (r029).

### 3. Run the bulk-sync script to backfill existing products

`prototypes/checkweedny-bulk-sync/sync.py` implements the above flow as a standalone script:

```bash
python sync.py --write --skip-existing   # backfill, don't overwrite existing terpenes
python sync.py --write --brand "Ayrloom" # target a single brand first as a test
```

Before running at scale, resolve the normalization gap (see Risks).

---

## Evidence Summary

### Files API — core mechanics

- **Upload method** (r002, documented): `client.beta.files.upload(file=("document.pdf", open(...), "application/pdf"))` returns a `file_id`.
- **Message reference** (r003, r016, documented): Use `client.beta.messages.create(..., betas=["files-api-2025-04-14"])` with `content: [{type: "document", source: {type: "file", file_id: ...}}]`.
- **Model support** (r006, documented): All models supporting the file type can use file_id references. PDFs require a model with native PDF support (claude-haiku-4-5 and above).
- **Mechanism** (r007, documented): Anthropic extracts text from each page and converts each page to an image — identical to what the old rasterization loop did manually.
- **Limits** (r004, r008, documented): 500 MB/file, 600 pages/request (100 for base64), ~100 req/min (beta), 32 MB request payload cap.
- **Billing** (r012, documented): Upload/download/list/delete operations are free. File content in messages is billed as input tokens identically to inline content.
- **Beta constraints** (r011, r014, documented): Not ZDR-eligible. Breaking changes possible before GA.

### Files API — prototype results

- **Payload reduction** (p002, tested): 1-page COA, 1,466-byte PDF → current approach sends 147,849 bytes (base64 PNG); Files API sends 1,977 bytes at message time. 99% payload reduction per call.
- **Extraction parity** (p005, tested): Identical results on a live 1-page COA — 10 terpenes, 8 cannabinoids, same confidence score.
- **Latency** (p006, x001, x002, tested): 1-page: +0.93s (new is slower). Crossover at 2+ pages because old approach exits early on the first page that yields terpenes. New approach always processes the whole PDF in 1 call.
- **Code reduction** (p003, tested): Removes 3 functions (~60 lines). No new dependencies.
- **API call count** (p004, tested): Old = 1 call. New = 3 calls (upload + messages + delete). For multi-page PDFs where old approach would make N page calls, new approach is still 3 calls — net reduction.

### CheckWeedNY API

- **Dataset** (r018, tested): 32,518 COAs, 671 clients, 532 brands, 26 labs. Spans 2008–April 2026.
- **Filter params** (r029, x003, tested): `?batch=`, `?brand=`, `?product=`, `?lab=` all work. Partial, case-insensitive. `?batch=` returns exactly 1 result for a full batch string (x004).
- **List schema** (r020, tested): Each record includes `id`, `brand_name`, `product_name`, `batch_number`, `terpene_count`, `parse_confidence`, `pdf_url`, inline cannabinoid pct fields, pass/fail booleans.
- **Detail schema** (r021, tested): Adds `terpenes: [{compound, value_pct}]`, `pesticides`, `solvents`, `heavy_metals`, `microbials`, `mycotoxins` nested arrays.
- **parse_confidence** (r025, tested): 0.0–1.0. Values ≥ 0.7 are reliable for direct use. Values ≤ 0.5 indicate garbled extraction; fall back to Claude.
- **pdf_url** (r024, tested): Present on every record. Can be fetched and piped into the Files API parser for records with good confidence but no terpene data.
- **Terpene coverage** (r022, tested): Flower and concentrate records typically have terpene data. In the Ayrloom sample (393 COAs), all 5 sampled records had `terpene_count > 0`.

### Bulk sync prototype

- **Lookup logic** (p007, p009, tested): Batch-first, brand+product fallback. Dry-run by default. Flags: `--write`, `--skip-existing`, `--product-id`, `--brand`, `--min-confidence`.
- **Normalization** (p008, tested): 30-entry map converts API names to canonical names. Unmapped names pass through as-is.

---

## Tradeoffs and Risks

| Risk | Evidence | Severity | Mitigation |
|---|---|---|---|
| **Files API beta instability** (r014) | documented | Medium | Pin the beta header string; monitor Anthropic changelog before GA |
| **1-page latency regression** (p006, x002) | tested | Low | Most COAs are multi-page; 1-page case is rare in production |
| **Not ZDR-eligible** (r011) | documented | Medium | Assess with legal/compliance if ZDR is a customer requirement |
| **28% confidence miss rate on flowers** (x005) | tested | Medium | 14/50 sampled flower COAs had `parse_confidence < 0.7` — these fall back to Claude, providing no API benefit |
| **~2% null batch_number** (x006) | tested | Low | Products without a linked LabReport can only be found by brand+name; acceptable fallback to Claude |
| **Terpene name normalization gap** (x007, p008) | tested | Medium | Prototype has 30-entry map but unmapped names silently create duplicates across API-sourced and Claude-sourced records. Expand the map or add a post-write deduplication pass before production rollout |
| **Ingestibles/tinctures/topicals coverage** (r028) | tested | Low | `terpene_count = null` for these categories — CheckWeedNY provides no benefit; they always fall through to Claude |
| **Brand name exact matching** (r027) | tested | Low | All filter params are partial+case-insensitive (r029), so partial brand names work; verify brand strings in the products table match CheckWeedNY's `brand_name` format |

---

## Resolved Conflicts

### x004 supersedes r026 step 1

**What disagreed**: r026 (recommendation) described the primary lookup as "search by brand (required) + paginate through results to match by batch_number client-side." x004 (challenge) showed this was wrong — `?batch=<batch_number>` returns exactly 1 result directly, no brand filter needed, no client-side scanning.

**How resolved**: Both claims were `tested` tier. Manual adjudication favored x004 because x003 had already confirmed `?batch=` works, and x004 is a narrower, more specific factual finding that directly contradicts an untested assumption in r026 step 1.

**Winner**: x004. The correct primary lookup is `GET /v1/coas?batch=<batch_number>`.

---

## Appendix: Claim Inventory

| ID | Type | Topic | Evidence | Content (truncated) |
|---|---|---|---|---|
| d001 | constraint | done-criteria | stated | Done looks like: Decision-ready brief with evidence |
| r001 | factual | files-api-beta-header | documented | Files API requires beta header `anthropic-beta: files-api-2025-04-14` |
| r002 | factual | files-api-upload-sdk-method | documented | Python SDK: `client.beta.files.upload(file=("document.pdf", open(...), "application/pdf"))` |
| r003 | factual | files-api-message-reference | documented | Reference uploaded PDF via `document` block with `source.type = "file"` |
| r004 | factual | files-api-limits | documented | 500 MB/file, 600 pages/request, ~100 req/min (beta) |
| r005 | factual | files-api-supported-types | documented | PDF → document block; plain text → document block; images → image block |
| r006 | factual | files-api-model-support | documented | file_id references supported in all models that support the given file type |
| r007 | factual | native-pdf-support-mechanism | documented | Anthropic extracts text + converts each page to image — same as manual rasterization |
| r008 | factual | pdf-limits | documented | Max 600 pages/request (100 for base64), 32 MB request payload cap |
| r009 | factual | pdf-three-source-options | documented | Three source types: `url`, `base64`, `file` (file_id) |
| r010 | factual | current-parser-approach | documented | Current parser uses PyMuPDF at 200 DPI, sends each page as base64 PNG sequentially |
| r011 | factual | files-api-not-zdr | documented | Files API is NOT eligible for Zero Data Retention |
| r012 | factual | files-api-billing | documented | Upload/list/delete are free; file content in messages billed as input tokens |
| r013 | recommendation | migration-approach | documented | Migration: remove PyMuPDF, upload PDF, send document block, delete after |
| r014 | risk | files-api-beta-instability | documented | Beta API — breaking changes possible before GA |
| r015 | factual | document-block-optional-fields | documented | `document` block supports optional `title` and `context` fields |
| r016 | factual | files-api-message-sdk-path | documented | Must use `client.beta.messages.create` (not `client.messages.create`) with files-api beta |
| r017 | factual | messages-sdk-path-distinction | documented | `client.messages.create` vs `client.beta.messages.create` depends on source type used |
| r018 | factual | checkweedny-dataset-scale | tested | 32,518 COAs, 671 clients, 532 brands, 26 labs |
| r019 | factual | checkweedny-auth | tested | Auth via `X-API-Key` header; base URL `https://api.checkweedny.com/v1` |
| r020 | factual | checkweedny-list-schema | tested | List schema: id, brand_name, batch_number, terpene_count, parse_confidence, pdf_url, cannabinoid pcts |
| r021 | factual | checkweedny-detail-schema | tested | Detail adds: terpenes[], pesticides[], solvents[], heavy_metals{}, microbials{}, mycotoxins{} |
| r022 | factual | checkweedny-terpene-coverage | tested | Flower/concentrate records have terpene data; ingestibles/tinctures/topicals do not |
| r024 | factual | checkweedny-pdf-url | tested | `pdf_url` present on every COA record |
| r025 | factual | checkweedny-parse-confidence | tested | parse_confidence 0.0–1.0; ≥0.7 reliable; ≤0.5 garbled |
| r027 | risk | checkweedny-filter-limitation | tested | Partial risk: brand is not the only filter; all short params work (r029 supersedes original claim) |
| r028 | risk | checkweedny-terpene-gap | tested | Terpenes null for ingestibles/tinctures/topicals/beverages |
| r029 | factual | checkweedny-filter-params | tested | `?brand=`, `?batch=`, `?product=`, `?lab=` all work; partial, case-insensitive |
| x003 | factual | checkweedny-filter-params | tested | Short param names work (`?batch=`, not `?batch_number=`) |
| x004 | factual | checkweedny-integration-strategy | tested | `?batch=<batch_number>` returns exactly 1 result; no brand filter needed |
| x005 | risk | checkweedny-integration-strategy | tested | 28% miss rate: 14/50 flower COAs had parse_confidence < 0.7 |
| x006 | risk | checkweedny-integration-strategy | tested | ~2% of COAs have null batch_number — cannot be found by ?batch= |
| x007 | risk | checkweedny-integration-strategy | tested | API terpene names differ from canonical (e.g. "Alpha-Pinene" vs "α-Pinene") |
| p001 | factual | prototype-structural-validation | tested | Files API parser imports cleanly; Pydantic models reused unchanged |
| p002 | factual | payload-size-reduction | tested | 1-page COA: current sends 147,849-byte base64 PNG; Files API sends 1,977 bytes |
| p003 | factual | code-reduction | tested | Removes 3 functions (~60 lines); no new dependencies |
| p004 | factual | api-call-count-tradeoff | tested | Old = 1 call; New = 3 calls (upload + messages + delete) |
| p005 | factual | extraction-quality-parity | tested | Identical extraction results on live 1-page COA |
| p006 | factual | latency-1-page | tested | 1-page: old 5.08s, new 6.01s (+0.93s); crossover at 2+ pages |
| x001 | factual | latency-1-page | tested | Old parser exits early at page 1 for single-page COAs (1 API call total) |
| x002 | factual | latency-1-page | tested | Latency crossover occurs at 2+ page COAs where old approach would make N calls |
| p007 | factual | checkweedny-bulk-sync-design | tested | Prototype sync.py: batch-first lookup, brand+product fallback, confidence threshold gate |
| p008 | factual | checkweedny-terpene-normalization | tested | 30-entry normalization map; unmapped names pass through as-is (silent duplicate risk) |
| p009 | factual | checkweedny-bulk-sync-design | tested | CLI flags: --write, --skip-existing, --product-id, --brand, --min-confidence |

---

*Compilation certificate: sha256:37dd67b2ca62bf488cce28b0e1d449c953f05067c63689012971a74312fa3c28 | Compiler: wheat v0.2.0 | Claims: 44 active | Compiled: 2026-04-12T21:31:16.732Z*
