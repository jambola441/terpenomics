import { useState } from 'react'
import Checkout from './Checkout'
import type { CartItem, Order } from '../types'
import { t, radius, font } from '../theme'

interface CartDrawerProps {
  items: CartItem[]
  open: boolean
  onClose: () => void
  onRemove: (listingId: string) => void
  onClear: () => void
  onPlaced: (order: Order) => void
  onViewOrders: () => void
}

export default function CartDrawer({ items, open, onClose, onRemove, onClear, onPlaced, onViewOrders }: CartDrawerProps) {
  const [checkingOut, setCheckingOut] = useState(false)
  const total = items.reduce((sum, i) => sum + (i.price_cents ?? 0) * i.quantity, 0)
  const dispensaryName = items[0]?.dispensaryName ?? ''

  // The drawer is reused for checkout, so reopening it must always land on the
  // cart rather than on a stale checkout step.
  function close() {
    setCheckingOut(false)
    onClose()
  }

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          onClick={close}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
            zIndex: 2200, backdropFilter: 'blur(2px)',
          }}
        />
      )}

      {/* Drawer */}
      <div style={{
        position: 'fixed',
        bottom: 0, left: 0, right: 0,
        background: t.surface1,
        borderTop: `1px solid ${t.border}`,
        borderRadius: `${radius['2xl']} ${radius['2xl']} 0 0`,
        zIndex: 2300,
        transform: open ? 'translateY(0)' : 'translateY(100%)',
        transition: 'transform 0.32s cubic-bezier(0.32, 0.72, 0, 1)',
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
            <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, letterSpacing: '-0.01em' }}>
              {checkingOut ? 'Confirm pickup order' : 'Your cart'}
            </div>
            {dispensaryName && (
              <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>{dispensaryName}</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {items.length > 0 && !checkingOut && (
              <button
                onClick={onClear}
                style={{
                  background: 'transparent', border: `1px solid ${t.border}`,
                  borderRadius: radius.sm, color: t.text3, fontSize: font.size.small,
                  padding: '6px 11px', cursor: 'pointer',
                }}
              >
                Clear
              </button>
            )}
            <button
              onClick={close}
              aria-label="Close cart"
              style={{
                background: t.surface2, border: `1px solid ${t.border}`,
                borderRadius: radius.sm, color: t.text2, fontSize: 18,
                width: 32, height: 32, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              ×
            </button>
          </div>
        </div>

        {checkingOut ? (
          <Checkout
            items={items}
            onBack={() => setCheckingOut(false)}
            onPlaced={onPlaced}
            onViewOrders={() => { setCheckingOut(false); onViewOrders() }}
            onClose={close}
          />
        ) : (
        <>
        {/* Items */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '16px 20px 0' }}>
          {items.length === 0 ? (
            <div style={{ color: t.text3, fontSize: font.size.body, textAlign: 'center', padding: '40px 0' }}>
              <div style={{ fontSize: 30, marginBottom: 10 }}>🛒</div>
              Your cart is empty
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {items.map(item => (
                <div key={item.listingId} style={{
                  display: 'flex', gap: 12, alignItems: 'center',
                  background: t.surface2, borderRadius: radius.lg, padding: 12, border: `1px solid ${t.border}`,
                }}>
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt=""
                      style={{ width: 48, height: 48, borderRadius: radius.sm, objectFit: 'contain', background: t.tile, padding: 4, boxSizing: 'border-box', flexShrink: 0 }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  ) : (
                    <div style={{ width: 48, height: 48, borderRadius: radius.sm, background: t.surface3, flexShrink: 0 }} />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.body, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.name}
                    </div>
                    {item.variant && (
                      <div style={{ color: t.text3, fontSize: font.size.small }}>{item.variant}</div>
                    )}
                    {item.price_cents != null && (
                      <div style={{ color: t.accent, fontWeight: font.weight.bold, fontSize: font.size.small + 1, marginTop: 2 }}>
                        ${(item.price_cents / 100).toFixed(2)}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => onRemove(item.listingId)}
                    aria-label="Remove item"
                    style={{
                      background: 'transparent', border: 'none',
                      color: t.text3, fontSize: 18, cursor: 'pointer',
                      padding: '4px 8px', flexShrink: 0,
                    }}
                  >
                    ×
                  </button>
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
                <span style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title }}>
                  ${(total / 100).toFixed(2)}
                </span>
              </div>
            )}
            <button
              onClick={() => setCheckingOut(true)}
              style={{
                display: 'block', width: '100%', boxSizing: 'border-box',
                background: t.accent, border: 'none', borderRadius: radius.lg,
                color: t.accentInk, fontWeight: font.weight.bold, fontSize: font.size.callout,
                padding: '14px', textAlign: 'center', cursor: 'pointer',
                boxShadow: 'var(--e-1)',
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
