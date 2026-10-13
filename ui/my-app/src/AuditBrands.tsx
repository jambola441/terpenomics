import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { badge, navBtnStyle, pageWrap, primaryBtnStyle, selectStyle, tdStyle, thStyle } from './components/AdminTable'
import { Icon } from './components/Icon'
import api from './api/client'
import type { AuditBrandHealth, AuditJudgeModel, AuditRun } from './types'
import { t, font, radius, tone } from './theme'
import { pct, statusTone, when } from './utils/audits'

/**
 * Brand health: per catalog brand, its trusted share, review backlog, last audit
 * (error rate on the random sample of trusted listings) and what is still open.
 * "Run audit" picks brands, a sample size and a judge (a Claude model, or by hand);
 * the audit worker builds the run, so the page lists recent runs with their status.
 */

export default function AuditBrands() {
  const navigate = useNavigate()
  const [brands, setBrands] = useState<AuditBrandHealth[] | null>(null)
  const [runs, setRuns] = useState<AuditRun[]>([])
  const [models, setModels] = useState<AuditJudgeModel[]>([])
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [sample, setSample] = useState(20)
  const [judge, setJudge] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('')
  const judgeSet = useRef(false)

  async function load() {
    try {
      const [b, r] = await Promise.all([api.audits.brands(), api.audits.runs()])
      setBrands(b.brands)
      setRuns(r.runs)
    } catch (err: any) {
      setError(err.message)
    }
  }
  useEffect(() => { load() }, [])
  useEffect(() => {
    api.audits.models(sample).then(m => {
      setModels(m.models)
      // The default judge once, on first load; later the admin's pick (by hand too) stays.
      if (!judgeSet.current) { judgeSet.current = true; setJudge(m.default) }
    }).catch(() => { /* the form still works by hand */ })
  }, [sample])

  // Runs still being built or judged: poll until they settle.
  const busyRuns = runs.some(r => ['queued', 'building', 'judging'].includes(r.status))
  useEffect(() => {
    if (!busyRuns) return
    const id = window.setInterval(load, 5000)
    return () => window.clearInterval(id)
  }, [busyRuns])

  const shown = useMemo(
    () => (brands ?? []).filter(b => !filter || b.brand.toLowerCase().includes(filter.toLowerCase())),
    [brands, filter],
  )

  function toggle(brand: string) {
    setPicked(p => {
      const next = new Set(p)
      if (next.has(brand)) next.delete(brand)
      else next.add(brand)
      return next
    })
  }

  async function runAudit() {
    if (!picked.size) return
    setBusy(true)
    setError(null)
    try {
      const run = await api.audits.createRun({ brands: [...picked], sample_size: sample, judge_model: judge || null })
      navigate(`/admin/audits/runs/${run.id}`)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const model = models.find(m => m.id === judge)

  return (
    <div style={pageWrap}>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600 }}>Brand health</h1>
          <div style={{ flex: 1 }} />
          <Link to="/admin/audits/proposals" style={{ ...navBtnStyle, textDecoration: 'none' }}>
            <Icon name="check-circle" size={14} />Proposals queue
          </Link>
        </div>

        {error && <div style={{ color: t.danger, marginBottom: 12 }}>{error}</div>}

        <section style={{ ...panel, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
          <b>Run audit</b>
          <span style={{ color: t.text3, fontSize: 13 }}>
            {picked.size ? [...picked].join(', ') : 'tick brands below'}
          </span>
          <label style={{ fontSize: 13, color: t.text2 }}>
            Sample{' '}
            <input type="number" min={0} max={200} value={sample}
                   onChange={e => setSample(Math.max(0, Math.min(200, Number(e.target.value) || 0)))}
                   style={{ ...selectStyle, width: 64 }} />
          </label>
          <select value={judge} onChange={e => setJudge(e.target.value)} style={selectStyle} aria-label="Judge">
            <option value="">Judge by hand</option>
            {models.map(m => <option key={m.id} value={m.id}>{m.label} (~${m.est_run_usd.toFixed(3)}/brand)</option>)}
          </select>
          {model && (
            <span style={{ fontSize: 12, color: t.text3 }}>
              ${model.price_per_mtok[0]}/${model.price_per_mtok[1]} per M tokens in/out · ~${model.est_per_item_usd.toFixed(4)} an item
            </span>
          )}
          <div style={{ flex: 1 }} />
          <button onClick={runAudit} disabled={!picked.size || busy} style={{ ...primaryBtnStyle, opacity: picked.size ? 1 : 0.5 }}>
            <Icon name="play" size={14} />Run audit
          </button>
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2.2fr) minmax(280px, 1fr)', gap: 16, alignItems: 'start' }}>
          <section style={{ ...panel, padding: 0, overflowX: 'auto' }}>
            <div style={{ padding: 12 }}>
              <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter brands"
                     style={{ ...selectStyle, width: 220 }} />
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: 'left', borderBottom: `1px solid ${t.border}` }}>
                  <th style={thStyle} />
                  <th style={thStyle}>Brand</th>
                  <th style={thStyle}>Listings</th>
                  <th style={thStyle}>Trusted</th>
                  <th style={thStyle}>Review backlog</th>
                  <th style={thStyle}>Last audit</th>
                  <th style={thStyle} title="Error rate on the random sample of trusted listings">Sample error</th>
                  <th style={thStyle}>Open flags</th>
                  <th style={thStyle}>Proposals</th>
                </tr>
              </thead>
              <tbody>
                {brands === null && <tr><td style={tdStyle} colSpan={9}>Loading…</td></tr>}
                {shown.map(b => {
                  const err = b.last_audit?.sample.error_rate
                  return (
                    <tr key={b.brand} style={{ borderBottom: `1px solid ${t.border}` }}>
                      <td style={tdStyle}>
                        <input type="checkbox" checked={picked.has(b.brand)} onChange={() => toggle(b.brand)} aria-label={`Pick ${b.brand}`} />
                      </td>
                      <td style={{ ...tdStyle, color: t.text1, fontWeight: 600 }}>{b.brand}</td>
                      <td style={mono}>{b.listings}</td>
                      <td style={mono}>{b.trusted_pct == null ? '—' : `${b.trusted_pct}%`}</td>
                      <td style={mono}>{b.review_backlog || '—'}</td>
                      <td style={tdStyle}>
                        {b.last_audit ? (
                          <Link to={`/admin/audits/runs/${b.last_audit.id}`} style={{ color: t.accent }}>
                            {when(b.last_audit.created_at)}
                          </Link>
                        ) : '—'}
                      </td>
                      <td style={{ ...mono, color: err != null && err > 0.05 ? t.danger : t.text2 }}>{pct(err)}</td>
                      <td style={mono}>{b.open_flags || '—'}</td>
                      <td style={mono}>{b.open_proposals || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section style={panel}>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>Recent runs</div>
            {runs.length === 0 && <div style={{ color: t.text3, fontSize: 13 }}>No audits yet.</div>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {runs.slice(0, 20).map(r => (
                <Link key={r.id} to={`/admin/audits/runs/${r.id}`}
                      style={{ display: 'block', padding: 10, borderRadius: radius.md, border: `1px solid ${t.border}`, color: 'inherit', textDecoration: 'none' }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ ...badge, background: tone[statusTone(r.status)].bg, color: tone[statusTone(r.status)].fg }}>{r.status}</span>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{r.brands.join(', ')}</span>
                  </div>
                  <div style={{ fontSize: 12, color: t.text3, marginTop: 4 }}>
                    {when(r.created_at)} · {r.judged_items}/{r.total_items} judged
                    · {r.judge_label ?? 'by hand'}{r.cost_usd ? ` · $${r.cost_usd.toFixed(3)}` : ''}
                  </div>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

const panel: CSSProperties = { background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: 16 }
const mono: CSSProperties = { ...tdStyle, fontFamily: font.family.mono }
