import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View, useWindowDimensions } from 'react-native'
import { router } from 'expo-router'
import { alpha, categoryStyle } from '@web/design/tokens'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import ShopHeader from '@/components/ShopHeader'
import { CategoryIcon } from '@/components/Icon'
import { FeedState, categoryName, styles } from '@/components/ui'
import { t, font, fonts, radius, space } from '@/lib/theme'

/** Shop → Categories, as on the web (components/CategoriesPage.tsx): a short,
 *  stable list, so a plain grid of tinted tiles with the category's glyph. */
export default function Categories() {
  const { data, error, loading, refreshing, refresh } = useFetch('categories', () => api.portal.getCategories())
  const { width } = useWindowDimensions()
  const tile = (width - space[4] * 2 - 12) / 2
  const total = data?.reduce((n, c) => n + c.listing_count, 0) ?? 0

  return (
    <FlatList
      style={styles.screen}
      data={data ?? []}
      numColumns={2}
      keyExtractor={c => c.name}
      ListHeaderComponent={
        <ShopHeader
          active="categories"
          sub={data ? `${total.toLocaleString()} listings across ${data.length} categories` : 'Shop by what you’re after'}
        />
      }
      contentContainerStyle={{ gap: 12, paddingBottom: space[7] }}
      columnWrapperStyle={{ gap: 12, paddingHorizontal: space[4] }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={t.text3} />}
      ListEmptyComponent={
        <FeedState
          loading={loading}
          error={error}
          onRetry={refresh}
          icon="package"
          empty={loading || error ? null : 'No categories yet'}
          style={{ paddingVertical: 48 }}
        />
      }
      renderItem={({ item, index }) => {
        const hue = categoryStyle(item.name).color
        return (
          <Pressable
            onPress={() => router.push({ pathname: '/shop/[category]', params: { category: item.name } })}
            accessibilityRole="button"
            accessibilityLabel={`${categoryName(item.name)}, ${item.listing_count} listings`}
            style={({ pressed }) => [
              s.tile,
              { width: tile, marginTop: index < 2 ? 16 : 0, backgroundColor: alpha(hue, 0.09), borderColor: alpha(hue, 0.22) },
              pressed && { opacity: 0.8 },
            ]}
          >
            {/* The glyph twice: small as the label's icon, large and faint
                as a specimen drawing bled off the corner. */}
            <CategoryIcon category={item.name} size={92} strokeWidth={1} style={s.bleed} />
            <View style={[s.chip, { backgroundColor: alpha(hue, 0.14), borderColor: alpha(hue, 0.3) }]}>
              <CategoryIcon category={item.name} size={20} />
            </View>
            <View style={{ marginTop: 18 }}>
              <Text style={s.name}>{categoryName(item.name)}</Text>
              <Text style={s.count}>{item.listing_count.toLocaleString()} listings</Text>
            </View>
          </Pressable>
        )
      }}
    />
  )
}

const s = StyleSheet.create({
  tile: {
    minHeight: 132, justifyContent: 'space-between', overflow: 'hidden',
    paddingTop: 16, paddingHorizontal: 14, paddingBottom: 14,
    borderRadius: radius.xl, borderWidth: 1,
  },
  bleed: { position: 'absolute', right: -14, bottom: -12, opacity: 0.16 },
  chip: { width: 36, height: 36, borderRadius: radius.md, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  name: { fontFamily: fonts.display, fontSize: font.size.title + 1, letterSpacing: -0.18, color: t.text1, marginBottom: 2 },
  count: { fontFamily: fonts.mono, fontSize: font.size.caption, color: t.text3, fontVariant: ['tabular-nums'] },
})
