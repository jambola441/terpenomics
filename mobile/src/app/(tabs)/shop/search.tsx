import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { Stack, useLocalSearchParams } from 'expo-router'
import type { PortalProduct } from '@web/types'
import { categoryStyle } from '@web/design/tokens'
import {
  SEARCH_MAX_ROWS, SEARCH_PAGE, SORTS_NO_LOCATION, priceBoundsOf, priceRangeLabel, productKey,
  searchCard, searchFacet, searchMatches, searchRowKey, searchSort, sortLabelOf, toggled,
  type SearchFilters, type SortKey,
} from '@web/utils/browseLogic'
import { api } from '@/lib/api'
import { openProduct } from '@/lib/products'
import { CategoryIcon, Icon } from '@/components/Icon'
import { FeedState, categoryName } from '@/components/ui'
import BrowseCard from '@/components/browse/BrowseCard'
import BrowseList, { type ScrollToTop } from '@/components/browse/BrowseList'
import FilterSheet, { type SheetGroup } from '@/components/browse/FilterSheet'
import {
  ActiveChip, BackButton, BrowseToolbar, FacetChip, GridSkeleton, HeroTitle, SearchField, Stats,
} from '@/components/browse/controls'
import { t, font, fonts } from '@/lib/theme'

/** Search across every store, as on the web (components/SearchView.tsx): the
 *  query goes to the server, a page at a time up to a thousand rows, and the
 *  facets, price range and sort work over what came back. */
export default function Search() {
  // A link may bring a query or a category; from Shop's field it brings neither
  // and the shopper meant to type, so the field takes focus.
  const params = useLocalSearchParams<{ q?: string; category?: string }>()
  const [focusOnOpen] = useState(() => !params.q && !params.category)

  const [rows, setRows] = useState<PortalProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [truncated, setTruncated] = useState(false)
  const [attempt, setAttempt] = useState(0)

  const [input, setInput] = useState(params.q ?? '')
  const [query, setQuery] = useState(params.q?.trim() ?? '')

  const [category, setCategory] = useState<Set<string>>(() => new Set(params.category ? [params.category] : []))
  const [subtype, setSubtype] = useState<Set<string>>(() => new Set())
  const [brand, setBrand] = useState<Set<string>>(() => new Set())
  const [variant, setVariant] = useState<Set<string>>(() => new Set())
  const [price, setPrice] = useState<[number, number] | null>(null)
  const [sort, setSort] = useState<SortKey>('featured')
  const [sheet, setSheet] = useState(false)
  const listRef = useRef<ScrollToTop>(null)

  // Debounce typing so we aren't firing a request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setQuery(input.trim()), 250)
    return () => clearTimeout(id)
  }, [input])

  // Page through the matches so the facet counts describe the whole result
  // set; the first page goes on screen as soon as it lands.
  useEffect(() => {
    let cancelled = false
    listRef.current?.scrollToOffset({ offset: 0, animated: false })
    ;(async () => {
      setLoading(true); setLoadingMore(false); setError(null); setTruncated(false)
      const acc: PortalProduct[] = []
      try {
        for (let offset = 0; offset < SEARCH_MAX_ROWS; offset += SEARCH_PAGE) {
          const page = await api.portal.getProducts({ q: query || undefined, limit: SEARCH_PAGE, offset })
          if (cancelled) return
          acc.push(...page)
          const more = page.length === SEARCH_PAGE && acc.length < SEARCH_MAX_ROWS
          setRows([...acc])
          setLoading(false)
          setLoadingMore(more)
          if (!more) break
        }
        if (cancelled) return
        setTruncated(acc.length >= SEARCH_MAX_ROWS)
      } catch (e: any) {
        if (cancelled) return
        // A later page failing still leaves the first ones worth showing.
        if (acc.length) setLoadingMore(false)
        else { setError(e?.message ?? 'Failed to load products'); setLoading(false) }
      }
    })()
    return () => { cancelled = true }
  }, [query, attempt])

  const filters: SearchFilters = useMemo(
    () => ({ category, subtype, brand, variant, price }),
    [category, subtype, brand, variant, price],
  )
  const priceBounds = useMemo(() => priceBoundsOf(rows.map(p => p.min_price_cents)), [rows])
  const categoryFacet = useMemo(() => searchFacet(rows, filters, 'category'), [rows, filters])
  const subtypeFacet = useMemo(() => searchFacet(rows, filters, 'subtype'), [rows, filters])
  const brandFacet = useMemo(() => searchFacet(rows, filters, 'brand'), [rows, filters])
  const variantFacet = useMemo(() => searchFacet(rows, filters, 'variant'), [rows, filters])
  const filtered = useMemo(() => rows.filter(p => searchMatches(p, filters)), [rows, filters])
  const sorted = useMemo(() => searchSort(filtered, sort), [filtered, sort])
  const brandCount = useMemo(() => new Set(rows.map(p => p.brand).filter(Boolean)).size, [rows])

  const activeCount = category.size + subtype.size + brand.size + variant.size + (price ? 1 : 0)
  const sortLabel = sortLabelOf(sort)
  // Colour the facets by the category being browsed, once it's the only one.
  const c = category.size === 1 ? categoryStyle([...category][0]).color : t.accent

  const toggle = (setter: Dispatch<SetStateAction<Set<string>>>, value: string) => setter(prev => toggled(prev, value))

  function clearAll() {
    setCategory(new Set()); setSubtype(new Set()); setBrand(new Set()); setVariant(new Set())
    setPrice(null)
  }

  const groups: SheetGroup[] = [
    { key: 'category', title: 'Category', facet: categoryFacet, sel: category, onToggle: v => toggle(setCategory, v) },
    { key: 'subtype', title: 'Subtype', facet: subtypeFacet, sel: subtype, onToggle: v => toggle(setSubtype, v) },
    { key: 'variant', title: 'Weight / Size', facet: variantFacet, sel: variant, onToggle: v => toggle(setVariant, v), capitalize: false },
    { key: 'brand', title: 'Brand', facet: brandFacet, sel: brand, onToggle: v => toggle(setBrand, v) },
  ]

  const hero = (
    <>
      <BackButton />
      <View style={{ marginTop: 18 }}>
        <HeroTitle size={34}>Search</HeroTitle>
        {!loading && !error && rows.length > 0 ? (
          <Stats
            color={t.accent}
            style={{ marginTop: 9 }}
            stats={[
              { value: rows.length, one: 'product', many: 'products' },
              { value: brandCount, one: 'brand', many: 'brands' },
              { value: categoryFacet.length, one: 'category', many: 'categories' },
            ]}
          />
        ) : null}
      </View>
      <View style={{ marginTop: 16 }}>
        <SearchField
          value={input}
          onChange={setInput}
          placeholder="Search products, brands, strains…"
          autoFocus={focusOnOpen}
        />
      </View>
    </>
  )

  const toolbar = (
    <BrowseToolbar
      activeCount={activeCount}
      sortLabel={sortLabel}
      onOpenSheet={() => setSheet(true)}
      onClear={clearAll}
      quickRail={categoryFacet.length > 1 ? (
        // The quick category rail: the first cut shoppers make when searching.
        <>
          <FacetChip label="All" active={category.size === 0} color={t.accent} onPress={() => setCategory(new Set())} />
          {categoryFacet.map(f => (
            <FacetChip
              key={f.value}
              label={categoryName(f.value)}
              icon={<CategoryIcon category={f.value} size={15} color={category.has(f.value) ? undefined : t.text3} />}
              capitalize={false}
              count={f.count}
              active={category.has(f.value)}
              color={categoryStyle(f.value).color}
              onPress={() => toggle(setCategory, f.value)}
            />
          ))}
        </>
      ) : null}
      activeChips={(
        <>
          {price ? <ActiveChip label={priceRangeLabel(price)} capitalize={false} onRemove={() => setPrice(null)} /> : null}
          {[...category].map(v => <ActiveChip key={'c' + v} label={categoryName(v)} onRemove={() => toggle(setCategory, v)} />)}
          {[...subtype].map(v => <ActiveChip key={'s' + v} label={v} onRemove={() => toggle(setSubtype, v)} />)}
          {[...brand].map(v => <ActiveChip key={'b' + v} label={v} onRemove={() => toggle(setBrand, v)} />)}
          {[...variant].map(v => <ActiveChip key={'v' + v} label={v} capitalize={false} onRemove={() => toggle(setVariant, v)} />)}
        </>
      )}
    />
  )

  const status = !loading && !error && rows.length > 0 ? (
    <View style={s.countRow}>
      <Text style={s.count}>
        {sorted.length} {sorted.length === 1 ? 'product' : 'products'}
        {sorted.length !== rows.length ? <Text style={{ color: t.text4 }}> of {rows.length}</Text> : null}
        {loadingMore ? <Text style={{ color: t.text4 }}> · loading more…</Text> : null}
      </Text>
      {truncated ? <Text style={s.note}>refine to see more</Text> : null}
    </View>
  ) : null

  let body = null
  if (loading) body = <GridSkeleton />
  else if (error) body = <FeedState error={error} onRetry={() => setAttempt(n => n + 1)} style={s.state} />
  else if (rows.length === 0) {
    body = (
      <FeedState
        empty="No products found"
        hint={query ? `Nothing matches “${query}”.` : 'Try a different search.'}
        icon="search"
        style={s.state}
      />
    )
  } else if (sorted.length === 0) {
    body = (
      <FeedState
        empty="No matches"
        hint={query ? `Nothing matches “${query}” with these filters.` : 'Try removing a filter or widening the price range.'}
        icon="search"
        style={s.state}
      />
    )
  }

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <BrowseList<PortalProduct>
        listRef={listRef}
        color={t.accent}
        wash={0.14}
        decoration={
          <View pointerEvents="none" style={{ position: 'absolute', right: -30, top: -26, opacity: 0.12 }}>
            <Icon name="search" size={168} strokeWidth={0.75} color={t.accent} />
          </View>
        }
        hero={hero}
        toolbar={toolbar}
        status={status}
        items={sorted}
        keyOf={searchRowKey}
        renderCard={(p, width) => (
          <BrowseCard
            item={searchCard(p)}
            color={categoryStyle(p.category).color}
            suppressSubtype={p.category}
            width={width}
            // A row's identity is the same five-part key the product endpoint takes.
            onPress={() => openProduct(productKey(p), p.brand ?? null)}
          />
        )}
        body={body}
      />
      <FilterSheet
        open={sheet}
        onClose={() => setSheet(false)}
        resultCount={sorted.length}
        color={c}
        sort={sort}
        onSort={setSort}
        sorts={SORTS_NO_LOCATION}
        priceBounds={priceBounds}
        price={price}
        onPrice={setPrice}
        groups={groups}
        onClear={clearAll}
        activeCount={activeCount}
      />
    </>
  )
}

const s = StyleSheet.create({
  countRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12,
    paddingTop: 14, paddingHorizontal: 16, paddingBottom: 4,
  },
  count: { fontFamily: fonts.sansMedium, fontSize: font.size.small + 1, color: t.text2 },
  note: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3 },
  state: { flex: 0, minHeight: 300, paddingVertical: 48 },
})
