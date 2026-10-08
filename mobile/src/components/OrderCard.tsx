import { Text, View } from 'react-native'
import type { Order, OrderStatus } from '@web/types'
import { formatDate, formatDollars } from '@web/utils/format'
import { Button, Label, Pill, StoreBullet, styles, type Tone } from './ui'
import type { IconName } from './Icon'
import { t, space, font, fonts, radius, type } from '@/lib/theme'

// Mirrors ORDER_STATUS_STYLE in the web OrderCard: a word, a glyph and a tone,
// so the state never rests on colour alone.
const STATUS: Record<OrderStatus, { label: string; tone: Tone; icon: IconName; hint: string }> = {
  submitted: { label: 'Submitted', tone: 'warning', icon: 'clock', hint: 'The store is preparing your order.' },
  ready: { label: 'Ready', tone: 'success', icon: 'check-circle', hint: 'Waiting at the counter — pay when you collect it.' },
  completed: { label: 'Picked up', tone: 'neutral', icon: 'check', hint: '' },
  cancelled: { label: 'Cancelled', tone: 'danger', icon: 'x-circle', hint: '' },
}

export default function OrderCard({ order, cancelling, onCancel }: {
  order: Order
  cancelling?: boolean
  onCancel?: () => void
}) {
  const s = STATUS[order.status]
  const open = order.status === 'submitted' || order.status === 'ready'
  const store = order.dispensary_name ?? 'Order'

  return (
    <View style={[styles.card, { padding: space[4], gap: space[2] }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[3] }}>
        <StoreBullet name={store} address={order.dispensary_address} />
        <Text style={[type.title, { flex: 1, fontSize: font.size.title, lineHeight: 22 }]} numberOfLines={1}>{store}</Text>
        <Pill tone={s.tone} icon={s.icon}>{s.label}</Pill>
      </View>
      <Text style={styles.meta}>
        {formatDate(order.submitted_at)} · {order.items.length} item{order.items.length === 1 ? '' : 's'} ·{' '}
        <Text style={{ fontFamily: fonts.sansSemibold, color: t.text2, fontVariant: ['tabular-nums'] }}>
          {formatDollars(order.total_amount_cents)}
        </Text>
      </Text>

      {open ? (
        <View style={{ backgroundColor: t.surface2, borderRadius: radius.md, borderWidth: 1, borderColor: t.border, padding: space[3], marginTop: space[1], gap: space[1] }}>
          <Label>Pickup code</Label>
          <Text style={type.code}>{order.pickup_code}</Text>
          {s.hint ? <Text style={styles.meta}>{s.hint}</Text> : null}
        </View>
      ) : null}

      {order.items.map(item => (
        <View key={item.id} style={{ flexDirection: 'row', alignItems: 'baseline', gap: space[2] }}>
          <Text style={[type.mono, { color: t.text3, minWidth: 24 }]}>{item.quantity}×</Text>
          <Text style={[type.meta, { color: t.text2, flex: 1 }]} numberOfLines={1}>{item.name}</Text>
        </View>
      ))}

      {open && onCancel ? (
        <Button title="Cancel order" variant="danger" onPress={onCancel} loading={cancelling} style={{ marginTop: space[2] }} />
      ) : null}
    </View>
  )
}
