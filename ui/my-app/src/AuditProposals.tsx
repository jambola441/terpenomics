import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { badge, navBtnStyle, pageWrap, primaryBtnStyle, selectStyle } from './components/AdminTable'
import { ProductImage } from './components/ui'
import { Icon } from './components/Icon'
import api from './api/client'
import type { AuditProposal, MeasureChange } from './types'
import { money } from './utils/partners'
import { PROPOSAL_KINDS, statusTone, when } from './utils/audits'
import { t, font, radius, tone } from './theme'

/**
 * Proposals queue, one card at a time (the Review Queue's keyboard style): what the
 * proposal changes, why (the audit item's listing, photo, links), and its measured
 * effect (trusted listings before and after, trusted matches lost or moved, listings
 * that change). A approves (the worker applies it, syncs the grid, re-matches the
 * brand), R rejects, E edits the params and re-measures; J / K or the arrows move.
 * Only a measured proposal can be approved.
 */

export default function AuditProposals() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<AuditProposal[] | null>(null)
  const [at, setAt] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [why, setWhy] = useState('')
  const [view, setView] = useState<'open' | 'decided'>('open')

  const load = useCallback(async () => {
    try {
      setRows((await api.audits.proposals(view)).proposals)
    } catch (err: any) {
      setError(err.message)
    }
  }, [view])
  useEffect(() => { load() }, [load])

  const pending = !!rows?.some(p => ['measuring', 'approved', 'applying'].includes(p.status))
  useEffect(() => {
    if (!pending) return
    const id = window.setInterval(load, 4000)
    return () => window.clearInterval(id)
  }, [pending, load])

  const card = rows && rows.length ? rows[Math.min(at, rows.length - 1)] : null
  useEffect(() => { setEditing(null) }, [card?.id])

  async function act(fn: () => Promise<AuditProposal>) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const got = await fn()
      setRows(r => r && r.map(p => (p.id === got.id ? { ...p, ...got } : p)))
      setEditing(null)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function saveEdit() {
    if (!card || editing === null) return
    let params: Record<string, unknown>
    try { params = JSON.parse(editing) } catch { setError('Params are not valid JSON'); return }
    act(() => api.audits.editProposal(card.id, { params, why }))
  }

  const keyRef = useRef<(e: KeyboardEvent) => void>(() => {})
  keyRef.current = (e: KeyboardEvent) => {
    const el = e.target as HTMLElement | null
    if (e.metaKey || e.ctrlKey || e.altKey) return
    if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) return
    if (!rows || !card) return
    const k = e.key.toLowerCase()
    if (k === 'j' || k === 'arrowright') { e.preventDefault(); setAt(i => Math.min(rows.length - 1, i + 1)) }
    else if (k === 'k' || k === 'arrowleft') { e.preventDefault(); setAt(i => Math.max(0, i - 1)) }
    else if (k === 'a' && card.status === 'measured') { e.preventDefault(); act(() => api.audits.approve(card.id)) }
    else if (k === 'r' && ['measuring', 'measured', 'failed'].includes(card.status)) { e.preventDefault(); act(() => api.audits.reject(card.id)) }
    else if (k === 'e' && ['measuring', 'measured', 'failed'].includes(card.status)) {
      e.preventDefault()
      setEditing(JSON.stringify(card.params, null, 1))
      setWhy(card.why ?? '')
    }
  }
  useEffect(() => {
    const on = (e: KeyboardEvent) => keyRef.current(e)
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [])

  return (
    <div style={pageWrap}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/admin/audits')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Brand health</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600 }}>Proposals</h1>
          <select value={view} onChange={e => { setView(e.target.value as 'open' | 'decided'); setAt(0) }} style={selectStyle} aria-label="Show">
            <option value="open">Open</option>
            <option value="decided">Decided</option>
          </select>
          <div style={{ flex: 1 }} />
          {rows && rows.length > 0 && (
            <span style={{ fontFamily: font.family.mono, color: t.text3 }}>{Math.min(at, rows.length - 1) + 1} / {rows.length}</span>
          )}
        </div>
        {error && <div style={{ color: t.danger, marginBottom: 12 }}>{error}</div>}
        {rows === null ? 'Loading…' : !card ? (
          <div style={{ ...panel, textAlign: 'center', padding: 48 }}>
            <Icon name="check-circle" size={32} color={t.success} />
            <div style={{ fontWeight: 600, marginTop: 8 }}>{view === 'open' ? 'No open proposals' : 'Nothing decided yet'}</div>
          </div>
        ) : (
          <>
            <Card p={card} />
            {editing !== null && (
              <div style={{ ...panel, marginTop: 12 }}>
                <div style={{ fontSize: 12, color: t.text3, marginBottom: 4 }}>{PROPOSAL_KINDS.find(k => k.kind === card.kind)?.hint}</div>
                <textarea value={editing} onChange={e => setEditing(e.target.value)} rows={8}
                          style={{ ...selectStyle, width: '100%', fontFamily: font.family.mono, boxSizing: 'border-box' }} />
                <textarea value={why} onChange={e => setWhy(e.target.value)} rows={2} placeholder="Why"
                          style={{ ...selectStyle, width: '100%', marginTop: 6, boxSizing: 'border-box' }} />
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button onClick={saveEdit} disabled={busy} style={primaryBtnStyle}>Save and re-measure</button>
                  <button onClick={() => setEditing(null)} style={navBtnStyle}>Cancel</button>
                </div>
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
              <Action k="K" label="Previous" onClick={() => setAt(i => Math.max(0, i - 1))} disabled={at === 0} />
              <Action k="A" label="Approve" onClick={() => act(() => api.audits.approve(card.id))} disabled={busy || card.status !== 'measured'} />
              <Action k="R" label="Reject" onClick={() => act(() => api.audits.reject(card.id))} disabled={busy || !['measuring', 'measured', 'failed'].includes(card.status)} />
              <Action k="E" label="Edit and re-measure" onClick={() => { setEditing(JSON.stringify(card.params, null, 1)); setWhy(card.why ?? '') }}
                      disabled={busy || !['measuring', 'measured', 'failed'].includes(card.status)} />
              <Action k="J" label="Next" onClick={() => setAt(i => Math.min(rows.length - 1, i + 1))} disabled={at >= rows.length - 1} />
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Card({ p }: { p: AuditProposal }) {
  const ev = p.item?.evidence
  const l = ev?.listing
  const m = p.measure
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 1fr) minmax(320px, 1.3fr)', gap: 16, alignItems: 'start' }}>
      <section style={panel}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
          <span style={{ ...badge, background: tone[statusTone(p.status)].bg, color: tone[statusTone(p.status)].fg }}>{p.status}</span>
          <b>{PROPOSAL_KINDS.find(k => k.kind === p.kind)?.label ?? p.kind}</b>
          <span style={{ color: t.text3 }}>{p.brand}</span>
        </div>
        <pre style={{ fontFamily: font.family.mono, fontSize: 12, background: t.surface2, padding: 8, borderRadius: radius.md, whiteSpace: 'pre-wrap', margin: 0 }}>
          {JSON.stringify(p.params, null, 1)}
        </pre>
        {p.why && <p style={{ fontSize: 13, color: t.text2 }}><b>Why:</b> {p.why}</p>}
        {l && (
          <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
            <ProductImage src={l.image_url} category={l.category} height={100} style={{ width: 100, flexShrink: 0 }} />
            <div style={{ fontSize: 13, minWidth: 0 }}>
              <div style={{ fontWeight: 600 }}>{l.name}</div>
              <div style={{ color: t.text2 }}>{l.store}{l.price_cents != null && ` · ${money(l.price_cents)}`}</div>
              <div style={{ color: t.text3 }}>→ {ev?.entry ? `${ev.entry.name} ${ev.entry.variant ?? ''}` : 'no entry'}</div>
              {l.url && <a href={l.url} target="_blank" rel="noreferrer" style={{ color: t.accent }}>Store page ↗</a>}
              {p.run_id && <> · <a href={`/admin/audits/runs/${p.run_id}`} style={{ color: t.accent }}>Audit run</a></>}
            </div>
          </div>
        )}
        {p.item?.explanation && <p style={{ fontSize: 12, color: t.text3 }}>Judge: {p.item.explanation}</p>}
        <div style={{ fontSize: 12, color: t.text3, marginTop: 8 }}>
          by {p.created_by} {when(p.created_at)}{p.decided_by && ` · ${p.status} by ${p.decided_by} ${when(p.decided_at)}`}
        </div>
      </section>
      <section style={panel}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Measured effect</div>
        {p.error && <div style={{ color: t.danger, fontSize: 13, marginBottom: 8 }}>{p.error}</div>}
        {!m ? (
          <div style={{ color: t.text3, fontSize: 13 }}>{p.status === 'measuring' ? 'Measuring… (the audit worker runs the matcher before and after)' : 'Not measured.'}</div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 16, alignItems: 'baseline', flexWrap: 'wrap' }}>
              <span style={{ fontFamily: font.family.mono, fontSize: font.size.title, fontWeight: 600 }}>
                trusted {m.trusted_before} → {m.trusted_after}
              </span>
              <span style={{ fontSize: 12, color: t.text3 }}>
                over {m.listings} active listing(s){m.category ? ` (${m.category})` : ''}{m.jev === false ? ' · stored readings (no Jev)' : ''}
                {m.noise ? ` · ${m.noise} noisy` : ''}
              </span>
            </div>
            <div style={{ fontSize: 13, color: t.text2, margin: '6px 0' }}>
              {Object.entries(m.tally).map(([k, v]) => `${k} ${v}`).join(' · ') || 'no listing changes'}
            </div>
            {m.risky.length > 0 && (
              <Block title={`Losses / moves to check (${m.risky.length})`} color={t.danger}>
                {m.risky.map(c => <Change key={c.listing_id} c={c} />)}
              </Block>
            )}
            {m.changes.length > 0 && (
              <Block title={`Changed listings (${m.changes.length + m.more})`}>
                {m.changes.slice(0, 25).map(c => <Change key={c.listing_id} c={c} />)}
              </Block>
            )}
            {m.notes.length > 0 && <div style={{ fontSize: 12, color: t.text3, marginTop: 8 }}>{m.notes.join(' · ')}</div>}
          </>
        )}
        {p.result && (
          <Block title="Result">
            <pre style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(p.result, null, 1)}</pre>
          </Block>
        )}
      </section>
    </div>
  )
}

function Change({ c }: { c: MeasureChange }) {
  return (
    <div style={{ fontSize: 12, padding: '4px 0', borderBottom: `1px solid ${t.border}` }}>
      <div style={{ color: t.text1 }}>{c.name}{c.variant ? ` [${c.variant}]` : ''}</div>
      <div style={{ color: t.text3 }}>
        {c.before.trust} {c.before.entry ?? ''} → {c.after.trust} {c.after.entry ?? ''}{c.move ? ` (${c.move})` : ''}
      </div>
    </div>
  )
}

function Block({ title, color, children }: { title: string; color?: string; children: ReactNode }) {
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: color ?? t.text2, marginBottom: 4 }}>{title}</div>
      <div style={{ maxHeight: 260, overflow: 'auto' }}>{children}</div>
    </div>
  )
}

function Action({ k, label, onClick, disabled }: { k: string; label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{ ...navBtnStyle, padding: '8px 12px', opacity: disabled ? 0.5 : 1 }}>
      <kbd style={{ fontFamily: font.family.mono, fontSize: 11, padding: '1px 5px', borderRadius: 4, border: `1px solid ${t.borderStrong}` }}>{k}</kbd>
      {label}
    </button>
  )
}

const panel: CSSProperties = { background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: 16 }
