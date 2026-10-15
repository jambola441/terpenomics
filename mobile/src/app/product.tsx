import { useMemo } from 'react'
import { FlatList, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { formatDist, formatDollars, haversineMi } from '@web/utils/format'
import { LINE_MIN_PRODUCTS, nameWithinLine } from '@web/utils/lines'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useFetch } from '@/lib/useFetch'
import { openBrand, openListing, openProduct } from '@/lib/products'
import { useKnownPosition } from '@/components/partners'
import {
  CannabinoidTiles, CategoryTag, ClassificationTag, CollapsibleBlock, DetailBlock, FeedState, Label,
  ProductImage, SpecRow, TerpeneProfile, categoryName, styles,
} from '@/components/ui'
import { Icon } from '@/components/Icon'
import { t, space, font, fonts, radius, type } from '@/lib/theme'

/**
 * One product across every store that carries it: the web's ProductView.
 * Where to buy comes first, sorted by distance when the phone already shares
 * where it is (in stock before out), then the price spread, the rest of its
 * line, and lab data borrowed from the cheapest offering's listing.
 */
export default function ProductScreen() {
  const { key, brand: brandParam } = useLocalSearchParams<{ key: string; brand?: string }>()
  const brand = brandParam || null
  const flags = useAuth().profile?.flags
  const linesOn = flags?.lines === true
  const userPos = useKnownPosition()

  const { data: product, error, loading, refresh } = useFetch(`product:${brand ?? ''}:${key}`, () =>
    api.portal.getProductDetail(key, brand),
  )

  // Lab data, the description and the type come from one representative
  // listing: the cheapest offering, as on the web.
  const rep = useMemo(() => {
    if (!product?.offerings.length) return null
    return [...product.offerings]
      .filter(o => o.price_cents != null)
      .sort((a, b) => a.price_cents! - b.price_cents!)[0] ?? product.offerings[0]
  }, [product])
  const { data: detail } = useFetch(rep ? `rep:${rep.dispensary_id}/${rep.listing_id}` : 'rep:none', () =>
    rep ? api.portal.getListing(rep.dispensary_id, rep.listing_id) : Promise.resolve(null),
  )

  // The rest of this product's line (flag `lines`).
  const lineBrand = product?.brand ?? null
  const lineName = product?.product_line ?? null
  const { data: line } = useFetch(
    linesOn && lineBrand && lineName ? `line:${lineBrand}:${lineName}` : 'line:none',
    () => (linesOn && lineBrand && lineName ? api.portal.getBrandLine(lineBrand, lineName) : Promise.resolve(null)),
  )
  const lineProducts = line?.products ?? null
  const lineIsReal = lineProducts != null && lineProducts.length >= LINE_MIN_PRODUCTS
  const moreInLine = lineIsReal
    ? lineProducts.filter(p => p.key !== key).sort((a, b) => b.dispensary_count - a.dispensary_count).slice(0, 12)
    : []

  const offerings = useMemo(() => {
    if (!product) return []
    const withDist = product.offerings.map(o => ({
      offering: o,
      dist: userPos && o.lat != null && o.lng != null ? haversineMi(userPos.lat, userPos.lng, o.lat, o.lng) : null,
    }))
    return withDist.sort((a, b) => {
      if (a.offering.in_stock !== b.offering.in_stock) return a.offering.in_stock ? -1 : 1
      if (a.dist != null && b.dist != null) return a.dist - b.dist
      if (a.dist != null) return -1
      if (b.dist != null) return 1
      const pa = a.offering.price_cents
      const pb = b.offering.price_cents
      if (pa == null) return 1
      if (pb == null) return -1
      return pa - pb
    })
  }, [product, userPos])

  if (loading || error) return <FeedState loading={loading} error={error} onRetry={refresh} />
  if (!product) return <FeedState empty="Product not found" icon="package" />

  // Lowest and average among stores that have it in stock; everything if
  // nobody does right now.
  const stocked = product.offerings.filter(o => o.in_stock)
  const priced = stocked.length ? stocked : product.offerings
  const prices = priced.map(o => o.price_cents).filter((p): p is number => p != null)
  const minPrice = prices.length ? Math.min(...prices) : null
  const maxPrice = prices.length ? Math.max(...prices) : null
  const avgPrice = prices.length ? Math.round(prices.reduce((s, p) => s + p, 0) / prices.length) : null
  const savings = minPrice != null && maxPrice != null ? maxPrice - minPrice : 0

  const classification = detail?.classification ?? null
  const strain = product.strain ?? detail?.strain ?? null
  const subtype = product.subtype ?? detail?.subtype ?? null
  const productLine = product.product_line ?? detail?.product_line ?? null
  const description = detail?.description ?? null
  const cannabinoids = detail?.cannabinoids ?? []
  const terpenes = detail?.terpenes ?? []
  const hasSpecs = !!(strain || subtype || productLine || product.variant || classification)

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ paddingBottom: space[8] }}>
      {product.brand ? (
        <View style={s.crumbs} accessibilityLabel="Breadcrumb">
          <Crumb label={product.brand} onPress={() => openBrand(product.brand!)} />
          {linesOn && product.category ? (
            <>
              <Text style={s.sep}>›</Text>
              <Crumb label={categoryName(product.category)} onPress={() => openBrand(product.brand!, { category: product.category! })} />
            </>
          ) : null}
          {linesOn && lineIsReal && lineName ? (
            <>
              <Text style={s.sep}>›</Text>
              <Crumb label={lineName} current onPress={() => openBrand(product.brand!, { line: lineName })} />
            </>
          ) : null}
        </View>
      ) : null}

      <View style={s.hero}>
        <ProductImage uri={product.image_url} size={96} category={product.category} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.name} accessibilityRole="header">{product.name}</Text>
          <View style={s.tags}>
            {product.category ? <CategoryTag category={product.category} /> : null}
            {classification ? <ClassificationTag classification={classification} /> : null}
            {product.variant ? <Text style={[type.mono, { fontSize: font.size.caption, color: t.text3 }]}>{product.variant}</Text> : null}
          </View>
          {minPrice != null ? (
            <Text style={[type.mono, { color: t.text2, marginTop: 8 }]}>
              {minPrice === maxPrice ? formatDollars(minPrice) : `${formatDollars(minPrice)} – ${formatDollars(maxPrice!)}`}
            </Text>
          ) : null}
        </View>
      </View>

      {minPrice != null ? (
        <View style={s.gutter}>
          <View style={s.insights}>
            {[
              { label: 'Lowest', value: formatDollars(minPrice), accent: true },
              { label: 'Average', value: avgPrice != null ? formatDollars(avgPrice) : '—', accent: false },
              { label: 'Highest', value: maxPrice != null ? formatDollars(maxPrice) : '—', accent: false },
            ].map((cell, i) => (
              <View key={cell.label} style={[s.cell, i > 0 && { borderLeftWidth: 1, borderLeftColor: t.border }]}>
                <Text style={[type.price, { fontSize: font.size.title, lineHeight: 22, color: cell.accent ? t.success : t.text1 }]}>{cell.value}</Text>
                <Text style={[type.label, { marginTop: 3 }]}>{cell.label}</Text>
              </View>
            ))}
          </View>
          {savings > 0 ? (
            <Text style={s.savings}>Save up to {formatDollars(savings)} by choosing the lowest-priced store</Text>
          ) : null}
        </View>
      ) : null}

      <View style={[s.gutter, { marginTop: space[5] }]}>
        <Label style={{ marginBottom: 2 }}>Where to buy</Label>
        <Text style={s.heading}>
          {product.dispensary_count === 1 ? 'Available at 1 dispensary' : `Available at ${product.dispensary_count} dispensaries`}
        </Text>
        {!userPos ? (
          <View style={s.hint}>
            <Icon name="locate" size={13} color={t.text3} />
            <Text style={type.meta}>Turn on location to sort by distance</Text>
          </View>
        ) : null}
      </View>

      <View style={[s.gutter, { gap: 10, marginTop: space[2] }]}>
        {offerings.map(({ offering: o, dist }) => {
          const isCheapest = o.price_cents != null && o.price_cents === minPrice && minPrice !== maxPrice
          return (
            <Pressable
              key={o.listing_id}
              onPress={() => openListing(o.dispensary_id, o.listing_id)}
              accessibilityRole="button"
              style={({ pressed }) => [styles.card, s.offer, pressed && { backgroundColor: t.surface2 }]}
            >
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[styles.name, { fontSize: font.size.callout }]} numberOfLines={1}>{o.dispensary_name}</Text>
                <View style={s.offerMeta}>
                  {dist != null ? (
                    <>
                      <Icon name="pin" size={12} color={t.text3} />
                      <Text style={type.meta}>{formatDist(dist)} ·</Text>
                    </>
                  ) : null}
                  <Text style={[type.meta, { color: o.in_stock ? t.success : t.warning }]}>{o.in_stock ? 'In stock' : 'Out of stock'}</Text>
                </View>
              </View>
              <View style={{ alignItems: 'flex-end', gap: 2 }}>
                {o.price_cents != null ? <Text style={[type.price, { fontSize: font.size.callout }]}>{formatDollars(o.price_cents)}</Text> : null}
                {isCheapest ? <Text style={[type.label, { color: t.success }]}>lowest</Text> : null}
              </View>
              <Icon name="chevron-right" size={18} color={t.text3} />
            </Pressable>
          )
        })}
      </View>

      {moreInLine.length > 0 && lineBrand && lineName ? (
        <View style={{ marginTop: space[6] }}>
          <View style={[s.gutter, s.rowHead]}>
            <Label>More in {lineName}</Label>
            <Pressable onPress={() => openBrand(lineBrand, { line: lineName })} hitSlop={8} style={s.rowAction} accessibilityRole="button">
              <Text style={type.link}>All {lineProducts!.length}</Text>
              <Icon name="chevron-right" size={14} color={t.text2} />
            </Pressable>
          </View>
          <FlatList
            horizontal
            data={moreInLine}
            keyExtractor={p => p.key}
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: space[4], gap: 12 }}
            renderItem={({ item: p }) => (
              <Pressable onPress={() => openProduct(p.key, lineBrand)} style={{ width: 128, gap: 6 }} accessibilityRole="button">
                <ProductImage uri={p.image_url} size={128} category={p.category} />
                {p.min_price_cents != null ? <Text style={[type.price, { fontSize: font.size.callout }]}>{formatDollars(p.min_price_cents)}</Text> : null}
                <Text style={[type.body, { fontSize: font.size.small + 1, lineHeight: 17 }]} numberOfLines={2}>{nameWithinLine(p.name, lineName)}</Text>
                <Text style={type.label} numberOfLines={1}>
                  {[p.variant, `${p.dispensary_count} ${p.dispensary_count === 1 ? 'store' : 'stores'}`].filter(Boolean).join(' · ')}
                </Text>
              </Pressable>
            )}
          />
        </View>
      ) : null}

      {cannabinoids.length > 0 ? (
        <DetailBlock title="Cannabinoids" style={[s.gutter, s.block]}>
          <CannabinoidTiles items={cannabinoids} />
        </DetailBlock>
      ) : null}

      {terpenes.length > 0 ? (
        <DetailBlock title="Terpene profile" style={[s.gutter, s.block]}>
          <TerpeneProfile terpenes={terpenes} />
        </DetailBlock>
      ) : null}

      {hasSpecs ? (
        <DetailBlock title="Details" style={[s.gutter, s.block]}>
          {strain ? <SpecRow label="Strain" value={strain} /> : null}
          {classification ? <SpecRow label="Type" value={classification} /> : null}
          {subtype ? <SpecRow label="Form" value={subtype} /> : null}
          {productLine ? <SpecRow label="Product line" value={productLine} /> : null}
          {product.variant ? <SpecRow label="Size" value={product.variant} /> : null}
        </DetailBlock>
      ) : null}

      {description ? (
        <CollapsibleBlock title="Product Description" style={[s.gutter, s.block]}>
          <Text style={[type.body, { color: t.text2, fontSize: font.size.small, lineHeight: 21 }]}>{description}</Text>
        </CollapsibleBlock>
      ) : null}
    </ScrollView>
  )
}

/** One step of the breadcrumb; the last names where the product sits. */
function Crumb({ label, current = false, onPress }: { label: string; current?: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} hitSlop={6} accessibilityRole="link" style={{ maxWidth: 160, paddingVertical: 6 }}>
      <Text
        numberOfLines={1}
        style={{
          fontFamily: current ? fonts.sansSemibold : fonts.sansMedium,
          fontSize: font.size.small + 1,
          color: current ? t.text1 : t.text2,
        }}
      >
        {label}
      </Text>
    </Pressable>
  )
}

const s = StyleSheet.create({
  gutter: { paddingHorizontal: space[4] },
  block: { marginTop: space[6] },
  crumbs: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6, paddingHorizontal: space[4], paddingTop: space[1] },
  sep: { color: t.text4, fontSize: font.size.small + 1 },
  hero: { flexDirection: 'row', alignItems: 'center', gap: space[4], padding: space[4], paddingTop: space[2] },
  name: { ...type.title, fontSize: font.size.display, lineHeight: 30 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 8 },
  insights: { flexDirection: 'row', backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border, borderRadius: radius.lg, overflow: 'hidden' },
  cell: { flex: 1, alignItems: 'center', paddingVertical: 12, paddingHorizontal: 8 },
  savings: { ...type.meta, color: t.success, fontFamily: fonts.sansMedium, textAlign: 'center', marginTop: 10 },
  heading: { ...type.title, fontSize: font.size.heading, lineHeight: 24 },
  hint: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 4 },
  offer: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
  offerMeta: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 3 },
  rowHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  rowAction: { flexDirection: 'row', alignItems: 'center', gap: 2 },
})
