import { useEffect, useRef, useState } from 'react'
import api from './api/client'
import type { LabReport, LabReportResult, LabReportUpload, Product } from './types'

// ---------------------------------------------------------------------------
// Confidence badge
// ---------------------------------------------------------------------------
function ConfidenceBadge({ score }: { score: number }) {
  const color =
    score >= 4 ? '#1a7f37' : score === 3 ? '#9a6700' : '#cf222e'
  const bg =
    score >= 4 ? '#dafbe1' : score === 3 ? '#fff8c5' : '#ffebe9'
  const label =
    score >= 4 ? 'High' : score === 3 ? 'Medium' : 'Low'

  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: 12,
      fontSize: 13,
      fontWeight: 600,
      background: bg,
      color,
      border: `1px solid ${color}40`,
    }}>
      {label} confidence ({score}/5)
    </span>
  )
}

// ---------------------------------------------------------------------------
// Pass/Fail badge
// ---------------------------------------------------------------------------
function PassFailBadge({ value }: { value: string | null }) {
  if (!value) return <span style={{ opacity: 0.4 }}>—</span>
  const pass = value.toUpperCase() === 'PASS'
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: 12,
      fontSize: 13,
      fontWeight: 600,
      background: pass ? '#dafbe1' : '#ffebe9',
      color: pass ? '#1a7f37' : '#cf222e',
    }}>
      {value.toUpperCase()}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Terpene bar chart row
// ---------------------------------------------------------------------------
function TerpeneRow({ name, percent, max }: { name: string; percent: number; max: number }) {
  const pct = max > 0 ? (percent / max) * 100 : 0
  return (
    <tr>
      <td style={{ padding: '5px 8px', whiteSpace: 'nowrap' }}>{name}</td>
      <td style={{ padding: '5px 8px', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            height: 14,
            width: `${pct}%`,
            minWidth: 2,
            background: '#1f6feb',
            borderRadius: 3,
            transition: 'width 0.4s ease',
          }} />
        </div>
      </td>
      <td style={{ padding: '5px 8px', textAlign: 'right', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
        {percent.toFixed(3)}%
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Results panel for a single report
// ---------------------------------------------------------------------------
function ResultsPanel({ result }: { result: LabReportResult }) {
  const maxPct = Math.max(...result.terpenes.map(t => t.percent ?? 0), 0.001)
  const sorted = [...result.terpenes].sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))

  return (
    <div style={{ marginTop: 16 }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <ConfidenceBadge score={result.confidence} />
        <PassFailBadge value={result.pass_fail} />
        {result.applied_to_product && (
          <span style={{
            fontSize: 13,
            background: '#ddf4ff',
            color: '#0969da',
            padding: '2px 10px',
            borderRadius: 12,
            border: '1px solid #0969da40',
            fontWeight: 600,
          }}>
            Applied to product
          </span>
        )}
      </div>

      {result.confidence_notes && (
        <p style={{ fontSize: 13, color: '#9a6700', background: '#fff8c5', padding: '8px 12px', borderRadius: 6, marginBottom: 16 }}>
          ⚠ {result.confidence_notes}
        </p>
      )}

      {/* Metadata */}
      <table style={{ borderCollapse: 'collapse', marginBottom: 24, fontSize: 14 }}>
        <tbody>
          {[
            ['Lab', result.lab_name],
            ['License', result.lab_license],
            ['Test date', result.test_date],
            ['Batch / lot ID', result.batch_id],
            ['Product (on report)', result.product_name],
            ['Total terpenes', result.total_terpenes != null ? `${result.total_terpenes}%` : null],
          ].map(([label, value]) => (
            <tr key={String(label)}>
              <td style={{ padding: '4px 16px 4px 0', color: '#57606a', whiteSpace: 'nowrap' }}>{label}</td>
              <td style={{ padding: '4px 0', fontWeight: value ? 500 : 400, color: value ? 'inherit' : '#57606a' }}>
                {value ?? <span style={{ opacity: 0.4 }}>—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Terpene table */}
      {sorted.length === 0 ? (
        <p style={{ color: '#57606a' }}>No terpenes detected on this report.</p>
      ) : (
        <>
          <h4 style={{ margin: '0 0 10px', fontSize: 15 }}>
            Terpenes ({sorted.length}) — total {result.terpenes.reduce((s, t) => s + (t.percent ?? 0), 0).toFixed(3)}%
          </h4>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              {sorted.map(t => (
                <TerpeneRow
                  key={t.name}
                  name={t.name}
                  percent={t.percent ?? 0}
                  max={maxPct}
                />
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status badge for list view
// ---------------------------------------------------------------------------
function StatusBadge({ status }: { status: LabReport['status'] }) {
  const styles: Record<string, { bg: string; color: string }> = {
    pending:   { bg: '#fff8c5', color: '#9a6700' },
    extracted: { bg: '#ddf4ff', color: '#0969da' },
    applied:   { bg: '#dafbe1', color: '#1a7f37' },
    failed:    { bg: '#ffebe9', color: '#cf222e' },
  }
  const s = styles[status] ?? styles.pending
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: 12,
      fontSize: 12,
      fontWeight: 600,
      background: s.bg,
      color: s.color,
    }}>
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function LabReportUpload() {
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [products, setProducts] = useState<Product[]>([])
  const [productId, setProductId] = useState('')
  const [uploading, setUploading] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploaded, setUploaded] = useState<LabReportUpload[]>([])
  const [results, setResults] = useState<LabReportResult[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const [labReports, setLabReports] = useState<LabReport[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [listOffset, setListOffset] = useState(0)
  const LIST_LIMIT = 50

  function loadLabReports(offset = 0) {
    setListLoading(true)
    setListError(null)
    api.labReports.list({ limit: LIST_LIMIT, offset })
      .then(data => {
        setLabReports(prev => offset === 0 ? data : [...prev, ...data])
        setListOffset(offset)
      })
      .catch(err => setListError(err.message))
      .finally(() => setListLoading(false))
  }

  // Load product list for the selector
  useEffect(() => {
    api.products.list({ limit: 200 })
      .then(setProducts)
      .catch(() => { /* non-fatal */ })
    loadLabReports(0)
  }, [])

  function addFiles(newFiles: File[]) {
    const pdfs = newFiles.filter(f => f.name.toLowerCase().endsWith('.pdf'))
    const invalid = newFiles.filter(f => !f.name.toLowerCase().endsWith('.pdf'))
    if (invalid.length > 0) {
      setError(`Only PDF files are supported (skipped: ${invalid.map(f => f.name).join(', ')})`)
    } else {
      setError(null)
    }
    if (pdfs.length > 0) {
      setFiles(prev => {
        const existing = new Set(prev.map(f => f.name))
        return [...prev, ...pdfs.filter(f => !existing.has(f.name))]
      })
      setUploaded([])
      setResults([])
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) addFiles(Array.from(e.target.files))
    e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files) addFiles(Array.from(e.dataTransfer.files))
  }

  function removeFile(name: string) {
    setFiles(prev => prev.filter(f => f.name !== name))
    setUploaded([])
    setResults([])
  }

  async function handleUpload() {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    setUploaded([])
    setResults([])
    try {
      const res = await api.labReports.upload(files)
      setUploaded(res)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  async function handleProcess() {
    if (uploaded.length === 0) return
    setProcessing(true)
    setError(null)
    setResults([])
    try {
      const ids = uploaded.map(u => u.lab_report_id)
      const res = await api.labReports.process(ids, productId || undefined)
      setResults(res)
      loadLabReports(0)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setProcessing(false)
    }
  }

  const step = uploaded.length > 0 ? 2 : 1

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <h1 style={{ margin: '0 0 4px' }}>COA Lab Report Upload</h1>
      <p style={{ margin: '0 0 24px', color: '#57606a', fontSize: 14 }}>
        Upload NY cannabis Certificate of Analysis PDFs. Claude extracts terpene data via vision API.
      </p>

      {/* ── Step 1: select & upload files ── */}
      <div style={{
        padding: '16px 20px',
        border: '1px solid #d0d7de',
        borderRadius: 8,
        marginBottom: 16,
        background: step === 1 ? '#fff' : '#f6f8fa',
      }}>
        <h2 style={{ margin: '0 0 12px', fontSize: 16 }}>
          Step 1 — Upload PDFs
        </h2>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          style={{
            border: `2px dashed ${dragging ? '#1f6feb' : '#d0d7de'}`,
            borderRadius: 8,
            padding: '24px',
            textAlign: 'center',
            cursor: 'pointer',
            background: dragging ? '#f0f6ff' : '#f6f8fa',
            transition: 'all 0.15s',
            marginBottom: 12,
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,application/pdf"
            multiple
            style={{ display: 'none' }}
            onChange={onFileChange}
          />
          <div style={{ fontSize: 24, marginBottom: 4 }}>⬆</div>
          <div style={{ fontWeight: 500, fontSize: 14 }}>Drop PDFs here or click to browse</div>
          <div style={{ fontSize: 13, color: '#57606a', marginTop: 2 }}>Multiple files supported · Max 20 MB each</div>
        </div>

        {/* Selected files list */}
        {files.length > 0 && (
          <ul style={{ margin: '0 0 12px', padding: 0, listStyle: 'none' }}>
            {files.map(f => (
              <li key={f.name} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 10px', background: '#f6f8fa',
                borderRadius: 6, marginBottom: 4, fontSize: 14,
              }}>
                <span>📄</span>
                <span style={{ flex: 1 }}>{f.name}</span>
                <span style={{ color: '#57606a', fontSize: 12 }}>{(f.size / 1024).toFixed(1)} KB</span>
                {uploaded.length === 0 && (
                  <button
                    onClick={e => { e.stopPropagation(); removeFile(f.name) }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#cf222e', fontSize: 16, lineHeight: 1 }}
                  >×</button>
                )}
              </li>
            ))}
          </ul>
        )}

        {uploaded.length === 0 && (
          <button
            onClick={handleUpload}
            disabled={files.length === 0 || uploading}
            style={{
              padding: '8px 20px',
              fontSize: 14,
              fontWeight: 600,
              borderRadius: 6,
              border: 'none',
              background: files.length === 0 || uploading ? '#d0d7de' : '#1f6feb',
              color: files.length === 0 || uploading ? '#57606a' : '#fff',
              cursor: files.length === 0 || uploading ? 'not-allowed' : 'pointer',
            }}
          >
            {uploading ? 'Uploading…' : `Upload ${files.length > 0 ? `${files.length} file${files.length > 1 ? 's' : ''}` : 'Files'}`}
          </button>
        )}

        {/* Uploaded confirmation */}
        {uploaded.length > 0 && (
          <div style={{ fontSize: 13, color: '#1a7f37', background: '#dafbe1', padding: '8px 12px', borderRadius: 6 }}>
            ✓ {uploaded.length} file{uploaded.length > 1 ? 's' : ''} uploaded successfully
          </div>
        )}
      </div>

      {/* ── Step 2: process ── */}
      <div style={{
        padding: '16px 20px',
        border: `1px solid ${step === 2 ? '#d0d7de' : '#e8ecef'}`,
        borderRadius: 8,
        marginBottom: 16,
        background: step === 2 ? '#fff' : '#f6f8fa',
        opacity: step === 2 ? 1 : 0.6,
      }}>
        <h2 style={{ margin: '0 0 12px', fontSize: 16 }}>
          Step 2 — Extract Terpenes
        </h2>

        {/* Product selector */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 4, fontSize: 14, fontWeight: 500 }}>
            Apply terpenes to product <span style={{ fontWeight: 400, color: '#57606a' }}>(optional)</span>
          </label>
          <select
            value={productId}
            onChange={e => setProductId(e.target.value)}
            disabled={step !== 2 || processing}
            style={{ width: '100%', padding: '6px 10px', borderRadius: 6, border: '1px solid #d0d7de', fontSize: 14 }}
          >
            <option value="">— extract only, don't write to a product —</option>
            {products.map(p => (
              <option key={p.id} value={p.id}>
                {p.name}{p.brand ? ` — ${p.brand}` : ''} ({p.category})
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleProcess}
          disabled={step !== 2 || processing || results.length > 0}
          style={{
            padding: '8px 20px',
            fontSize: 14,
            fontWeight: 600,
            borderRadius: 6,
            border: 'none',
            background: step !== 2 || processing || results.length > 0 ? '#d0d7de' : '#1f6feb',
            color: step !== 2 || processing || results.length > 0 ? '#57606a' : '#fff',
            cursor: step !== 2 || processing || results.length > 0 ? 'not-allowed' : 'pointer',
          }}
        >
          {processing ? 'Analyzing COAs…' : 'Process Reports'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          marginTop: 16,
          padding: '10px 14px',
          background: '#ffebe9',
          color: '#cf222e',
          borderRadius: 6,
          fontSize: 14,
        }}>
          {error}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div style={{ marginTop: 24 }}>
          {results.map((r, i) => (
            <div key={r.lab_report_id} style={{
              border: '1px solid #d0d7de',
              borderRadius: 8,
              padding: '16px 20px',
              marginBottom: 16,
            }}>
              <h3 style={{ margin: '0 0 4px', fontSize: 15 }}>
                {uploaded[i]?.filename ?? `Report ${i + 1}`}
              </h3>
              <ResultsPanel result={r} />
            </div>
          ))}
        </div>
      )}

      {/* ── All lab reports list ── */}
      <div style={{ marginTop: 40 }}>
        <h2 style={{ margin: '0 0 16px', fontSize: 18 }}>All Lab Reports</h2>

        {listError && (
          <div style={{ padding: '10px 14px', background: '#ffebe9', color: '#cf222e', borderRadius: 6, fontSize: 14, marginBottom: 12 }}>
            {listError}
          </div>
        )}

        {!listError && labReports.length === 0 && !listLoading && (
          <p style={{ color: '#57606a', fontSize: 14 }}>No lab reports yet.</p>
        )}

        {labReports.length > 0 && (
          <table border={1} cellPadding={8} style={{ borderCollapse: 'collapse', width: '100%', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f6f8fa' }}>
                <th style={{ textAlign: 'left' }}>Date</th>
                <th style={{ textAlign: 'left' }}>Status</th>
                <th style={{ textAlign: 'left' }}>Lab</th>
                <th style={{ textAlign: 'left' }}>Product (on report)</th>
                <th style={{ textAlign: 'left' }}>Batch ID</th>
                <th style={{ textAlign: 'left' }}>Test date</th>
                <th style={{ textAlign: 'right' }}>Total terpenes</th>
                <th style={{ textAlign: 'left' }}>Pass/Fail</th>
                <th style={{ textAlign: 'left' }}>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {labReports.map(r => (
                <tr key={r.id}>
                  <td style={{ whiteSpace: 'nowrap', color: '#57606a' }}>
                    {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td><StatusBadge status={r.status} /></td>
                  <td>{r.lab_name ?? <span style={{ opacity: 0.4 }}>—</span>}</td>
                  <td>{r.product_name_on_report ?? <span style={{ opacity: 0.4 }}>—</span>}</td>
                  <td>{r.batch_id ?? <span style={{ opacity: 0.4 }}>—</span>}</td>
                  <td>{r.test_date ?? <span style={{ opacity: 0.4 }}>—</span>}</td>
                  <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {r.total_terpenes != null ? `${r.total_terpenes}%` : <span style={{ opacity: 0.4 }}>—</span>}
                  </td>
                  <td><PassFailBadge value={r.pass_fail} /></td>
                  <td>
                    {r.confidence != null
                      ? <ConfidenceBadge score={r.confidence} />
                      : <span style={{ opacity: 0.4 }}>—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {listLoading && (
          <p style={{ color: '#57606a', fontSize: 14, marginTop: 8 }}>Loading…</p>
        )}

        {!listLoading && labReports.length === LIST_LIMIT + listOffset && (
          <button
            onClick={() => loadLabReports(listOffset + LIST_LIMIT)}
            style={{
              marginTop: 12,
              padding: '6px 16px',
              fontSize: 14,
              borderRadius: 6,
              border: '1px solid #d0d7de',
              background: '#f6f8fa',
              cursor: 'pointer',
            }}
          >
            Load more
          </button>
        )}
      </div>
    </div>
  )
}
