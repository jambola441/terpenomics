import { useState } from 'react'
import api from '../api/client'
import type { CartItem, Order } from '../types'
import { t, radius, font, alpha } from '../theme'
import { Spinner } from './ui'

/**
 * Checkout for a pickup order.
 *
 * Nothing is charged here and the screen says so more than once: the payment
 * notice sits above the submit button, not buried in fine print, because the
 * customer is agreeing to show up and pay a real total at a counter. The button
 * says "Place pickup order", never "Pay" or "Buy".
 */

function money(cents: number) {
  return `$${(cents / 100).toFixed(2)}`
}

// ─── Pay-at-store notice ──────────────────────────────────────────────────────

function PaymentNotice() {
  return (
    <div style={{
      display: 'flex',
      gap: 12,
      alignItems: 'flex-start',
      background: alpha('#f0b93b', 0.1),
      border: `1px solid ${alpha('#f0b93b', 0.32)}`,
      borderRadius: radius.lg,
      padding: '14px 16px',
    }}>
      <div style={{ fontSize: 18, lineHeight: 1.2, flexShrink: 0 }} aria-hidden>💵</div>
      <div style={{ minWidth: 0 }}>
        <div style={{
          color: '#f0b93b', fontWeight: font.weight.bold,
          fontSize: font.size.body, marginBottom: 3,
        }}>
          You pay at the store
        </div>
        <div style={{ color: t.text2, fontSize: font.size.small, lineHeight: 1.5 }}>
          No card is charged now. Your items are held at the counter and you pay
          when you pick them up. Bring a valid ID.
        </div>
      </div>
    </div>
  )
}

// ─── Confirmation ─────────────────────────────────────────────────────────────

function Confirmation({ order, onDone, onViewOrders }: {
  order: Order
  onDone: () => void
  onViewOrders: () => void
}) {
  return (
    <div style={{ padding: '8px 20px 20px', textAlign: 'center' }}>
      <div style={{
        width: 60, height: 60, borderRadius: '50%', margin: '4px auto 16px',
        background: alpha('#4ac97e', 0.14), border: `1px solid ${alpha('#4ac97e', 0.4)}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 26,
      }} aria-hidden>✓</div>

      <div style={{
        color: t.text1, fontWeight: font.weight.bold,
        fontSize: font.size.title, letterSpacing: '-0.01em',
      }}>
        Order placed
      </div>
      <div style={{ color: t.text3, fontSize: font.size.body, marginTop: 6, lineHeight: 1.5 }}>
        {order.dispensary_name} is getting it ready.
      </div>

      {/* The code is the whole point of the confirmation — give it the room. */}
      <div style={{
        marginTop: 22, padding: '18px 16px',
        background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.lg,
      }}>
        <div style={{
          color: t.text3, fontSize: font.size.small,
          textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
        }}>
          Pickup code
        </div>
        <div style={{
          color: t.accent, fontWeight: font.weight.bold, fontSize: 32,
          letterSpacing: '0.16em', fontVariantNumeric: 'tabular-nums',
        }}>
          {order.pickup_code}
        </div>
        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 10, lineHeight: 1.5 }}>
          Show this at the counter. You'll pay {money(order.total_amount_cents)} in store.
        </div>
      </div>

      {order.dispensary_address && (
        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 14, lineHeight: 1.5 }}>
          {order.dispensary_address}
        </div>
      )}

      <button
        onClick={onViewOrders}
        style={{
          width: '100%', marginTop: 22, boxSizing: 'border-box',
          background: t.accent, border: 'none', borderRadius: radius.lg,
          color: t.accentInk, fontWeight: font.weight.bold, fontSize: font.size.callout,
          padding: 14, cursor: 'pointer',
        }}
      >
        View my orders
      </button>
      <button
        onClick={onDone}
        style={{
          width: '100%', marginTop: 10, boxSizing: 'border-box',
          background: 'transparent', border: `1px solid ${t.border}`, borderRadius: radius.lg,
          color: t.text2, fontWeight: font.weight.semibold, fontSize: font.size.callout,
          padding: 13, cursor: 'pointer',
        }}
      >
        Keep browsing
      </button>
    </div>
  )
}

// ─── Review + submit ──────────────────────────────────────────────────────────

interface CheckoutProps {
  items: CartItem[]
  onBack: () => void
  /** Called once the order exists, so the cart can be emptied. */
  onPlaced: (order: Order) => void
  onViewOrders: () => void
  onClose: () => void
}

export default function Checkout({ items, onBack, onPlaced, onViewOrders, onClose }: CheckoutProps) {
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [placed, setPlaced] = useState<Order | null>(null)

  const dispensaryId = items[0]?.dispensaryId
  const dispensaryName = items[0]?.dispensaryName ?? ''
  // Priced client-side only to show a subtotal; the server reprices from the
  // listings and its number is the one that ends up on the order.
  const total = items.reduce((sum, i) => sum + (i.price_cents ?? 0) * i.quantity, 0)
  const anyUnpriced = items.some(i => i.price_cents == null)

  async function handleSubmit() {
    if (!dispensaryId || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const order = await api.orders.create({
        dispensary_id: dispensaryId,
        items: items.map(i => ({ listing_id: i.listingId, quantity: i.quantity })),
        note: note.trim() || undefined,
      })
      setPlaced(order)
      onPlaced(order)
    } catch (err) {
      // The server's message is the useful one here — it names the item that
      // went out of stock, or says the store stopped taking orders.
      const raw = err instanceof Error ? err.message : ''
      let message = raw
      try {
        const parsed = JSON.parse(raw)
        if (parsed?.detail) message = String(parsed.detail)
      } catch {
        // not JSON — fall through to the raw text
      }
      setError(message || 'Could not place your order. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (placed) {
    return <Confirmation order={placed} onDone={onClose} onViewOrders={onViewOrders} />
  }

  return (
    <>
      <div style={{ overflowY: 'auto', flex: 1, padding: '4px 20px 0' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <PaymentNotice />

          {/* Itemized review */}
          <div>
            <div style={{
              color: t.text3, fontSize: font.size.small, textTransform: 'uppercase',
              letterSpacing: '0.06em', marginBottom: 8,
            }}>
              {items.length} item{items.length === 1 ? '' : 's'} from {dispensaryName}
            </div>
            <div style={{
              background: t.surface2, border: `1px solid ${t.border}`,
              borderRadius: radius.lg, overflow: 'hidden',
            }}>
              {items.map((item, idx) => (
                <div
                  key={item.listingId}
                  style={{
                    display: 'flex', gap: 12, alignItems: 'center', padding: '12px 14px',
                    borderTop: idx === 0 ? 'none' : `1px solid ${t.border}`,
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.body,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>
                      {item.name}
                    </div>
                    <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
                      {[item.variant, item.quantity > 1 ? `×${item.quantity}` : null]
                        .filter(Boolean).join(' · ')}
                    </div>
                  </div>
                  <div style={{
                    color: t.text2, fontSize: font.size.body, flexShrink: 0,
                    fontVariantNumeric: 'tabular-nums',
                  }}>
                    {item.price_cents != null ? money(item.price_cents * item.quantity) : '—'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Note for the store */}
          <div>
            <label
              htmlFor="order-note"
              style={{
                display: 'block', color: t.text3, fontSize: font.size.small,
                textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8,
              }}
            >
              Note for the store (optional)
            </label>
            <textarea
              id="order-note"
              value={note}
              onChange={e => setNote(e.target.value)}
              maxLength={500}
              rows={2}
              placeholder="Anything they should know?"
              style={{
                width: '100%', boxSizing: 'border-box', resize: 'none',
                background: t.surface2, border: `1px solid ${t.border}`,
                borderRadius: radius.lg, color: t.text1,
                fontSize: font.size.body, fontFamily: 'inherit', padding: '11px 13px',
              }}
            />
          </div>

          {error && (
            <div
              role="alert"
              style={{
                background: alpha('#e5484d', 0.1), border: `1px solid ${alpha('#e5484d', 0.32)}`,
                borderRadius: radius.lg, color: t.danger,
                fontSize: font.size.small, padding: '11px 13px', lineHeight: 1.5,
              }}
            >
              {error}
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div style={{ padding: 20, borderTop: `1px solid ${t.border}`, marginTop: 14 }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          alignItems: 'baseline', marginBottom: 4,
        }}>
          <span style={{ color: t.text2, fontSize: font.size.body }}>Due at pickup</span>
          <span style={{
            color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title,
            fontVariantNumeric: 'tabular-nums',
          }}>
            {money(total)}
          </span>
        </div>
        <div style={{ color: t.text3, fontSize: font.size.small, marginBottom: 14, lineHeight: 1.5 }}>
          {anyUnpriced
            ? 'Some items have no listed price — the store will confirm the total.'
            : 'Taxes are calculated in store, so the final total may differ.'}
        </div>

        <button
          onClick={handleSubmit}
          disabled={submitting}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: submitting ? t.surface3 : t.accent,
            border: 'none', borderRadius: radius.lg,
            color: submitting ? t.text3 : t.accentInk,
            fontWeight: font.weight.bold, fontSize: font.size.callout,
            padding: 14, cursor: submitting ? 'default' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            boxShadow: submitting ? 'none' : 'var(--e-1)',
          }}
        >
          {submitting ? <><Spinner size={15} /> Placing order…</> : 'Place pickup order'}
        </button>
        <button
          onClick={onBack}
          disabled={submitting}
          style={{
            width: '100%', marginTop: 10, boxSizing: 'border-box',
            background: 'transparent', border: `1px solid ${t.border}`, borderRadius: radius.lg,
            color: t.text3, fontWeight: font.weight.semibold, fontSize: font.size.callout,
            padding: 13, cursor: submitting ? 'default' : 'pointer',
          }}
        >
          Back to cart
        </button>
      </div>
    </>
  )
}
