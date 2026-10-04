import { FlatList, Pressable, RefreshControl, Text, useWindowDimensions } from 'react-native'
import { router } from 'expo-router'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { FeedState, ProductImage, styles } from '@/components/ui'
import { t, space } from '@/lib/theme'

export default function Categories() {
  const { data, error, loading, refreshing, refresh } = useFetch('categories', () => api.portal.getCategories())
  const { width } = useWindowDimensions()
  const tile = (width - space[4] * 2 - space[3]) / 2

  if (loading || error) return <FeedState loading={loading} error={error} onRetry={refresh} />

  return (
    <FlatList
      style={styles.screen}
      data={data ?? []}
      numColumns={2}
      keyExtractor={c => c.name}
      contentContainerStyle={{ padding: space[4], gap: space[4] }}
      columnWrapperStyle={{ gap: space[3] }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={t.accent} />}
      ListEmptyComponent={<FeedState empty="No categories yet." />}
      renderItem={({ item }) => (
        <Pressable
          style={({ pressed }) => [{ width: tile }, pressed && { opacity: 0.7 }]}
          onPress={() => router.push({ pathname: '/shop/[category]', params: { category: item.name } })}
        >
          <ProductImage uri={item.image_url} size={tile} />
          <Text style={[styles.name, { marginTop: space[2], textTransform: 'capitalize' }]}>{item.name}</Text>
          <Text style={styles.meta}>{item.listing_count.toLocaleString()} listings</Text>
        </Pressable>
      )}
    />
  )
}
