import { useMemo } from 'react'
import { View } from 'react-native'
import { Stack, useLocalSearchParams } from 'expo-router'
import { categoryStyle } from '@web/design/tokens'
import { icons } from '@web/design/icons'
import { CATEGORY_FACETS, categoryItems } from '@web/utils/browseLogic'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { openProduct } from '@/lib/products'
import { CategoryIcon, type IconName } from '@/components/Icon'
import { categoryName } from '@/components/ui'
import BrowseScreen from '@/components/browse/BrowseScreen'
import { BackButton, HeroTitle, Stats } from '@/components/browse/controls'

/** One category across every store, as on the web (components/CategoryView.tsx):
 *  the browse engine over the category's products, with search-within, the
 *  subtype / brand / size facets and distance from the shopper. */
export default function Category() {
  const { category } = useLocalSearchParams<{ category: string }>()
  const { data, error, loading, refreshing, refresh } = useFetch(`category:${category}`, () => api.portal.getCategory(category))
  const items = useMemo(() => (data ? categoryItems(data) : []), [data])

  const c = categoryStyle(category).color
  const label = categoryName(category)
  const glyph = categoryStyle(category).icon

  return (
    <>
      {/* The hero carries the title and the way back, as on the web. */}
      <Stack.Screen options={{ headerShown: false }} />
      <BrowseScreen
        key={category}
        items={items}
        loading={loading && !data}
        error={data ? null : error}
        onRetry={refresh}
        refreshing={refreshing}
        onRefresh={refresh}
        color={c}
        facets={CATEGORY_FACETS}
        searchPlaceholder={`Search ${label.toLowerCase()}…`}
        totalCount={data?.product_count ?? 0}
        truncated={data?.truncated}
        suppressSubtype={category}
        emptyMessage={`No ${label.toLowerCase()} in stock`}
        emptyHint="Check back soon — menus update regularly."
        emptyIcon={glyph in icons ? (glyph as IconName) : 'package'}
        onOpen={item => openProduct(item.key, item.brand ?? null)}
        decoration={
          // The category glyph as a specimen drawing, bled off the right edge.
          <View pointerEvents="none" style={{ position: 'absolute', right: -26, top: -18, opacity: 0.2 }}>
            <CategoryIcon category={category} size={168} strokeWidth={0.75} />
          </View>
        }
        hero={
          <>
            <BackButton />
            <View style={{ marginTop: 18 }}>
              <HeroTitle size={34}>{label}</HeroTitle>
              {data ? (
                <Stats
                  color={c}
                  style={{ marginTop: 9 }}
                  stats={[
                    { value: data.product_count, one: 'product', many: 'products' },
                    { value: data.brand_count, one: 'brand', many: 'brands' },
                    { value: data.dispensary_count, one: 'dispensary', many: 'dispensaries' },
                  ]}
                />
              ) : null}
            </View>
          </>
        }
      />
    </>
  )
}
