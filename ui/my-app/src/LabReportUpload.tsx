import { useEffect, useRef, useState } from 'react'
import api from './api/client'
import type { LabReportResult, Product } from './types'

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
// Results panel
// ---------------------------------------------------------------------------
function ResultsPanel({ result }: { result: LabReportResult }) {
  const maxPct = Math.max(...result.terpenes.map(t => t.percent ?? 0), 0.001)
  const sorted = [...result.terpenes].sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))

  return (
    <div style={{ marginTop: 28 }}>
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
          <h3 style={{ margin: '0 0 10px', fontSize: 15 }}>
            Terpenes ({sorted.length}) — total {result.terpenes.reduce((s, t) => s + (t.percent ?? 0), 0).toFixed(3)}%
          </h3>
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
// Main page
// ---------------------------------------------------------------------------
export default function LabReportUpload() {
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [products, setProducts] = useState<Product[]>([])
  const [productId, setProductId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<LabReportResult | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Load product list for the selector
  useEffect(() => {
    api.products.list({ limit: 200 })
      .then(setProducts)
      .catch(() => { /* non-fatal */ })
  }, [])

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null
    if (f) pick(f)
  }

  function pick(f: File) {
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported.')
      return
    }
    setFile(f)
    setResult(null)
    setError(null)
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) pick(f)
  }

  async function handleUpload() {
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.labReports.upload(file, productId || undefined)
      setResult(res)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <h1 style={{ margin: '0 0 4px' }}>COA Lab Report Upload</h1>
      <p style={{ margin: '0 0 24px', color: '#57606a', fontSize: 14 }}>
        Upload a NY cannabis Certificate of Analysis PDF. Claude extracts terpene data via vision API.
      </p>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? '#1f6feb' : '#d0d7de'}`,
          borderRadius: 8,
          padding: '32px 24px',
          textAlign: 'center',
          cursor: 'pointer',
          background: dragging ? '#f0f6ff' : '#f6f8fa',
          transition: 'all 0.15s',
          marginBottom: 16,
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          style={{ display: 'none' }}
          onChange={onFileChange}
        />
        {file ? (
          <div>
            <div style={{ fontSize: 28, marginBottom: 6 }}>📄</div>
            <strong>{file.name}</strong>
            <div style={{ fontSize: 13, color: '#57606a', marginTop: 4 }}>
              {(file.size / 1024).toFixed(1)} KB — click or drop to replace
            </div>
          </div>
        ) : (
          <div>
            <div style={{ fontSize: 28, marginBottom: 6 }}>⬆</div>
            <div style={{ fontWeight: 500 }}>Drop a PDF here or click to browse</div>
            <div style={{ fontSize: 13, color: '#57606a', marginTop: 4 }}>Max 20 MB</div>
          </div>
        )}
      </div>

      {/* Product selector */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', marginBottom: 4, fontSize: 14, fontWeight: 500 }}>
          Apply terpenes to product <span style={{ fontWeight: 400, color: '#57606a' }}>(optional)</span>
        </label>
        <select
          value={productId}
          onChange={e => setProductId(e.target.value)}
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

      {/* Upload button */}
      <button
        onClick={handleUpload}
        disabled={!file || loading}
        style={{
          padding: '8px 20px',
          fontSize: 14,
          fontWeight: 600,
          borderRadius: 6,
          border: 'none',
          background: !file || loading ? '#d0d7de' : '#1f6feb',
          color: !file || loading ? '#57606a' : '#fff',
          cursor: !file || loading ? 'not-allowed' : 'pointer',
        }}
      >
        {loading ? 'Analyzing COA…' : 'Upload & Extract'}
      </button>

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
      {result && <ResultsPanel result={result} />}
    </div>
  )
}
