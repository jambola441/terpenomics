import { useCallback, useRef, useState } from 'react'
import {
  FlatList, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View, useWindowDimensions,
} from 'react-native'
import { router, useFocusEffect } from 'expo-router'
import { Image } from 'expo-image'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import {
  FEED_RAILS, type FeedListing, type FeedRail, type FeedRails, type FeedSection, type FeedView, type PortalDispensary,
} from '@web/types'
import { alpha, categoryStyle } from '@web/design/tokens'
import { api, HOME_FEED } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import FeedCard from '@/components/FeedCard'
import { PartnerStrip } from '@/components/partners'
import { CategoryIcon, Icon, type IconName } from '@/components/Icon'
import { FeedState, PageTitle, Segmented, StoreBullet, categoryName, styles } from '@/components/ui'
import { t, font, fonts, radius, space } from '@/lib/theme'

/* Home, the twin of the web portal's HomeFeed (components/HomeFeed.tsx).

   The feed is built from the stores the shopper follows, read two ways:
     By store   each followed store gets its own block of rails
     Combined   the same rails pooled, each product once, at the cheapest store
   Each block is four rails (featured, new, for you, deals), two cards deep,
   scrolling sideways. A category filter applies across every store at once. */

const RAIL_LABELS: Record<FeedRail, { title: string; blurb: string; icon: IconName }> = {
  featured: { title: 'Featured', blurb: 'Picked by the store', icon: 'star' },
  new: { title: 'New arrivals', blurb: 'Just hit the shelf', icon: 'sparkles' },
  recommended: { title: 'For you', blurb: 'Based on what you buy', icon: 'heart' },
  deals: { title: 'Deals', blurb: 'Cheaper than elsewhere', icon: 'tag' },
}

const VIEWS: { key: FeedView; label: string }[] = [
  { key: 'store', label: 'By store' },
  { key: 'combined', label: 'Combined' },
]

export default function Home() {
  const insets = useSafeAreaInsets()
  const [view, setView] = useState<FeedView>(HOME_FEED.view)
  const [category, setCategory] = useState<string | null>(null)

  // Refetch on a view or category change rather than reshaping here: each rail
  // is ranked and capped server-side, so filtering eight rows on the phone
  // would leave whatever survived instead of the category's own eight.
  const feed = useFetch(`feed:${view}:${category ?? ''}`, () =>
    api.me.getFeed({ ...HOME_FEED, view, category: category ?? undefined }),
  )
  const categories = useFetch('categories', () => api.portal.getCategories())

  // Back from picking stores, or from a listing where one was followed: show
  // the feed for the stores as they are now. The first focus is the load.
  const focused = useRef(false)
  const refreshFeed = feed.refresh
  useFocusEffect(
    useCallback(() => {
      if (focused.current) refreshFeed()
      focused.current = true
    }, [refreshFeed]),
  )

  const data = feed.data
  // The header, toggle and chips stay put while a new view or category loads;
  // only a failure with nothing to show takes the whole screen.
  if (!data && feed.error) {
    return <FeedState error={feed.error} onRetry={feed.refresh} style={{ paddingTop: insets.top }} />
  }
  if (data && data.dispensaries.length === 0) {
    return (
      <FeedState
        icon="store"
        empty="No stores yet"
        hint="Follow the stores you shop at and what's on their shelves shows up here."
        action={{ title: 'Pick your stores', onPress: () => router.push('/stores') }}
        style={{ paddingTop: insets.top }}
      />
    )
  }

  const stores = new Map((data?.dispensaries ?? []).map(d => [d.id, d]))
  const followed = data?.dispensaries.length ?? 0
  const openListing = (dispensaryId: string | undefined, id: string) => {
    if (dispensaryId) router.push(`/listing/${dispensaryId}/${id}`)
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ paddingTop: insets.top + 26, paddingBottom: space[7] }}
      refreshControl={<RefreshControl refreshing={feed.refreshing} onRefresh={feed.refresh} tintColor={t.text3} />}
    >
      <View style={s.header}>
        <PageTitle
          style={{ flex: 1 }}
          sub={data ? `${followed} ${followed === 1 ? 'store' : 'stores'} · what's on the shelf now` : ' '}
        >
          Your stores
        </PageTitle>
        <Pressable
          onPress={() => router.push('/stores')}
          accessibilityRole="button"
          style={({ pressed }) => [s.edit, pressed && { backgroundColor: t.surface2 }]}
        >
          <Icon name="edit" size={14} color={t.text1} />
          <Text style={s.editText}>Edit</Text>
        </Pressable>
      </View>

      <PartnerStrip />

      <Segmented options={VIEWS} value={view} onChange={setView} style={{ marginTop: 14, marginHorizontal: space[4] }} />

      {categories.data?.length ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: space[2], paddingHorizontal: space[4], paddingTop: space[3], paddingBottom: space[1] }}
        >
          <CategoryChip label="All" active={category === null} onPress={() => setCategory(null)} />
          {categories.data.map(c => (
            <CategoryChip
              key={c.name}
              label={categoryName(c.name)}
              category={c.name}
              active={category === c.name}
              onPress={() => setCategory(category === c.name ? null : c.name)}
            />
          ))}
        </ScrollView>
      ) : null}

      {!data ? (
        <FeedState loading style={{ paddingVertical: space[8] }} />
      ) : data.view === 'combined' ? (
        <CombinedFeed rails={data.combined} stores={stores} category={category} onOpen={openListing} />
      ) : (
        data.sections.map(section => (
          <StoreSection key={section.dispensary.id} section={section} category={category} onOpen={openListing} />
        ))
      )}
    </ScrollView>
  )
}

/* ── One store's block of rails ────────────────────────────────────────────── */

function StoreSection({ section, category, onOpen }: {
  section: FeedSection
  category: string | null
  onOpen: (dispensaryId: string | undefined, id: string) => void
}) {
  const { dispensary, rails, total } = section
  const empty = FEED_RAILS.every(rail => rails[rail].length === 0)
  return (
    <View style={{ marginBottom: 14 }}>
      <View style={s.storeHead}>
        <StoreAvatar dispensary={dispensary} size={38} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={s.storeName} accessibilityRole="header">{dispensary.name}</Text>
          <Text style={s.storeMeta}>
            {total.toLocaleString()} in stock{dispensary.accepts_pickup ? ' · pickup' : ''}
          </Text>
        </View>
      </View>
      {empty ? (
        <Text style={s.storeEmpty}>
          {category ? `No ${categoryName(category).toLowerCase()} in stock here right now.` : 'Nothing in stock here right now.'}
        </Text>
      ) : (
        FEED_RAILS.map(rail => (
          <Rail key={rail} rail={rail} items={rails[rail]} onOpen={l => onOpen(dispensary.id, l.id)} />
        ))
      )}
    </View>
  )
}

/* ── Every followed store at once ──────────────────────────────────────────── */

function CombinedFeed({ rails, stores, category, onOpen }: {
  rails: FeedRails | null
  stores: Map<string, PortalDispensary>
  category: string | null
  onOpen: (dispensaryId: string | undefined, id: string) => void
}) {
  if (!rails || FEED_RAILS.every(rail => rails[rail].length === 0)) {
    return (
      <FeedState
        icon="leaf"
        empty={category ? `No ${categoryName(category).toLowerCase()} across your stores right now.` : 'Nothing in stock across your stores.'}
        style={{ paddingVertical: 48 }}
      />
    )
  }
  return (
    <View style={{ marginTop: 6 }}>
      {FEED_RAILS.map(rail => (
        <Rail key={rail} rail={rail} items={rails[rail]} stores={stores} onOpen={l => onOpen(l.dispensary_id, l.id)} />
      ))}
    </View>
  )
}

/* ── A rail: two cards deep, scrolling sideways ─────────────────────────────── */

function Rail({ rail, items, stores, onOpen }: {
  rail: FeedRail
  items: FeedListing[]
  stores?: Map<string, PortalDispensary>
  onOpen: (listing: FeedListing) => void
}) {
  const { width: screen } = useWindowDimensions()
  // An empty rail says nothing worth the space, except Featured: it is empty
  // because nobody has curated it yet, and saying so is how a store learns
  // the slot exists.
  if (items.length === 0 && rail !== 'featured') return null
  const { title, blurb, icon } = RAIL_LABELS[rail]
  // The web's grid columns: minmax(148px, 46%).
  const cardWidth = Math.max(148, Math.round(screen * 0.46))
  // Filled column by column, so a swipe moves through pairs.
  const columns: FeedListing[][] = []
  for (let i = 0; i < items.length; i += 2) columns.push(items.slice(i, i + 2))

  return (
    <View style={{ marginTop: 14 }}>
      <View style={s.railHead}>
        <Icon name={icon} size={15} color={t.text3} />
        <Text style={s.railTitle} accessibilityRole="header">{title}</Text>
        <Text numberOfLines={1} style={s.railBlurb}>{blurb}</Text>
      </View>
      {items.length === 0 ? (
        <Text style={s.railEmpty}>No picks from this store right now.</Text>
      ) : (
        <FlatList
          horizontal
          data={columns}
          keyExtractor={col => col.map(l => `${l.dispensary_id ?? ''}-${l.id}`).join('|')}
          showsHorizontalScrollIndicator={false}
          snapToInterval={cardWidth + 10}
          decelerationRate="fast"
          contentContainerStyle={{ paddingHorizontal: space[4], gap: 10, paddingBottom: 4 }}
          renderItem={({ item: col }) => (
            <View style={{ gap: 10 }}>
              {col.map(listing => (
                <FeedCard
                  key={`${listing.dispensary_id ?? ''}-${listing.id}`}
                  listing={listing}
                  rail={rail}
                  width={cardWidth}
                  store={listing.dispensary_id ? stores?.get(listing.dispensary_id) : undefined}
                  onPress={() => onOpen(listing)}
                />
              ))}
            </View>
          )}
        />
      )}
    </View>
  )
}

/** A store's logo when it has one, else its subway bullet, as on the map. */
function StoreAvatar({ dispensary, size }: { dispensary: PortalDispensary; size: number }) {
  const logo = dispensary.logo_url || dispensary.banner_url
  const [broken, setBroken] = useState(false)
  if (!logo || broken) return <StoreBullet name={dispensary.name} address={dispensary.address} size={size} />
  return (
    <View style={[s.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
      <Image source={{ uri: logo }} style={{ width: '100%', height: '100%' }} contentFit="cover" onError={() => setBroken(true)} />
    </View>
  )
}

function CategoryChip({ label, active, category, onPress }: {
  label: string
  active: boolean
  category?: string
  onPress: () => void
}) {
  const hue = category ? categoryStyle(category).color : t.accent
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={[
        s.chip,
        { paddingLeft: category ? 10 : 13 },
        active
          ? { backgroundColor: alpha(hue, 0.12), borderColor: alpha(hue, 0.6) }
          : { backgroundColor: t.surface2, borderColor: t.border },
      ]}
    >
      {category ? <CategoryIcon category={category} size={15} color={active ? hue : undefined} /> : null}
      <Text style={{ fontFamily: active ? fonts.sansSemibold : fonts.sansMedium, fontSize: font.size.small + 1, color: active ? hue : t.text2 }}>
        {label}
      </Text>
    </Pressable>
  )
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingHorizontal: space[4], paddingBottom: 6 },
  edit: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4,
    borderWidth: 1, borderColor: t.borderStrong, borderRadius: radius.md, paddingVertical: 7, paddingHorizontal: 12,
  },
  editText: { fontFamily: fonts.sansSemibold, fontSize: font.size.small + 1, color: t.text1 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingVertical: 7, paddingRight: 13, borderRadius: radius.pill, borderWidth: 1,
  },
  storeHead: { flexDirection: 'row', alignItems: 'center', gap: 11, paddingTop: 20, paddingHorizontal: space[4], paddingBottom: 6 },
  storeName: { fontFamily: fonts.display, fontSize: font.size.heading, lineHeight: 24, letterSpacing: -0.3, color: t.text1 },
  storeMeta: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3, marginTop: 2, fontVariant: ['tabular-nums'] },
  storeEmpty: {
    marginTop: 8, marginHorizontal: space[4], paddingVertical: 18, paddingHorizontal: 16, textAlign: 'center', overflow: 'hidden',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.lg,
    fontFamily: fonts.sans, fontSize: font.size.small, color: t.text3,
  },
  railHead: { flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: space[4], paddingBottom: 10 },
  railTitle: { fontFamily: fonts.sansSemibold, fontSize: font.size.callout, color: t.text1 },
  railBlurb: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3, flexShrink: 1 },
  railEmpty: {
    marginHorizontal: space[4], paddingVertical: 14, paddingHorizontal: 16, textAlign: 'center',
    borderWidth: 1, borderStyle: 'dashed', borderColor: t.borderStrong, borderRadius: radius.lg,
    fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3,
  },
  avatar: { overflow: 'hidden', backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border },
})
