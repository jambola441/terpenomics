import { useState } from 'react'
import {
  Alert, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native'
import { Stack, router } from 'expo-router'
import { SafeAreaView } from 'react-native-safe-area-context'
import type { CartItem, Order } from '@web/types'
import { formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { MAX_QTY_PER_LINE, useCart } from '@/lib/cart'
import { useOrders } from '@/lib/orders'
import { checkLegalRegion } from '@/lib/region'
import { Button, FeedState, Label, ProductImage, styles } from '@/components/ui'
import { Icon } from '@/components/Icon'
import { t, space, font, fonts, radius, type } from '@/lib/theme'

/**
 * The cart, then checkout, then the pickup code: the web's CartDrawer and
 * Checkout. Nothing is charged, and checkout says so above the button; the
 * button says "Place pickup order", never "Pay".
 */
export default function Cart() {
  const cart = useCart()
  const [step, setStep] = useState<'cart' | 'checkout'>('cart')
  const [placed, setPlaced] = useState<Order | null>(null)
  const [placing, setPlacing] = useState(false)

  const title = placed ? 'Order placed' : step === 'checkout' ? 'Confirm pickup order' : 'Your cart'
  const header = (
    <Stack.Screen
      options={{
        title,
        // Closing mid-request would lose the pickup code.
        gestureEnabled: !placing,
        headerRight: () => (!placed && step === 'cart' && cart.items.length > 0 ? (
          <Pressable
            onPress={() => Alert.alert('Clear your cart?', 'Everything in it will be removed.', [
              { text: 'Keep it', style: 'cancel' },
              { text: 'Clear cart', style: 'destructive', onPress: cart.clear },
            ])}
            accessibilityRole="button"
            hitSlop={8}
            style={s.clear}
          >
            <Text style={s.clearText}>Clear</Text>
          </Pressable>
        ) : null),
      }}
    />
  )

  if (placed) return <>{header}<Placed order={placed} /></>

  if (!cart.items.length) {
    return (
      <>
        {header}
        <FeedState icon="bag" empty="Your cart is empty" hint="Add something from a store that takes pickup orders." />
      </>
    )
  }

  return (
    <>
      {header}
      {step === 'cart'
        ? <CartStep onCheckout={() => setStep('checkout')} />
        : <CheckoutStep onBack={() => setStep('cart')} onPlaced={setPlaced} onPlacing={setPlacing} />}
    </>
  )
}

/* ── Step one: the cart ───────────────────────────────────────────────────── */

function CartStep({ onCheckout }: { onCheckout: () => void }) {
  const cart = useCart()
  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={{ padding: 20, paddingTop: space[2], gap: 10 }}>
        <Text style={[type.meta, { marginBottom: 6 }]}>{cart.items[0].dispensaryName}</Text>
        {cart.items.map(item => (
          <View key={item.listingId} style={s.line}>
            <ProductImage uri={item.image_url} size={52} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text numberOfLines={1} style={styles.name}>{item.name}</Text>
              {item.variant ? <Text style={[type.mono, { fontSize: font.size.caption, color: t.text3, marginTop: 2 }]}>{item.variant}</Text> : null}
              {item.price_cents != null ? (
                <View style={s.lineMoney}>
                  <Text style={[type.price, { fontSize: font.size.body }]}>{formatDollars(item.price_cents * item.quantity)}</Text>
                  {item.quantity > 1 ? <Text style={type.meta}>{formatDollars(item.price_cents)} each</Text> : null}
                </View>
              ) : null}
            </View>
            <Stepper item={item} />
          </View>
        ))}
      </ScrollView>
      <SafeAreaView edges={['bottom']} style={s.footer}>
        {cart.totalCents > 0 ? (
          <View style={s.totalRow}>
            <Text style={[type.body, { color: t.text2 }]}>Estimated total</Text>
            <Text style={[type.price, { fontSize: font.size.title, lineHeight: 22 }]}>{formatDollars(cart.totalCents)}</Text>
          </View>
        ) : null}
        <Button title="Checkout · pay at the store" onPress={onCheckout} />
      </SafeAreaView>
    </View>
  )
}

/** − n + for one line. At one, minus becomes remove: one way to take a line out. */
function Stepper({ item }: { item: CartItem }) {
  const cart = useCart()
  const q = item.quantity
  const atMax = q >= MAX_QTY_PER_LINE
  const set = (n: number) => (n <= 0 ? cart.remove(item.listingId) : cart.setQuantity(item.listingId, n))
  return (
    <View style={s.stepper}>
      <Pressable
        onPress={() => set(q - 1)}
        hitSlop={4}
        accessibilityRole="button"
        accessibilityLabel={q <= 1 ? `Remove ${item.name}` : `One fewer ${item.name}`}
        style={s.step}
      >
        <Icon name={q <= 1 ? 'trash' : 'minus'} size={16} color={t.text1} strokeWidth={2} />
      </Pressable>
      <Text style={s.qty} accessibilityLiveRegion="polite">{q}</Text>
      <Pressable
        onPress={() => !atMax && set(q + 1)}
        disabled={atMax}
        hitSlop={4}
        accessibilityRole="button"
        accessibilityLabel={atMax ? `${MAX_QTY_PER_LINE} is the most per order` : `One more ${item.name}`}
        style={s.step}
      >
        <Icon name="plus" size={16} color={atMax ? t.text4 : t.text1} strokeWidth={2} />
      </Pressable>
    </View>
  )
}

/* ── Step two: checkout ───────────────────────────────────────────────────── */

function PaymentNotice() {
  return (
    <View style={s.notice}>
      <Icon name="dollar" size={19} color={t.warning} style={{ marginTop: 1 }} />
      <View style={{ flex: 1 }}>
        <Text style={[type.bodyStrong, { color: t.warning, marginBottom: 3 }]}>You pay at the store</Text>
        <Text style={[type.body, { color: t.text2, fontSize: font.size.small, lineHeight: 19 }]}>
          No card is charged now. Your items are held at the counter and you pay when you pick them up. Bring a valid ID.
        </Text>
      </View>
    </View>
  )
}

function CheckoutStep({ onBack, onPlaced, onPlacing }: {
  onBack: () => void
  onPlaced: (order: Order) => void
  onPlacing: (placing: boolean) => void
}) {
  const cart = useCart()
  const { upsert } = useOrders()
  const [note, setNote] = useState('')
  const [submitting, setSubmittingState] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setSubmitting = (v: boolean) => { setSubmittingState(v); onPlacing(v) }

  const items = cart.items
  const store = items[0]
  const anyUnpriced = items.some(i => i.price_cents == null)

  async function submit() {
    if (submitting) return
    setSubmitting(true)
    setError(null)
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
        items: items.map(i => ({ listing_id: i.listingId, quantity: i.quantity })),
        note: note.trim() || undefined,
      })
      cart.clear()
      // Into the Orders tab (and its badge) straight away, without a refetch.
      upsert(order)
      onPlaced(order)
    } catch (e: unknown) {
      // The backend's detail names the item that sold out, or says the store
      // stopped taking orders; it is written for the shopper.
      setError((e instanceof Error && e.message) || 'Could not place your order. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={64}>
      <ScrollView contentContainerStyle={{ padding: 20, paddingTop: space[2], gap: 14 }} keyboardShouldPersistTaps="handled">
        <PaymentNotice />

        <View>
          <Text style={s.caps}>{items.length} item{items.length === 1 ? '' : 's'} from {store.dispensaryName}</Text>
          <View style={s.review}>
            {items.map((item, idx) => (
              <View key={item.listingId} style={[s.reviewRow, idx > 0 && { borderTopWidth: 1, borderTopColor: t.border }]}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text numberOfLines={1} style={styles.name}>{item.name}</Text>
                  {item.variant || item.quantity > 1 ? (
                    <Text style={[type.meta, { fontSize: font.size.small, marginTop: 2 }]}>
                      {[item.variant, item.quantity > 1 ? `×${item.quantity}` : null].filter(Boolean).join(' · ')}
                    </Text>
                  ) : null}
                </View>
                <Text style={[type.body, { color: t.text2, fontVariant: ['tabular-nums'] }]}>
                  {item.price_cents != null ? formatDollars(item.price_cents * item.quantity) : '—'}
                </Text>
              </View>
            ))}
          </View>
        </View>

        <View>
          <Text style={s.caps}>Note for the store (optional)</Text>
          <TextInput
            value={note}
            onChangeText={setNote}
            maxLength={500}
            multiline
            placeholder="Anything they should know?"
            placeholderTextColor={t.text4}
            accessibilityLabel="Note for the store"
            style={[styles.input, s.note]}
          />
        </View>

        {error ? (
          <View style={s.error} accessibilityRole="alert">
            <Text style={[type.body, { color: t.danger, fontSize: font.size.small, lineHeight: 19 }]}>{error}</Text>
          </View>
        ) : null}
      </ScrollView>

      <SafeAreaView edges={['bottom']} style={s.footer}>
        <View>
          <View style={[s.totalRow, { marginBottom: 4 }]}>
            <Text style={[type.body, { color: t.text2 }]}>Due at pickup</Text>
            <Text style={[type.price, { fontSize: font.size.title, lineHeight: 22 }]}>{formatDollars(cart.totalCents)}</Text>
          </View>
          <Text style={[type.meta, { fontSize: font.size.small, lineHeight: 19 }]}>
            {anyUnpriced
              ? 'Some items have no listed price — the store will confirm the total.'
              : 'Taxes are calculated in store, so the final total may differ.'}
          </Text>
        </View>
        <Button title={submitting ? 'Placing order…' : 'Place pickup order'} onPress={submit} loading={submitting} />
        <Button title="Back to cart" variant="secondary" onPress={onBack} disabled={submitting} />
      </SafeAreaView>
    </KeyboardAvoidingView>
  )
}

/* ── Step three: the pickup code ──────────────────────────────────────────── */

function Placed({ order }: { order: Order }) {
  return (
    <SafeAreaView edges={['bottom']} style={[styles.screen, { paddingHorizontal: 20 }]}>
      <ScrollView contentContainerStyle={{ paddingTop: 8, paddingBottom: 20, alignItems: 'stretch' }}>
        <View style={s.placedDisc} accessibilityElementsHidden>
          <Icon name="check" size={28} color={t.success} strokeWidth={2} />
        </View>
        <Text style={[s.placedTitle]} accessibilityRole="header">Order placed</Text>
        <Text style={[type.body, { color: t.text3, textAlign: 'center', marginTop: 6 }]}>
          {order.dispensary_name} is getting it ready.
        </Text>

        {/* The code is the point of this screen: give it the room. A ticket stub. */}
        <View style={s.stub}>
          <Label style={{ marginBottom: 8, textAlign: 'center' }}>Pickup code</Label>
          <Text style={s.code} accessibilityLabel={`Pickup code ${order.pickup_code.split('').join(' ')}`}>{order.pickup_code}</Text>
          <Text style={[type.meta, { fontSize: font.size.small, lineHeight: 19, marginTop: 10, textAlign: 'center' }]}>
            Show this at the counter. You&apos;ll pay {formatDollars(order.total_amount_cents)} in store.
          </Text>
        </View>

        {order.dispensary_address ? (
          <Text style={[type.meta, { fontSize: font.size.small, textAlign: 'center', marginTop: 14 }]}>{order.dispensary_address}</Text>
        ) : null}

        <Button
          title="View my orders"
          style={{ marginTop: 22 }}
          onPress={() => {
            router.dismissAll()
            router.navigate('/orders')
          }}
        />
        <Button title="Keep browsing" variant="secondary" style={{ marginTop: 10 }} onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  clear: {
    paddingHorizontal: 11, paddingVertical: 6, borderRadius: radius.md,
    borderWidth: 1, borderColor: t.borderStrong,
  },
  clearText: { fontFamily: fonts.sans, fontSize: font.size.small + 1, color: t.text2 },
  line: {
    flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12,
    backgroundColor: t.surface2, borderRadius: radius.lg, borderWidth: 1, borderColor: t.border,
  },
  lineMoney: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', columnGap: 6, marginTop: 3 },
  stepper: {
    flexDirection: 'row', alignItems: 'center', padding: 2,
    backgroundColor: t.surface3, borderRadius: radius.pill, borderWidth: 1, borderColor: t.borderStrong,
  },
  step: { width: 40, height: 40, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  qty: { minWidth: 22, textAlign: 'center', fontFamily: fonts.sansBold, fontSize: font.size.body, color: t.text1, fontVariant: ['tabular-nums'] },
  footer: { padding: 20, gap: 10, borderTopWidth: 1, borderTopColor: t.border, backgroundColor: t.bg },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  notice: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 14, paddingHorizontal: 16,
    backgroundColor: t.warningTint, borderWidth: 1, borderColor: t.warningEdge, borderRadius: radius.lg,
  },
  caps: {
    fontFamily: fonts.sans, fontSize: font.size.small, color: t.text3,
    textTransform: 'uppercase', letterSpacing: 0.7, marginBottom: 8,
  },
  review: { backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.lg, overflow: 'hidden' },
  reviewRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, paddingHorizontal: 14 },
  note: { minHeight: 64, fontSize: font.size.body, padding: space[3], textAlignVertical: 'top', borderRadius: radius.lg },
  error: {
    paddingVertical: 11, paddingHorizontal: 13, borderRadius: radius.lg,
    backgroundColor: t.dangerTint, borderWidth: 1, borderColor: t.dangerEdge,
  },
  placedDisc: {
    width: 60, height: 60, borderRadius: 30, alignSelf: 'center', marginTop: 4, marginBottom: 16,
    borderWidth: 1, borderColor: t.successEdge, backgroundColor: t.successTint,
    alignItems: 'center', justifyContent: 'center',
  },
  placedTitle: { ...type.title, fontSize: font.size.display, lineHeight: 30, textAlign: 'center' },
  stub: {
    marginTop: 22, paddingVertical: 18, paddingHorizontal: 16, backgroundColor: t.bg,
    borderWidth: 1, borderStyle: 'dashed', borderColor: t.borderStrong, borderRadius: radius.lg,
  },
  code: {
    fontFamily: fonts.monoMedium, fontSize: 34, lineHeight: 42, letterSpacing: 6,
    color: t.text1, textAlign: 'center', fontVariant: ['tabular-nums'],
  },
})
