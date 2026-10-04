import { Alert, Linking, Pressable, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'
import type { ListingDetail, Terpene } from '@web/types'
import { formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { useCart } from '@/lib/cart'
import { Button, FeedState, Price, ProductImage, SectionTitle, styles } from '@/components/ui'
import { t, space, font, radius } from '@/lib/theme'

function Bars({ items }: { items: Terpene[] }) {
  const shown = items.filter(i => i.percent != null).sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0)).slice(0, 8)
  const max = Math.max(...shown.map(i => i.percent ?? 0), 0.01)
  if (!shown.length) return <Text style={[styles.meta, { paddingHorizontal: space[4] }]}>No lab data yet.</Text>
  return (
    <View style={{ paddingHorizontal: space[4], gap: space[2] }}>
      {shown.map(i => (
        <View key={i.name} style={{ flexDirection: 'row', alignItems: 'center', gap: space[3] }}>
          <Text style={[styles.meta, { width: 110, color: t.text2 }]} numberOfLines={1}>{i.name}</Text>
          <View style={{ flex: 1, height: 8, backgroundColor: t.surface2, borderRadius: radius.pill }}>
            <View style={{ width: `${((i.percent ?? 0) / max) * 100}%`, height: 8, backgroundColor: t.accent, borderRadius: radius.pill }} />
          </View>
          <Text style={[styles.meta, { width: 48, textAlign: 'right' }]}>{(i.percent ?? 0).toFixed(2)}%</Text>
        </View>
      ))}
    </View>
  )
}

/** One store's listing: price against the market, lab data, other stores,
 *  and add-to-cart when the store takes pickup orders. */
export default function ListingScreen() {
  const { dispensaryId, listingId } = useLocalSearchParams<{ dispensaryId: string; listingId: string }>()
  const { data: l, error, loading, refresh } = useFetch(`${dispensaryId}/${listingId}`, () =>
    api.portal.getListing(dispensaryId, listingId),
  )

  if (loading || error || !l) return <FeedState loading={loading} error={error} onRetry={refresh} />
  const ctx = l.price_context
  const listing = l

  return (
    <View style={styles.screen}>
    <ScrollView style={styles.screen} contentContainerStyle={{ paddingBottom: space[8] }}>
      <View style={{ alignItems: 'center', padding: space[4] }}>
        <ProductImage uri={l.image_url} size={240} />
      </View>

      <View style={{ paddingHorizontal: space[4], gap: space[1] }}>
        {l.scraped_brand ? <Text style={[styles.meta, { color: t.text2 }]}>{l.scraped_brand}</Text> : null}
        <Text style={{ color: t.text1, fontSize: font.size.heading, fontWeight: font.weight.heavy }}>{l.display_name}</Text>
        <Text style={styles.meta}>{[l.variant, l.subtype, l.strain].filter(Boolean).join(' · ')}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[3], marginTop: space[2] }}>
          <Price cents={l.price_cents} />
          {!l.in_stock ? <Text style={{ color: t.danger, fontSize: font.size.small }}>Out of stock</Text> : null}
        </View>
        {ctx.other_store_count > 0 && ctx.avg_cents != null ? (
          <Text style={styles.meta}>
            {ctx.is_cheapest ? 'Cheapest of ' : 'Compared with '}
            {ctx.other_store_count} other store{ctx.other_store_count === 1 ? '' : 's'} · avg {formatDollars(ctx.avg_cents)}
          </Text>
        ) : null}
        <Text style={[styles.meta, { marginTop: space[2] }]}>At {l.dispensary_name}</Text>
      </View>

      <SectionTitle>Terpenes</SectionTitle>
      <Bars items={l.terpenes} />

      <SectionTitle>Cannabinoids</SectionTitle>
      <Bars items={l.cannabinoids} />

      {l.description ? (
        <>
          <SectionTitle>About</SectionTitle>
          <Text style={[styles.meta, { paddingHorizontal: space[4], color: t.text2, lineHeight: 20 }]}>{l.description}</Text>
        </>
      ) : null}

      {l.also_available_at.length ? (
        <>
          <SectionTitle>Also at</SectionTitle>
          <View style={{ paddingHorizontal: space[4], gap: space[2] }}>
            {l.also_available_at.map(alt => (
              <Pressable
                key={alt.listing_id}
                onPress={() => router.push(`/listing/${alt.dispensary.id}/${alt.listing_id}`)}
                style={({ pressed }) => [styles.card, { padding: space[3], flexDirection: 'row' }, pressed && { opacity: 0.7 }]}
              >
                <Text style={[styles.name, { flex: 1 }]}>{alt.dispensary.name}</Text>
                <Price cents={alt.price_cents} />
              </Pressable>
            ))}
          </View>
        </>
      ) : null}

      {l.url ? (
        <Pressable onPress={() => Linking.openURL(l.url!)} style={{ padding: space[4], marginTop: space[4] }}>
          <Text style={{ color: t.accent, textAlign: 'center' }}>{"View on the store's site"}</Text>
        </Pressable>
      ) : null}
    </ScrollView>
    {l.dispensary_accepts_pickup && l.in_stock ? <AddToCart listing={listing} /> : null}
    </View>
  )
}

function AddToCart({ listing }: { listing: ListingDetail }) {
  const cart = useCart()
  const inCart = cart.items.find(i => i.listingId === listing.id)?.quantity ?? 0

  function add() {
    const result = cart.add(listing)
    if (result === 'full') {
      Alert.alert("That's the most you can reserve", 'Stores cap how much of one item a single order can hold.')
    } else if (result === 'other-store') {
      // An order goes to one store, so mixing stores would only fail at checkout.
      Alert.alert(
        'Start a new cart?',
        `Your cart has items from ${cart.items[0].dispensaryName}. An order can only be picked up from one store.`,
        [
          { text: 'Keep my cart', style: 'cancel' },
          { text: 'Start new cart', style: 'destructive', onPress: () => cart.replaceWith(listing) },
        ],
      )
    }
  }

  return (
    <SafeAreaView edges={['bottom']} style={{ padding: space[4], borderTopWidth: 1, borderTopColor: t.border, backgroundColor: t.bg }}>
      <Button title={inCart ? `Add another · ${inCart} in cart` : 'Add to cart'} onPress={add} />
    </SafeAreaView>
  )
}
