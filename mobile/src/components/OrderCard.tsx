import { useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import type { Order, OrderStatus } from '@web/types'
import { formatDate, formatDollars } from '@web/utils/format'
import { Label, Pill, styles, type Tone } from './ui'
import type { IconName } from './Icon'
import { t, font, fonts, radius, type } from '@/lib/theme'

// The web OrderCard's ORDER_STATUS_STYLE: a word, a glyph and a tone, so the
// state never rests on colour alone.
const STATUS: Record<OrderStatus, { label: string; tone: Tone; icon: IconName; hint: string }> = {
  submitted: { label: 'Preparing', tone: 'warning', icon: 'clock', hint: 'The store is preparing your order.' },
  ready: { label: 'Ready', tone: 'success', icon: 'check-circle', hint: 'Waiting at the counter — pay when you collect it.' },
  completed: { label: 'Picked up', tone: 'neutral', icon: 'check', hint: '' },
  cancelled: { label: 'Cancelled', tone: 'danger', icon: 'x-circle', hint: '' },
}

/** One pickup order, as on the web: store and status, the code as a ticket
 *  stub while it can still be collected, the lines, and a cancel that takes a
 *  second, deliberate tap (it sits right under the code shown at the counter). */
export default function OrderCard({ order, cancelling = false, cancelError = null, onCancel }: {
  order: Order
  cancelling?: boolean
  /** Why the last cancel failed, if it did. */
  cancelError?: string | null
  onCancel?: () => void
}) {
  const st = STATUS[order.status]
  const open = order.status === 'submitted' || order.status === 'ready'
  const [confirming, setConfirming] = useState(false)

  return (
    <View style={[styles.card, { padding: 16 }]}>
      <View style={s.head}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={[type.title, { fontSize: font.size.title, lineHeight: 22 }]}>{order.dispensary_name}</Text>
          <Text style={[type.meta, { fontSize: font.size.small, marginTop: 2 }]}>
            {formatDate(order.submitted_at)} · {order.items.length} item{order.items.length === 1 ? '' : 's'}
          </Text>
        </View>
        <Pill tone={st.tone} icon={st.icon} size="md">{st.label}</Pill>
      </View>

      {open ? (
        <View style={s.stub}>
          <View>
            <Label>Pickup code</Label>
            <Text style={s.code} accessibilityLabel={`Pickup code ${order.pickup_code.split('').join(' ')}`}>{order.pickup_code}</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Label>Due at pickup</Label>
            <Text style={[type.price, { fontSize: font.size.callout, marginTop: 2 }]}>{formatDollars(order.total_amount_cents)}</Text>
          </View>
        </View>
      ) : null}

      {st.hint ? <Text style={[type.meta, { fontSize: font.size.small, lineHeight: 19, marginTop: 10 }]}>{st.hint}</Text> : null}

      <View style={{ marginTop: 12, gap: 6 }}>
        {order.items.map(item => (
          <View key={item.id} style={s.itemRow}>
            <Text numberOfLines={1} style={[type.body, { color: t.text2, fontSize: font.size.small, flex: 1 }]}>
              {item.quantity > 1 ? `${item.quantity}× ` : ''}{item.name}{item.variant ? ` · ${item.variant}` : ''}
            </Text>
            <Text style={[type.meta, { fontSize: font.size.small, fontVariant: ['tabular-nums'] }]}>{formatDollars(item.line_amount_cents)}</Text>
          </View>
        ))}
      </View>

      {!open ? (
        <View style={s.total}>
          <Text style={[type.meta, { fontSize: font.size.small }]}>Total</Text>
          <Text style={[type.body, { color: t.text2, fontFamily: fonts.sansSemibold, fontSize: font.size.small, fontVariant: ['tabular-nums'] }]}>
            {formatDollars(order.total_amount_cents)}
          </Text>
        </View>
      ) : null}

      {open && onCancel && !confirming ? (
        <Pressable
          onPress={() => setConfirming(true)}
          disabled={cancelling}
          accessibilityRole="button"
          style={({ pressed }) => [s.cancel, pressed && { backgroundColor: t.surface2 }]}
        >
          <Text style={s.cancelText}>{cancelling ? 'Cancelling…' : 'Cancel order'}</Text>
        </Pressable>
      ) : null}

      {open && onCancel && confirming ? (
        <View style={s.confirm}>
          <Text style={type.bodyStrong}>Cancel this order?</Text>
          <Text style={[type.body, { color: t.text2, fontSize: font.size.small, lineHeight: 19, marginTop: 3 }]}>
            The store stops preparing it. To get these items you&apos;d need to order again.
          </Text>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
            <Pressable onPress={() => setConfirming(false)} accessibilityRole="button" style={[s.answer, s.keep]}>
              <Text style={type.bodyStrong}>Keep order</Text>
            </Pressable>
            <Pressable
              onPress={() => { setConfirming(false); onCancel() }}
              accessibilityRole="button"
              style={[s.answer, { borderColor: t.dangerEdge }]}
            >
              <Text style={[type.bodyStrong, { color: t.danger }]}>Yes, cancel it</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {open && cancelError ? (
        <Text accessibilityRole="alert" style={[type.body, { color: t.danger, fontSize: font.size.small, lineHeight: 19, marginTop: 8 }]}>
          {cancelError}
        </Text>
      ) : null}
    </View>
  )
}

const s = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  stub: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12,
    marginTop: 14, paddingVertical: 12, paddingHorizontal: 14, backgroundColor: t.bg,
    borderWidth: 1, borderStyle: 'dashed', borderColor: t.borderStrong, borderRadius: radius.md,
  },
  code: { fontFamily: fonts.monoMedium, fontSize: 24, lineHeight: 30, letterSpacing: 3.4, color: t.text1, marginTop: 2, fontVariant: ['tabular-nums'] },
  itemRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  total: {
    flexDirection: 'row', justifyContent: 'space-between', marginTop: 12, paddingTop: 10,
    borderTopWidth: 1, borderTopColor: t.border,
  },
  cancel: {
    minHeight: 44, marginTop: 12, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: t.borderStrong, borderRadius: radius.md,
  },
  cancelText: { fontFamily: fonts.sansMedium, fontSize: font.size.small + 1, color: t.text2 },
  confirm: {
    marginTop: 12, padding: 12, borderRadius: radius.md,
    backgroundColor: t.dangerTint, borderWidth: 1, borderColor: t.dangerEdge,
  },
  answer: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radius.md, borderWidth: 1 },
  keep: { backgroundColor: t.surface2, borderColor: t.borderStrong },
})
