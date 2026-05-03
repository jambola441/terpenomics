import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from './api/client'
import type { LabReport, LabReportResult, LabReportUpload, Product } from './types'

// ---------------------------------------------------------------------------
// Confidence badge
// ---------------------------------------------------------------------------
function ConfidenceBadge({ score }: { score: number }) {
  const color = score >= 4 ? '#86efac' : score === 3 ? '#fcd34d' : '#fca5a5'
  const bg    = score >= 4 ? '#14532d' : score === 3 ? '#451a03' : '#450a0a'
  const label = score >= 4 ? 'High'   : score === 3 ? 'Medium'  : 'Low'
  return (
    <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 13, fontWeight: 600, background: bg, color, border: `1px solid ${color}30` }}>
      {label} confidence ({score}/5)
    </span>
  )
}

function PassFailBadge({ value }: { value: string | null }) {
  if (!value) return <span style={{ color: '#475569' }}>—</span>
  const pass = value.toUpperCase() === 'PASS'
  return (
    <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 13, fontWeight: 600, background: pass ? '#14532d' : '#450a0a', color: pass ? '#86efac' : '#fca5a5' }}>
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
    pending:   { bg: '#451a03', color: '#fcd34d' },
    extracted: { bg: '#0c1a2e', color: '#93c5fd' },
    applied:   { bg: '#14532d', color: '#86efac' },
    failed:    { bg: '#450a0a', color: '#fca5a5' },
  }
  const s = styles[status] ?? styles.pending
  return (
    <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600, background: s.bg, color: s.color }}>
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function LabReportUpload() {
  const navigate = useNavigate()
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [products, setProducts] = useState<Product[]>([])
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

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [listProcessing, setListProcessing] = useState(false)
  const [listResults, setListResults] = useState<LabReportResult[]>([])

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
      const res = await api.labReports.process(ids)
      setResults(res)
      loadLabReports(0)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setProcessing(false)
    }
  }

  const step = uploaded.length > 0 ? 2 : 1

  const pendingIds = labReports.filter(r => r.status === 'pending').map(r => r.id)
  const allPendingSelected = pendingIds.length > 0 && pendingIds.every(id => selectedIds.has(id))

  function toggleSelectAll() {
    if (allPendingSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(pendingIds))
    }
  }

  function toggleSelected(id: string) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleListProcess() {
    if (selectedIds.size === 0) return
    setListProcessing(true)
    setListResults([])
    try {
      const ids: string[] = Array.from(selectedIds)
      const res = await api.labReports.process(ids)
      setListResults(res)
      setSelectedIds(new Set())
      loadLabReports(0)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setListProcessing(false)
    }
  }

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Lab Reports</h2>
            <p style={{ margin: '3px 0 0', fontSize: 13, color: '#475569' }}>Upload COA PDFs — Claude extracts terpene data via vision API</p>
          </div>
        </div>

        {/* Step 1 */}
        <div style={{ padding: '16px 20px', border: '1px solid #1e293b', borderRadius: 8, marginBottom: 12, background: '#0a0f1a' }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 15, color: '#94a3b8', fontWeight: 500 }}>Step 1 — Upload PDFs</h3>

          <div
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            style={{
              border: `2px dashed ${dragging ? '#6366f1' : '#1e293b'}`,
              borderRadius: 8, padding: 24, textAlign: 'center', cursor: 'pointer',
              background: dragging ? '#0f172a' : 'transparent', transition: 'all 0.15s', marginBottom: 12,
            }}
          >
            <input ref={inputRef} type="file" accept=".pdf,application/pdf" multiple style={{ display: 'none' }} onChange={onFileChange} />
            <div style={{ fontSize: 22, marginBottom: 4 }}>⬆</div>
            <div style={{ fontWeight: 500, fontSize: 14, color: '#cbd5e1' }}>Drop PDFs here or click to browse</div>
            <div style={{ fontSize: 13, color: '#475569', marginTop: 2 }}>Multiple files supported · Max 20 MB each</div>
          </div>

          {files.length > 0 && (
            <ul style={{ margin: '0 0 12px', padding: 0, listStyle: 'none' }}>
              {files.map(f => (
                <li key={f.name} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, marginBottom: 4, fontSize: 13 }}>
                  <span>📄</span>
                  <span style={{ flex: 1, color: '#cbd5e1' }}>{f.name}</span>
                  <span style={{ color: '#475569', fontSize: 12 }}>{(f.size / 1024).toFixed(1)} KB</span>
                  {uploaded.length === 0 && (
                    <button onClick={e => { e.stopPropagation(); removeFile(f.name) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569', fontSize: 16, lineHeight: 1 }}>×</button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {uploaded.length === 0 && (
            <button
              onClick={handleUpload}
              disabled={files.length === 0 || uploading}
              style={{ padding: '8px 20px', fontSize: 14, fontWeight: 600, borderRadius: 6, border: 'none', background: files.length === 0 || uploading ? '#1e293b' : '#4f46e5', color: files.length === 0 || uploading ? '#475569' : '#fff', cursor: files.length === 0 || uploading ? 'not-allowed' : 'pointer' }}
            >
              {uploading ? 'Uploading…' : `Upload ${files.length > 0 ? `${files.length} file${files.length > 1 ? 's' : ''}` : 'Files'}`}
            </button>
          )}

          {uploaded.length > 0 && (
            <div style={{ fontSize: 13, color: '#86efac', background: '#14532d30', padding: '8px 12px', borderRadius: 6, border: '1px solid #14532d' }}>
              ✓ {uploaded.length} file{uploaded.length > 1 ? 's' : ''} uploaded successfully
            </div>
          )}
        </div>

        {/* Step 2 */}
        <div style={{ padding: '16px 20px', border: '1px solid #1e293b', borderRadius: 8, marginBottom: 16, background: '#0a0f1a', opacity: step === 2 ? 1 : 0.5 }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 15, color: '#94a3b8', fontWeight: 500 }}>Step 2 — Extract Terpenes</h3>
          <button
            onClick={handleProcess}
            disabled={step !== 2 || processing || results.length > 0}
            style={{ padding: '8px 20px', fontSize: 14, fontWeight: 600, borderRadius: 6, border: 'none', background: step !== 2 || processing || results.length > 0 ? '#1e293b' : '#4f46e5', color: step !== 2 || processing || results.length > 0 ? '#475569' : '#fff', cursor: step !== 2 || processing || results.length > 0 ? 'not-allowed' : 'pointer' }}
          >
            {processing ? 'Analyzing COAs…' : 'Process Reports'}
          </button>
        </div>

        {error && <div style={{ marginBottom: 16, padding: '10px 14px', background: '#450a0a', color: '#fca5a5', borderRadius: 6, fontSize: 14 }}>{error}</div>}

        {results.length > 0 && (
          <div style={{ marginBottom: 32 }}>
            {results.map((r, i) => (
              <div key={r.lab_report_id} style={{ border: '1px solid #1e293b', borderRadius: 8, padding: '16px 20px', marginBottom: 12, background: '#0a0f1a' }}>
                <h3 style={{ margin: '0 0 4px', fontSize: 15, color: '#f1f5f9' }}>{uploaded[i]?.filename ?? `Report ${i + 1}`}</h3>
                <ResultsPanel result={r} />
              </div>
            ))}
          </div>
        )}

        {/* All lab reports */}
        <div style={{ marginTop: 40 }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 17, fontWeight: 600 }}>All Lab Reports</h3>

          {listError && <div style={{ padding: '10px 14px', background: '#450a0a', color: '#fca5a5', borderRadius: 6, fontSize: 14, marginBottom: 12 }}>{listError}</div>}
          {!listError && labReports.length === 0 && !listLoading && <p style={{ color: '#475569', fontSize: 14 }}>No lab reports yet.</p>}

          {labReports.length > 0 && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12, padding: '10px 14px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6 }}>
                <span style={{ fontSize: 13, color: '#94a3b8', minWidth: 120 }}>
                  {selectedIds.size > 0 ? `${selectedIds.size} selected` : 'Select pending reports to process'}
                </span>
                <button
                  onClick={handleListProcess}
                  disabled={selectedIds.size === 0 || listProcessing}
                  style={{ padding: '6px 18px', fontSize: 13, fontWeight: 600, borderRadius: 6, border: 'none', background: selectedIds.size === 0 || listProcessing ? '#1e293b' : '#4f46e5', color: selectedIds.size === 0 || listProcessing ? '#475569' : '#fff', cursor: selectedIds.size === 0 || listProcessing ? 'not-allowed' : 'pointer', whiteSpace: 'nowrap' }}
                >
                  {listProcessing ? 'Analyzing COAs…' : 'Process Selected'}
                </button>
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                    <th style={{ width: 36, padding: '8px', textAlign: 'center' }}>
                      <input type="checkbox" title="Select all pending" checked={allPendingSelected} disabled={pendingIds.length === 0} onChange={toggleSelectAll} />
                    </th>
                    <th style={thStyle}>Date</th>
                    <th style={thStyle}>Status</th>
                    <th style={thStyle}>Lab</th>
                    <th style={thStyle}>Assigned Product</th>
                    <th style={thStyle}>Product on Report</th>
                    <th style={thStyle}>Batch ID</th>
                    <th style={thStyle}>Test Date</th>
                    <th style={{ ...thStyle, textAlign: 'right' }}>Total Terpenes</th>
                    <th style={thStyle}>Pass/Fail</th>
                    <th style={thStyle}>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const productMap = new Map(products.map(p => [p.id, p]))
                    return labReports.map(r => {
                      const canSelect = r.status === 'pending'
                      const isSelected = selectedIds.has(r.id)
                      const assignedProduct = r.product_id ? productMap.get(r.product_id) : undefined
                      return (
                        <tr
                          key={r.id}
                          style={{ borderBottom: '1px solid #0f172a', cursor: 'pointer', background: isSelected ? '#0c1a2e' : 'transparent' }}
                          onClick={() => navigate(`/admin/lab-reports/${r.id}`)}
                          onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLTableRowElement).style.background = '#0a0f1a' }}
                          onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLTableRowElement).style.background = 'transparent' }}
                        >
                          <td style={{ textAlign: 'center', padding: '10px 8px' }} onClick={e => e.stopPropagation()}>
                            <input type="checkbox" checked={isSelected} disabled={!canSelect || listProcessing} title={canSelect ? undefined : 'Only pending reports can be processed'} onChange={() => toggleSelected(r.id)} />
                          </td>
                          <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}</td>
                          <td style={tdStyle}><StatusBadge status={r.status} /></td>
                          <td style={tdStyle}>{r.lab_name ?? <span style={{ color: '#475569' }}>—</span>}</td>
                          <td style={{ ...tdStyle, color: '#f1f5f9' }}>{assignedProduct ? assignedProduct.name : <span style={{ color: '#475569' }}>—</span>}</td>
                          <td style={tdStyle}>{r.product_name_on_report ?? <span style={{ color: '#475569' }}>—</span>}</td>
                          <td style={tdStyle}>{r.batch_id ?? <span style={{ color: '#475569' }}>—</span>}</td>
                          <td style={tdStyle}>{r.test_date ?? <span style={{ color: '#475569' }}>—</span>}</td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                            {r.total_terpenes != null ? `${r.total_terpenes}%` : <span style={{ color: '#475569' }}>—</span>}
                          </td>
                          <td style={tdStyle}><PassFailBadge value={r.pass_fail} /></td>
                          <td style={tdStyle}>{r.confidence != null ? <ConfidenceBadge score={r.confidence} /> : <span style={{ color: '#475569' }}>—</span>}</td>
                        </tr>
                      )
                    })
                  })()}
                </tbody>
              </table>

              {listResults.length > 0 && (
                <div style={{ marginTop: 24 }}>
                  <h3 style={{ margin: '0 0 12px', fontSize: 15, color: '#94a3b8' }}>Processing Results</h3>
                  {listResults.map(r => (
                    <div key={r.lab_report_id} style={{ border: '1px solid #1e293b', borderRadius: 8, padding: '16px 20px', marginBottom: 12, background: '#0a0f1a' }}>
                      <h4 style={{ margin: '0 0 4px', fontSize: 14, color: '#94a3b8' }}>{r.lab_report_id}</h4>
                      <ResultsPanel result={r} />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {listLoading && <p style={{ color: '#475569', fontSize: 14, marginTop: 8 }}>Loading…</p>}

          {!listLoading && labReports.length === LIST_LIMIT + listOffset && (
            <button onClick={() => loadLabReports(listOffset + LIST_LIMIT)} style={{ ...navBtnStyle, marginTop: 12 }}>
              Load more
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
