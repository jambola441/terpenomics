import { useMemo } from 'react'
import { View } from 'react-native'
import { Stack, useLocalSearchParams } from 'expo-router'
import { brandFacetKeys, brandItems, hasRealLine } from '@web/utils/browseLogic'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useFetch } from '@/lib/useFetch'
import { openProduct } from '@/lib/products'
import BrandMark from '@/components/BrandMark'
import BrowseScreen from '@/components/browse/BrowseScreen'
import { BackButton, HeroTitle, Stats } from '@/components/browse/controls'
import { t } from '@/lib/theme'

/** One brand across every store, as on the web (components/BrandView.tsx): the
 *  same engine as a category, with category leading the facets in place of
 *  brand, and the brand's product lines where the flags and the data allow. */
export default function Brand() {
  const { name, category, line } = useLocalSearchParams<{ name: string; category?: string; line?: string }>()
  const { data, error, loading, refreshing, refresh } = useFetch(`brand:${name}`, () => api.portal.getBrand(name))
  const items = useMemo(() => (data ? brandItems(data) : []), [data])

  // Feature flags come with /me, as on the web (hooks/useFlag): off until it
  // answers and for any name it did not send.
  const flags = useAuth().profile?.flags
  const showLines = flags?.lines === true && data != null && hasRealLine(data)
  // Shelves by line ride on the line filter: their See all links select a line.
  const groupable = flags?.lines_grouped === true && showLines
  const facets = useMemo(() => brandFacetKeys(showLines), [showLines])

  const c = t.accent

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <BrowseScreen
        key={`${name}|${category ?? ''}|${line ?? ''}|${showLines}`}
        items={items}
        loading={loading && !data}
        error={data ? null : error}
        onRetry={refresh}
        refreshing={refreshing}
        onRefresh={refresh}
        color={c}
        wash={0.16}
        facets={facets}
        groupable={groupable}
        initialFacets={{ category, line }}
        searchPlaceholder={`Search ${name}…`}
        totalCount={data?.product_count ?? 0}
        emptyMessage={`Nothing from ${name} in stock`}
        emptyHint="Check back soon — menus update regularly."
        emptyIcon="tag"
        onOpen={item => openProduct(item.key, data?.name ?? name)}
        hero={
          <>
            <BackButton />
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 18 }}>
              <BrandMark name={name} imageUrl={data?.logo_url ?? data?.image_url} size={60} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <HeroTitle>{name}</HeroTitle>
                {data ? (
                  <Stats
                    color={c}
                    style={{ marginTop: 7 }}
                    stats={[
                      { value: data.product_count, one: 'product', many: 'products' },
                      { value: data.dispensary_count, one: 'dispensary', many: 'dispensaries' },
                    ]}
                  />
                ) : null}
              </View>
            </View>
          </>
        }
      />
    </>
  )
}
