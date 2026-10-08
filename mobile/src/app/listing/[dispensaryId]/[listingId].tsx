import { Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'
import type { Cannabinoid, ListingDetail } from '@web/types'
import { formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { useCart } from '@/lib/cart'
import {
  Button, CategoryTag, ClassificationTag, FeedState, Pill, Price, ProductImage, SectionTitle, StoreBullet,
  TerpeneProfile, formatPercent, styles,
} from '@/components/ui'
import { Icon } from '@/components/Icon'
import { t, space, font, radius, type } from '@/lib/theme'

/** Measured cannabinoids as small specimen tiles: name, then the figure. */
function Cannabinoids({ items }: { items: Cannabinoid[] }) {
  const shown = items.filter(i => i.percent != null).sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))
  if (!shown.length) return <Text style={[styles.meta, s.gutter]}>No lab data yet.</Text>
  return (
    <View style={[s.gutter, { flexDirection: 'row', flexWrap: 'wrap', gap: space[2] }]}>
      {shown.map(c => (
        <View key={c.name} style={s.tile}>
          <Text style={type.bodyStrong}>{c.name}</Text>
          <Text style={type.mono}>{formatPercent(c.percent!)}</Text>
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
  const detail = [l.subtype, l.strain].filter(Boolean).join(' · ')

  return (
    <View style={styles.screen}>
    <ScrollView style={styles.screen} contentContainerStyle={{ paddingBottom: space[8] }}>
      <View style={{ alignItems: 'center', padding: space[4] }}>
        <ProductImage uri={l.image_url} size={240} category={l.scraped_category} radius={radius.xl} />
      </View>

      <View style={[s.gutter, { gap: space[1] }]}>
        <View style={s.tags}>
          {l.scraped_category ? <CategoryTag category={l.scraped_category} /> : null}
          {l.classification ? <ClassificationTag classification={l.classification} /> : null}
          {l.variant ? <Pill>{l.variant}</Pill> : null}
          {!l.in_stock ? <Pill tone="danger">Out of stock</Pill> : null}
        </View>
        {l.scraped_brand ? <Text style={[type.body, { color: t.text2 }]}>{l.scraped_brand}</Text> : null}
        <Text style={s.name} accessibilityRole="header">{l.display_name}</Text>
        {detail ? <Text style={styles.meta}>{detail}</Text> : null}
        <Price cents={l.price_cents} style={s.price} />
        {ctx.other_store_count > 0 && ctx.avg_cents != null ? (
          <Text style={styles.meta}>
            {ctx.is_cheapest ? (
              <Text style={{ color: t.success }}>Cheapest of </Text>
            ) : 'Compared with '}
            {ctx.other_store_count} other store{ctx.other_store_count === 1 ? '' : 's'} · avg {formatDollars(ctx.avg_cents)}
          </Text>
        ) : null}

        <View style={s.store}>
          <StoreBullet name={l.dispensary_name} address={l.dispensary?.address} />
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{l.dispensary_name}</Text>
            {l.dispensary?.address ? <Text style={styles.meta} numberOfLines={1}>{l.dispensary.address}</Text> : null}
          </View>
        </View>
      </View>

      <SectionTitle>Terpenes</SectionTitle>
      <View style={s.gutter}>
        {l.terpenes.length ? (
          <TerpeneProfile terpenes={l.terpenes} />
        ) : (
          <Text style={styles.meta}>No lab data yet.</Text>
        )}
      </View>

      <SectionTitle>Cannabinoids</SectionTitle>
      <Cannabinoids items={l.cannabinoids} />

      {l.description ? (
        <>
          <SectionTitle>About</SectionTitle>
          <Text style={[type.body, s.gutter, { color: t.text2 }]}>{l.description}</Text>
        </>
      ) : null}

      {l.also_available_at.length ? (
        <>
          <SectionTitle>Also at</SectionTitle>
          <View style={[s.gutter, { gap: space[2] }]}>
            {l.also_available_at.map(alt => (
              <Pressable
                key={alt.listing_id}
                onPress={() => router.push(`/listing/${alt.dispensary.id}/${alt.listing_id}`)}
                style={({ pressed }) => [styles.card, s.altRow, pressed && { backgroundColor: t.surface2 }]}
                accessibilityRole="button"
              >
                <StoreBullet name={alt.dispensary.name} address={alt.dispensary.address} size={24} />
                <Text style={[styles.name, { flex: 1 }]} numberOfLines={1}>{alt.dispensary.name}</Text>
                <Price cents={alt.price_cents} />
                <Icon name="chevron-right" size={16} color={t.text3} />
              </Pressable>
            ))}
          </View>
        </>
      ) : null}

      {l.url ? (
        <Pressable
          onPress={() => Linking.openURL(l.url!)}
          style={({ pressed }) => [s.external, pressed && { backgroundColor: t.surface1 }]}
          accessibilityRole="link"
        >
          <Text style={type.link}>{"View on the store's site"}</Text>
          <Icon name="arrow-up-right" size={16} color={t.text2} />
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
    <SafeAreaView edges={['bottom']} style={s.footer}>
      <Button icon="bag" title={inCart ? `Add another · ${inCart} in cart` : 'Add to cart'} onPress={add} />
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  gutter: { paddingHorizontal: space[4] },
  tags: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space[2], marginBottom: space[2] },
  name: { ...type.title, fontSize: font.size.display, lineHeight: 30 },
  price: { fontSize: font.size.heading, lineHeight: 26, marginTop: space[2] },
  store: {
    flexDirection: 'row', alignItems: 'center', gap: space[3], marginTop: space[4],
    paddingTop: space[4], borderTopWidth: 1, borderTopColor: t.border,
  },
  tile: {
    minWidth: 74, alignItems: 'center', gap: 3, paddingVertical: 9, paddingHorizontal: 14,
    backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  altRow: { flexDirection: 'row', alignItems: 'center', gap: space[3], padding: space[3] },
  external: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space[1],
    marginHorizontal: space[4], marginTop: space[6], padding: space[3],
    borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  footer: { padding: space[4], borderTopWidth: 1, borderTopColor: t.border, backgroundColor: t.bg },
})
