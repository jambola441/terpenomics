import { useCallback, useEffect, useState } from 'react'
import {
  ActivityIndicator, FlatList, Pressable, StyleSheet, Text, TextInput, View, useWindowDimensions,
} from 'react-native'
import { router } from 'expo-router'
import type { PortalBrand } from '@web/types'
import { api } from '@/lib/api'
import ShopHeader from '@/components/ShopHeader'
import BrandMark from '@/components/BrandMark'
import { Icon } from '@/components/Icon'
import { FeedState, styles } from '@/components/ui'
import { t, font, fonts, radius, space } from '@/lib/theme'

const PAGE = 48
type Sort = 'listings' | 'name'

/** Shop → Brands, as on the web (components/BrandsPage.tsx): every brand,
 *  searchable, sorted by how widely stocked it is or A–Z, paged as you scroll. */
export default function Brands() {
  const { width } = useWindowDimensions()
  const columns = Math.max(3, Math.floor((width - space[4] * 2 + 12) / (104 + 12)))
  const tile = (width - space[4] * 2 - 12 * (columns - 1)) / columns

  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<Sort>('listings')
  const [brands, setBrands] = useState<PortalBrand[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [exhausted, setExhausted] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [attempt, setAttempt] = useState(0)

  // Debounced: the brand list is a grouped aggregate, so a request per
  // keystroke is a scan per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setQuery(input.trim()), 250)
    return () => clearTimeout(id)
  }, [input])

  useEffect(() => {
    let live = true
    api.portal.getBrands({ q: query || undefined, sort, limit: PAGE })
      .then(rows => {
        if (!live) return
        setBrands(rows)
        setExhausted(rows.length < PAGE)
        setError(null)
      })
      .catch(() => { if (live) setError('Could not load brands.') })
    return () => { live = false }
  }, [query, sort, attempt])

  const loadMore = useCallback(() => {
    if (!brands || exhausted || loadingMore) return
    setLoadingMore(true)
    api.portal.getBrands({ q: query || undefined, sort, limit: PAGE, offset: brands.length })
      .then(rows => {
        setBrands(prev => [...(prev ?? []), ...rows])
        if (rows.length < PAGE) setExhausted(true)
      })
      .catch(() => setExhausted(true))
      .finally(() => setLoadingMore(false))
  }, [brands, exhausted, loadingMore, query, sort])

  const header = (
    <View>
      <ShopHeader active="brands" sub="Every brand stocked across the stores we track" />
      <View style={s.searchRow}>
        <View style={s.search}>
          <Icon name="search" size={16} color={t.text3} />
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Filter brands"
            placeholderTextColor={t.text4}
            autoCorrect={false}
            autoCapitalize="none"
            returnKeyType="search"
            style={s.input}
          />
        </View>
        {input ? (
          <Pressable onPress={() => setInput('')} accessibilityLabel="Clear search" style={s.clear}>
            <Icon name="close" size={16} color={t.text2} />
          </Pressable>
        ) : null}
      </View>
      <View style={s.sorts}>
        <SortChip label="Most stocked" active={sort === 'listings'} onPress={() => setSort('listings')} />
        <SortChip label="A–Z" active={sort === 'name'} onPress={() => setSort('name')} />
      </View>
    </View>
  )

  return (
    <FlatList
      style={styles.screen}
      key={columns}
      data={brands ?? []}
      numColumns={columns}
      keyExtractor={b => b.name}
      ListHeaderComponent={header}
      contentContainerStyle={{ gap: 12, paddingBottom: space[7] }}
      columnWrapperStyle={{ gap: 12, paddingHorizontal: space[4] }}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      onEndReachedThreshold={0.6}
      onEndReached={loadMore}
      ListEmptyComponent={
        error ? (
          <FeedState error={error} onRetry={() => setAttempt(n => n + 1)} style={{ paddingVertical: 48 }} />
        ) : brands === null ? (
          <FeedState loading style={{ paddingVertical: 48 }} />
        ) : (
          <FeedState
            icon="tag"
            empty={query ? `No brands matching "${query}"` : 'No brands yet'}
            hint={query ? 'Try a shorter search.' : null}
            style={{ paddingVertical: 48 }}
          />
        )
      }
      ListFooterComponent={
        brands?.length ? (
          <View style={{ paddingVertical: 18, alignItems: 'center' }}>
            {loadingMore ? (
              <ActivityIndicator color={t.text3} />
            ) : exhausted ? (
              <Text style={s.footer}>{brands.length.toLocaleString()} brands</Text>
            ) : null}
          </View>
        ) : null
      }
      renderItem={({ item }) => (
        <Pressable
          onPress={() => router.push({ pathname: '/shop/brand/[name]', params: { name: item.name } })}
          accessibilityRole="button"
          accessibilityLabel={`${item.name}, ${item.listing_count} listed`}
          style={({ pressed }) => [s.tile, { width: tile }, pressed && { backgroundColor: t.surface2 }]}
        >
          <BrandMark name={item.name} imageUrl={item.logo_url ?? item.image_url} size={64} />
          <Text numberOfLines={1} style={s.name}>{item.name}</Text>
          <Text style={s.count}>{item.listing_count.toLocaleString()} listed</Text>
        </Pressable>
      )}
    />
  )
}

function SortChip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={[s.chip, active ? { backgroundColor: t.accentTint, borderColor: t.accentDim } : { backgroundColor: t.surface2, borderColor: t.border }]}
    >
      <Text style={{ fontFamily: active ? fonts.sansSemibold : fonts.sansMedium, fontSize: font.size.small, color: active ? t.accent : t.text2 }}>
        {label}
      </Text>
    </Pressable>
  )
}

const s = StyleSheet.create({
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: space[4], paddingTop: 12 },
  search: {
    flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, paddingLeft: 12,
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  input: { flex: 1, fontFamily: fonts.sans, fontSize: font.size.body, color: t.text1, paddingVertical: 11, paddingRight: 14 },
  clear: {
    width: 42, height: 42, alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  sorts: { flexDirection: 'row', gap: 8, paddingHorizontal: space[4], paddingTop: 12, paddingBottom: 14 },
  chip: { paddingVertical: 7, paddingHorizontal: 13, borderRadius: radius.pill, borderWidth: 1 },
  tile: {
    alignItems: 'center', gap: 9, paddingTop: 14, paddingHorizontal: 10, paddingBottom: 12,
    backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border, borderRadius: radius.lg,
  },
  name: { fontFamily: fonts.sansSemibold, fontSize: font.size.caption + 1, color: t.text1, textAlign: 'center', alignSelf: 'stretch' },
  count: { fontFamily: fonts.mono, fontSize: font.size.micro + 0.5, color: t.text3, fontVariant: ['tabular-nums'] },
  footer: { fontFamily: fonts.sans, fontSize: font.size.small, color: t.text3 },
})
