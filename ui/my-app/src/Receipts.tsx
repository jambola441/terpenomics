import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { badge, navBtnStyle } from './components/AdminTable'
import api from './api/client'
import type {
  AdminReceipt, AdminReceiptDetail, AdminReceiptQueue, ReceiptFlag, ReceiptOrderCandidate, ReceiptReading, ReceiptStatus,
} from './types'
import { inputStyle, money, primaryBtn, when } from './utils/partners'
import { t, font } from './theme'
import { Icon } from './components/Icon'

/**
 * Receipt review queue.
 *
 * Customers upload a receipt photo for a partner purchase the POS sync couldn't
 * match (no phone number at checkout, or a partner whose POS isn't connected).
 * The receipt reader (connectors/receipt_reader.py, in the 15-minute cron) has
 * usually read the photo already: its values pre-fill the form, its flags sit
 * above it, and when the store's POS is connected the matching synced sale is
 * offered with "Approve with this sale" (the order then earns the points). A
 * person still decides: approve by sale, approve by subtotal (before tax and
 * tip), or reject with a reason the customer will see.
 *
 * The queue is oldest-first so nobody waits longest; after each decision the
 * next pending receipt opens. Possible duplicates (the same customer's other
 * receipts, and synced orders at that store around that date) sit under the
 * form so they're checked before approving.
 */
const TABS: ReceiptStatus[] = ['pending', 'approved', 'rejected']

export default function Receipts() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('status') as ReceiptStatus) || 'pending'
  const selected = params.get('id')
  const [queue, setQueue] = useState<AdminReceiptQueue | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load(nextSelected?: string | null) {
    setError(null)
    try {
      const q = await api.receipts.list(tab)
      setQueue(q)
      const keep = nextSelected !== undefined ? nextSelected : selected
      const id = keep && q.items.some(r => r.id === keep) ? keep : q.items[0]?.id ?? null
      select(id, true)
    } catch (err: any) {
      setError(err.message)
    }
  }

  useEffect(() => { load() }, [tab])

  function select(id: string | null, replace = false) {
    const next = new URLSearchParams(params)
    next.set('status', tab)
    if (id) next.set('id', id)
    else next.delete('id')
    setParams(next, { replace })
  }

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h2 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Receipts</h2>
          <div style={{ display: 'flex', gap: 6 }}>
            {TABS.map(s => (
              <button
                key={s}
                onClick={() => setParams({ status: s })}
                style={{
                  ...navBtnStyle, textTransform: 'capitalize',
                  ...(s === tab ? { color: t.accent, borderColor: t.accentDim, background: t.accentTint } : {}),
                }}
              >
                {s}{queue ? ` · ${queue.counts[s]}` : ''}
              </button>
            ))}
          </div>
        </div>

        {error && <div style={{ color: t.danger, marginBottom: 12 }}>Error: {error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 300px) 1fr', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {!queue ? (
              <div style={muted}>Loading…</div>
            ) : queue.items.length === 0 ? (
              <div style={muted}>{tab === 'pending' ? 'Nothing to review — all caught up.' : `No ${tab} receipts.`}</div>
            ) : queue.items.map(r => <QueueItem key={r.id} r={r} active={r.id === selected} onClick={() => select(r.id)} />)}
          </div>

          <div>
            {selected
              ? <ReviewPanel key={selected} id={selected} onDone={() => load(null)} />
              : queue && queue.items.length > 0 && <div style={muted}>Pick a receipt.</div>}
          </div>
        </div>
      </div>
    </div>
  )
}

function QueueItem({ r, active, onClick }: { r: AdminReceipt; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        textAlign: 'left', cursor: 'pointer', padding: '10px 12px', borderRadius: 8,
        background: active ? t.surface2 : t.surface1, border: `1px solid ${active ? t.accentDim : t.border}`, color: 'inherit',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontWeight: 500, color: t.text1 }}>{r.partner_name}</span>
        {r.status === 'approved' && <span style={{ color: t.success, fontSize: 12 }}>+{r.points ?? 0}</span>}
      </div>
      <div style={{ fontSize: 12, color: t.text3, marginTop: 3 }}>
        {r.customer_name || r.customer_phone || 'Customer'} · {r.purchased_on ?? '—'}
      </div>
      <div style={{ fontSize: 11, color: t.text3, marginTop: 2 }}>
        uploaded {when(r.created_at)}
        {r.status === 'pending' && r.read_status !== 'read' ? ` · ${r.read_status === 'failed' ? 'not readable' : 'not read yet'}` : ''}
      </div>
    </button>
  )
}

function ReviewPanel({ id, onDone }: { id: string; onDone: () => void }) {
  const [r, setR] = useState<AdminReceiptDetail | null>(null)
  const [img, setImg] = useState<string | null>(null)
  const [imgError, setImgError] = useState<string | null>(null)
  const [subtotal, setSubtotal] = useState('')
  const [day, setDay] = useState('')
  const [partnerId, setPartnerId] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let url: string | null = null
    api.receipts.get(id).then(d => {
      setR(d)
      // Pre-fill from what the reader found; the reviewer corrects anything wrong.
      const read = d.status === 'pending' ? d.reading.read : null
      const readPartner = read?.partner_id && d.partners.some(p => p.id === read.partner_id) ? read.partner_id : null
      setDay(read?.purchase_date ?? d.purchased_on ?? d.created_at.slice(0, 10))
      setPartnerId(readPartner ?? d.partner_id)
      const cents = d.subtotal_cents ?? read?.subtotal_cents ?? null
      setSubtotal(cents != null ? (cents / 100).toFixed(2) : '')
      if (d.status === 'pending' && d.reading.suggestion === 'reject_duplicate') {
        setReason('This purchase already earned points through the phone number on your account.')
      }
    }).catch(err => setError(err.message))
    api.receipts.imageUrl(id).then(u => { url = u; setImg(u) }).catch(err => setImgError(err.message))
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [id])

  const cents = useMemo(() => {
    const v = Number(subtotal.replace(/[$,\s]/g, ''))
    return Number.isFinite(v) && v > 0 ? Math.round(v * 100) : null
  }, [subtotal])

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onDone()
    } catch (err: any) {
      setError(err.message)
      setBusy(false)
    }
  }

  if (!r) return <div style={muted}>{error ? `Error: ${error}` : 'Loading…'}</div>

  const pending = r.status === 'pending'
  const preview = cents != null ? Math.floor(cents * r.points_per_dollar / 100) : null
  const sameCustomerOrders = r.nearby_orders.filter(o => o.same_customer)
  const reading = r.reading
  const readSubtotal = pending ? reading.read?.subtotal_cents ?? null : null

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(280px, 380px)', gap: 20, alignItems: 'start' }}>
      {/* Photo */}
      <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 10, padding: 10, minHeight: 300 }}>
        {img ? (
          <a href={img} target="_blank" rel="noreferrer" title="Open full size">
            <img src={img} alt="Receipt" style={{ width: '100%', borderRadius: 6, display: 'block' }} />
          </a>
        ) : (
          <div style={muted}>{imgError ?? 'Loading photo…'}</div>
        )}
        {r.image_content_type.includes('heic') || r.image_content_type.includes('heif') ? (
          <div style={{ ...muted, fontSize: 12, marginTop: 6 }}>HEIC photo — if it doesn't show, open it full size.</div>
        ) : null}
      </div>

      {/* Form */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{r.customer_name || 'Customer'}</div>
          <div style={{ fontSize: 13, color: t.text3 }}>{r.customer_phone} · uploaded {when(r.created_at)}</div>
          {r.customer_note && <div style={{ fontSize: 13, color: t.text2, marginTop: 8, fontStyle: 'italic' }}>“{r.customer_note}”</div>}
        </div>

        {pending && reading.flags.map(f => <Flag key={f.code} tone={f.level}>{f.message}</Flag>)}
        {!pending && r.stale && <Flag tone="warn">Purchase date is more than 30 days ago.</Flag>}
        {pending && reading.read && <ReadSummary reading={reading} />}
        {pending && reading.has_pos && (
          <SquareMatches
            reading={reading}
            pointsPerDollar={r.points_per_dollar}
            busy={busy}
            onUse={o => {
              const pts = Math.floor(o.subtotal_cents * r.points_per_dollar / 100)
              if (window.confirm(`Approve with the ${money(o.total_cents)} sale from ${when(o.ordered_at)}? It earns ${pts} points.`)) {
                act(() => api.receipts.approve(id, { pos_order_id: o.id }))
              }
            }}
          />
        )}
        {sameCustomerOrders.length > 0 && !reading.flags.some(f => f.code === 'already_earned') && (
          <Flag tone="warn">
            This customer already has {sameCustomerOrders.length} synced order{sameCustomerOrders.length === 1 ? '' : 's'} at this
            store around this date — check it isn't the same purchase.
          </Flag>
        )}
        {r.duplicate_receipts.length > 0 && (
          <Flag tone="warn">
            {r.duplicate_receipts.length} other receipt{r.duplicate_receipts.length === 1 ? '' : 's'} from this customer at this store
            within 2 days: {r.duplicate_receipts.map(d => `${d.purchased_on ?? '?'} (${d.status}${d.subtotal_cents != null ? `, ${money(d.subtotal_cents)}` : ''})`).join('; ')}
          </Flag>
        )}

        {pending ? (
          <form
            onSubmit={e => {
              e.preventDefault()
              if (cents == null) return
              act(() => api.receipts.approve(id, { subtotal_cents: cents, purchased_on: day, partner_id: partnerId }))
            }}
            style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
          >
            <Field label="Store">
              <select value={partnerId} onChange={e => setPartnerId(e.target.value)} style={{ ...inputStyle, width: '100%' }}>
                {r.partners.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Purchase date">
              <input type="date" value={day} onChange={e => setDay(e.target.value)} style={{ ...inputStyle, width: '100%', boxSizing: 'border-box' }} />
            </Field>
            {reading.has_pos && (
              <div style={{ fontSize: 11, color: t.text3, fontFamily: font.family.mono, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Or approve by subtotal
              </div>
            )}
            <Field label={readSubtotal != null && cents === readSubtotal ? 'Subtotal (before tax and tip) · read from the photo' : 'Subtotal (before tax and tip)'}>
              <input
                autoFocus={!reading.best_order_id}
                inputMode="decimal"
                placeholder="0.00"
                value={subtotal}
                onChange={e => setSubtotal(e.target.value)}
                style={{ ...inputStyle, width: '100%', boxSizing: 'border-box', fontSize: 18 }}
              />
            </Field>
            <div style={{ fontSize: 13, color: t.text2 }}>
              {preview != null
                ? <>Awards <b style={{ color: t.success }}>{preview} point{preview === 1 ? '' : 's'}</b>, available {r.pending_days} days after the purchase.</>
                : 'Enter the subtotal to see the points.'}
            </div>
            <button type="submit" disabled={busy || cents == null} style={primaryBtn(busy || cents == null)}>
              {busy ? 'Saving…' : reading.has_pos ? 'Approve by subtotal' : 'Approve'}
            </button>

            <div style={{ borderTop: `1px solid ${t.border}`, paddingTop: 12, display: 'flex', gap: 8 }}>
              <input
                placeholder="Reason, shown to the customer"
                value={reason}
                onChange={e => setReason(e.target.value)}
                style={{ ...inputStyle, flex: 1 }}
              />
              <button
                type="button"
                disabled={busy || !reason.trim()}
                onClick={() => act(() => api.receipts.reject(id, reason))}
                style={{ ...navBtnStyle, color: t.danger, borderColor: t.dangerEdge, opacity: busy || !reason.trim() ? 0.5 : 1 }}
              >
                Reject
              </button>
            </div>
          </form>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
            <div>
              <span style={{ ...badge, ...(r.status === 'approved' ? { background: t.successTint, color: t.success } : { background: t.dangerTint, color: t.danger }) }}>
                {r.status}
              </span>
              <span style={{ color: t.text3, marginLeft: 8 }}>by {r.reviewed_by} · {when(r.reviewed_at)}</span>
            </div>
            {r.status === 'approved' && (
              <div>
                {r.partner_name} · {r.purchased_on} · subtotal {money(r.subtotal_cents ?? 0)} · <b style={{ color: t.success }}>+{r.points} points</b>
                {r.pos_order_id && <div style={{ color: t.text3, marginTop: 4 }}>Approved with the matching Square sale; refunds on it adjust these points.</div>}
              </div>
            )}
            {r.reject_reason && <div style={{ color: t.danger }}>{r.reject_reason}</div>}
            {r.status === 'approved' && (
              <div style={{ display: 'flex', gap: 8, borderTop: `1px solid ${t.border}`, paddingTop: 12 }}>
                <input placeholder="Why void it?" value={reason} onChange={e => setReason(e.target.value)} style={{ ...inputStyle, flex: 1 }} />
                <button
                  disabled={busy || !reason.trim()}
                  onClick={() => {
                    if (window.confirm(`Void this receipt and take back ${r.points} points?`)) act(() => api.receipts.void(id, reason))
                  }}
                  style={{ ...navBtnStyle, color: t.danger, borderColor: t.dangerEdge, opacity: busy || !reason.trim() ? 0.5 : 1 }}
                >
                  Void
                </button>
              </div>
            )}
          </div>
        )}

        {error && <div style={{ color: t.danger, fontSize: 13 }}>{error}</div>}

        {r.nearby_orders.length > 0 && (
          <div>
            <div style={{ fontSize: 11, color: t.text3, fontFamily: font.family.mono, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
              Synced orders at this store around this date
            </div>
            {r.nearby_orders.map(o => (
              <div key={o.id} style={{ display: 'flex', gap: 10, fontSize: 12, padding: '4px 0', color: o.same_customer ? t.warning : t.text2 }}>
                <span style={{ flex: 1 }}>{when(o.ordered_at)}</span>
                <span>subtotal {money(o.subtotal_cents)}</span>
                <span>{o.same_customer ? 'this customer' : o.matched ? 'other member' : 'unmatched'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const muted: CSSProperties = { color: t.text3, fontSize: 13, lineHeight: 1.7 }

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5, fontSize: 12, color: t.text2 }}>
      {label}
      {children}
    </label>
  )
}

const FLAG_TONES: Record<ReceiptFlag['level'], CSSProperties> = {
  bad: { background: t.dangerTint, border: `1px solid ${t.dangerEdge}`, color: t.danger },
  warn: { background: t.warningTint, border: `1px solid ${t.warningEdge}`, color: t.warning },
  info: { background: t.surface1, border: `1px solid ${t.border}`, color: t.text2 },
}

function Flag({ tone, children }: { tone: ReceiptFlag['level']; children: ReactNode }) {
  return (
    <div style={{ fontSize: 12, lineHeight: 1.5, padding: '8px 10px', borderRadius: 6, ...FLAG_TONES[tone] }}>
      {children}
    </div>
  )
}

const label: CSSProperties = { fontSize: 11, color: t.text3, fontFamily: font.family.mono, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }

/** What Claude read off the photo, compact, so the reviewer can check it against the image. */
function ReadSummary({ reading }: { reading: ReceiptReading }) {
  const read = reading.read!
  const amount = (c: number | null) => (c == null ? '—' : money(c))
  const rows: [string, string][] = [
    ['Store', read.merchant_name ?? '—'],
    ['When', [read.purchase_date, read.purchase_time].filter(Boolean).join(' ') || '—'],
    ['Subtotal', amount(read.subtotal_cents)],
    ['Tax · Tip', `${amount(read.tax_cents)} · ${amount(read.tip_cents)}`],
    ['Total', amount(read.total_cents)],
    ['Card', read.card_last4 ? `${read.card_brand ?? 'Card'} ${read.card_last4}` : '—'],
  ]
  if (read.receipt_number) rows.push(['Receipt #', read.receipt_number])
  return (
    <div>
      <div style={label}>Read from the photo · {read.confidence} confidence</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 12px', fontSize: 12 }}>
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}>
            <span style={{ color: t.text3 }}>{k}</span>
            <span style={{ color: t.text2 }}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const SIGNAL_LABEL: Record<string, string> = {
  total: 'total', subtotal: 'subtotal', tax: 'tax', card: 'card', time: 'time', time_close: 'about the time',
  date: 'date', receipt_number: 'receipt #',
}

/** Synced sales at this store that share something with the receipt, best first. */
function SquareMatches({ reading, pointsPerDollar, busy, onUse }: {
  reading: ReceiptReading
  pointsPerDollar: number
  busy: boolean
  onUse: (o: ReceiptOrderCandidate) => void
}) {
  if (reading.candidates.length === 0) return null
  return (
    <div>
      <div style={label}>Matching sales in the store's Square</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {reading.candidates.map(o => {
          const best = o.id === reading.best_order_id
          const usable = o.claimed === null && o.strength !== 'weak'
          return (
            <div key={o.id} style={{
              padding: '8px 10px', borderRadius: 8, fontSize: 12,
              background: best ? t.successTint : t.surface1, border: `1px solid ${best ? t.successEdge : t.border}`,
            }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <b style={{ color: t.text1, fontSize: 13 }}>{money(o.total_cents)}</b>
                <span style={{ color: t.text2, flex: 1 }}>{when(o.ordered_at)}{o.cards.length ? ` · ${o.cards.join(', ')}` : ''}</span>
                <span style={{ color: o.strength === 'exact' ? t.success : o.strength === 'likely' ? t.warning : t.text3 }}>{o.strength}</span>
              </div>
              <div style={{ color: t.text3, marginTop: 3 }}>
                matches {o.signals.map(sig => SIGNAL_LABEL[sig] ?? sig).join(', ')} · earns {Math.floor(o.subtotal_cents * pointsPerDollar / 100)} pts
                {o.claimed === 'this_customer' ? ' · already earned by this customer' : o.claimed === 'other_customer' ? ' · already earned by another customer' : ''}
              </div>
              {usable && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onUse(o)}
                  style={{ ...primaryBtn(busy), marginTop: 8, padding: '6px 12px', fontSize: 12 }}
                >
                  Approve with this sale
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
