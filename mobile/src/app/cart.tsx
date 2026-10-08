import { useState } from 'react'
import { Alert, FlatList, KeyboardAvoidingView, Linking, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { router } from 'expo-router'
import { SafeAreaView } from 'react-native-safe-area-context'
import type { Order } from '@web/types'
import { formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { MAX_QTY_PER_LINE, useCart } from '@/lib/cart'
import { checkLegalRegion } from '@/lib/region'
import { Button, FeedState, Label, Price, ProductImage, StoreBullet, styles } from '@/components/ui'
import { Icon } from '@/components/Icon'
import { t, space, font, fonts, radius, type } from '@/lib/theme'

function Stepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const btn = (dir: 'minus' | 'plus', next: number, disabled: boolean) => (
    <Pressable
      onPress={() => onChange(next)}
      disabled={disabled}
      hitSlop={6}
      style={({ pressed }) => [s.step, pressed && { backgroundColor: t.surface1 }, disabled && { opacity: 0.35 }]}
      accessibilityRole="button"
      accessibilityLabel={dir === 'minus' ? (value === 1 ? 'Remove from cart' : 'Decrease quantity') : 'Increase quantity'}
    >
      <Icon name={dir === 'minus' && value === 1 ? 'trash' : dir} size={16} color={t.text1} strokeWidth={2} />
    </Pressable>
  )
  return (
    <View style={s.stepper}>
      {btn('minus', value - 1, false)}
      <Text style={[type.number, { minWidth: 20, textAlign: 'center' }]}>{value}</Text>
      {btn('plus', value + 1, value >= MAX_QTY_PER_LINE)}
    </View>
  )
}

function Placed({ order }: { order: Order }) {
  return (
    <SafeAreaView edges={['bottom']} style={[styles.screen, { padding: space[6], justifyContent: 'center', gap: space[4] }]}>
      <View style={s.placedDisc}>
        <Icon name="check" size={24} color={t.success} strokeWidth={2.25} />
      </View>
      <Text style={type.display} accessibilityRole="header">Order placed</Text>
      <Text style={type.copy}>{order.dispensary_name} is getting it ready.</Text>
      <View style={[styles.card, { padding: space[5], alignItems: 'center', gap: space[2] }]}>
        <Label>Your pickup code</Label>
        {/* Above the type scale on purpose: it is read across a counter. */}
        <Text style={[type.code, { fontSize: 40, lineHeight: 48 }]}>{order.pickup_code}</Text>
        <Text style={[styles.meta, { textAlign: 'center' }]}>
          Show this at the counter. Pay when you collect: <Text style={s.figure}>{formatDollars(order.total_amount_cents)}</Text>
        </Text>
      </View>
      {order.dispensary_name ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[3] }}>
          <StoreBullet name={order.dispensary_name} address={order.dispensary_address} />
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{order.dispensary_name}</Text>
            {order.dispensary_address ? <Text style={styles.meta}>{order.dispensary_address}</Text> : null}
          </View>
        </View>
      ) : null}
      <Button
        title="View my orders"
        onPress={() => {
          router.dismissAll()
          router.navigate('/orders')
        }}
      />
      <Button title="Done" variant="secondary" onPress={() => router.back()} />
    </SafeAreaView>
  )
}

export default function Cart() {
  const cart = useCart()
  const [note, setNote] = useState('')
  const [placing, setPlacing] = useState(false)
  const [placed, setPlaced] = useState<Order | null>(null)

  if (placed) return <Placed order={placed} />

  if (!cart.items.length) {
    return (
      <FeedState
        icon="bag"
        empty="Your cart is empty"
        hint="Add something from a store's menu to reserve it for pickup."
      />
    )
  }

  const store = cart.items[0]
  const unpriced = cart.items.some(i => i.price_cents == null)

  async function place() {
    setPlacing(true)
    try {
      const region = await checkLegalRegion()
      if (!region.ok) {
        Alert.alert(
          "Can't place this order here",
          region.message,
          region.reason === 'permission'
            ? [{ text: 'Not now', style: 'cancel' }, { text: 'Open Settings', onPress: () => Linking.openSettings() }]
            : undefined,
        )
        return
      }
      const order = await api.orders.create({
        dispensary_id: store.dispensaryId,
        items: cart.items.map(i => ({ listing_id: i.listingId, quantity: i.quantity })),
        note: note.trim() || undefined,
      })
      cart.clear()
      setPlaced(order)
    } catch (e: any) {
      // The backend explains itself: sold out, too many open orders, store
      // stopped taking pickups. Its detail string is written for the shopper.
      Alert.alert('Could not place your order', e?.message ?? String(e))
    } finally {
      setPlacing(false)
    }
  }

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={64}>
      <FlatList
        data={cart.items}
        keyExtractor={i => i.listingId}
        contentContainerStyle={{ padding: space[4], gap: space[4] }}
        ListHeaderComponent={
          <View style={{ gap: space[1] }}>
            <Label>Pickup at</Label>
            <Text style={type.title}>{store.dispensaryName}</Text>
          </View>
        }
        renderItem={({ item }) => (
          <View style={{ flexDirection: 'row', gap: space[3], alignItems: 'center' }}>
            <ProductImage uri={item.image_url} size={64} />
            <View style={{ flex: 1, gap: 2 }}>
              <Text numberOfLines={2} style={styles.name}>{item.name}</Text>
              <Text numberOfLines={1} style={styles.meta}>{[item.brand, item.variant].filter(Boolean).join(' · ')}</Text>
              <Price cents={item.price_cents == null ? null : item.price_cents * item.quantity} />
            </View>
            <Stepper value={item.quantity} onChange={n => cart.setQuantity(item.listingId, n)} />
          </View>
        )}
        ListFooterComponent={
          <TextInput
            style={[styles.input, s.note]}
            value={note}
            onChangeText={setNote}
            placeholder="Note for the store (optional)"
            placeholderTextColor={t.text4}
            maxLength={500}
            multiline
          />
        }
      />
      <SafeAreaView edges={['bottom']} style={s.footer}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space[3] }}>
          <View style={{ flex: 1, gap: 2 }}>
            <Label>Pay at pickup</Label>
            {unpriced ? <Text style={styles.meta}>Some items have no listed price</Text> : null}
          </View>
          <Text style={[type.price, { fontSize: font.size.title, lineHeight: 22 }]}>{formatDollars(cart.totalCents)}</Text>
        </View>
        <Button title="Reserve for pickup" onPress={place} loading={placing} />
      </SafeAreaView>
    </KeyboardAvoidingView>
  )
}

const s = StyleSheet.create({
  stepper: {
    flexDirection: 'row', alignItems: 'center', gap: space[2], padding: 4,
    backgroundColor: t.surface2, borderRadius: radius.pill, borderWidth: 1, borderColor: t.border,
  },
  step: { width: 28, height: 28, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: t.surface3 },
  note: { marginTop: space[2], minHeight: 64, fontSize: font.size.body, padding: space[3], textAlignVertical: 'top' },
  footer: { padding: space[4], gap: space[3], borderTopWidth: 1, borderTopColor: t.border, backgroundColor: t.bg },
  placedDisc: {
    width: 48, height: 48, borderRadius: 24, borderWidth: 1, borderColor: t.successEdge, backgroundColor: t.successTint,
    alignItems: 'center', justifyContent: 'center',
  },
  figure: { color: t.text2, fontFamily: fonts.sansBold, fontVariant: ['tabular-nums'] },
})
