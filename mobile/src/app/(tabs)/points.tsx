import { useCallback, useRef } from 'react'
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { router, useFocusEffect } from 'expo-router'
import type { MyReceipt, PointsEntry } from '@web/types'
import { formatDate, formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { FeedState, Label, SectionTitle, styles } from '@/components/ui'
import { Icon } from '@/components/Icon'
import { t, space, font, fonts, radius, type } from '@/lib/theme'

const KIND: Record<string, string> = { earn: 'Earned', receipt: 'Receipt', refund: 'Refunded', adjust: 'Adjusted' }

/** Terpee points from shopping at partner stores, the receipts sent in for
 *  review, and the way to send one. Same content as the web portal's
 *  You → Points pane (ui/my-app/src/components/ProfileView.tsx). */
export default function Points() {
  const points = useFetch('points', () => api.me.getPoints())
  const receipts = useFetch('receipts', () => api.me.getReceipts())

  // Coming back from the upload screen, or after a reviewer approves, should
  // show the change without a pull. The first focus is the initial load.
  const focused = useRef(false)
  const refreshPoints = points.refresh
  const refreshReceipts = receipts.refresh
  useFocusEffect(
    useCallback(() => {
      if (focused.current) {
        refreshPoints()
        refreshReceipts()
      }
      focused.current = true
    }, [refreshPoints, refreshReceipts]),
  )

  if (points.loading || points.error) {
    return <FeedState loading={points.loading} error={points.error} onRetry={points.refresh} />
  }
  const data = points.data!

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ paddingBottom: space[8] }}
      refreshControl={
        <RefreshControl
          refreshing={points.refreshing}
          onRefresh={() => {
            points.refresh()
            receipts.refresh()
          }}
          tintColor={t.text3}
        />
      }
    >
      <View style={[styles.card, { margin: space[4], padding: space[5], flexDirection: 'row', alignItems: 'flex-end', gap: space[6] }]}>
        <View>
          <Label>Available</Label>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[2], marginTop: space[1] }}>
            <Icon name="drop" size={26} color={t.accent} strokeWidth={2} />
            <Text style={s.balance}>{data.available.toLocaleString()}</Text>
          </View>
        </View>
        <View style={{ paddingBottom: space[1] }}>
          <Label>Pending</Label>
          <Text style={[type.number, { color: t.text2, fontSize: font.size.title, marginTop: space[1] }]}>
            {data.pending.toLocaleString()}
          </Text>
        </View>
      </View>

      <Text style={[styles.meta, { paddingHorizontal: space[4], lineHeight: 18, color: t.text2 }]}>
        Earn {data.points_per_dollar === 1 ? '1 point' : `${data.points_per_dollar} points`} per dollar (before tax
        and tip) when you shop at Terpee partner stores with your phone number on the receipt. Points become
        available {data.pending_days} days after your purchase.
      </Text>

      <Pressable
        onPress={() => router.push('/receipt')}
        style={({ pressed }) => [s.upload, pressed && { backgroundColor: t.surface2 }]}
        accessibilityRole="button"
      >
        <View style={s.uploadDisc}>
          <Icon name="receipt" size={20} color={t.text2} />
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={[styles.name, { fontSize: font.size.callout }]}>Upload a receipt</Text>
          <Text style={styles.meta}>{"Didn't give your number at a partner store? Send us the receipt and we'll add the points."}</Text>
        </View>
        <Icon name="chevron-right" size={18} color={t.text3} />
      </Pressable>

      {receipts.data?.length ? (
        <>
          <SectionTitle>Your receipts</SectionTitle>
          <View style={{ paddingHorizontal: space[4] }}>
            {receipts.data.map(r => <ReceiptRow key={r.id} receipt={r} />)}
          </View>
        </>
      ) : null}

      <SectionTitle>History</SectionTitle>
      {data.entries.length === 0 ? (
        <Text style={[styles.meta, { paddingHorizontal: space[4] }]}>
          No points yet. Shop at a Terpee partner store and give them your phone number at checkout.
        </Text>
      ) : (
        <View style={{ paddingHorizontal: space[4] }}>
          {data.entries.map(e => <EntryRow key={e.id} entry={e} />)}
        </View>
      )}
    </ScrollView>
  )
}

function Row({ title, detail, value, color }: { title: string; detail: string; value: string; color: string }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[3], paddingVertical: space[3], borderBottomWidth: 1, borderBottomColor: t.border }}>
      <View style={{ flex: 1 }}>
        <Text style={styles.name} numberOfLines={1}>{title}</Text>
        <Text style={[styles.meta, { marginTop: 2 }]}>{detail}</Text>
      </View>
      <Text style={[type.number, { color, fontSize: font.size.callout }]}>{value}</Text>
    </View>
  )
}

function EntryRow({ entry: e }: { entry: PointsEntry }) {
  const detail = `${KIND[e.kind] ?? e.kind} · ${formatDate(e.created_at)}` +
    (e.pending && e.points > 0 ? ` · available ${formatDate(e.available_at)}` : '')
  return (
    <Row
      title={e.partner_name ?? 'Terpee'}
      detail={detail}
      value={`${e.points > 0 ? '+' : ''}${e.points.toLocaleString()}`}
      color={e.points < 0 ? t.danger : e.pending ? t.text3 : t.success}
    />
  )
}

function ReceiptRow({ receipt: r }: { receipt: MyReceipt }) {
  let detail = r.purchased_on ? formatDate(r.purchased_on + 'T12:00:00') : formatDate(r.created_at)
  if (r.status === 'approved' && r.subtotal_cents != null) detail += ` · ${formatDollars(r.subtotal_cents)}`
  if (r.status === 'rejected' && r.reject_reason) detail += ` · ${r.reject_reason}`
  return (
    <Row
      title={r.partner_name ?? 'Store'}
      detail={detail}
      value={r.status === 'approved' ? `+${r.points ?? 0}` : r.status === 'rejected' ? 'Not approved' : 'In review'}
      color={r.status === 'approved' ? t.success : r.status === 'rejected' ? t.danger : t.text3}
    />
  )
}

const s = StyleSheet.create({
  balance: { fontFamily: fonts.sansBold, fontSize: font.size.hero, lineHeight: 36, color: t.text1, fontVariant: ['tabular-nums'] },
  upload: {
    flexDirection: 'row', alignItems: 'center', gap: space[3],
    margin: space[4], padding: space[4],
    borderRadius: radius.lg, borderWidth: 1, borderStyle: 'dashed', borderColor: t.borderStrong,
    backgroundColor: t.surface1,
  },
  uploadDisc: {
    width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border,
  },
})
