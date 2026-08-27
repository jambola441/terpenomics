import type { Order, OrderStatus } from '../types'
import { t, radius, font, alpha } from '../theme'
import { formatDate, formatDollars } from '../utils/format'

const ORDER_STATUS_STYLE: Record<OrderStatus, { label: string; color: string; hint: string }> = {
  submitted: { label: 'Submitted', color: '#f0b93b', hint: 'The store is preparing your order.' },
  ready:     { label: 'Ready',     color: '#4ac97e', hint: 'Waiting at the counter — pay when you collect it.' },
  completed: { label: 'Picked up', color: 'var(--text-3)', hint: '' },
  cancelled: { label: 'Cancelled', color: 'var(--danger)', hint: '' },
}

export default function OrderCard({ order, onCancel, cancelling }: {
  order: Order
  onCancel: (orderId: string) => void
  cancelling: boolean
}) {
  const style = ORDER_STATUS_STYLE[order.status]
  const open = order.status === 'submitted' || order.status === 'ready'

  return (
    <div style={{
      background: t.surface2, border: `1px solid ${t.border}`,
      borderRadius: radius.lg, padding: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{
            color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.body,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {order.dispensary_name}
          </div>
          <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
            {formatDate(order.submitted_at)} · {order.items.length} item{order.items.length === 1 ? '' : 's'}
          </div>
        </div>
        <span style={{
          flexShrink: 0, borderRadius: radius.pill, padding: '4px 10px',
          fontSize: font.size.small, fontWeight: font.weight.bold,
          color: style.color, background: alpha(style.color, 0.12),
          border: `1px solid ${alpha(style.color, 0.3)}`,
        }}>
          {style.label}
        </span>
      </div>

      {/* The code is only useful while the order is still collectable. */}
      {open && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: 12, marginTop: 12, padding: '10px 12px',
          background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.md,
        }}>
          <div>
            <div style={{
              color: t.text3, fontSize: font.size.small,
              textTransform: 'uppercase', letterSpacing: '0.07em',
            }}>
              Pickup code
            </div>
            <div style={{
              color: t.accent, fontWeight: font.weight.bold, fontSize: 20,
              letterSpacing: '0.12em', fontVariantNumeric: 'tabular-nums', marginTop: 2,
            }}>
              {order.pickup_code}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: t.text3, fontSize: font.size.small }}>Due at pickup</div>
            <div style={{
              color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout,
              fontVariantNumeric: 'tabular-nums', marginTop: 2,
            }}>
              {formatDollars(order.total_amount_cents)}
            </div>
          </div>
        </div>
      )}

      {style.hint && (
        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 10, lineHeight: 1.5 }}>
          {style.hint}
        </div>
      )}

      <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {order.items.map(item => (
          <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <span style={{
              color: t.text2, fontSize: font.size.small, minWidth: 0,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {item.quantity > 1 ? `${item.quantity}× ` : ''}{item.name}
              {item.variant ? ` · ${item.variant}` : ''}
            </span>
            <span style={{
              color: t.text3, fontSize: font.size.small, flexShrink: 0,
              fontVariantNumeric: 'tabular-nums',
            }}>
              {formatDollars(item.line_amount_cents)}
            </span>
          </div>
        ))}
      </div>

      {!open && (
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          marginTop: 12, paddingTop: 10, borderTop: `1px solid ${t.border}`,
        }}>
          <span style={{ color: t.text3, fontSize: font.size.small }}>Total</span>
          <span style={{
            color: t.text2, fontWeight: font.weight.semibold, fontSize: font.size.small,
            fontVariantNumeric: 'tabular-nums',
          }}>
            {formatDollars(order.total_amount_cents)}
          </span>
        </div>
      )}

      {open && (
        <button
          onClick={() => onCancel(order.id)}
          disabled={cancelling}
          style={{
            width: '100%', marginTop: 12, boxSizing: 'border-box',
            background: 'transparent', border: `1px solid ${t.border}`,
            borderRadius: radius.md, color: t.text3,
            fontSize: font.size.small, fontWeight: font.weight.semibold,
            padding: '9px 0', cursor: cancelling ? 'default' : 'pointer',
          }}
        >
          {cancelling ? 'Cancelling…' : 'Cancel order'}
        </button>
      )}
    </div>
  )
}
