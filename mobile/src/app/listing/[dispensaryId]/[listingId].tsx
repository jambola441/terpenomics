import { Linking, Pressable, ScrollView, Text, View } from 'react-native'
import { router, useLocalSearchParams } from 'expo-router'
import type { Terpene } from '@web/types'
import { formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { FeedState, Price, ProductImage, SectionTitle, styles } from '@/components/ui'
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

/** One store's listing: price against the market, lab data, other stores.
 *  Add-to-cart and checkout come with the cart port. */
export default function ListingScreen() {
  const { dispensaryId, listingId } = useLocalSearchParams<{ dispensaryId: string; listingId: string }>()
  const { data: l, error, loading, refresh } = useFetch(`${dispensaryId}/${listingId}`, () =>
    api.portal.getListing(dispensaryId, listingId),
  )

  if (loading || error || !l) return <FeedState loading={loading} error={error} onRetry={refresh} />
  const ctx = l.price_context

  return (
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
  )
}
