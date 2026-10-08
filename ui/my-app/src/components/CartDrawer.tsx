import { useId, useRef, useState, type CSSProperties } from 'react'
import Checkout from './Checkout'
import type { CartItem, Order } from '../types'
import { t, radius, font } from '../theme'
import { Icon } from './Icon'
import { FeedState, ProductImage } from './ui'
import { useDialog } from '../hooks/useDialog'

interface CartDrawerProps {
  items: CartItem[]
  open: boolean
  onClose: () => void
  onRemove: (listingId: string) => void
  /** Zero removes the line. */
  onSetQuantity: (listingId: string, quantity: number) => void
  /** The backend's per-line limit. */
  maxQuantity: number
  onClear: () => void
  onPlaced: (order: Order) => void
  onViewOrders: () => void
}

export default function CartDrawer({
  items, open, onClose, onRemove, onSetQuantity, maxQuantity, onClear, onPlaced, onViewOrders,
}: CartDrawerProps) {
  const [checkingOut, setCheckingOut] = useState(false)
  // While an order is being placed the drawer can't be closed: the request
  // would finish behind it, empty the cart and never show the pickup code.
  const [placing, setPlacing] = useState(false)
  const [placed, setPlaced] = useState(false)
  const total = items.reduce((sum, i) => sum + (i.price_cents ?? 0) * i.quantity, 0)
  const dispensaryName = items[0]?.dispensaryName ?? ''
  const drawer = useRef<HTMLDivElement>(null)
  const titleId = useId()

  // The drawer is reused for checkout, so reopening it must always land on the
  // cart rather than on a stale checkout step.
  function close() {
    if (placing) return
    setCheckingOut(false)
    setPlaced(false)
    onClose()
  }

  useDialog(drawer, open, { onEscape: close })

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          onClick={close}
          aria-hidden
          style={{
            position: 'fixed', inset: 0, background: t.scrim,
            zIndex: 2200, backdropFilter: 'blur(2px)',
          }}
        />
      )}

      {/* Drawer. Inert while closed: it stays mounted for the slide, and its
          buttons must not be reachable by Tab off-screen. */}
      <div
        ref={drawer}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        inert={!open}
        style={{
        position: 'fixed',
        bottom: 0, left: 0, right: 0,
        background: t.surface1,
        borderTop: `1px solid ${t.border}`,
        borderRadius: `${radius['2xl']} ${radius['2xl']} 0 0`,
        zIndex: 2300,
        transform: open ? 'translateY(0)' : 'translateY(100%)',
        // Hidden once it has slid away, so it leaves the accessibility tree
        // too; shown at once when opening.
        visibility: open ? 'visible' : 'hidden',
        transition: open
          ? 'transform 0.32s cubic-bezier(0.32, 0.72, 0, 1)'
          : 'transform 0.32s cubic-bezier(0.32, 0.72, 0, 1), visibility 0s linear 0.32s',
        maxHeight: '80dvh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: 'var(--e-3)',
      }}>
        {/* Handle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: t.surface3 }} />
        </div>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px 0' }}>
          <div>
            <h2 id={titleId} style={{ margin: 0, color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold, fontSize: font.size.display, letterSpacing: '-0.02em' }}>
              {placed ? 'Order placed' : checkingOut ? 'Confirm pickup order' : 'Your cart'}
            </h2>
            {dispensaryName && (
              <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>{dispensaryName}</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {items.length > 0 && !checkingOut && (
              <button
                onClick={onClear}
                style={{
                  background: 'transparent', border: `1px solid ${t.borderStrong}`,
                  borderRadius: radius.md, color: t.text2, fontSize: font.size.small + 1,
                  padding: '6px 11px', cursor: 'pointer',
                }}
              >
                Clear
              </button>
            )}
            <button
              onClick={close}
              disabled={placing}
              aria-label="Close cart"
              style={{
                background: t.surface2, border: `1px solid ${t.border}`,
                borderRadius: radius.pill, color: t.text2,
                width: 34, height: 34, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        </div>

        {checkingOut ? (
          <Checkout
            items={items}
            onBack={() => setCheckingOut(false)}
            onPlaced={order => { setPlaced(true); onPlaced(order) }}
            onSubmittingChange={setPlacing}
            onViewOrders={() => { setCheckingOut(false); onViewOrders() }}
            onClose={close}
          />
        ) : (
        <>
        {/* Items */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '16px 20px 0' }}>
          {items.length === 0 ? (
            <FeedState kind="empty" message="Your cart is empty" hint="Add something from a store that takes pickup orders." icon="bag" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {items.map(item => (
                <div key={item.listingId} style={{
                  display: 'flex', gap: 12, alignItems: 'center',
                  background: t.surface2, borderRadius: radius.lg, padding: 12, border: `1px solid ${t.border}`,
                }}>
                  <ProductImage src={item.image_url} height={52} pad={4} radius={radius.md} style={{ width: 52, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.body, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.name}
                    </div>
                    {item.variant && (
                      <div style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.caption, marginTop: 2 }}>{item.variant}</div>
                    )}
                    {item.price_cents != null && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', columnGap: 6, marginTop: 3 }}>
                        <span className="num" style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.body }}>
                          ${((item.price_cents * item.quantity) / 100).toFixed(2)}
                        </span>
                        {item.quantity > 1 && (
                          <span className="num" style={{ color: t.text3, fontSize: font.size.small, whiteSpace: 'nowrap' }}>
                            ${(item.price_cents / 100).toFixed(2)} each
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <QuantityStepper
                    name={item.name}
                    quantity={item.quantity}
                    max={maxQuantity}
                    onChange={q => (q <= 0 ? onRemove(item.listingId) : onSetQuantity(item.listingId, q))}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {items.length > 0 && (
          <div style={{ padding: 20, borderTop: `1px solid ${t.border}`, marginTop: 16 }}>
            {total > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <span style={{ color: t.text2, fontSize: font.size.body }}>Estimated total</span>
                <span className="num" style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title }}>
                  ${(total / 100).toFixed(2)}
                </span>
              </div>
            )}
            <button
              onClick={() => setCheckingOut(true)}
              style={{
                display: 'block', width: '100%', boxSizing: 'border-box',
                background: t.accent, border: 'none', borderRadius: radius.md,
                color: t.accentInk, fontWeight: font.weight.bold, fontSize: font.size.callout,
                padding: '14px', textAlign: 'center', cursor: 'pointer',
              }}
            >
              Checkout · pay at the store
            </button>
          </div>
        )}
        </>
        )}
        <div style={{ height: 'env(safe-area-inset-bottom, 0px)' }} />
      </div>
    </>
  )
}

/** − n + for one cart line. At one, minus becomes remove, so there is one way
 *  to take a line out rather than a second button beside the stepper. */
function QuantityStepper({ name, quantity, max, onChange }: {
  name: string
  quantity: number
  max: number
  onChange: (quantity: number) => void
}) {
  const atMax = quantity >= max
  const button = (disabled: boolean): CSSProperties => ({
    width: 40, height: 40, borderRadius: radius.pill, border: 'none', background: 'transparent',
    color: disabled ? t.text4 : t.text1, cursor: disabled ? 'default' : 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
  })
  return (
    <div style={{
      display: 'flex', alignItems: 'center', flexShrink: 0,
      background: t.surface3, border: `1px solid ${t.borderStrong}`, borderRadius: radius.pill, padding: 2,
    }}>
      <button
        onClick={() => onChange(quantity - 1)}
        aria-label={quantity <= 1 ? `Remove ${name}` : `One fewer ${name}`}
        style={button(false)}
      >
        <Icon name={quantity <= 1 ? 'trash' : 'minus'} size={16} strokeWidth={2} />
      </button>
      <span className="num" aria-live="polite" style={{
        minWidth: 22, textAlign: 'center', color: t.text1,
        fontWeight: font.weight.bold, fontSize: font.size.body,
      }}>
        {quantity}
      </span>
      <button
        onClick={() => !atMax && onChange(quantity + 1)}
        disabled={atMax}
        aria-label={atMax ? `${max} is the most per order` : `One more ${name}`}
        title={atMax ? `Up to ${max} of one item per order` : undefined}
        style={button(atMax)}
      >
        <Icon name="plus" size={16} strokeWidth={2} />
      </button>
    </div>
  )
}
