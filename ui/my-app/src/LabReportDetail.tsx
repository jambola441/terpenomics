import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from './api/client'
import type { LabReportDetail, LabReportResult, Listing } from './types'
import { ListingSearch } from './components/ListingSearch'
import { Icon } from './components/Icon'
import { t, font, tone } from './theme'
import { terpeneStyle } from './design/tokens'

// ---------------------------------------------------------------------------
// Shared badge components
// ---------------------------------------------------------------------------
function ConfidenceBadge({ score }: { score: number }) {
  const tn = tone[score >= 4 ? 'success' : score === 3 ? 'warning' : 'danger']
  const label = score >= 4 ? 'High' : score === 3 ? 'Medium' : 'Low'
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 12,
      fontSize: 13, fontWeight: 600, background: tn.bg, color: tn.fg,
      border: `1px solid ${tn.edge}`,
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
      background: pass ? t.successTint : t.dangerTint,
      color: pass ? t.success : t.danger,
    }}>
      {value.toUpperCase()}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, { bg: string; color: string }> = {
    pending:   { bg: t.warningTint, color: t.warning },
    extracted: { bg: t.infoTint, color: t.info },
    applied:   { bg: t.successTint, color: t.success },
    failed:    { bg: t.dangerTint, color: t.danger },
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

/** One labelled bar. Terpenes wear their aroma colour (as on the customer's
 *  terpene profile); pass `color` for anything else. */
function TerpeneRow({ name, percent, max, color }: { name: string; percent: number; max: number; color?: string }) {
  const pct = max > 0 ? (percent / max) * 100 : 0
  const fill = color ?? terpeneStyle(name).color
  return (
    <tr>
      <td style={{ padding: '5px 8px', whiteSpace: 'nowrap' }}>
        <span aria-hidden style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: fill, marginRight: 8 }} />
        {name}
      </td>
      <td style={{ padding: '5px 8px', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            height: 14, width: `${pct}%`, minWidth: 2,
            background: fill, borderRadius: 4, transition: 'width 0.4s ease',
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

  const [report, setReport] = useState<LabReportDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Listing assignment. A report's terpenes are written to one store's listing;
  // this tracks the listing currently picked in the search.
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null)
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
        // If already assigned, pre-populate the selected listing
        if (reportData.listing_id) {
          api.listings.get(reportData.listing_id)
            .then(l => setSelectedListing(l))
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
      const updated = await api.labReports.assign(reportId, selectedListing?.id ?? null)
      setReport(prev => prev ? { ...prev, listing_id: updated.listing_id } : prev)
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
        selectedListing?.id ?? undefined,
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
          cannabinoids: result.cannabinoids,
          // Processing sets the report's listing to whatever was sent, null included.
          listing_id: selectedListing?.id ?? null,
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
        <Link to="/admin/lab-reports" style={backLink}><Icon name="arrow-left" size={15} /> All Lab Reports</Link>
        <p style={{ marginTop: 24, color: t.text3 }}>Loading…</p>
      </div>
    )
  }

  if (error || !report) {
    return (
      <div style={{ padding: 24 }}>
        <Link to="/admin/lab-reports" style={backLink}><Icon name="arrow-left" size={15} /> All Lab Reports</Link>
        <div style={{ marginTop: 24, padding: '10px 14px', background: t.dangerTint, color: t.danger, borderRadius: 6 }}>
          {error ?? 'Report not found'}
        </div>
      </div>
    )
  }

  const sortedTerpenes = [...report.terpenes].sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))
  const maxPct = Math.max(...report.terpenes.map(tp => tp.percent ?? 0), 0.001)
  const sortedCannabinoids = [...report.cannabinoids].sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))
  const maxCbdPct = Math.max(...report.cannabinoids.map(c => c.percent ?? 0), 0.001)
  const listingChanged = (selectedListing?.id ?? null) !== (report.listing_id ?? null)
  const canProcess = report.status === 'pending' || report.status === 'failed' || report.status === 'extracted'

  return (
    <div style={{ padding: 24, maxWidth: 760 }}>
      {/* Breadcrumb */}
      <Link to="/admin/lab-reports" style={backLink}>
        <Icon name="arrow-left" size={15} /> All Lab Reports
      </Link>

      {/* Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Lab Report</h1>
        <StatusBadge status={report.status} />
        {report.confidence != null && <ConfidenceBadge score={report.confidence} />}
        <PassFailBadge value={report.pass_fail} />
      </div>

      {/* Metadata */}
      <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
        <h2 style={sectionTitle}>Report Details</h2>
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
                <td style={{ padding: '5px 16px 5px 0', color: t.text3, whiteSpace: 'nowrap', verticalAlign: 'top' }}>{label}</td>
                <td style={{ padding: '5px 0', fontWeight: value ? 500 : 400, color: value ? 'inherit' : t.text3, wordBreak: 'break-all' }}>
                  {value ?? <span style={{ opacity: 0.4 }}>—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {report.confidence_notes && (
          <p style={{ fontSize: 13, color: t.warning, background: t.warningTint, border: `1px solid ${t.warningEdge}`, padding: '8px 12px', borderRadius: 6, marginTop: 14, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <Icon name="alert" size={15} style={{ marginTop: 2 }} /> {report.confidence_notes}
          </p>
        )}
      </div>

      {/* Listing assignment */}
      <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
        <h2 style={sectionTitle}>Assigned Listing</h2>

        {selectedListing ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{
              flex: 1, padding: '8px 12px', borderRadius: 6,
              border: `1px solid ${t.border}`, background: t.surface2, fontSize: 14,
            }}>
              <span style={{ fontWeight: 600 }}>{selectedListing.scraped_name ?? '(unnamed listing)'}</span>
              {selectedListing.scraped_brand && <span style={{ color: t.text3 }}> — {selectedListing.scraped_brand}</span>}
              <span style={{ color: t.text3 }}> ({selectedListing.dispensary_name})</span>
            </div>
            <button
              onClick={() => { setSelectedListing(null); setAssignSuccess(false) }}
              disabled={assigning}
              style={{
                padding: '6px 12px', fontSize: 13, borderRadius: 6,
                border: `1px solid ${t.border}`, background: t.surface2,
                cursor: assigning ? 'not-allowed' : 'pointer', color: t.text2,
              }}
            >
              Clear
            </button>
          </div>
        ) : (
          <div style={{ marginBottom: 12 }}>
            <ListingSearch
              onSelect={l => { setSelectedListing(l); setAssignSuccess(false) }}
              disabled={assigning}
              placeholder="Search for a listing to assign…"
            />
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={handleAssign}
            disabled={assigning || !listingChanged}
            style={{
              padding: '6px 18px', fontSize: 14, fontWeight: 600, borderRadius: 6, border: 'none',
              background: assigning || !listingChanged ? t.surface2 : t.accent,
              color: assigning || !listingChanged ? t.text4 : t.accentInk,
              cursor: assigning || !listingChanged ? 'not-allowed' : 'pointer',
            }}
          >
            {assigning ? 'Saving…' : 'Save Assignment'}
          </button>
          {selectedListing && (
            <Link to={`/admin/listings/${selectedListing.id}`} style={{ fontSize: 13, color: t.text2, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              View listing <Icon name="arrow-right" size={14} />
            </Link>
          )}
        </div>

        {assignSuccess && (
          <p style={{ margin: '10px 0 0', fontSize: 13, color: t.success, display: 'flex', alignItems: 'center', gap: 6 }}><Icon name="check-circle" size={15} /> Listing assignment saved</p>
        )}
        {assignError && (
          <p style={{ margin: '10px 0 0', fontSize: 13, color: t.danger }}>{assignError}</p>
        )}
      </div>

      {/* Process / re-process */}
      <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
        <h2 style={{ margin: '0 0 8px', fontSize: 16 }}>
          {report.status === 'pending' ? 'Process Report' : 'Re-process Report'}
        </h2>
        <p style={{ margin: '0 0 14px', fontSize: 13, color: t.text3 }}>
          Runs Claude vision extraction on the uploaded PDF.
          {selectedListing && ' Terpenes and cannabinoids will be written to the assigned listing.'}
        </p>
        <button
          onClick={handleProcess}
          disabled={processing || !canProcess}
          style={{
            padding: '8px 20px', fontSize: 14, fontWeight: 600, borderRadius: 6, border: 'none',
            background: processing || !canProcess ? t.surface2 : t.accent,
            color: processing || !canProcess ? t.text4 : t.accentInk,
            cursor: processing || !canProcess ? 'not-allowed' : 'pointer',
          }}
        >
          {processing ? 'Analyzing COA…' : report.status === 'pending' ? 'Process Report' : 'Re-process Report'}
        </button>
        {!canProcess && (
          <span style={{ marginLeft: 12, fontSize: 13, color: t.text3 }}>Report is already applied</span>
        )}

        {processError && (
          <div style={{ marginTop: 12, padding: '8px 12px', background: t.dangerTint, color: t.danger, borderRadius: 6, fontSize: 14 }}>
            {processError}
          </div>
        )}
        {processResult && (
          <div style={{ marginTop: 16, padding: '10px 14px', background: t.successTint, color: t.success, border: `1px solid ${t.successEdge}`, borderRadius: 6, fontSize: 14, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <Icon name="check-circle" size={15} /> Extraction complete — {processResult.terpenes.length} terpenes found
            {processResult.applied_to_listing && ', applied to listing'}
          </div>
        )}
      </div>

      {/* Cannabinoids */}
      <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
        <h2 style={sectionTitle}>
          Cannabinoids
          {sortedCannabinoids.length > 0 && (
            <span style={{ fontWeight: 400, fontSize: 14, color: t.text3, marginLeft: 8 }}>
              ({sortedCannabinoids.length})
            </span>
          )}
        </h2>

        {sortedCannabinoids.length === 0 ? (
          <p style={{ color: t.text3, fontSize: 14, margin: 0 }}>
            {report.status === 'pending' || report.status === 'failed'
              ? 'No cannabinoid data yet — process the report to extract cannabinoids.'
              : 'No cannabinoids detected on this report.'}
          </p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <tbody>
              {sortedCannabinoids.map(c => (
                <TerpeneRow key={c.name} name={c.name} percent={c.percent ?? 0} max={maxCbdPct} color={t.text3} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Terpenes */}
      <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 12, padding: '16px 20px' }}>
        <h2 style={sectionTitle}>
          Terpenes
          {sortedTerpenes.length > 0 && (
            <span style={{ fontWeight: 400, fontSize: 14, color: t.text3, marginLeft: 8 }}>
              ({sortedTerpenes.length}) — total {sortedTerpenes.reduce((s, tp) => s + (tp.percent ?? 0), 0).toFixed(3)}%
            </span>
          )}
        </h2>

        {sortedTerpenes.length === 0 ? (
          <p style={{ color: t.text3, fontSize: 14, margin: 0 }}>
            {report.status === 'pending' || report.status === 'failed'
              ? 'No terpene data yet — process the report to extract terpenes.'
              : 'No terpenes detected on this report.'}
          </p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <tbody>
              {sortedTerpenes.map(tp => (
                <TerpeneRow key={tp.name} name={tp.name} percent={tp.percent ?? 0} max={maxPct} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const backLink = { fontSize: 14, color: t.text2, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6 } as const
const sectionTitle = { margin: '0 0 14px', fontFamily: font.family.mono, fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.08em', color: t.text3 } as const
