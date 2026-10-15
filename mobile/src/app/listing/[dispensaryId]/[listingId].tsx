import { useEffect, useRef, useState } from 'react'
import { Alert, FlatList, Linking, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native'
import { Stack, useLocalSearchParams } from 'expo-router'
import { Image } from 'expo-image'
import type { ListingDetail, PortalDispensary } from '@web/types'
import { formatDist, formatDollars, haversineMi } from '@web/utils/format'
import { photoAt } from '@web/utils/photoUrl'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { addToCart, useCart } from '@/lib/cart'
import { directionsUrl, openListing, openProduct, openStore } from '@/lib/products'
import { useKnownPosition } from '@/components/partners'
import {
  CannabinoidTiles, CategoryTag, ClassificationTag, CollapsibleBlock, DetailBlock, FeedState, Label, Pill,
  ProductImage, SpecRow, StoreBullet, TerpeneProfile, styles,
} from '@/components/ui'
import { Icon, type IconName } from '@/components/Icon'
import { t, space, font, fonts, radius, type } from '@/lib/theme'

type Pos = { lat: number; lng: number } | null

/** "3 hours ago", roughly: precision past that is not something a shopper can
 *  act on, and a scrape time to the minute reads as false certainty. */
function checkedAgo(iso: string | null): string | null {
  if (!iso) return null
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (!Number.isFinite(minutes) || minutes < 0) return null
  if (minutes < 90) return `${Math.max(1, minutes)} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 36) return `${hours} hr ago`
  return `${Math.round(hours / 24)} days ago`
}

function distanceTo(pos: Pos, store: { lat: number | null; lng: number | null }): number | null {
  if (!pos || store.lat == null || store.lng == null) return null
  return haversineMi(pos.lat, pos.lng, store.lat, store.lng)
}

/**
 * One product on one store's shelf: the web's ListingDetail. Who sells it
 * (the store card), who else does and for how much, and what else is like it
 * on this shelf, alongside the product's own lab data.
 */
export default function ListingScreen() {
  const { dispensaryId, listingId } = useLocalSearchParams<{ dispensaryId: string; listingId: string }>()
  const { data: l, error, loading, refresh } = useFetch(`${dispensaryId}/${listingId}`, () =>
    api.portal.getListing(dispensaryId, listingId),
  )
  const pos = useKnownPosition()
  const { width } = useWindowDimensions()

  if (loading || error || !l) return <FeedState loading={loading} error={error} onRetry={refresh} />

  const cat = l.scraped_category ?? 'other'
  const context = l.price_context ?? { other_store_count: 0, min_cents: null, avg_cents: null, max_cents: null, is_cheapest: false }
  const elsewhere = l.also_available_at ?? []
  const similar = l.similar_at_dispensary ?? []
  const checked = checkedAgo(l.last_seen_at ?? null)
  // Scraped text, so only follow it if it is a real web link.
  const productUrl = l.url && /^https?:\/\//i.test(l.url) ? l.url : null
  const hero = l.image_url ? photoAt(l.image_url, Math.round(width * 2)) ?? l.image_url : null

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ paddingBottom: space[8] }}>
      <Stack.Screen options={{ title: l.dispensary_name }} />
      {hero ? (
        <HeroPhoto uri={hero} original={l.image_url!} size={width} label={l.display_name} />
      ) : (
        <ProductImage uri={null} size={width} category={cat} radius={0} />
      )}

      <View style={s.body}>
        <View style={s.tags}>
          <CategoryTag category={cat} />
          {l.classification ? <ClassificationTag classification={l.classification} /> : null}
          {l.variant ? <Pill>{l.variant}</Pill> : null}
          {!l.in_stock ? <Pill tone="danger">Out of stock</Pill> : null}
        </View>

        <Text style={s.name} accessibilityRole="header">{l.display_name}</Text>
        {l.scraped_brand ? <Text style={[type.body, { color: t.text2, fontSize: font.size.callout, marginBottom: 20 }]}>{l.scraped_brand}</Text> : null}

        <View style={s.priceRow}>
          {l.price_cents != null ? <Text style={[type.price, s.price]}>{formatDollars(l.price_cents)}</Text> : null}
          {l.dispensary_accepts_pickup && l.in_stock ? <AddToCart listing={l} /> : null}
        </View>

        <PriceContextLine listing={l} />

        {checked ? (
          <View style={s.checked}>
            <Icon name="clock" size={12} color={t.text3} />
            <Text style={type.meta}>Stock last checked {checked}</Text>
          </View>
        ) : null}

        {productUrl ? (
          <Pressable
            onPress={() => Linking.openURL(productUrl)}
            accessibilityRole="link"
            style={({ pressed }) => [s.outline, { marginTop: 14 }, pressed && { backgroundColor: t.surface1 }]}
          >
            <Text style={s.outlineText} numberOfLines={1}>View on {l.dispensary_name}&apos;s website</Text>
            <Icon name="arrow-up-right" size={15} color={t.text1} />
          </Pressable>
        ) : null}

        {l.dispensary ? <StoreCard store={l.dispensary} distanceMi={distanceTo(pos, l.dispensary)} /> : null}

        {elsewhere.length > 0 ? (
          <View style={{ marginTop: 28 }}>
            <Label style={{ marginBottom: 4 }}>Also available at</Label>
            <Text style={[type.meta, { marginBottom: 10 }]}>
              {elsewhere.length} other {elsewhere.length === 1 ? 'store' : 'stores'} carry this exact product
            </Text>
            <View style={{ gap: 8 }}>
              {elsewhere.map(row => (
                <AlternativeRow
                  key={row.listing_id}
                  name={row.dispensary.name}
                  address={row.dispensary.address}
                  priceCents={row.price_cents}
                  herePriceCents={l.price_cents}
                  distanceMi={distanceTo(pos, row.dispensary)}
                  acceptsPickup={row.dispensary.accepts_pickup}
                  onPress={() => openListing(row.dispensary.id, row.listing_id)}
                />
              ))}
            </View>
            <Pressable
              onPress={() => openProduct(l.product_key, l.scraped_brand ?? null)}
              accessibilityRole="button"
              style={({ pressed }) => [s.outline, { marginTop: 10 }, pressed && { backgroundColor: t.surface1 }]}
            >
              <Text style={s.outlineText}>Compare all {context.other_store_count + 1} stores</Text>
              <Icon name="arrow-right" size={15} color={t.text1} />
            </Pressable>
          </View>
        ) : null}

        {l.cannabinoids.length > 0 ? (
          <DetailBlock title="Cannabinoids" style={{ marginTop: 28 }}>
            <CannabinoidTiles items={l.cannabinoids} />
          </DetailBlock>
        ) : null}

        {l.terpenes.length > 0 ? (
          <DetailBlock title="Terpene profile" style={{ marginTop: 28 }}>
            <TerpeneProfile terpenes={l.terpenes} />
          </DetailBlock>
        ) : null}

        {l.strain || l.subtype || l.product_line || l.variant || l.classification ? (
          <DetailBlock title="Details" style={{ marginTop: 28 }}>
            {l.strain ? <SpecRow label="Strain" value={l.strain} /> : null}
            {l.classification ? <SpecRow label="Type" value={l.classification} /> : null}
            {l.subtype ? <SpecRow label="Form" value={l.subtype} /> : null}
            {l.product_line ? <SpecRow label="Product line" value={l.product_line} /> : null}
            {l.variant ? <SpecRow label="Size" value={l.variant} /> : null}
          </DetailBlock>
        ) : null}

        {l.description ? (
          <CollapsibleBlock title="Product Description" style={{ marginTop: 28 }}>
            <Text style={[type.body, { color: t.text2, fontSize: font.size.small, lineHeight: 21 }]}>{l.description}</Text>
          </CollapsibleBlock>
        ) : null}
      </View>

      {similar.length > 0 ? (
        <View>
          <View style={{ paddingHorizontal: 20, paddingBottom: 10 }}>
            <Label style={{ marginBottom: 4 }}>Similar at this store</Label>
            <Text style={type.meta}>More like this on {l.dispensary_name}&apos;s shelf</Text>
          </View>
          <FlatList
            horizontal
            data={similar}
            keyExtractor={r => r.id}
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: 20, gap: 10 }}
            renderItem={({ item: row }) => (
              <Pressable
                onPress={() => openListing(l.dispensary_id, row.id)}
                accessibilityRole="button"
                style={({ pressed }) => [styles.card, s.similar, pressed && { backgroundColor: t.surface2 }]}
              >
                <ProductImage uri={row.image_url} size={142} category={row.scraped_category} radius={0} />
                <View style={{ padding: 10, paddingTop: 8 }}>
                  {row.scraped_brand ? (
                    <Text numberOfLines={1} style={[type.meta, { fontFamily: fonts.sansSemibold, marginBottom: 2 }]}>{row.scraped_brand}</Text>
                  ) : null}
                  <Text numberOfLines={2} style={[type.bodyStrong, { fontSize: font.size.small, lineHeight: 17, height: 34 }]}>{row.display_name}</Text>
                  <View style={s.similarFoot}>
                    <Text style={[type.price, { fontSize: font.size.small + 2 }]}>{row.price_cents != null ? formatDollars(row.price_cents) : '—'}</Text>
                    {row.variant ? <Text style={[type.mono, { fontSize: font.size.caption, color: t.text3 }]}>{row.variant}</Text> : null}
                  </View>
                </View>
              </Pressable>
            )}
          />
        </View>
      ) : null}
    </ScrollView>
  )
}

/** The listing's photo across the screen, on the light plate. Sized outright
 *  (a flex child drew blank until the first scroll), and the original file
 *  when the resized one fails. */
function HeroPhoto({ uri, original, size, label }: { uri: string; original: string; size: number; label: string }) {
  const [failed, setFailed] = useState(false)
  return (
    <View style={{ width: size, height: size, backgroundColor: t.tile, padding: 24 }}>
      <Image
        source={{ uri: failed ? original : uri }}
        style={{ width: size - 48, height: size - 48 }}
        contentFit="contain"
        transition={150}
        accessibilityLabel={label}
        onError={() => setFailed(true)}
      />
    </View>
  )
}

/* ── Where this price sits ─────────────────────────────────────────────────── */

function PriceContextLine({ listing }: { listing: ListingDetail }) {
  const { price_context: context, price_cents: price } = listing
  if (!context || context.other_store_count === 0) {
    return <Text style={[type.meta, { fontSize: font.size.small, marginTop: 8 }]}>No other store we track carries this.</Text>
  }
  if (price == null || context.avg_cents == null) return null

  const gap = context.avg_cents - price
  const stores = `${context.other_store_count} other ${context.other_store_count === 1 ? 'store' : 'stores'}`
  const line = { ...type.body, color: t.text2, fontSize: font.size.small + 1, lineHeight: 20 }

  // Somewhere cheaper is the thing to say first.
  if (!context.is_cheapest && context.min_cents != null && context.min_cents < price) {
    const cheapest = (listing.also_available_at ?? []).find(a => a.price_cents === context.min_cents)
    return (
      <Text style={[line, { marginTop: 10 }]}>
        <Text style={{ color: t.warning, fontFamily: fonts.sansSemibold }}>
          {formatDollars(price - context.min_cents)} less at {cheapest ? cheapest.dispensary.name : 'another store'}
        </Text>
        {' · '}average at {stores} {formatDollars(context.avg_cents)}
      </Text>
    )
  }

  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 10 }}>
      {context.is_cheapest ? <Pill tone="success" size="md">Cheapest of {context.other_store_count + 1}</Pill> : null}
      <Text style={line}>
        {gap > 0
          ? `${formatDollars(gap)} below the average at ${stores}`
          : gap < 0
            ? `${formatDollars(-gap)} above the average at ${stores}`
            : `The same as the average at ${stores}`}
      </Text>
    </View>
  )
}

/* ── The store ─────────────────────────────────────────────────────────────── */

function StoreCard({ store, distanceMi }: { store: PortalDispensary; distanceMi: number | null }) {
  const directions = directionsUrl(store)
  const [logoFailed, setLogoFailed] = useState(false)
  return (
    <View style={[styles.card, { marginTop: 26, padding: 14 }]}>
      <Label style={{ marginBottom: 12 }}>Sold at</Label>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        {store.logo_url && !logoFailed ? (
          <View style={s.logo}>
            <Image source={{ uri: store.logo_url }} style={{ width: '100%', height: '100%' }} contentFit="cover" onError={() => setLogoFailed(true)} />
          </View>
        ) : (
          <StoreBullet name={store.name} address={store.address} size={44} />
        )}
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={[type.title, { fontSize: font.size.title, lineHeight: 22 }]}>{store.name}</Text>
          <Text numberOfLines={2} style={[type.meta, { marginTop: 2 }]}>
            {store.address ?? 'Address unknown'}
            {distanceMi != null ? ` · ${formatDist(distanceMi)}` : ''}
          </Text>
        </View>
        <FollowStore dispensaryId={store.id} name={store.name} />
      </View>
      <View style={{ marginTop: 12 }}>
        {store.accepts_pickup ? <Pill tone="success" icon="bag">Order for pickup</Pill> : <Pill>In-store only</Pill>}
      </View>
      <View style={s.actions}>
        <StoreAction label="Menu" icon="list" onPress={() => openStore(store.id)} />
        {directions ? <StoreAction label="Directions" icon="navigate" onPress={() => Linking.openURL(directions)} /> : null}
        {store.website_url ? <StoreAction label="Website" icon="arrow-up-right" onPress={() => Linking.openURL(store.website_url!)} /> : null}
      </View>
    </View>
  )
}

function StoreAction({ label, icon, onPress }: { label: string; icon: IconName; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [s.storeAction, pressed && { backgroundColor: t.surface3 }]}
    >
      <Icon name={icon} size={15} color={t.text3} />
      <Text style={[type.bodyStrong, { fontFamily: fonts.sansMedium, fontSize: font.size.small + 1 }]}>{label}</Text>
    </Pressable>
  )
}

/** Follow / Following, so a shopper can add a store to Home from where they
 *  found it. */
function FollowStore({ dispensaryId, name }: { dispensaryId: string; name: string }) {
  const { data: followed, setData } = useFetch('followed', () => api.me.listPreferredDispensaries())
  const [busy, setBusy] = useState(false)
  if (!followed) return null
  const following = followed.some(d => d.id === dispensaryId)

  async function toggle() {
    setBusy(true)
    try {
      const next = following
        ? await api.me.removePreferredDispensary(dispensaryId)
        : await api.me.addPreferredDispensary(dispensaryId)
      setData(() => next)
    } catch {
      Alert.alert("That didn't save", 'Check your connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Pressable
      onPress={toggle}
      disabled={busy}
      accessibilityRole="button"
      accessibilityState={{ selected: following, busy }}
      accessibilityLabel={following ? `Unfollow ${name}` : `Follow ${name}`}
      style={[s.follow, following ? { borderColor: t.accent } : { backgroundColor: t.accent, borderColor: t.accent }]}
    >
      {following ? <Icon name="check" size={14} color={t.accent} /> : null}
      <Text style={[type.button, { fontSize: 14, color: following ? t.accent : t.accentInk }]}>
        {following ? 'Following' : 'Follow'}
      </Text>
    </Pressable>
  )
}

/* ── The same product somewhere else ───────────────────────────────────────── */

function AlternativeRow({ name, address, priceCents, herePriceCents, distanceMi, acceptsPickup, onPress }: {
  name: string
  address: string | null
  priceCents: number | null
  herePriceCents: number | null
  distanceMi: number | null
  acceptsPickup: boolean
  onPress: () => void
}) {
  // The difference is the number that matters: the price here is already on screen.
  const gap = priceCents != null && herePriceCents != null ? priceCents - herePriceCents : null
  const gapColor = gap == null || gap === 0 ? t.text3 : gap < 0 ? t.success : t.danger
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [styles.card, s.altRow, pressed && { backgroundColor: t.surface2 }]}
    >
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text numberOfLines={1} style={[type.bodyStrong, { fontSize: font.size.small + 1 }]}>{name}</Text>
        <Text numberOfLines={1} style={[type.meta, { marginTop: 2 }]}>
          {distanceMi != null ? formatDist(distanceMi) : address ?? '—'}
          {acceptsPickup ? ' · pickup' : ''}
        </Text>
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={[type.price, { fontSize: font.size.body }]}>{priceCents != null ? formatDollars(priceCents) : '—'}</Text>
        {gap != null ? (
          <Text style={[type.mono, { fontSize: font.size.caption, color: gapColor, marginTop: 2 }]}>
            {gap === 0 ? 'same price' : `${gap < 0 ? '−' : '+'}${formatDollars(Math.abs(gap))}`}
          </Text>
        ) : null}
      </View>
    </Pressable>
  )
}

/* ── Add to cart, beside the price as on the web ────────────────────────────── */

function AddToCart({ listing }: { listing: ListingDetail }) {
  const cart = useCart()
  const inCart = cart.items.find(i => i.listingId === listing.id)?.quantity ?? 0
  const [flash, setFlash] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  function showAdded() {
    setFlash(true)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setFlash(false), 1500)
  }

  const add = () => addToCart(cart, listing, showAdded)

  return (
    <Pressable
      onPress={add}
      accessibilityRole="button"
      style={({ pressed }) => [s.add, { backgroundColor: flash ? t.success : pressed ? t.accentStrong : t.accent }]}
    >
      <Icon name={flash ? 'check' : 'bag'} size={17} color={t.accentInk} strokeWidth={2} />
      <Text style={[type.button, { color: t.accentInk, fontFamily: fonts.sansBold, fontSize: font.size.callout }]}>
        {flash ? 'Added' : inCart > 0 ? `Add another · ${inCart} in cart` : 'Add to cart'}
      </Text>
    </Pressable>
  )
}

const s = StyleSheet.create({
  body: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 32 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 14 },
  name: { ...type.title, fontSize: font.size.hero - 2, lineHeight: 32, marginBottom: 6 },
  priceRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 14 },
  price: { fontSize: font.size.hero - 2, lineHeight: 34 },
  add: {
    flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: radius.md,
    paddingVertical: 12, paddingLeft: 16, paddingRight: 20,
  },
  checked: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 8 },
  outline: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, padding: 12,
    borderWidth: 1, borderColor: t.borderStrong, borderRadius: radius.md,
  },
  outlineText: { ...type.bodyStrong, fontFamily: fonts.sansMedium, fontSize: font.size.small + 1, flexShrink: 1 },
  logo: {
    width: 44, height: 44, borderRadius: 22, overflow: 'hidden',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border,
  },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  storeAction: {
    flex: 1, minWidth: 92, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    paddingVertical: 10, paddingHorizontal: 12, backgroundColor: t.surface2,
    borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  follow: {
    flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: 32,
    paddingHorizontal: space[3], borderRadius: radius.pill, borderWidth: 1,
  },
  altRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, paddingHorizontal: 13 },
  similar: { width: 142, overflow: 'hidden' },
  similarFoot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6, marginTop: 7 },
})
