import { useCallback, useRef } from 'react'
import { FlatList, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native'
import { router, useFocusEffect } from 'expo-router'
import { FEED_RAILS, type FeedListing, type FeedRail } from '@web/types'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import ListingCard from '@/components/ListingCard'
import { FeedState, SectionTitle, styles } from '@/components/ui'
import { t, space, type } from '@/lib/theme'

const RAIL_TITLES: Record<FeedRail, string> = {
  featured: 'Featured',
  new: 'New on the shelf',
  recommended: 'Picked for you',
  deals: 'Best prices',
}

/** The combined feed across every store the shopper follows. Stores are
 *  picked in the stores screen (app/stores.tsx). */
export default function Home() {
  const { data: feed, error, loading, refreshing, refresh } = useFetch('feed', () => api.me.getFeed({ view: 'combined' }))

  // Back from picking stores, or from a listing where one was followed: show
  // the feed for the stores as they are now. The first focus is the load.
  const focused = useRef(false)
  useFocusEffect(
    useCallback(() => {
      if (focused.current) refresh()
      focused.current = true
    }, [refresh]),
  )

  if (loading || error) return <FeedState loading={loading} error={error} onRetry={refresh} />
  if (!feed?.combined || feed.dispensaries.length === 0) {
    return (
      <FeedState
        icon="store"
        empty="No stores yet"
        hint="Follow the stores you shop at and what's on their shelves shows up here."
        action={{ title: 'Pick your stores', onPress: () => router.push('/stores') }}
      />
    )
  }

  const stores = new Map(feed.dispensaries.map(d => [d.id, d]))
  const open = (l: FeedListing) => {
    if (l.dispensary_id) router.push(`/listing/${l.dispensary_id}/${l.id}`)
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ paddingBottom: space[8] }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={t.text3} />}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: space[4], paddingTop: space[3] }}>
        <Text style={type.meta}>
          {feed.dispensaries.length} {feed.dispensaries.length === 1 ? 'store' : 'stores'} you follow
        </Text>
        <Pressable onPress={() => router.push('/stores')} accessibilityRole="button" hitSlop={12}>
          <Text style={[type.link, { color: t.accent }]}>Edit</Text>
        </Pressable>
      </View>
      {FEED_RAILS.map(rail => {
        const items = feed.combined![rail]
        if (!items?.length) return null
        return (
          <View key={rail}>
            <SectionTitle>{RAIL_TITLES[rail]}</SectionTitle>
            <FlatList
              horizontal
              data={items}
              keyExtractor={l => l.id}
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: space[4], gap: space[3] }}
              renderItem={({ item }) => (
                <ListingCard
                  listing={item}
                  store={item.dispensary_id ? stores.get(item.dispensary_id) : null}
                  onPress={() => open(item)}
                />
              )}
            />
          </View>
        )
      })}
      <Text style={[styles.meta, { textAlign: 'center', marginTop: space[6] }]}>
        From {feed.dispensaries.length} store{feed.dispensaries.length === 1 ? '' : 's'} you follow
      </Text>
    </ScrollView>
  )
}
