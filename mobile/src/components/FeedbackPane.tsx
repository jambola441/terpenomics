import { useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import type { Feedback } from '@web/types'
import { alpha, categoryStyle } from '@web/design/tokens'
import { formatDate, formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { FeedState, Label, ProductImage, categoryName } from './ui'
import { Icon, type IconName } from './Icon'
import { t, font, fonts, radius, space } from '@/lib/theme'

const RATINGS: { value: Exclude<Feedback, null>; icon: IconName; color: string; label: string }[] = [
  { value: 'like', icon: 'thumbs-up', color: t.success, label: 'Liked it' },
  { value: 'neutral', icon: 'face-neutral', color: t.text2, label: 'It was OK' },
  { value: 'dislike', icon: 'thumbs-down', color: t.danger, label: "Didn't like it" },
]

/** You → Feedback, as on the web portal: rating a past purchase is the only
 *  signal the recommender has, so this makes the un-rated items easy to find
 *  and one tap to clear. */
export default function FeedbackPane({ customerId }: { customerId: string }) {
  const purchases = useFetch(`purchases:${customerId}`, () => api.portal.getPurchases(customerId))
  // Ratings made here, over what the server sent; a failed save rolls back.
  const [mine, setMine] = useState<Record<string, Feedback>>({})
  const [saving, setSaving] = useState<Set<string>>(new Set())

  if (purchases.loading || purchases.error) {
    return <FeedState loading={purchases.loading} error={purchases.error} onRetry={purchases.refresh} style={{ paddingVertical: space[8] }} />
  }
  const list = purchases.data ?? []
  if (list.length === 0) {
    return (
      <FeedState
        icon="thumbs-up"
        empty="Nothing to rate yet"
        hint="Once you've bought something, rate it here and your recommendations start to fit."
        style={{ paddingVertical: space[8] }}
      />
    )
  }

  const current = (id: string, server: Feedback | undefined): Feedback =>
    id in mine ? mine[id] : server ?? null

  async function rate(itemId: string, previous: Feedback, value: Feedback) {
    setMine(m => ({ ...m, [itemId]: value }))
    setSaving(prev => new Set(prev).add(itemId))
    try {
      await api.portal.setFeedback(customerId, itemId, value)
    } catch {
      setMine(m => ({ ...m, [itemId]: previous }))
    } finally {
      setSaving(prev => {
        const next = new Set(prev)
        next.delete(itemId)
        return next
      })
    }
  }

  const items = list.flatMap(p => p.items)
  const rated = items.filter(i => current(i.id, i.feedback) !== null).length

  return (
    <View style={{ paddingHorizontal: space[4], paddingTop: 18, gap: 18 }}>
      <Text style={s.intro}>
        {rated} of {items.length} rated. Ratings feed your recommendations: a thumbs-down is as useful as a thumbs-up.
      </Text>
      {list.map(purchase => (
        <View key={purchase.id}>
          <View style={s.purchaseHead}>
            <Label>{formatDate(purchase.purchased_at)}</Label>
            <Text style={s.total}>{purchase.total_amount_cents ? formatDollars(purchase.total_amount_cents) : '—'}</Text>
          </View>
          <View style={{ gap: 10 }}>
            {purchase.items.map(item => {
              const value = current(item.id, item.feedback)
              const busy = saving.has(item.id)
              return (
                <View key={item.id} style={s.item}>
                  <ProductImage uri={null} size={48} category={item.product_category} radius={radius.sm} />
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text numberOfLines={1} style={s.itemName}>{item.product_name ?? 'Item'}</Text>
                    {item.product_category ? (
                      <Text style={[s.itemCat, { color: categoryStyle(item.product_category).color }]}>
                        {categoryName(item.product_category)}
                      </Text>
                    ) : null}
                  </View>
                  <View style={{ flexDirection: 'row', gap: 5 }}>
                    {RATINGS.map(r => {
                      const active = value === r.value
                      return (
                        <Pressable
                          key={r.value}
                          disabled={busy}
                          onPress={() => rate(item.id, value, active ? null : r.value)}
                          accessibilityRole="button"
                          accessibilityLabel={r.label}
                          accessibilityState={{ selected: active, disabled: busy }}
                          style={[
                            s.rating,
                            busy && { opacity: 0.5 },
                            active
                              ? { backgroundColor: alpha(r.color, 0.14), borderColor: r.color }
                              : { backgroundColor: t.surface2, borderColor: t.border },
                          ]}
                        >
                          <Icon name={r.icon} size={17} color={active ? r.color : t.text3} />
                        </Pressable>
                      )
                    })}
                  </View>
                </View>
              )
            })}
          </View>
        </View>
      ))}
    </View>
  )
}

const s = StyleSheet.create({
  intro: { fontFamily: fonts.sans, fontSize: font.size.small, lineHeight: 18, color: t.text3 },
  purchaseHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 },
  total: { fontFamily: fonts.mono, fontSize: font.size.small, color: t.text2, fontVariant: ['tabular-nums'] },
  item: {
    flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12,
    backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border, borderRadius: radius.lg,
  },
  itemName: { fontFamily: fonts.sansSemibold, fontSize: font.size.small + 1, color: t.text1 },
  itemCat: {
    fontFamily: fonts.mono, fontSize: font.size.caption, textTransform: 'uppercase',
    letterSpacing: font.size.caption * 0.06, marginTop: 3,
  },
  rating: { width: 36, height: 34, borderRadius: radius.md, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
})
