import { Pressable, StyleSheet, Text, View } from 'react-native'
import type { FeedListing, FeedRail, PortalDispensary } from '@web/types'
import { categoryStyle } from '@web/design/tokens'
import { formatDollars } from '@web/utils/format'
import { MarketNote, Pill, ProductImage } from './ui'
import { t, font, fonts, radius } from '@/lib/theme'

/** A Home rail card, the twin of the web's FeedCard (components/HomeFeed.tsx):
 *  square plate with the size top-left and, on the deals rail only, the saving
 *  top-right; then price, name, brand, subtype; then, pinned to the bottom so a
 *  rail's cards line up, whose shelf it is on and the market note. */
export default function FeedCard({ listing, rail, store, width, onPress }: {
  listing: FeedListing
  rail: FeedRail
  /** The store it is at, in the combined view where a rail mixes stores. */
  store?: PortalDispensary
  width: number
  onPress: () => void
}) {
  const saving = listing.saving_cents
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [s.card, { width }, pressed && { backgroundColor: t.surface2 }]}
    >
      <View>
        <ProductImage uri={listing.image_url} size={width - 2} category={listing.scraped_category} radius={0} />
        {listing.variant ? <Text style={[s.corner, { left: 8 }]}>{listing.variant}</Text> : null}
        {rail === 'deals' && saving != null && saving > 0 ? (
          <Text style={[s.corner, s.save]}>Save {formatDollars(saving)}</Text>
        ) : null}
      </View>

      <View style={s.body}>
        <Text style={listing.price_cents != null ? s.price : s.noPrice}>
          {listing.price_cents != null ? formatDollars(listing.price_cents) : 'Price not listed'}
        </Text>
        <Text numberOfLines={2} style={s.name}>{listing.display_name}</Text>
        {listing.scraped_brand ? <Text numberOfLines={1} style={s.brand}>{listing.scraped_brand}</Text> : null}
        {listing.subtype ? (
          <Pill color={categoryStyle(listing.scraped_category).color} style={{ marginTop: 8 }}>{listing.subtype}</Pill>
        ) : null}

        <View style={{ marginTop: 'auto', paddingTop: 8 }}>
          {store ? (
            <Text numberOfLines={1} style={s.store}>
              {store.name}
              {listing.preferred_store_count > 1 ? ` · at ${listing.preferred_store_count} of yours` : ''}
            </Text>
          ) : null}
          <MarketNote market={listing.market} priceCents={listing.price_cents} />
        </View>
      </View>
    </Pressable>
  )
}

const s = StyleSheet.create({
  card: {
    backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border,
    borderRadius: radius.lg, overflow: 'hidden',
  },
  corner: {
    position: 'absolute', top: 8, overflow: 'hidden',
    backgroundColor: 'rgba(12, 15, 13, 0.78)', color: t.text1,
    fontFamily: fonts.monoMedium, fontSize: font.size.micro + 0.5,
    paddingHorizontal: 7, paddingVertical: 3, borderRadius: radius.sm,
  },
  save: { left: undefined, right: 8, backgroundColor: t.success, color: t.accentInk, fontVariant: ['tabular-nums'] },
  body: { flex: 1, paddingTop: 10, paddingHorizontal: 11, paddingBottom: 12 },
  price: {
    fontFamily: fonts.sansBold, fontSize: font.size.callout + 1, color: t.text1,
    letterSpacing: -0.16, marginBottom: 4, fontVariant: ['tabular-nums'],
  },
  noPrice: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3, marginBottom: 4 },
  // Two lines, always: cards in a rail keep one height whatever the name.
  name: { fontFamily: fonts.sansSemibold, fontSize: font.size.small + 1, lineHeight: 17, height: 34, color: t.text1 },
  brand: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3, marginTop: 3 },
  store: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text2, marginBottom: 2 },
})
