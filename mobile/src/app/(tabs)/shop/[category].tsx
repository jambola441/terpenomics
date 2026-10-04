import { Alert, FlatList, Pressable, Text, View } from 'react-native'
import { router, Stack, useLocalSearchParams } from 'expo-router'
import type { PortalCategoryProduct } from '@web/types'
import { formatDollars } from '@web/utils/format'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { FeedState, ProductImage, styles } from '@/components/ui'
import { space } from '@/lib/theme'

function priceRange(p: PortalCategoryProduct) {
  if (p.min_price_cents == null) return '—'
  if (p.max_price_cents == null || p.max_price_cents === p.min_price_cents) return formatDollars(p.min_price_cents)
  return `${formatDollars(p.min_price_cents)} – ${formatDollars(p.max_price_cents)}`
}

/** Every product in a category. The cross-store product page isn't ported
 *  yet, so a tap opens the cheapest store's listing. */
export default function Category() {
  const { category } = useLocalSearchParams<{ category: string }>()
  const { data, error, loading, refresh } = useFetch(category, () => api.portal.getCategory(category))

  const header = <Stack.Screen options={{ title: category.charAt(0).toUpperCase() + category.slice(1) }} />
  if (loading || error) return <>{header}<FeedState loading={loading} error={error} onRetry={refresh} /></>

  async function open(p: PortalCategoryProduct) {
    if (!data) return
    const byPrice = (a: { price_cents: number | null }, b: { price_cents: number | null }) =>
      (a.price_cents ?? Infinity) - (b.price_cents ?? Infinity)

    // Unbranded products carry a listing id on their offerings. Branded ones
    // are addressed by key, so ask for the product's offerings and open the
    // cheapest in stock. A cross-store product page will replace this.
    const cheapest = [...p.offerings].sort(byPrice)[0]
    if (cheapest?.listing_id) {
      router.push(`/listing/${data.dispensaries[cheapest.dispensary_index].id}/${cheapest.listing_id}`)
      return
    }
    try {
      const detail = await api.portal.getProductDetail(p.key, p.brand)
      const best = detail.offerings.filter(o => o.in_stock).sort(byPrice)[0] ?? detail.offerings[0]
      if (best) router.push(`/listing/${best.dispensary_id}/${best.listing_id}`)
    } catch (e: any) {
      Alert.alert('Could not open product', e?.message ?? String(e))
    }
  }

  return (
    <>
      {header}
      <FlatList
        style={styles.screen}
        data={data?.products ?? []}
        keyExtractor={p => p.key}
        contentContainerStyle={{ padding: space[4], gap: space[3] }}
        ListHeaderComponent={
          data ? (
            <Text style={styles.meta}>
              {data.product_count.toLocaleString()} products · {data.brand_count} brands · {data.dispensary_count} stores
            </Text>
          ) : null
        }
        ListEmptyComponent={<FeedState empty="Nothing in this category right now." />}
        renderItem={({ item }) => (
          <Pressable onPress={() => open(item)} style={({ pressed }) => [{ flexDirection: 'row', gap: space[3] }, pressed && { opacity: 0.7 }]}>
            <ProductImage uri={item.image_url} size={72} />
            <View style={{ flex: 1, justifyContent: 'center' }}>
              <Text numberOfLines={2} style={styles.name}>{item.name}</Text>
              {item.brand ? <Text numberOfLines={1} style={styles.meta}>{item.brand}</Text> : null}
              <Text style={[styles.meta, { marginTop: 2 }]}>
                {priceRange(item)} · {item.dispensary_count} store{item.dispensary_count === 1 ? '' : 's'}
              </Text>
            </View>
          </Pressable>
        )}
      />
    </>
  )
}
