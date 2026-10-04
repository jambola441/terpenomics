import { Text, View } from 'react-native'
import type { Order, OrderStatus } from '@web/types'
import { formatDate, formatDollars } from '@web/utils/format'
import { Button, styles } from './ui'
import { t, space, font, radius } from '@/lib/theme'

// Mirrors ORDER_STATUS_STYLE in the web OrderCard.
const STATUS: Record<OrderStatus, { label: string; color: string; hint: string }> = {
  submitted: { label: 'Submitted', color: '#f0b93b', hint: 'The store is preparing your order.' },
  ready: { label: 'Ready', color: '#4ac97e', hint: 'Waiting at the counter — pay when you collect it.' },
  completed: { label: 'Picked up', color: t.text3, hint: '' },
  cancelled: { label: 'Cancelled', color: t.danger, hint: '' },
}

export default function OrderCard({ order, cancelling, onCancel }: {
  order: Order
  cancelling?: boolean
  onCancel?: () => void
}) {
  const s = STATUS[order.status]
  const open = order.status === 'submitted' || order.status === 'ready'

  return (
    <View style={[styles.card, { padding: space[4], gap: space[2] }]}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={[styles.name, { fontSize: font.size.callout }]}>{order.dispensary_name ?? 'Order'}</Text>
        <Text style={{ color: s.color, fontWeight: font.weight.bold, fontSize: font.size.small }}>{s.label}</Text>
      </View>
      <Text style={styles.meta}>
        {formatDate(order.submitted_at)} · {order.items.length} item{order.items.length === 1 ? '' : 's'} · {formatDollars(order.total_amount_cents)}
      </Text>

      {open ? (
        <View style={{ backgroundColor: t.surface2, borderRadius: radius.md, padding: space[3], marginTop: space[1] }}>
          <Text style={styles.meta}>Pickup code</Text>
          <Text style={{ color: t.text1, fontSize: font.size.hero, fontWeight: font.weight.heavy, letterSpacing: 2 }}>
            {order.pickup_code}
          </Text>
          {s.hint ? <Text style={[styles.meta, { marginTop: space[1] }]}>{s.hint}</Text> : null}
        </View>
      ) : null}

      {order.items.map(item => (
        <Text key={item.id} style={{ color: t.text2, fontSize: font.size.small }} numberOfLines={1}>
          {item.quantity} × {item.name}
        </Text>
      ))}

      {open && onCancel ? (
        <Button title="Cancel order" variant="danger" onPress={onCancel} loading={cancelling} style={{ marginTop: space[2] }} />
      ) : null}
    </View>
  )
}
