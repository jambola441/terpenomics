/* Admin queue for pickup orders.

   Staff work this as a queue, so the default filter is the open work rather
   than all history, and the pickup code is the leftmost column — it is what a
   customer says at the counter, so it is what gets matched against.

   No money is handled here. "Picked up" records that the customer collected the
   order and paid in store; nothing in this app takes payment. */

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api, { type AdminOrderRow, type AdminOrderDetail } from './api/client'
import type { OrderStatus } from './types'
import { AdminTable, navBtnStyle, selectStyle, badge, pageWrap, Dash, type Column } from './components/AdminTable'

const STATUS_COLORS: Record<OrderStatus, { background: string; color: string }> = {
  submitted: { background: '#422006', color: '#fcd34d' },
  ready:     { background: '#052e16', color: '#86efac' },
  completed: { background: '#1e293b', color: '#94a3b8' },
  cancelled: { background: '#450a0a', color: '#fca5a5' },
}

const STATUS_LABELS: Record<OrderStatus, string> = {
  submitted: 'Submitted',
  ready: 'Ready',
  completed: 'Picked up',
  cancelled: 'Cancelled',
}

function dollars(cents: number | null | undefined) {
  if (cents == null) return '—'
  return `$${(cents / 100).toFixed(2)}`
}

export default function Orders() {
  const [rows, setRows] = useState<AdminOrderRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(true)
  const [status, setStatus] = useState<string>('submitted')
  const [limit, setLimit] = useState<number>(50)
  const [selected, setSelected] = useState<AdminOrderDetail | null>(null)
  const [updating, setUpdating] = useState(false)
  const navigate = useNavigate()

  const queryKey = useMemo(() => `${status}|${limit}`, [status, limit])

  useEffect(() => {
    void load(true)
  }, [queryKey])

  async function load(reset: boolean = true) {
    setLoading(true)
    setError(null)
    try {
      const offset = reset ? 0 : rows.length
      const data = await api.adminOrders.list({
        status: (status || undefined) as OrderStatus | undefined,
        limit,
        offset,
      })
      setRows(prev => (reset ? data : [...prev, ...data]))
      setHasMore(data.length === limit)
    } catch (e: any) {
      setError(e?.message ?? String(e))
      if (reset) setRows([])
    } finally {
      setLoading(false)
    }
  }

  async function openOrder(id: string) {
    setError(null)
    try {
      setSelected(await api.adminOrders.get(id))
    } catch (e: any) {
      setError(e?.message ?? String(e))
    }
  }

  async function advance(next: Exclude<OrderStatus, 'submitted'>) {
    if (!selected || updating) return
    setUpdating(true)
    setError(null)
    try {
      const updated = await api.adminOrders.setStatus(selected.id, next)
      setSelected(updated)
      // Reload rather than patching in place: the row may no longer belong in
      // the current filter once its status changed.
      void load(true)
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setUpdating(false)
    }
  }

  const columns: Column<AdminOrderRow>[] = [
    {
      key: 'code', header: 'Code',
      td: { fontFamily: 'ui-monospace, monospace', color: '#f1f5f9', fontWeight: 600, letterSpacing: '0.05em' },
      render: r => r.pickup_code,
    },
    {
      key: 'status', header: 'Status',
      render: r => (
        <span style={{ ...badge, ...STATUS_COLORS[r.status] }}>{STATUS_LABELS[r.status]}</span>
      ),
    },
    { key: 'placed', header: 'Placed', render: r => new Date(r.submitted_at).toLocaleString() },
    { key: 'dispensary', header: 'Dispensary', render: r => r.dispensary_name ?? <Dash /> },
    {
      key: 'customer', header: 'Customer', td: { color: '#f1f5f9', fontWeight: 500 },
      render: r => r.customer_name ?? r.customer_id,
    },
    { key: 'phone', header: 'Phone', render: r => r.customer_phone ?? <Dash /> },
    {
      key: 'items', header: 'Items', align: 'right', th: { textAlign: 'right' },
      render: r => r.item_count ?? <Dash />,
    },
    {
      key: 'total', header: 'Due at pickup', align: 'right',
      th: { textAlign: 'right' }, td: { fontVariantNumeric: 'tabular-nums' },
      render: r => dollars(r.total_amount_cents),
    },
  ]

  return (
    <div style={pageWrap}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 8 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Pickup orders</h2>
          <button onClick={() => load(true)} disabled={loading} style={{ ...navBtnStyle, marginLeft: 'auto' }}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
        <p style={{ fontSize: 13, color: '#475569', margin: '0 0 20px' }}>
          Customers pay in store. Marking an order picked up records collection, not payment.
        </p>

        <div style={{ display: 'flex', gap: 8, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={status} onChange={e => setStatus(e.target.value)} style={selectStyle}>
            <option value="submitted">Submitted</option>
            <option value="ready">Ready</option>
            <option value="completed">Picked up</option>
            <option value="cancelled">Cancelled</option>
            <option value="">All statuses</option>
          </select>
          <select value={String(limit)} onChange={e => setLimit(Number(e.target.value))} style={selectStyle}>
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="200">200</option>
          </select>
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>Error: {error}</div>}

        {rows.length > 0 && (
          <p style={{ fontSize: 13, color: '#475569', marginBottom: 12 }}>Showing {rows.length} order(s)</p>
        )}

        {loading && rows.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : rows.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>No orders found.</div>
        ) : (
          <AdminTable
            columns={columns}
            rows={rows}
            rowKey={r => r.id}
            onRowClick={r => openOrder(r.id)}
          />
        )}

        {loading && rows.length > 0 && (
          <div style={{ padding: 16, color: '#475569', textAlign: 'center' }}>Loading more…</div>
        )}

        {!loading && hasMore && rows.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button onClick={() => load(false)} style={navBtnStyle}>Load more</button>
          </div>
        )}
      </div>

      {selected && (
        <OrderDrawer
          order={selected}
          updating={updating}
          onAdvance={advance}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

function OrderDrawer({ order, updating, onAdvance, onClose }: {
  order: AdminOrderDetail
  updating: boolean
  onAdvance: (next: Exclude<OrderStatus, 'submitted'>) => void
  onClose: () => void
}) {
  return (
    <>
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 40 }}
      />
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(460px, 100%)',
        background: '#0b1220', borderLeft: '1px solid #1e293b', zIndex: 50,
        overflowY: 'auto', padding: 24, boxSizing: 'border-box',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <div style={{
              fontFamily: 'ui-monospace, monospace', fontSize: 26, fontWeight: 700,
              color: '#f1f5f9', letterSpacing: '0.08em',
            }}>
              {order.pickup_code}
            </div>
            <div style={{ marginTop: 6 }}>
              <span style={{ ...badge, ...STATUS_COLORS[order.status] }}>{STATUS_LABELS[order.status]}</span>
            </div>
          </div>
          <button onClick={onClose} style={navBtnStyle}>Close</button>
        </div>

        <dl style={{ margin: '22px 0 0', fontSize: 13, color: '#94a3b8', display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 16px' }}>
          <dt>Customer</dt>
          <dd style={{ margin: 0, color: '#f1f5f9' }}>{order.customer_name ?? '—'}</dd>
          <dt>Phone</dt>
          <dd style={{ margin: 0 }}>{order.customer_phone ?? '—'}</dd>
          <dt>Email</dt>
          <dd style={{ margin: 0, overflowWrap: 'anywhere' }}>{order.customer_email ?? '—'}</dd>
          <dt>Dispensary</dt>
          <dd style={{ margin: 0 }}>{order.dispensary_name ?? '—'}</dd>
          <dt>Placed</dt>
          <dd style={{ margin: 0 }}>{new Date(order.submitted_at).toLocaleString()}</dd>
        </dl>

        {order.note && (
          <div style={{
            marginTop: 18, padding: 12, borderRadius: 6,
            background: '#0f172a', border: '1px solid #1e293b',
            fontSize: 13, color: '#cbd5e1', lineHeight: 1.5,
          }}>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#475569', marginBottom: 5 }}>
              Customer note
            </div>
            {order.note}
          </div>
        )}

        <div style={{ marginTop: 22 }}>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#475569', marginBottom: 10 }}>
            Items
          </div>
          {order.items.map(item => (
            <div key={item.id} style={{
              display: 'flex', justifyContent: 'space-between', gap: 12,
              padding: '9px 0', borderTop: '1px solid #1e293b', fontSize: 13,
            }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ color: '#f1f5f9' }}>
                  {item.quantity > 1 ? `${item.quantity}× ` : ''}{item.name}
                </div>
                <div style={{ color: '#475569', fontSize: 12, marginTop: 2 }}>
                  {[item.brand, item.variant].filter(Boolean).join(' · ') || '—'}
                </div>
              </div>
              <div style={{ color: '#cbd5e1', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
                {dollars(item.line_amount_cents)}
              </div>
            </div>
          ))}
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            padding: '12px 0 0', marginTop: 4, borderTop: '1px solid #1e293b',
            fontSize: 14, fontWeight: 600, color: '#f1f5f9',
          }}>
            <span>Due at pickup</span>
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>{dollars(order.total_amount_cents)}</span>
          </div>
          <div style={{ fontSize: 12, color: '#475569', marginTop: 6 }}>
            Collected in store — this app never charges a card.
          </div>
        </div>

        {/* The server decides what is legal; this only renders what it allows. */}
        <div style={{ marginTop: 26, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {order.allowed_transitions.length === 0 ? (
            <div style={{ fontSize: 13, color: '#475569' }}>
              This order is {STATUS_LABELS[order.status].toLowerCase()} — nothing left to do.
            </div>
          ) : (
            order.allowed_transitions.map(next => (
              <button
                key={next}
                onClick={() => onAdvance(next as Exclude<OrderStatus, 'submitted'>)}
                disabled={updating}
                style={{
                  ...navBtnStyle,
                  padding: '9px 16px',
                  cursor: updating ? 'default' : 'pointer',
                  ...(next === 'cancelled'
                    ? { color: '#fca5a5', borderColor: '#450a0a' }
                    : { background: '#14532d', borderColor: '#166534', color: '#86efac', fontWeight: 600 }),
                }}
              >
                {updating ? 'Saving…' : next === 'ready' ? 'Mark ready'
                  : next === 'completed' ? 'Mark picked up' : 'Cancel order'}
              </button>
            ))
          )}
        </div>
      </div>
    </>
  )
}
