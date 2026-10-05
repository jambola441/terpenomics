import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { badge, navBtnStyle } from './components/AdminTable'
import api from './api/client'
import type { AdminReceipt, AdminReceiptDetail, AdminReceiptQueue, ReceiptStatus } from './types'
import { inputStyle, money, primaryBtn, when } from './utils/partners'

/**
 * Receipt review queue.
 *
 * Customers upload a receipt photo for a partner purchase the POS sync couldn't
 * match (no phone number at checkout, or a partner whose POS isn't connected).
 * Here a person reads the subtotal — before tax and tip — off the photo,
 * confirms the store and date, and approves it, which awards points at the
 * usual rate. Or rejects it with a reason the customer will see.
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
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Receipts</h2>
          <div style={{ display: 'flex', gap: 6 }}>
            {TABS.map(s => (
              <button
                key={s}
                onClick={() => setParams({ status: s })}
                style={{
                  ...navBtnStyle, textTransform: 'capitalize',
                  ...(s === tab ? { color: '#e0e7ff', borderColor: '#4338ca', background: '#1e1b4b' } : {}),
                }}
              >
                {s}{queue ? ` · ${queue.counts[s]}` : ''}
              </button>
            ))}
          </div>
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 12 }}>Error: {error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 300px) 1fr', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {!queue ? (
              <div style={muted}>Loading…</div>
            ) : queue.items.length === 0 ? (
              <div style={muted}>{tab === 'pending' ? 'Nothing to review. 🎉' : `No ${tab} receipts.`}</div>
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
        background: active ? '#111827' : '#0f172a', border: `1px solid ${active ? '#4338ca' : '#1e293b'}`, color: 'inherit',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontWeight: 500, color: '#f1f5f9' }}>{r.partner_name}</span>
        {r.status === 'approved' && <span style={{ color: '#86efac', fontSize: 12 }}>+{r.points ?? 0}</span>}
      </div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>
        {r.customer_name || r.customer_phone || 'Customer'} · {r.purchased_on ?? '—'}
      </div>
      <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>uploaded {when(r.created_at)}</div>
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
      setDay(d.purchased_on ?? d.created_at.slice(0, 10))
      setPartnerId(d.partner_id)
      setSubtotal(d.subtotal_cents != null ? (d.subtotal_cents / 100).toFixed(2) : '')
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

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(280px, 380px)', gap: 20, alignItems: 'start' }}>
      {/* Photo */}
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 10, minHeight: 300 }}>
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
          <div style={{ fontSize: 13, color: '#64748b' }}>{r.customer_phone} · uploaded {when(r.created_at)}</div>
          {r.customer_note && <div style={{ fontSize: 13, color: '#cbd5e1', marginTop: 8, fontStyle: 'italic' }}>“{r.customer_note}”</div>}
        </div>

        {r.stale && <Flag tone="warn">Purchase date is more than 30 days ago.</Flag>}
        {sameCustomerOrders.length > 0 && (
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
            <Field label="Subtotal (before tax and tip)">
              <input
                autoFocus
                inputMode="decimal"
                placeholder="0.00"
                value={subtotal}
                onChange={e => setSubtotal(e.target.value)}
                style={{ ...inputStyle, width: '100%', boxSizing: 'border-box', fontSize: 18 }}
              />
            </Field>
            <div style={{ fontSize: 13, color: '#94a3b8' }}>
              {preview != null
                ? <>Awards <b style={{ color: '#86efac' }}>{preview} point{preview === 1 ? '' : 's'}</b>, available {r.pending_days} days after the purchase.</>
                : 'Enter the subtotal to see the points.'}
            </div>
            <button type="submit" disabled={busy || cents == null} style={primaryBtn(busy || cents == null)}>
              {busy ? 'Saving…' : 'Approve'}
            </button>

            <div style={{ borderTop: '1px solid #1e293b', paddingTop: 12, display: 'flex', gap: 8 }}>
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
                style={{ ...navBtnStyle, color: '#fca5a5', borderColor: '#7f1d1d', opacity: busy || !reason.trim() ? 0.5 : 1 }}
              >
                Reject
              </button>
            </div>
          </form>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
            <div>
              <span style={{ ...badge, ...(r.status === 'approved' ? { background: '#14532d', color: '#86efac' } : { background: '#450a0a', color: '#fca5a5' }) }}>
                {r.status}
              </span>
              <span style={{ color: '#64748b', marginLeft: 8 }}>by {r.reviewed_by} · {when(r.reviewed_at)}</span>
            </div>
            {r.status === 'approved' && (
              <div>{r.partner_name} · {r.purchased_on} · subtotal {money(r.subtotal_cents ?? 0)} · <b style={{ color: '#86efac' }}>+{r.points} points</b></div>
            )}
            {r.reject_reason && <div style={{ color: '#fca5a5' }}>{r.reject_reason}</div>}
            {r.status === 'approved' && (
              <div style={{ display: 'flex', gap: 8, borderTop: '1px solid #1e293b', paddingTop: 12 }}>
                <input placeholder="Why void it?" value={reason} onChange={e => setReason(e.target.value)} style={{ ...inputStyle, flex: 1 }} />
                <button
                  disabled={busy || !reason.trim()}
                  onClick={() => {
                    if (window.confirm(`Void this receipt and take back ${r.points} points?`)) act(() => api.receipts.void(id, reason))
                  }}
                  style={{ ...navBtnStyle, color: '#fca5a5', borderColor: '#7f1d1d', opacity: busy || !reason.trim() ? 0.5 : 1 }}
                >
                  Void
                </button>
              </div>
            )}
          </div>
        )}

        {error && <div style={{ color: '#f87171', fontSize: 13 }}>{error}</div>}

        {r.nearby_orders.length > 0 && (
          <div>
            <div style={{ fontSize: 11, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              Synced orders at this store around this date
            </div>
            {r.nearby_orders.map(o => (
              <div key={o.id} style={{ display: 'flex', gap: 10, fontSize: 12, padding: '4px 0', color: o.same_customer ? '#fbbf24' : '#94a3b8' }}>
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

const muted: CSSProperties = { color: '#475569', fontSize: 13, lineHeight: 1.7 }

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5, fontSize: 12, color: '#94a3b8' }}>
      {label}
      {children}
    </label>
  )
}

function Flag({ tone, children }: { tone: 'warn'; children: ReactNode }) {
  return (
    <div style={{
      fontSize: 12, lineHeight: 1.5, padding: '8px 10px', borderRadius: 6,
      ...(tone === 'warn' ? { background: '#422006', border: '1px solid #713f12', color: '#fbbf24' } : {}),
    }}>
      {children}
    </div>
  )
}
