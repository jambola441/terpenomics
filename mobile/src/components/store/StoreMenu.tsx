import { useCallback, useMemo, useRef, useState } from 'react'
import { FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Image } from 'expo-image'
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg'
import type { DispensaryListing, PortalDispensary } from '@web/types'
import { alpha, categoryStyle } from '@web/design/tokens'
import { boroughColor } from '@web/utils/boroughs'
import { formatDollars, haversineMi } from '@web/utils/format'
import { api } from '@/lib/api'
import { openListing, openStore } from '@/lib/products'
import { useKeyboardHeight } from '@/lib/useKeyboardHeight'
import { useFetch } from '@/lib/useFetch'
import { useKnownPosition } from '@/components/partners'
import { FeedState, MarketNote, Pill, ProductImage, StoreBullet, categoryName, styles } from '@/components/ui'
import { CategoryIcon, Icon } from '@/components/Icon'
import { BackButton } from '@/components/browse/controls'
import CartCorner from './CartCorner'
import { t, font, fonts, radius, type } from '@/lib/theme'

/** The store's usual aisle order; anything unknown after. Same as the web. */
const CATEGORIES = ['flower', 'preroll', 'vaporizers', 'edible', 'concentrate', 'tinctures', 'topical', 'merch', 'other']
export function inShelfOrder(names: string[]): string[] {
  const known = CATEGORIES.filter(c => names.includes(c))
  return [...known, ...names.filter(n => !CATEGORIES.includes(n))]
}

/** Cards per category rail. */
const RAIL = 10
const SEARCH_LIMIT = 100
const CARD = 132

/**
 * A store's page: the web's DispensaryListings. Banner in the store's borough
 * colour, its identity, a menu search, the aisles it has stock in, and one
 * rail per aisle with its first ten, each with See all into the aisle.
 */
export default function StoreMenu({ store }: { store: PortalDispensary }) {
  const insets = useSafeAreaInsets()
  const keyboard = useKeyboardHeight()
  const pos = useKnownPosition()
  const distanceMi = pos && store.lat != null && store.lng != null ? haversineMi(pos.lat, pos.lng, store.lat, store.lng) : null

  const [input, setInput] = useState('')
  const [search, setSearch] = useState('')
  // What the store has in stock, by aisle: the strip and the rails both read it.
  const options = useRef<ReturnType<typeof api.portal.getDispensaryFilterOptions> | null>(null)
  const filterOptions = useCallback(() => {
    options.current ??= api.portal.getDispensaryFilterOptions(store.id)
    return options.current
  }, [store.id])

  const menu = useFetch(`menu:${store.id}:${search}`, async () => {
    try {
      if (search) {
        return { shelf: null, listings: await api.portal.getDispensaryListings(store.id, { q: search, limit: SEARCH_LIMIT, offset: 0 }) }
      }
      const o = await filterOptions()
      if (!o.categories) {
        return { shelf: null, listings: await api.portal.getDispensaryListings(store.id, { limit: SEARCH_LIMIT, offset: 0 }) }
      }
      // One request per aisle, so a big store's flower can't crowd out the rest.
      const rails = await Promise.all(o.categories.map(c =>
        api.portal.getDispensaryListings(store.id, { category: c.name, limit: RAIL, offset: 0 })))
      return { shelf: o.categories, listings: rails.flat() }
    } catch {
      options.current = null // Try again asks afresh
      throw new Error('Failed to load menu')
    }
  })
  const { loading, error } = menu
  const listings = useMemo(() => menu.data?.listings ?? [], [menu.data])
  // The strip keeps the aisles while a search is showing.
  const shelf = useFetch(`options:${store.id}`, filterOptions).data?.categories ?? null

  const byCategory = useMemo(() => {
    const map = new Map<string, DispensaryListing[]>()
    for (const l of listings) {
      const key = l.scraped_category ?? 'other'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(l)
    }
    return inShelfOrder([...map.keys()]).map(k => [k, map.get(k)!] as const)
  }, [listings])
  const shelfCount = useMemo(() => new Map((shelf ?? []).map(c => [c.name, c.count])), [shelf])

  // The store wears its borough's line colour, as its bullet does on the map.
  const line = boroughColor(store.address)

  const submit = () => setSearch(input.trim())
  const clear = () => { setInput(''); setSearch('') }

  return (
    <ScrollView
      style={styles.screen}
      stickyHeaderIndices={[2]}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      contentContainerStyle={{ paddingBottom: 80 + keyboard }}
    >
      {/* Banner */}
      <View style={{ height: 160 + insets.top, backgroundColor: t.surface1 }}>
        {store.banner_url ? (
          <Image source={{ uri: store.banner_url }} style={StyleSheet.absoluteFill} contentFit="cover" />
        ) : (
          <Svg style={StyleSheet.absoluteFill}>
            <Defs>
              <LinearGradient id="banner" x1="0" y1="0" x2="0.6" y2="1">
                <Stop offset="0" stopColor={line} stopOpacity={0.28} />
                <Stop offset="0.55" stopColor={line} stopOpacity={0.06} />
                <Stop offset="1" stopColor={t.surface1} stopOpacity={1} />
              </LinearGradient>
            </Defs>
            <Rect width="100%" height="100%" fill="url(#banner)" />
          </Svg>
        )}
        <Svg style={StyleSheet.absoluteFill}>
          <Defs>
            <LinearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={t.bg} stopOpacity={0.1} />
              <Stop offset="1" stopColor={t.bg} stopOpacity={1} />
            </LinearGradient>
          </Defs>
          <Rect width="100%" height="100%" fill="url(#fade)" />
        </Svg>
        <View style={{ position: 'absolute', top: insets.top + 8, left: 14 }}>
          <BackButton />
        </View>
      </View>

      {/* Identity */}
      <View style={s.identity}>
        {store.logo_url ? (
          <View style={s.logo}>
            <Image source={{ uri: store.logo_url }} style={{ width: '100%', height: '100%' }} contentFit="cover" />
          </View>
        ) : (
          <View style={s.logoRing}>
            <StoreBullet name={store.name} address={store.address} size={68} />
          </View>
        )}
        <Text style={s.name} accessibilityRole="header">{store.name}</Text>
        {store.address || distanceMi != null ? (
          <View style={s.where}>
            {store.address ? (
              <>
                <Icon name="pin" size={14} color={t.text3} />
                <Text style={[type.meta, { color: t.text2, fontSize: font.size.small + 1 }]}>{store.address}</Text>
              </>
            ) : null}
            {distanceMi != null ? (
              <Text style={[type.meta, { fontSize: font.size.small + 1 }]}>
                · {distanceMi < 0.1 ? '< 0.1' : distanceMi.toFixed(1)} mi away
              </Text>
            ) : null}
          </View>
        ) : null}
        {store.accepts_pickup
          ? <Pill tone="success" size="md" icon="bag" style={{ alignSelf: 'center' }}>Pickup orders</Pill>
          : <Pill size="md" style={{ alignSelf: 'center' }}>In store only</Pill>}
      </View>

      {/* Sticky search */}
      <View style={s.searchBar}>
        <View style={{ flex: 1, justifyContent: 'center' }}>
          <Icon name="search" size={16} color={t.text3} style={{ position: 'absolute', left: 12, zIndex: 1 }} />
          <TextInput
            value={input}
            onChangeText={setInput}
            onSubmitEditing={submit}
            placeholder="Search menu…"
            placeholderTextColor={t.text4}
            returnKeyType="search"
            autoCorrect={false}
            autoCapitalize="none"
            accessibilityLabel="Search menu"
            style={s.input}
          />
        </View>
        {search ? (
          <Pressable onPress={clear} accessibilityRole="button" accessibilityLabel="Clear search" style={s.clear}>
            <Icon name="close" size={16} color={t.text2} />
          </Pressable>
        ) : null}
      </View>

      {/* Aisles this store carries */}
      {shelf && shelf.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.strip}>
          {inShelfOrder(shelf.map(c => c.name)).map(cat => {
            const c = categoryStyle(cat).color
            return (
              <Pressable
                key={cat}
                onPress={() => openStore(store.id, cat)}
                accessibilityRole="button"
                accessibilityLabel={categoryName(cat)}
                style={s.aisle}
              >
                <View style={[s.aisleTile, { backgroundColor: alpha(c, 0.1), borderColor: alpha(c, 0.26) }]}>
                  <CategoryIcon category={cat} size={24} strokeWidth={1.6} />
                </View>
                <Text style={s.aisleLabel} numberOfLines={1}>{categoryName(cat)}</Text>
              </Pressable>
            )
          })}
        </ScrollView>
      ) : null}

      {loading ? (
        <FeedState loading style={{ minHeight: 240 }} />
      ) : error ? (
        <FeedState error={error} onRetry={menu.refresh} style={{ minHeight: 240 }} />
      ) : byCategory.length === 0 ? (
        <FeedState
          empty="Nothing found"
          hint={search ? `No menu items match “${search}”.` : 'This menu has no items right now.'}
          icon="search"
          style={{ minHeight: 240 }}
        />
      ) : (
        byCategory.map(([cat, items]) => (
          <View key={cat} style={{ marginBottom: 6 }}>
            <View style={s.railHead}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexShrink: 1 }}>
                <CategoryIcon category={cat} size={19} color={categoryStyle(cat).color} />
                <Text style={s.railTitle} accessibilityRole="header">{categoryName(cat)}</Text>
              </View>
              <Pressable onPress={() => openStore(store.id, cat)} hitSlop={8} accessibilityRole="button" style={s.seeAll}>
                <Text style={[type.link, { fontFamily: fonts.sansSemibold }]}>
                  See all{!search && shelfCount.get(cat) ? ` ${shelfCount.get(cat)}` : ''}
                </Text>
                <Icon name="chevron-right" size={15} color={t.text2} />
              </Pressable>
            </View>
            <FlatList
              horizontal
              data={items.slice(0, RAIL)}
              keyExtractor={l => l.id}
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 12, gap: 10 }}
              renderItem={({ item: l }) => <MenuCard listing={l} store={store} />}
            />
          </View>
        ))
      )}
    </ScrollView>
  )
}

/** A card on a store's rail: plate, price, name, size, and the market note. */
function MenuCard({ listing: l, store }: { listing: DispensaryListing; store: PortalDispensary }) {
  return (
    <View style={{ width: CARD }}>
      <Pressable
        onPress={() => openListing(store.id, l.id)}
        accessibilityRole="button"
        accessibilityLabel={[l.display_name, l.variant, l.price_cents != null ? formatDollars(l.price_cents) : null].filter(Boolean).join(', ')}
        style={({ pressed }) => [styles.card, { flex: 1, overflow: 'hidden' }, pressed && { backgroundColor: t.surface2 }]}
      >
        <ProductImage uri={l.image_url} size={CARD - 2} category={l.scraped_category} radius={0} />
        <View style={{ padding: 9, paddingBottom: 11 }}>
          {l.price_cents != null ? (
            <Text style={[type.price, { fontSize: font.size.callout, marginBottom: 3 }]}>{formatDollars(l.price_cents)}</Text>
          ) : null}
          <Text numberOfLines={2} style={[type.bodyStrong, { fontSize: font.size.small, lineHeight: 17 }]}>{l.display_name}</Text>
          {l.variant ? (
            <Text numberOfLines={1} style={[type.mono, { fontSize: font.size.caption, color: t.text3, marginTop: 4 }]}>{l.variant}</Text>
          ) : null}
          <MarketNote market={l.market} priceCents={l.price_cents} style={{ marginTop: 5 }} />
        </View>
      </Pressable>
      {store.accepts_pickup ? (
        <View style={{ position: 'absolute', right: 8, top: CARD - 2 - 44 }}>
          <CartCorner listing={l} store={store} />
        </View>
      ) : null}
    </View>
  )
}

const s = StyleSheet.create({
  identity: { alignItems: 'center', marginTop: -34, marginBottom: 18, paddingHorizontal: 16 },
  logo: {
    width: 74, height: 74, borderRadius: 37, borderWidth: 3, borderColor: t.bg,
    overflow: 'hidden', backgroundColor: t.surface2, marginBottom: 12,
  },
  logoRing: { borderRadius: 40, borderWidth: 3, borderColor: t.bg, marginBottom: 12 },
  name: {
    fontFamily: fonts.display, fontSize: font.size.hero - 2, lineHeight: 31, color: t.text1,
    textAlign: 'center', marginBottom: 8, letterSpacing: -0.5,
  },
  where: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', gap: 4, marginBottom: 12 },
  searchBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8, paddingHorizontal: 16,
    backgroundColor: alpha(t.bg, 0.96), borderBottomWidth: 1, borderBottomColor: t.border,
  },
  input: {
    ...type.input, fontSize: font.size.body, minHeight: 42, paddingLeft: 36, paddingRight: 13,
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.md, color: t.text1,
  },
  clear: {
    width: 42, height: 42, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border,
  },
  strip: { paddingTop: 16, paddingHorizontal: 8, paddingBottom: 8 },
  aisle: { alignItems: 'center', gap: 7, paddingHorizontal: 9 },
  aisleTile: { width: 54, height: 54, borderRadius: radius.lg, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  aisleLabel: { fontFamily: fonts.sansMedium, fontSize: font.size.caption, color: t.text2 },
  railHead: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingTop: 18, paddingHorizontal: 16, paddingBottom: 11,
  },
  railTitle: { fontFamily: fonts.display, fontSize: font.size.heading, lineHeight: 24, color: t.text1, letterSpacing: -0.3 },
  seeAll: { flexDirection: 'row', alignItems: 'center', gap: 2 },
})
