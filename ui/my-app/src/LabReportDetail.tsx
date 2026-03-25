import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import api from './api/client'
import type { LabReportDetail, LabReportResult, Product } from './types'
import { ProductSearch } from './components/ProductSearch'

// ---------------------------------------------------------------------------
// Shared badge components
// ---------------------------------------------------------------------------
function ConfidenceBadge({ score }: { score: number }) {
  const color = score >= 4 ? '#1a7f37' : score === 3 ? '#9a6700' : '#cf222e'
  const bg = score >= 4 ? '#dafbe1' : score === 3 ? '#fff8c5' : '#ffebe9'
  const label = score >= 4 ? 'High' : score === 3 ? 'Medium' : 'Low'
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 12,
      fontSize: 13, fontWeight: 600, background: bg, color,
      border: `1px solid ${color}40`,
    }}>
      {label} confidence ({score}/5)
    </span>
  )
}

function PassFailBadge({ value }: { value: string | null }) {
  if (!value) return <span style={{ opacity: 0.4 }}>—</span>
  const pass = value.toUpperCase() === 'PASS'
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 12,
      fontSize: 13, fontWeight: 600,
      background: pass ? '#dafbe1' : '#ffebe9',
      color: pass ? '#1a7f37' : '#cf222e',
    }}>
      {value.toUpperCase()}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, { bg: string; color: string }> = {
    pending:   { bg: '#fff8c5', color: '#9a6700' },
    extracted: { bg: '#ddf4ff', color: '#0969da' },
    applied:   { bg: '#dafbe1', color: '#1a7f37' },
    failed:    { bg: '#ffebe9', color: '#cf222e' },
  }
  const s = styles[status] ?? styles.pending
  return (
    <span style={{
      display: 'inline-block', padding: '3px 12px', borderRadius: 12,
      fontSize: 13, fontWeight: 600, background: s.bg, color: s.color,
    }}>
      {status}
    </span>
  )
}

function TerpeneRow({ name, percent, max }: { name: string; percent: number; max: number }) {
  const pct = max > 0 ? (percent / max) * 100 : 0
  return (
    <tr>
      <td style={{ padding: '5px 8px', whiteSpace: 'nowrap' }}>{name}</td>
      <td style={{ padding: '5px 8px', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            height: 14, width: `${pct}%`, minWidth: 2,
            background: '#1f6feb', borderRadius: 3, transition: 'width 0.4s ease',
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
// Main page
// ---------------------------------------------------------------------------
export default function LabReportDetailPage() {
  const { reportId } = useParams<{ reportId: string }>()
  const navigate = useNavigate()

  const [report, setReport] = useState<LabReportDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Product assignment — tracks the currently-selected product (from search)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [assigning, setAssigning] = useState(false)
  const [assignError, setAssignError] = useState<string | null>(null)
  const [assignSuccess, setAssignSuccess] = useState(false)

  // Re-processing
  const [processing, setProcessing] = useState(false)
  const [processResult, setProcessResult] = useState<LabReportResult | null>(null)
  const [processError, setProcessError] = useState<string | null>(null)

  useEffect(() => {
    if (!reportId) return
    setLoading(true)
    api.labReports.get(reportId)
      .then(reportData => {
        setReport(reportData)
        // If already assigned, pre-populate the selected product
        if (reportData.product_id) {
          api.products.get(reportData.product_id)
            .then(p => setSelectedProduct(p))
            .catch(() => { /* non-fatal */ })
        }
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [reportId])

  async function handleAssign() {
    if (!reportId) return
    setAssigning(true)
    setAssignError(null)
    setAssignSuccess(false)
    try {
      const updated = await api.labReports.assign(reportId, selectedProduct?.id ?? null)
      setReport(prev => prev ? { ...prev, product_id: updated.product_id } : prev)
      setAssignSuccess(true)
    } catch (err: any) {
      setAssignError(err.message)
    } finally {
      setAssigning(false)
    }
  }

  async function handleProcess() {
    if (!reportId) return
    setProcessing(true)
    setProcessError(null)
    setProcessResult(null)
    try {
      const results = await api.labReports.process(
        [reportId],
        selectedProduct?.id ?? undefined,
      )
      const result = results[0] ?? null
      setProcessResult(result)
      if (result) {
        setReport(prev => prev ? {
          ...prev,
          status: result.status,
          lab_name: result.lab_name,
          lab_license: result.lab_license,
          test_date: result.test_date,
          batch_id: result.batch_id,
          product_name_on_report: result.product_name,
          total_terpenes: result.total_terpenes,
          pass_fail: result.pass_fail,
          confidence: result.confidence,
          confidence_notes: result.confidence_notes,
          terpenes: result.terpenes,
        } : prev)
      }
    } catch (err: any) {
      setProcessError(err.message)
    } finally {
      setProcessing(false)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 24 }}>
        <Link to="/lab-reports" style={{ fontSize: 14, color: '#57606a' }}>← All Lab Reports</Link>
        <p style={{ marginTop: 24, color: '#57606a' }}>Loading…</p>
      </div>
    )
  }

  if (error || !report) {
    return (
      <div style={{ padding: 24 }}>
        <Link to="/lab-reports" style={{ fontSize: 14, color: '#57606a' }}>← All Lab Reports</Link>
        <div style={{ marginTop: 24, padding: '10px 14px', background: '#ffebe9', color: '#cf222e', borderRadius: 6 }}>
          {error ?? 'Report not found'}
        </div>
      </div>
    )
  }

  const sortedTerpenes = [...report.terpenes].sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))
  const maxPct = Math.max(...report.terpenes.map(t => t.percent ?? 0), 0.001)
  const sortedCannabinoids = [...report.cannabinoids].sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))
  const maxCbdPct = Math.max(...report.cannabinoids.map(c => c.percent ?? 0), 0.001)
  const productChanged = (selectedProduct?.id ?? null) !== (report.product_id ?? null)
  const canProcess = report.status === 'pending' || report.status === 'failed' || report.status === 'extracted'

  return (
    <div style={{ padding: 24, maxWidth: 760 }}>
      {/* Breadcrumb */}
      <Link to="/lab-reports" style={{ fontSize: 14, color: '#57606a', textDecoration: 'none' }}>
        ← All Lab Reports
      </Link>

      {/* Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <h1 style={{ margin: 0, fontSize: 20 }}>Lab Report</h1>
        <StatusBadge status={report.status} />
        {report.confidence != null && <ConfidenceBadge score={report.confidence} />}
        <PassFailBadge value={report.pass_fail} />
      </div>

      {/* Metadata */}
      <div style={{ border: '1px solid #d0d7de', borderRadius: 8, padding: '16px 20px', marginBottom: 20 }}>
        <h2 style={{ margin: '0 0 14px', fontSize: 16 }}>Report Details</h2>
        <table style={{ borderCollapse: 'collapse', fontSize: 14, width: '100%' }}>
          <tbody>
            {([
              ['ID', report.id],
              ['Uploaded', report.created_at ? new Date(report.created_at).toLocaleString() : null],
              ['Lab name', report.lab_name],
              ['Lab license', report.lab_license],
              ['Test date', report.test_date],
              ['Batch / lot ID', report.batch_id],
              ['Product (on report)', report.product_name_on_report ?? report.product_name],
              ['Total terpenes', report.total_terpenes != null ? `${report.total_terpenes}%` : null],
            ] as [string, string | null][]).map(([label, value]) => (
              <tr key={label}>
                <td style={{ padding: '5px 16px 5px 0', color: '#57606a', whiteSpace: 'nowrap', verticalAlign: 'top' }}>{label}</td>
                <td style={{ padding: '5px 0', fontWeight: value ? 500 : 400, color: value ? 'inherit' : '#57606a', wordBreak: 'break-all' }}>
                  {value ?? <span style={{ opacity: 0.4 }}>—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {report.confidence_notes && (
          <p style={{ fontSize: 13, color: '#9a6700', background: '#fff8c5', padding: '8px 12px', borderRadius: 6, marginTop: 14, marginBottom: 0 }}>
            ⚠ {report.confidence_notes}
          </p>
        )}
      </div>

      {/* Product assignment */}
      <div style={{ border: '1px solid #d0d7de', borderRadius: 8, padding: '16px 20px', marginBottom: 20 }}>
        <h2 style={{ margin: '0 0 14px', fontSize: 16 }}>Assigned Product</h2>

        {selectedProduct ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{
              flex: 1, padding: '8px 12px', borderRadius: 6,
              border: '1px solid #d0d7de', background: '#373737', fontSize: 14,
            }}>
              <span style={{ fontWeight: 600 }}>{selectedProduct.name}</span>
              {selectedProduct.brand && <span style={{ color: '#57606a' }}> — {selectedProduct.brand}</span>}
              <span style={{ color: '#57606a' }}> ({selectedProduct.category})</span>
            </div>
            <button
              onClick={() => { setSelectedProduct(null); setAssignSuccess(false) }}
              disabled={assigning}
              style={{
                padding: '6px 12px', fontSize: 13, borderRadius: 6,
                border: '1px solid #d0d7de', background: '#f6f8fa',
                cursor: assigning ? 'not-allowed' : 'pointer', color: '#57606a',
              }}
            >
              Clear
            </button>
          </div>
        ) : (
          <div style={{ marginBottom: 12 }}>
            <ProductSearch
              onSelect={p => { setSelectedProduct(p); setAssignSuccess(false) }}
              disabled={assigning}
              placeholder="Search for a product to assign…"
            />
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={handleAssign}
            disabled={assigning || !productChanged}
            style={{
              padding: '6px 18px', fontSize: 14, fontWeight: 600, borderRadius: 6, border: 'none',
              background: assigning || !productChanged ? '#d0d7de' : '#1f6feb',
              color: assigning || !productChanged ? '#57606a' : '#fff',
              cursor: assigning || !productChanged ? 'not-allowed' : 'pointer',
            }}
          >
            {assigning ? 'Saving…' : 'Save Assignment'}
          </button>
          {selectedProduct && (
            <Link to={`/products/${selectedProduct.id}`} style={{ fontSize: 13, color: '#57606a' }}>
              View product →
            </Link>
          )}
        </div>

        {assignSuccess && (
          <p style={{ margin: '10px 0 0', fontSize: 13, color: '#1a7f37' }}>✓ Product assignment saved</p>
        )}
        {assignError && (
          <p style={{ margin: '10px 0 0', fontSize: 13, color: '#cf222e' }}>{assignError}</p>
        )}
      </div>

      {/* Process / re-process */}
      <div style={{ border: '1px solid #d0d7de', borderRadius: 8, padding: '16px 20px', marginBottom: 20 }}>
        <h2 style={{ margin: '0 0 8px', fontSize: 16 }}>
          {report.status === 'pending' ? 'Process Report' : 'Re-process Report'}
        </h2>
        <p style={{ margin: '0 0 14px', fontSize: 13, color: '#57606a' }}>
          Runs Claude vision extraction on the uploaded PDF.
          {selectedProduct && ' Terpenes will be written to the assigned product.'}
        </p>
        <button
          onClick={handleProcess}
          disabled={processing || !canProcess}
          style={{
            padding: '8px 20px', fontSize: 14, fontWeight: 600, borderRadius: 6, border: 'none',
            background: processing || !canProcess ? '#d0d7de' : '#1f6feb',
            color: processing || !canProcess ? '#57606a' : '#fff',
            cursor: processing || !canProcess ? 'not-allowed' : 'pointer',
          }}
        >
          {processing ? 'Analyzing COA…' : report.status === 'pending' ? 'Process Report' : 'Re-process Report'}
        </button>
        {!canProcess && (
          <span style={{ marginLeft: 12, fontSize: 13, color: '#57606a' }}>Report is already applied</span>
        )}

        {processError && (
          <div style={{ marginTop: 12, padding: '8px 12px', background: '#ffebe9', color: '#cf222e', borderRadius: 6, fontSize: 14 }}>
            {processError}
          </div>
        )}
        {processResult && (
          <div style={{ marginTop: 16, padding: '10px 14px', background: '#dafbe1', color: '#1a7f37', borderRadius: 6, fontSize: 14 }}>
            ✓ Extraction complete — {processResult.terpenes.length} terpenes found
            {processResult.applied_to_product && ', applied to product'}
          </div>
        )}
      </div>

      {/* Cannabinoids */}
      <div style={{ border: '1px solid #d0d7de', borderRadius: 8, padding: '16px 20px', marginBottom: 20 }}>
        <h2 style={{ margin: '0 0 14px', fontSize: 16 }}>
          Cannabinoids
          {sortedCannabinoids.length > 0 && (
            <span style={{ fontWeight: 400, fontSize: 14, color: '#57606a', marginLeft: 8 }}>
              ({sortedCannabinoids.length})
            </span>
          )}
        </h2>

        {sortedCannabinoids.length === 0 ? (
          <p style={{ color: '#57606a', fontSize: 14, margin: 0 }}>
            {report.status === 'pending' || report.status === 'failed'
              ? 'No cannabinoid data yet — process the report to extract cannabinoids.'
              : 'No cannabinoids detected on this report.'}
          </p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <tbody>
              {sortedCannabinoids.map(c => (
                <TerpeneRow key={c.name} name={c.name} percent={c.percent ?? 0} max={maxCbdPct} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Terpenes */}
      <div style={{ border: '1px solid #d0d7de', borderRadius: 8, padding: '16px 20px' }}>
        <h2 style={{ margin: '0 0 14px', fontSize: 16 }}>
          Terpenes
          {sortedTerpenes.length > 0 && (
            <span style={{ fontWeight: 400, fontSize: 14, color: '#57606a', marginLeft: 8 }}>
              ({sortedTerpenes.length}) — total {sortedTerpenes.reduce((s, t) => s + (t.percent ?? 0), 0).toFixed(3)}%
            </span>
          )}
        </h2>

        {sortedTerpenes.length === 0 ? (
          <p style={{ color: '#57606a', fontSize: 14, margin: 0 }}>
            {report.status === 'pending' || report.status === 'failed'
              ? 'No terpene data yet — process the report to extract terpenes.'
              : 'No terpenes detected on this report.'}
          </p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <tbody>
              {sortedTerpenes.map(t => (
                <TerpeneRow key={t.name} name={t.name} percent={t.percent ?? 0} max={maxPct} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
