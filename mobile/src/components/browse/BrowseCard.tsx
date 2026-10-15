import type { ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { formatDist, formatDollars } from '@web/utils/format'
import { availabilityOf, showsSubtype, type BrowseCardItem } from '@web/utils/browseLogic'
import { Pill, ProductImage } from '@/components/ui'
import { Icon } from '@/components/Icon'
import { t, font, fonts, radius } from '@/lib/theme'

/** A product in a browse grid or shelf, the twin of the web's BrowseCard
 *  (components/browse.tsx): the square plate with the size top-left, the
 *  distance top-right and "Out of stock" bottom-left; then "from $X", name,
 *  brand, subtype; then, pinned to the bottom so a row's cards line up, where
 *  it is sold. */
export default function BrowseCard({ item, color, suppressSubtype, width, onPress, action, footer }: {
  item: BrowseCardItem
  color: string
  /** Hide the subtype tag when it just restates the page ("flower" on Flower). */
  suppressSubtype?: string | null
  width: number
  onPress: () => void
  /** Drawn over the photo's bottom-right corner, beside the card's button
   *  rather than inside it (add to cart on a store's aisle). */
  action?: ReactNode
  /** Replaces the availability footer (a store's aisle shows the market note). */
  footer?: ReactNode
}) {
  const availability = availabilityOf(item)
  const price = item.priceCents != null ? formatDollars(item.priceCents) : null
  const card = (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={[
        item.name, item.brand, item.variant,
        price ? `${item.multiPriced ? 'from ' : ''}${price}` : 'price not listed',
        item.outOfStock ? 'out of stock' : null,
        item.distanceMi != null ? formatDist(item.distanceMi) : null,
      ].filter(Boolean).join(', ')}
      style={({ pressed }) => [s.card, { width }, action ? { flexGrow: 1 } : null, pressed && { backgroundColor: t.surface2 }]}
    >
      <View>
        <ProductImage uri={item.imageUrl} size={width - 2} category={item.category} radius={0} />
        {item.variant ? <Text style={[s.badge, s.badgeText, { top: 8, left: 8 }]}>{item.variant}</Text> : null}
        {item.outOfStock ? (
          <Text style={[s.badge, s.badgeText, s.out, { bottom: 8, left: 8 }]}>Out of stock</Text>
        ) : null}
        {item.distanceMi != null ? (
          <View style={[s.badge, s.distance, { top: 8, right: 8 }]}>
            <Icon name="pin" size={11} strokeWidth={2} color={t.text1} />
            <Text style={s.badgeText}>{formatDist(item.distanceMi)}</Text>
          </View>
        ) : null}
      </View>

      <View style={s.body}>
        {price ? (
          <View style={s.priceRow}>
            {item.multiPriced ? <Text style={s.from}>from</Text> : null}
            <Text style={s.price}>{price}</Text>
          </View>
        ) : (
          <Text style={s.noPrice}>Price not listed</Text>
        )}
        <Text numberOfLines={2} style={s.name}>{item.name}</Text>
        {item.brand ? <Text numberOfLines={1} style={s.brand}>{item.brand}</Text> : null}
        {showsSubtype(item, suppressSubtype) ? (
          <Pill color={color} style={{ marginTop: 8 }}>{item.subtype}</Pill>
        ) : null}

        {footer ? (
          <View style={s.footer}>{footer}</View>
        ) : availability ? (
          <View style={s.footer}>
            {item.dispensaryCount > 1 ? <Icon name="pin" size={12} color={t.text3} /> : null}
            <Text numberOfLines={1} style={s.availability}>{availability}</Text>
          </View>
        ) : null}
      </View>
    </Pressable>
  )
  if (!action) return card
  return (
    <View style={{ width }}>
      {card}
      <View style={[s.corner, { top: width - 2 - 44 }]}>{action}</View>
    </View>
  )
}

const s = StyleSheet.create({
  corner: { position: 'absolute', right: 8 },
  card: {
    backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border,
    borderRadius: radius.lg, overflow: 'hidden',
  },
  // Dark glass on the plate, mono figures.
  badge: {
    position: 'absolute', overflow: 'hidden',
    backgroundColor: 'rgba(12, 15, 13, 0.78)',
    paddingHorizontal: 7, paddingVertical: 3, borderRadius: radius.sm,
  },
  badgeText: { fontFamily: fonts.monoMedium, fontSize: font.size.micro + 0.5, color: t.text1 },
  out: { color: t.warning, textTransform: 'uppercase', letterSpacing: 0.6 },
  distance: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  body: { flex: 1, paddingTop: 10, paddingHorizontal: 11, paddingBottom: 12 },
  priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 5, marginBottom: 4 },
  from: {
    fontFamily: fonts.mono, fontSize: font.size.micro, color: t.text3,
    textTransform: 'uppercase', letterSpacing: 0.6,
  },
  price: {
    fontFamily: fonts.sansBold, fontSize: font.size.callout + 1, color: t.text1,
    letterSpacing: -0.16, fontVariant: ['tabular-nums'],
  },
  noPrice: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3, marginBottom: 4 },
  name: { fontFamily: fonts.sansSemibold, fontSize: font.size.small + 1, lineHeight: 17, color: t.text1 },
  brand: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3, marginTop: 3 },
  footer: { marginTop: 'auto', paddingTop: 8, flexDirection: 'row', alignItems: 'center', gap: 4 },
  availability: { flexShrink: 1, fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3 },
})
