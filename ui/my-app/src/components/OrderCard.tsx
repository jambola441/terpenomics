import type { Order, OrderStatus } from '../types'
import { t, radius, font, tone, type Tone } from '../theme'
import { formatDate, formatDollars } from '../utils/format'
import { Icon, type IconName } from './Icon'

const ORDER_STATUS_STYLE: Record<OrderStatus, { label: string; tone: Tone; icon: IconName; hint: string }> = {
  submitted: { label: 'Preparing', tone: 'warning', icon: 'clock', hint: 'The store is preparing your order.' },
  ready:     { label: 'Ready',     tone: 'success', icon: 'check-circle', hint: 'Waiting at the counter — pay when you collect it.' },
  completed: { label: 'Picked up', tone: 'neutral', icon: 'check', hint: '' },
  cancelled: { label: 'Cancelled', tone: 'danger', icon: 'x-circle', hint: '' },
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
      background: t.surface1, border: `1px solid ${t.border}`,
      borderRadius: radius.lg, padding: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{
            color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold, fontSize: font.size.title,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {order.dispensary_name}
          </div>
          <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
            {formatDate(order.submitted_at)} · {order.items.length} item{order.items.length === 1 ? '' : 's'}
          </div>
        </div>
        <span style={{
          flexShrink: 0, borderRadius: radius.pill, padding: '4px 10px 4px 8px',
          display: 'inline-flex', alignItems: 'center', gap: 5,
          fontFamily: font.family.mono, fontSize: font.size.caption, fontWeight: font.weight.medium,
          textTransform: 'uppercase', letterSpacing: '0.06em',
          color: tone[style.tone].fg, background: tone[style.tone].bg,
          border: `1px solid ${tone[style.tone].edge}`,
        }}>
          <Icon name={style.icon} size={13} strokeWidth={2} />
          {style.label}
        </span>
      </div>

      {/* The code is only useful while the order is still collectable. */}
      {open && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: 12, marginTop: 14, padding: '12px 14px',
          // A ticket stub: the code is what gets shown at the counter.
          background: t.bg, border: `1px dashed ${t.borderStrong}`, borderRadius: radius.md,
        }}>
          <div>
            <div style={{
              color: t.text3, fontFamily: font.family.mono, fontSize: font.size.caption,
              textTransform: 'uppercase', letterSpacing: '0.08em',
            }}>
              Pickup code
            </div>
            <div style={{
              color: t.text1, fontFamily: font.family.mono, fontWeight: font.weight.medium, fontSize: 24,
              letterSpacing: '0.14em', fontVariantNumeric: 'tabular-nums', marginTop: 2,
            }}>
              {order.pickup_code}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.caption, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Due at pickup</div>
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
            background: 'transparent', border: `1px solid ${t.borderStrong}`,
            borderRadius: radius.md, color: t.text2,
            fontSize: font.size.small + 1, fontWeight: font.weight.medium,
            padding: '9px 0', cursor: cancelling ? 'default' : 'pointer',
          }}
        >
          {cancelling ? 'Cancelling…' : 'Cancel order'}
        </button>
      )}
    </div>
  )
}
