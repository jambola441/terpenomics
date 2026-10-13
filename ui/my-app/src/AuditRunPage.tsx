import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { badge, navBtnStyle, pageWrap, primaryBtnStyle, selectStyle } from './components/AdminTable'
import { ProductImage } from './components/ui'
import { Icon } from './components/Icon'
import api from './api/client'
import type { AuditCandidate, AuditItem, AuditJudgeModel, AuditRunDetail, AuditVerdict, ProposalKind } from './types'
import { money } from './utils/partners'
import { PROPOSAL_KINDS, draftFromFix, pct, statusTone, when } from './utils/audits'
import { t, font, radius, tone } from './theme'

/**
 * One audit run: live progress while the worker builds and judges it, the error rate
 * (overall, on the random sample, on flagged items) and each flag's precision, and
 * the items. Each item opens to its evidence (listing, photo, matched entry, the
 * entry's other listings and prices) and the judge's verdict; a person can give or
 * change the verdict and fix a listing: pick its entry (a manual match), mark a store
 * error, or draft a catalog proposal (measured by the worker, approved in the queue).
 */

const VERDICT_TONE: Record<AuditVerdict, keyof typeof tone> = { right: 'success', wrong: 'danger', unsure: 'warning' }

export default function AuditRunPage() {
  const { runId = '' } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<AuditRunDetail | null>(null)
  const [models, setModels] = useState<AuditJudgeModel[]>([])
  const [judgeModel, setJudgeModel] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [only, setOnly] = useState<'all' | 'flag' | 'sample' | 'wrong' | 'unjudged'>('all')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await api.audits.run(runId))
    } catch (err: any) {
      setError(err.message)
    }
  }, [runId])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    api.audits.models().then(m => { setModels(m.models); setJudgeModel(m.default) }).catch(() => {})
  }, [])

  const live = !!data && (['queued', 'building', 'judging'].includes(data.run.status) || data.pending_jobs.length > 0)
  useEffect(() => {
    if (!live) return
    const id = window.setInterval(load, 3000)
    return () => window.clearInterval(id)
  }, [live, load])

  function replace(item: AuditItem) {
    setData(d => d && { ...d, items: d.items.map(i => (i.id === item.id ? { ...i, ...item, proposals: i.proposals } : i)) })
  }

  async function judgeAll() {
    if (!judgeModel) return
    try {
      await api.audits.judge(runId, judgeModel)
      await load()
    } catch (err: any) {
      setError(err.message)
    }
  }

  if (!data) {
    return <div style={pageWrap}>{error ? <span style={{ color: t.danger }}>{error}</span> : 'Loading…'}</div>
  }
  const { run, summary } = data
  const unjudged = data.items.filter(i => !i.verdict).length
  const items = data.items.filter(i =>
    only === 'all' ? true : only === 'wrong' ? i.verdict === 'wrong' : only === 'unjudged' ? !i.verdict : i.source === only)
  const progress = run.total_items ? Math.round((run.judged_items / run.total_items) * 100) : 0

  return (
    <div style={pageWrap}>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/admin/audits')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Brand health</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600 }}>
            Audit · {run.brands.join(', ')}
          </h1>
          <span style={{ ...badge, background: tone[statusTone(run.status)].bg, color: tone[statusTone(run.status)].fg }}>{run.status}</span>
          <div style={{ flex: 1 }} />
          <Link to="/admin/audits/proposals" style={{ ...navBtnStyle, textDecoration: 'none' }}>Proposals queue</Link>
        </div>
        <div style={{ color: t.text3, fontSize: 13, marginBottom: 12 }}>
          {when(run.created_at)} by {run.created_by} · sample {run.sample_size} · judge {run.judge_label ?? 'by hand'}
          {run.input_tokens > 0 && ` · ${run.input_tokens.toLocaleString()} in / ${run.output_tokens.toLocaleString()} out tokens · $${run.cost_usd.toFixed(4)}`}
        </div>
        {run.error && <div style={{ color: t.warning, marginBottom: 12 }}>{run.error}</div>}
        {error && <div style={{ color: t.danger, marginBottom: 12 }}>{error}</div>}

        <div style={{ ...panel, marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
            <span>{live ? 'Working…' : 'Judged'}</span>
            <span style={{ fontFamily: font.family.mono, color: t.text3 }}>{run.judged_items}/{run.total_items}</span>
          </div>
          <div style={{ height: 8, borderRadius: radius.pill, background: t.surface3, overflow: 'hidden' }}>
            <div style={{ width: `${progress}%`, height: '100%', background: progress === 100 ? t.success : t.accent, transition: 'width 300ms' }} />
          </div>
          {!live && unjudged > 0 && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 }}>
              <span style={{ fontSize: 13, color: t.text2 }}>{unjudged} without a verdict:</span>
              <select value={judgeModel} onChange={e => setJudgeModel(e.target.value)} style={selectStyle} aria-label="Judge model">
                {models.map(m => <option key={m.id} value={m.id}>{m.label} (~${(m.est_per_item_usd * unjudged).toFixed(3)})</option>)}
              </select>
              <button onClick={judgeAll} style={primaryBtnStyle}><Icon name="sparkles" size={14} />Judge with LLM</button>
              <span style={{ fontSize: 12, color: t.text3 }}>or judge them by hand below</span>
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 16 }}>
          <Stat label="Error rate (all judged)" value={pct(summary.all.error_rate)} sub={`${summary.all.wrong} wrong of ${summary.all.right + summary.all.wrong}; ${summary.all.unsure} unsure`} />
          <Stat label="Sample error (trusted)" value={pct(summary.sample.error_rate)} sub={`${summary.sample.wrong}/${summary.sample.right + summary.sample.wrong} of the random sample`} />
          <Stat label="Flagged that were wrong" value={pct(summary.flagged.error_rate)} sub={`${summary.flagged.items} flagged`} />
          {Object.entries(summary.flags).map(([kind, r]) => (
            <Stat key={kind} label={`${kind} precision`} value={pct(r.precision)} sub={`${r.wrong}/${r.right + r.wrong} judged wrong`} />
          ))}
        </div>

        <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
          {(['all', 'flag', 'sample', 'wrong', 'unjudged'] as const).map(k => (
            <button key={k} onClick={() => setOnly(k)}
                    style={{ ...navBtnStyle, background: only === k ? t.accentTint : t.surface2, color: only === k ? t.accent : t.text2 }}>
              {k}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(i => (
            <ItemRow key={i.id} item={i} open={open === i.id} onToggle={() => setOpen(o => (o === i.id ? null : i.id))}
                     onChange={replace} onProposal={load} />
          ))}
          {items.length === 0 && <div style={{ color: t.text3, padding: 24 }}>{live ? 'Building the run…' : 'No items.'}</div>}
        </div>
      </div>
    </div>
  )
}

function ItemRow({ item, open, onToggle, onChange, onProposal }: {
  item: AuditItem; open: boolean; onToggle: () => void; onChange: (i: AuditItem) => void; onProposal: () => void
}) {
  const l = item.evidence.listing
  const e = item.evidence.entry
  return (
    <div style={{ ...panel, padding: 0 }}>
      <button onClick={onToggle} style={{
        display: 'grid', gridTemplateColumns: '90px 70px minmax(0, 2fr) minmax(0, 1.5fr) 80px 150px', gap: 10, width: '100%',
        padding: '10px 14px', background: 'none', border: 'none', color: 'inherit', textAlign: 'left', cursor: 'pointer', alignItems: 'center',
      }}>
        {item.verdict
          ? <span style={{ ...badge, background: tone[VERDICT_TONE[item.verdict]].bg, color: tone[VERDICT_TONE[item.verdict]].fg, justifySelf: 'start' }}>{item.verdict}</span>
          : <span style={{ ...badge, background: t.surface2, color: t.text3, justifySelf: 'start' }}>unjudged</span>}
        <span style={{ fontSize: 12, color: t.text3 }}>{item.source === 'flag' ? item.flags.map(f => f.kind).join(', ') : 'sample'}</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 600 }}>{l?.name ?? item.listing_id}</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: t.text2, fontSize: 13 }}>
          → {e ? `${e.name} ${e.variant ?? ''}` : 'no entry'}
        </span>
        <span style={{ fontFamily: font.family.mono, fontSize: 13 }}>{l?.price_cents != null ? money(l.price_cents) : '—'}</span>
        <span style={{ fontSize: 12, color: item.fix ? t.success : t.text3 }}>
          {item.fix ? `fixed: ${item.fix.action}` : item.proposals.length ? `${item.proposals.length} proposal(s)` : item.cause ?? ''}
        </span>
      </button>
      {open && <ItemDetail item={item} onChange={onChange} onProposal={onProposal} />}
    </div>
  )
}

function ItemDetail({ item, onChange, onProposal }: { item: AuditItem; onChange: (i: AuditItem) => void; onProposal: () => void }) {
  const ev = item.evidence
  const l = ev.listing
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<'none' | 'pick' | 'store' | 'proposal'>('none')
  const [candidates, setCandidates] = useState<AuditCandidate[] | null>(null)
  const [note, setNote] = useState('')
  const draft = draftFromFix(item)
  const [kind, setKind] = useState<ProposalKind>(draft.kind)
  const [params, setParams] = useState(JSON.stringify(draft.params, null, 1))
  const [why, setWhy] = useState(item.explanation ?? '')

  async function act(fn: () => Promise<AuditItem | void>) {
    setBusy(true)
    setError(null)
    try {
      const got = await fn()
      if (got) onChange(got)
      setMode('none')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function openPick() {
    setMode('pick')
    if (!candidates) {
      try { setCandidates((await api.audits.candidates(item.id)).candidates) } catch (err: any) { setError(err.message) }
    }
  }

  async function propose() {
    let parsed: Record<string, unknown>
    try { parsed = JSON.parse(params) } catch { setError('Params are not valid JSON'); return }
    await act(async () => {
      await api.audits.createProposal({ kind, params: parsed, why: why.trim() || undefined, item_id: item.id })
      onProposal()
    })
  }

  return (
    <div style={{ borderTop: `1px solid ${t.border}`, padding: 14, display: 'grid', gridTemplateColumns: 'minmax(260px, 1fr) minmax(300px, 1.2fr)', gap: 16 }}>
      <div>
        <div style={{ display: 'flex', gap: 12 }}>
          <ProductImage src={l?.image_url ?? null} category={l?.category ?? null} height={120} style={{ width: 120, flexShrink: 0 }} />
          <div style={{ minWidth: 0, fontSize: 13 }}>
            <div style={{ fontWeight: 600, fontSize: 15 }}>{l?.name}</div>
            <div style={{ color: t.text2 }}>{l?.store} · size field {l?.size_field ?? '—'} · {l?.match_method}</div>
            {l?.url && <a href={l.url} target="_blank" rel="noreferrer" style={{ color: t.accent }}>Store page ↗</a>}
            {' · '}<Link to={`/admin/listings/${item.listing_id}`} style={{ color: t.accent }}>Listing</Link>
          </div>
        </div>
        {l?.description && <p style={{ fontSize: 12, color: t.text2, whiteSpace: 'pre-wrap', maxHeight: 120, overflow: 'auto' }}>{l.description}</p>}
        {item.flags.map((f, n) => <div key={n} style={{ fontSize: 12, color: t.warning, marginTop: 4 }}>⚑ {f.kind}: {f.text}</div>)}
        <div style={{ marginTop: 10, fontSize: 13 }}>
          <b>Matched entry:</b> {ev.entry ? `${ev.entry.name} · ${ev.entry.variant ?? '?'} [${[ev.entry.category, ev.entry.subtype].filter(Boolean).join('/')}]` : 'none'}
          {ev.product_other_sizes && ev.product_other_sizes.length > 0 && (
            <div style={{ color: t.text3 }}>Other sizes: {ev.product_other_sizes.map(s => s.variant).join(', ')}</div>
          )}
        </div>
        <div style={{ marginTop: 10, fontSize: 12 }}>
          <b>Other listings on this entry</b> ({ev.siblings_total ?? 0})
          {(ev.siblings ?? []).map((s, n) => (
            <div key={n} style={{ display: 'flex', gap: 8, color: t.text2 }}>
              <span style={{ fontFamily: font.family.mono, minWidth: 64 }}>{s.price_cents != null ? money(s.price_cents) : '—'}</span>
              {s.url ? <a href={s.url} target="_blank" rel="noreferrer" style={{ color: t.text2 }}>{s.name}</a> : <span>{s.name}</span>}
              <span style={{ color: t.text3 }}>{s.store}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ fontSize: 13 }}>
          <b>Verdict:</b> {item.verdict ?? '—'}{item.cause ? ` · ${item.cause}` : ''}
          {item.judged_by && <span style={{ color: t.text3 }}> ({item.judged_by})</span>}
          {item.explanation && <p style={{ margin: '6px 0 0', color: t.text2 }}>{item.explanation}</p>}
          {item.proposed_fix && item.proposed_fix.kind !== 'none' && (
            <div style={{ marginTop: 6, fontSize: 12, color: t.text3 }}>Judge proposes: <code>{JSON.stringify(item.proposed_fix)}</code></div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {(['right', 'wrong', 'unsure'] as AuditVerdict[]).map(v => (
            <button key={v} disabled={busy} onClick={() => act(() => api.audits.verdict(item.id, { verdict: v, cause: v === 'right' ? null : item.cause, note: note || undefined }))}
                    style={{ ...navBtnStyle, borderColor: item.verdict === v ? tone[VERDICT_TONE[v]].fg : t.border }}>{v}</button>
          ))}
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Note (optional)" style={{ ...selectStyle, flex: 1, minWidth: 140 }} />
        </div>
        {item.fix ? (
          <div style={{ fontSize: 13, color: t.success }}>Fixed: {item.fix.action} {String(item.fix.entry ?? item.fix.what ?? '')}</div>
        ) : (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button onClick={openPick} style={navBtnStyle}><Icon name="link" size={14} />Pick entry</button>
            <button onClick={() => setMode('store')} style={navBtnStyle}><Icon name="store" size={14} />Store error</button>
            <button onClick={() => setMode('proposal')} style={navBtnStyle}><Icon name="edit" size={14} />Catalog proposal</button>
          </div>
        )}
        {item.proposals.map(p => (
          <div key={p.id} style={{ fontSize: 12 }}>Proposal {p.kind}: <b>{p.status}</b></div>
        ))}
        {error && <div style={{ color: t.danger, fontSize: 13 }}>{error}</div>}
        {mode === 'pick' && (
          <Box>
            {!candidates && 'Loading…'}
            {candidates?.length === 0 && 'No entries to offer.'}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
              {candidates?.map(c => (
                <button key={c.id} disabled={busy} onClick={() => act(() => api.audits.manualMatch(item.id, c.id))}
                        style={{ ...navBtnStyle, flexDirection: 'column', alignItems: 'flex-start', borderColor: c.judge_pick ? t.accent : t.border }}>
                  <span style={{ fontWeight: 600, color: t.text1 }}>{c.name}</span>
                  <span>{[c.product_line, c.subtype, c.variant].filter(Boolean).join(' · ')}</span>
                  {c.judge_pick && <span style={{ color: t.accent, fontSize: 11 }}>judge's pick</span>}
                  {c.suggested && <span style={{ color: t.text3, fontSize: 11 }}>current match</span>}
                </button>
              ))}
            </div>
          </Box>
        )}
        {mode === 'store' && (
          <Box>
            <div style={{ fontSize: 13, marginBottom: 6 }}>The match is right; the store's data is wrong. Which?</div>
            {(['price', 'photo', 'title'] as const).map(w => (
              <button key={w} disabled={busy} onClick={() => act(() => api.audits.storeError(item.id, w, note || undefined))}
                      style={{ ...navBtnStyle, marginRight: 6 }}>{w}</button>
            ))}
          </Box>
        )}
        {mode === 'proposal' && (
          <Box>
            <select value={kind} onChange={e => setKind(e.target.value as ProposalKind)} style={selectStyle} aria-label="Proposal kind">
              {PROPOSAL_KINDS.map(k => <option key={k.kind} value={k.kind}>{k.label}</option>)}
            </select>
            <div style={{ fontSize: 11, color: t.text3, margin: '4px 0' }}>{PROPOSAL_KINDS.find(k => k.kind === kind)?.hint}</div>
            <textarea value={params} onChange={e => setParams(e.target.value)} rows={6}
                      style={{ ...selectStyle, width: '100%', fontFamily: font.family.mono, boxSizing: 'border-box' }} />
            <textarea value={why} onChange={e => setWhy(e.target.value)} rows={2} placeholder="Why"
                      style={{ ...selectStyle, width: '100%', marginTop: 6, boxSizing: 'border-box' }} />
            <button disabled={busy} onClick={propose} style={{ ...primaryBtnStyle, marginTop: 6 }}>Create and measure</button>
          </Box>
        )}
      </div>
    </div>
  )
}

function Box({ children }: { children: ReactNode }) {
  return <div style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.md, padding: 10 }}>{children}</div>
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={panel}>
      <div style={{ fontSize: 11, color: t.text3, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
      <div style={{ fontFamily: font.family.mono, fontSize: font.size.title, fontWeight: 600 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: t.text3 }}>{sub}</div>}
    </div>
  )
}

const panel: CSSProperties = { background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: 14 }
