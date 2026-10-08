/* ============================================================================
   OrdersScreen — the Orders tab.

   The pickup code is what a shopper shows at the counter, so orders have their
   own tab rather than sitting two taps down under You. The shell owns the list
   (it also refreshes it while an order is open); this draws it.
   ========================================================================== */

import type { Order } from '../types'
import { t } from '../theme'
import { FeedState, PageTitle } from './ui'
import OrderCard from './OrderCard'

export default function OrdersScreen({
  orders, loading, error, onCancelOrder, onRetry, cancellingIds, cancelErrors,
}: {
  orders: Order[]
  loading: boolean
  /** Loading the list failed. A failed cancel is per card, not this. */
  error: string | null
  onCancelOrder: (orderId: string) => void
  onRetry: () => void
  cancellingIds: Set<string>
  /** A failed cancel, by order id. Shown on that order's card only. */
  cancelErrors: Record<string, string>
}) {
  const open = orders.filter(o => o.status === 'submitted' || o.status === 'ready').length

  return (
    <div style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      <PageTitle
        style={{ padding: 'calc(env(safe-area-inset-top, 0px) + 26px) 16px 6px' }}
        sub={open > 0
          ? `${open} open · show the code at the counter`
          : 'Pickup orders and their codes'}
      >
        Orders
      </PageTitle>

      <div style={{ padding: '14px 16px 28px', maxWidth: 560, margin: '0 auto' }}>
        {loading ? (
          <FeedState kind="loading" message="Loading your orders…" />
        ) : error ? (
          <FeedState kind="error" message={error} onRetry={onRetry} />
        ) : orders.length === 0 ? (
          <FeedState
            kind="empty"
            message="No orders yet"
            hint="Orders you place for pickup show up here with their pickup code."
            icon="bag"
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {orders.map(order => (
              <OrderCard
                key={order.id}
                order={order}
                onCancel={onCancelOrder}
                cancelling={cancellingIds.has(order.id)}
                cancelError={cancelErrors[order.id] ?? null}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
