import { useState } from 'react'
import { Alert, FlatList, KeyboardAvoidingView, Linking, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { router } from 'expo-router'
import { SafeAreaView } from 'react-native-safe-area-context'
import type { Order } from '@web/types'
import { formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { MAX_QTY_PER_LINE, useCart } from '@/lib/cart'
import { checkLegalRegion } from '@/lib/region'
import { Button, Price, ProductImage, styles } from '@/components/ui'
import { t, space, font, radius } from '@/lib/theme'

function Stepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const btn = (label: string, next: number, disabled: boolean) => (
    <Pressable
      onPress={() => onChange(next)}
      disabled={disabled}
      hitSlop={6}
      style={[s.step, disabled && { opacity: 0.35 }]}
      accessibilityLabel={label === '−' ? 'Decrease quantity' : 'Increase quantity'}
    >
      <Text style={s.stepText}>{label}</Text>
    </Pressable>
  )
  return (
    <View style={s.stepper}>
      {btn('−', value - 1, false)}
      <Text style={[styles.name, { minWidth: 20, textAlign: 'center' }]}>{value}</Text>
      {btn('+', value + 1, value >= MAX_QTY_PER_LINE)}
    </View>
  )
}

function Placed({ order }: { order: Order }) {
  return (
    <SafeAreaView edges={['bottom']} style={[styles.screen, { padding: space[6], justifyContent: 'center', gap: space[4] }]}>
      <Text style={{ color: t.accent, fontSize: font.size.display, fontWeight: font.weight.heavy }}>Order placed</Text>
      <Text style={{ color: t.text2, fontSize: font.size.callout }}>{order.dispensary_name} is getting it ready.</Text>
      <View style={[styles.card, { padding: space[5], alignItems: 'center', gap: space[1] }]}>
        <Text style={styles.meta}>Your pickup code</Text>
        <Text style={{ color: t.text1, fontSize: 40, fontWeight: font.weight.heavy, letterSpacing: 4 }}>{order.pickup_code}</Text>
        <Text style={styles.meta}>Show this at the counter. Pay when you collect: {formatDollars(order.total_amount_cents)}</Text>
      </View>
      {order.dispensary_address ? <Text style={styles.meta}>{order.dispensary_address}</Text> : null}
      <Button
        title="View my orders"
        onPress={() => {
          router.dismissAll()
          router.navigate('/orders')
        }}
      />
      <Button title="Done" variant="ghost" onPress={() => router.back()} />
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
      <View style={styles.center}>
        <Text style={styles.muted}>{"Your cart is empty. Add something from a store's menu to reserve it for pickup."}</Text>
      </View>
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
        ListHeaderComponent={<Text style={styles.meta}>Pickup at {store.dispensaryName}</Text>}
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
            style={s.note}
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
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={styles.meta}>Pay at pickup{unpriced ? ' · some items have no listed price' : ''}</Text>
          <Text style={[styles.name, { fontSize: font.size.title }]}>{formatDollars(cart.totalCents)}</Text>
        </View>
        <Button title="Reserve for pickup" onPress={place} loading={placing} />
      </SafeAreaView>
    </KeyboardAvoidingView>
  )
}

const s = StyleSheet.create({
  stepper: { flexDirection: 'row', alignItems: 'center', gap: space[2], backgroundColor: t.surface2, borderRadius: radius.pill, padding: 4 },
  step: { width: 28, height: 28, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: t.surface3 },
  stepText: { color: t.text1, fontSize: font.size.title, fontWeight: font.weight.bold },
  note: {
    marginTop: space[2],
    minHeight: 64,
    backgroundColor: t.surface2,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: t.border,
    color: t.text1,
    fontSize: font.size.body,
    padding: space[3],
  },
  footer: { padding: space[4], gap: space[3], borderTopWidth: 1, borderTopColor: t.border, backgroundColor: t.bg },
})
