import { FlatList, RefreshControl, ScrollView, Text, View } from 'react-native'
import { router } from 'expo-router'
import { FEED_RAILS, type FeedListing, type FeedRail } from '@web/types'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import ListingCard from '@/components/ListingCard'
import { FeedState, SectionTitle, styles } from '@/components/ui'
import { t, space } from '@/lib/theme'

const RAIL_TITLES: Record<FeedRail, string> = {
  featured: 'Featured',
  new: 'New on the shelf',
  recommended: 'Picked for you',
  deals: 'Best prices',
}

/** The combined feed across every store the shopper follows. Following stores
 *  is done on the web for now; the Map tab that does it comes later. */
export default function Home() {
  const { data: feed, error, loading, refreshing, refresh } = useFetch('feed', () => api.me.getFeed({ view: 'combined' }))

  if (loading || error) return <FeedState loading={loading} error={error} onRetry={refresh} />
  if (!feed?.combined || feed.dispensaries.length === 0) {
    return (
      <FeedState
        icon="store"
        empty="No stores yet"
        hint="Follow a few stores on the Terpee website and their menus will show up here."
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
