import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { badge, navBtnStyle, selectStyle } from './components/AdminTable'
import { ProductImage } from './components/ui'
import { Icon } from './components/Icon'
import api from './api/client'
import type { ReviewCandidate, ReviewCard, ReviewDecisionKind, ReviewProgress, ReviewReading, ReviewReason } from './types'
import { money } from './utils/partners'
import { t, font, radius, tone } from './theme'

/**
 * Catalog review queue.
 *
 * The matcher (scripts/catalog_match.py) leaves listings it could not settle
 * with a review reason. One card at a time: the store's listing on the left,
 * up to four of the brand's catalog entries on the right. The reviewer says
 * which entry it is (1-4), none of these (N), that the catalog is missing the
 * product or size (C), or skips (S); U undoes the last call.
 *
 * Decisions are recorded only — they never change the listing's match or the
 * catalog. Every issue is fixed in the catalog, from these records.
 *
 * The card after the one on screen is fetched in the background, so the next
 * card appears as soon as a key is pressed; the decision saves behind it.
 */

const REASON: Record<ReviewReason, { label: string; hint: string; tone: keyof typeof tone }> = {
  review_unsure:  { label: 'Unsure reading',  hint: 'Read against the catalog, but some step unsurely', tone: 'warning' },
  review_missing: { label: 'Catalog missing?', hint: 'The catalog most likely lacks this product',     tone: 'danger' },
  review_near:    { label: 'One off',          hint: 'One entry differs on one attribute (often size)', tone: 'info' },
}

// Below this a reading step counts as unsure (catalog_reading TRUST_AT / NARROW_AT).
const SURE = 0.9

type Prefetch = { after: string; card: Promise<ReviewCard | null> }

export default function ReviewQueue() {
  const navigate = useNavigate()
  const [brand, setBrand] = useState('')
  const [card, setCard] = useState<ReviewCard | null>(null)
  const [loading, setLoading] = useState(true)
  const [progress, setProgress] = useState<ReviewProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [cleared, setCleared] = useState<string | null>(null)
  const [session, setSession] = useState({ count: 0, started: Date.now() })
  const [busy, setBusy] = useState(false)
  const prefetch = useRef<Prefetch | null>(null)
  const filter = brand || undefined

  /** Fetch the card after `current` in the background. */
  const prefetchAfter = useCallback((current: ReviewCard | null) => {
    prefetch.current = current
      ? { after: current.listing.id, card: api.review.next({ brand: filter, exclude: [current.listing.id] }) }
      : null
    prefetch.current?.card.catch(() => { /* fetched again when needed */ })
  }, [filter])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [next, p] = await Promise.all([api.review.next({ brand: filter }), api.review.progress()])
      setCard(next)
      setProgress(p)
      prefetchAfter(next)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filter, prefetchAfter])

  useEffect(() => { load() }, [load])

  async function decide(decision: ReviewDecisionKind, entryId?: string) {
    if (!card || busy) return
    const decided = card
    const pending = prefetch.current?.after === decided.listing.id
      ? prefetch.current.card
      : api.review.next({ brand: filter, exclude: [decided.listing.id] })
    prefetch.current = null
    setBusy(true)
    setError(null)
    const saved = api.review.decide(
      { listing_id: decided.listing.id, decision, entry_id: entryId, note: note.trim() || undefined })
    setNote('')
    try {
      // The next card goes up as soon as it is here; the save finishes behind it.
      const next = await pending.catch(() => null)
      setCard(next)
      setLoading(next === null)
      const res = await saved
      setProgress(res.progress)
      setSession(s => ({ ...s, count: s.count + 1 }))
      const mine = res.progress.brands.find(b => b.brand === decided.brand)
      if (mine && mine.remaining === 0) celebrate(mine.brand)
      // The prefetched card was fetched before this save; only a fresh look
      // is sure to skip the card just decided.
      const fresh = next ?? await api.review.next({ brand: filter })
      if (!next) setCard(fresh)
      prefetchAfter(fresh)
    } catch (err: any) {
      // Not saved: put the card back so the call can be made again.
      setError(`Not saved: ${err.message}`)
      setCard(decided)
      prefetchAfter(decided)
    } finally {
      setLoading(false)
      setBusy(false)
    }
  }

  async function undo() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.review.undo()
      setProgress(res.progress)
      setSession(s => ({ ...s, count: Math.max(0, s.count - 1) }))
      if (res.card) {
        // The card that was on screen is the one after it again.
        const was = card
        setCard(res.card)
        prefetch.current = { after: res.card.listing.id, card: Promise.resolve(was) }
      } else {
        await load()
      }
    } catch (err: any) {
      setError(err.status === 404 ? 'Nothing to undo.' : err.message)
    } finally {
      setBusy(false)
    }
  }

  function celebrate(name: string) {
    setCleared(name)
    window.setTimeout(() => setCleared(c => (c === name ? null : c)), 3500)
  }

  // Keys: 1-4 pick, N none, C catalog missing, S skip, U undo. Not while typing.
  const keyRef = useRef<(e: KeyboardEvent) => void>(() => {})
  keyRef.current = (e: KeyboardEvent) => {
    const el = e.target as HTMLElement | null
    if (e.metaKey || e.ctrlKey || e.altKey) return
    if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) return
    const k = e.key.toLowerCase()
    if (k === 'u') { e.preventDefault(); undo(); return }
    if (!card) return
    const n = Number(k)
    if (n >= 1 && n <= card.candidates.length) { e.preventDefault(); decide('entry', card.candidates[n - 1].id) }
    else if (k === 'n') { e.preventDefault(); decide('none') }
    else if (k === 'c') { e.preventDefault(); decide('missing') }
    else if (k === 's') { e.preventDefault(); decide('skip') }
  }
  useEffect(() => {
    const on = (e: KeyboardEvent) => keyRef.current(e)
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [])

  const brandName = card?.brand ?? (brand || null)
  const current = progress?.brands.find(b => b.brand === brandName)
  const minutes = Math.max(1, (Date.now() - session.started) / 60000)

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Review Queue</h1>
          <select value={brand} onChange={e => setBrand(e.target.value)} style={selectStyle} aria-label="Brand">
            <option value="">All brands{progress ? ` · ${progress.totals.remaining}` : ''}</option>
            {progress?.brands.filter(b => b.remaining > 0 || b.brand === brand).map(b => (
              <option key={b.brand} value={b.brand}>{b.brand} · {b.remaining}</option>
            ))}
          </select>
          <div style={{ flex: 1 }} />
          <Stat label="This session" value={String(session.count)} />
          <Stat label="Pace" value={`${(session.count / minutes).toFixed(1)}/min`}
                title={progress ? `Last 10 min: ${(progress.me.last_10_min / 10).toFixed(1)}/min` : undefined} />
          <Stat label="Today" value={String(progress?.me.today ?? 0)} />
        </div>

        {progress && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12, marginBottom: 16 }}>
            {current && <Bar label={current.brand} decided={current.decided} total={current.total} />}
            <Bar label="All brands" decided={progress.totals.decided} total={progress.totals.total} />
          </div>
        )}

        {cleared && (
          <div style={{
            marginBottom: 16, padding: '12px 16px', borderRadius: radius.lg, display: 'flex', alignItems: 'center', gap: 10,
            background: t.successTint, border: `1px solid ${t.successEdge}`, color: t.success, fontWeight: 600,
          }}>
            <Icon name="check-circle" size={20} color={t.success} />
            {cleared} cleared — every card in its queue has a call.
          </div>
        )}

        {error && <div style={{ color: t.danger, marginBottom: 12 }}>{error}</div>}

        {card ? (
          <>
            <Card card={card} onPick={id => decide('entry', id)} disabled={busy} />
            <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap', alignItems: 'center' }}>
              <Action k="N" label="None of these" onClick={() => decide('none')} disabled={busy} />
              <Action k="C" label="Catalog missing this product / size" onClick={() => decide('missing')} disabled={busy} />
              <Action k="S" label="Skip" onClick={() => decide('skip')} disabled={busy} />
              <Action k="U" label="Undo last" onClick={undo} disabled={busy} icon="undo" />
              <input
                value={note}
                onChange={e => setNote(e.target.value)}
                onKeyDown={e => { if (e.key === 'Escape') (e.target as HTMLInputElement).blur() }}
                placeholder="Note for the catalog fix (optional, saved with the next call)"
                style={{ ...selectStyle, flex: 1, minWidth: 240, padding: '8px 10px' }}
              />
            </div>
          </>
        ) : loading ? (
          <div style={{ color: t.text3, padding: 40, textAlign: 'center' }}>Loading…</div>
        ) : (
          <div style={{ padding: 48, textAlign: 'center', background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg }}>
            <Icon name="check-circle" size={32} color={t.success} />
            <div style={{ fontSize: font.size.heading, fontWeight: 600, marginTop: 10 }}>
              {brand ? `${brand} is cleared` : 'Queue cleared'}
            </div>
            <div style={{ color: t.text3, marginTop: 6 }}>Every listing left for review has a call.</div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 16 }}>
              {brand && <button onClick={() => setBrand('')} style={navBtnStyle}>All brands</button>}
              <Action k="U" label="Undo last" onClick={undo} disabled={busy} icon="undo" />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Card({ card, onPick, disabled }: { card: ReviewCard; onPick: (id: string) => void; disabled: boolean }) {
  const l = card.listing
  const reason = REASON[card.reason]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(320px, 1.3fr)', gap: 20, alignItems: 'start' }}>
      <section style={panel}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <span style={{ ...badge, background: tone[reason.tone].bg, color: tone[reason.tone].fg }} title={reason.hint}>{reason.label}</span>
          <span style={{ fontSize: 12, color: t.text3 }}>{reason.hint}</span>
        </div>
        <div style={{ display: 'flex', gap: 14 }}>
          <ProductImage src={l.image_url} category={l.category} height={140} style={{ width: 140, flexShrink: 0 }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: font.size.title, fontWeight: 600, lineHeight: 1.3 }}>{l.name ?? '—'}</div>
            <div style={{ color: t.text2, marginTop: 4 }}>{l.brand} · {l.store}</div>
            <div style={{ marginTop: 8, display: 'flex', gap: 12, color: t.text1, fontFamily: font.family.mono, fontSize: 13 }}>
              <span>{l.size ?? l.variant ?? 'no size'}</span>
              {l.size && l.variant && l.size !== l.variant && <span style={{ color: t.text3 }}>store: {l.variant}</span>}
              {l.price_cents != null && <span>{money(l.price_cents)}</span>}
            </div>
            {l.url && (
              <a href={l.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: t.accent, display: 'inline-flex', gap: 4, alignItems: 'center', marginTop: 8 }}>
                Store page <Icon name="arrow-up-right" size={12} />
              </a>
            )}
          </div>
        </div>
        {card.reading && <Reading reading={card.reading} />}
        {l.description && (
          <p style={{ fontSize: 13, color: t.text2, lineHeight: 1.5, margin: '12px 0 0', whiteSpace: 'pre-wrap' }}>{l.description}</p>
        )}
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
        {card.candidates.length === 0 && (
          <div style={{ ...panel, gridColumn: '1 / -1', color: t.text3 }}>No catalog entries to offer — N or C.</div>
        )}
        {card.candidates.map((c, i) => (
          <Candidate key={c.id} n={i + 1} c={c} onPick={() => onPick(c.id)} disabled={disabled} />
        ))}
      </section>
    </div>
  )
}

/** The catalog reading, step by step; an unsure step (p below SURE) stands out. */
function Reading({ reading }: { reading: ReviewReading }) {
  const p = reading.p ?? {}
  const steps: { label: string; value: string | null; p?: number }[] = [
    { label: 'category', value: reading.category, p: p.category },
    { label: 'subtype', value: reading.subtype, p: p.subtype },
    { label: 'line', value: reading.product_line, p: p.line ?? p.product_line },
    { label: 'strain', value: reading.strain, p: p.strain },
    { label: 'size', value: reading.size, p: p.size },
  ]
  return (
    <div style={{ marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {steps.map(s => {
        const unsure = s.p !== undefined && s.p < SURE
        return (
          <span key={s.label} style={{
            ...badge, fontSize: 12, padding: '3px 8px',
            background: unsure ? t.warningTint : t.surface2,
            color: unsure ? t.warning : t.text2,
            border: `1px solid ${unsure ? t.warningEdge : t.border}`,
          }}>
            <span style={{ color: unsure ? t.warning : t.text3 }}>{s.label}</span>{' '}
            <b style={{ fontWeight: 600 }}>{s.value ?? '—'}</b>
            {s.p !== undefined && <span style={{ fontFamily: font.family.mono, marginLeft: 4 }}>{Math.round(s.p * 100)}%</span>}
          </span>
        )
      })}
      {reading.store_category && (
        <span style={{ ...badge, fontSize: 12, padding: '3px 8px', background: t.surface2, color: t.text3 }}>store files it: {reading.store_category}</span>
      )}
    </div>
  )
}

function Candidate({ n, c, onPick, disabled }: { n: number; c: ReviewCandidate; onPick: () => void; disabled: boolean }) {
  return (
    <button
      onClick={onPick}
      disabled={disabled}
      style={{
        ...panel, textAlign: 'left', cursor: disabled ? 'default' : 'pointer', color: 'inherit',
        display: 'flex', flexDirection: 'column', gap: 8,
        borderColor: c.suggested ? t.accentDim : t.border,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Kbd>{String(n)}</Kbd>
        {c.suggested && <span style={{ ...badge, background: t.accentTint, color: t.accent }}>suggested</span>}
        {!c.is_active && <span style={{ ...badge, background: t.surface2, color: t.text3 }}>inactive</span>}
      </div>
      <ProductImage src={c.image_url} category={c.category} height={110} />
      <div style={{ fontWeight: 600, lineHeight: 1.3 }}>{c.name}</div>
      <div style={{ fontSize: 12, color: t.text3 }}>
        {[c.product_line, c.strain && c.strain !== c.name ? c.strain : null, c.subtype].filter(Boolean).join(' · ') || '—'}
      </div>
      <div style={{ fontFamily: font.family.mono, fontSize: 13 }}>{c.variant ?? 'no size'}</div>
    </button>
  )
}

function Bar({ label, decided, total }: { label: string; decided: number; total: number }) {
  const pct = total ? Math.round((decided / total) * 100) : 100
  return (
    <div style={{ ...panel, padding: '10px 14px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span style={{ color: t.text3, fontFamily: font.family.mono }}>{decided}/{total} · {total - decided} left</span>
      </div>
      <div style={{ height: 8, borderRadius: radius.pill, background: t.surface3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: pct === 100 ? t.success : t.accent, transition: 'width 300ms ease' }} />
      </div>
    </div>
  )
}

function Stat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div title={title} style={{ textAlign: 'right' }}>
      <div style={{ fontSize: 11, color: t.text3, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
      <div style={{ fontFamily: font.family.mono, fontSize: font.size.title, fontWeight: 600 }}>{value}</div>
    </div>
  )
}

function Action({ k, label, onClick, disabled, icon }: {
  k: string; label: string; onClick: () => void; disabled: boolean; icon?: 'undo'
}) {
  return (
    <button onClick={onClick} disabled={disabled} style={{ ...navBtnStyle, padding: '8px 12px', opacity: disabled ? 0.6 : 1 }}>
      {icon && <Icon name={icon} size={14} />}
      <Kbd>{k}</Kbd>{label}
    </button>
  )
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd style={{
      fontFamily: font.family.mono, fontSize: 11, minWidth: 18, textAlign: 'center',
      padding: '1px 5px', borderRadius: 4, border: `1px solid ${t.borderStrong}`, background: t.surface1, color: t.text2,
    }}>{children}</kbd>
  )
}

const panel: CSSProperties = {
  background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: 16,
}
