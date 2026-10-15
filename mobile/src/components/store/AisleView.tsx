import { useEffect, useMemo, useRef, useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { router } from 'expo-router'
import type { DispensaryListing, PortalDispensary } from '@web/types'
import { categoryStyle } from '@web/design/tokens'
import {
  SORTS_NO_LOCATION, priceRangeLabel, variantWeight, type BrowseCardItem, type Facet, type SortKey,
} from '@web/utils/browseLogic'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { openListing } from '@/lib/products'
import { FeedState, MarketNote, categoryName } from '@/components/ui'
import { CategoryIcon } from '@/components/Icon'
import BrowseCard from '@/components/browse/BrowseCard'
import BrowseList, { type ScrollToTop } from '@/components/browse/BrowseList'
import FilterSheet, { type SheetGroup } from '@/components/browse/FilterSheet'
import {
  ActiveChip, BackButton, BrowseToolbar, FacetChip, GridSkeleton, HeroTitle, SearchField, Stats,
} from '@/components/browse/controls'
import CartCorner from './CartCorner'
import { inShelfOrder } from './StoreMenu'
import { t, font, fonts } from '@/lib/theme'

type FacetKey = 'brand' | 'subtype' | 'variant'
type Filters = {
  search: string
  brand: Set<string>
  subtype: Set<string>
  variant: Set<string>
  price: [number, number] | null
}

const FACET_FIELD: Record<FacetKey, 'scraped_brand' | 'subtype' | 'variant'> = {
  brand: 'scraped_brand',
  subtype: 'subtype',
  variant: 'variant',
}

/** Does a listing survive the filters? `except` skips one, for its own counts. */
function matches(l: DispensaryListing, f: Filters, except?: FacetKey | 'price'): boolean {
  if (f.search) {
    const hay = [l.display_name, l.scraped_name, l.scraped_brand, l.strain, l.subtype].filter(Boolean).join(' ').toLowerCase()
    if (!hay.includes(f.search)) return false
  }
  if (except !== 'brand' && f.brand.size && !(l.scraped_brand && f.brand.has(l.scraped_brand))) return false
  if (except !== 'subtype' && f.subtype.size && !(l.subtype && f.subtype.has(l.subtype))) return false
  if (except !== 'variant' && f.variant.size && !(l.variant && f.variant.has(l.variant))) return false
  if (except !== 'price' && f.price) {
    const p = l.price_cents
    if (p == null || p < f.price[0] || p > f.price[1]) return false
  }
  return true
}

function toCard(l: DispensaryListing): BrowseCardItem {
  return {
    name: l.display_name,
    brand: l.scraped_brand,
    category: l.scraped_category,
    subtype: l.subtype,
    variant: l.variant,
    imageUrl: l.image_url,
    priceCents: l.price_cents,
    multiPriced: false,
    dispensaryCount: 1,
    distanceMi: null,
    storeName: null,
  }
}

function toggled(set: Set<string>, v: string): Set<string> {
  const next = new Set(set)
  if (next.has(v)) next.delete(v)
  else next.add(v)
  return next
}

/**
 * One aisle of one store: the web's AisleView. The whole aisle is loaded once
 * (in pages of 100) and filtered on the phone. The quick rail switches aisle
 * in place, offering only the aisles the store has stock in.
 */
export default function AisleView({ store, category }: { store: PortalDispensary; category: string }) {
  const [carried, setCarried] = useState<string[] | null>(null)
  useEffect(() => {
    let live = true
    api.portal.getDispensaryFilterOptions(store.id)
      .then(o => { if (live && o.categories) setCarried(inShelfOrder(o.categories.map(c => c.name))) })
      .catch(() => {})
    return () => { live = false }
  }, [store.id])

  // The whole aisle once, in pages of 100 (the API's cap), then filtered here.
  const aisle = useFetch(`aisle:${store.id}:${category}`, async () => {
    const PAGE = 100
    const MAX = 1000
    const acc: DispensaryListing[] = []
    for (let offset = 0; offset < MAX; offset += PAGE) {
      const page = await api.portal.getDispensaryListings(store.id, { category, limit: PAGE, offset })
      acc.push(...page)
      if (page.length < PAGE) break
    }
    return acc
  })
  const all = useMemo(() => aisle.data ?? [], [aisle.data])
  const loading = aisle.loading
  const error = aisle.error ? 'Failed to load' : null

  const [search, setSearch] = useState('')
  const [brand, setBrand] = useState<Set<string>>(new Set())
  const [subtype, setSubtype] = useState<Set<string>>(new Set())
  const [variant, setVariant] = useState<Set<string>>(new Set())
  const [price, setPrice] = useState<[number, number] | null>(null)
  const [sort, setSort] = useState<SortKey>('featured')
  const [sheet, setSheet] = useState(false)
  const listRef = useRef<ScrollToTop>(null)

  const filters: Filters = useMemo(
    () => ({ search: search.trim().toLowerCase(), brand, subtype, variant, price }),
    [search, brand, subtype, variant, price],
  )

  const priceBounds = useMemo<[number, number] | null>(() => {
    const prices = all.map(l => l.price_cents).filter((p): p is number => p != null)
    if (prices.length < 2) return null
    const lo = Math.min(...prices)
    const hi = Math.max(...prices)
    return hi > lo ? [lo, hi] : null
  }, [all])

  const facets = useMemo(() => {
    const facetFor = (key: FacetKey): Facet[] => {
      const counts = new Map<string, number>()
      for (const l of all) {
        if (!matches(l, filters, key)) continue
        const v = l[FACET_FIELD[key]]
        if (v) counts.set(v, (counts.get(v) ?? 0) + 1)
      }
      return [...counts.entries()].map(([value, count]) => ({ value, count }))
    }
    return {
      brand: facetFor('brand').sort((a, b) => b.count - a.count),
      subtype: facetFor('subtype').sort((a, b) => b.count - a.count),
      variant: facetFor('variant').sort((a, b) => variantWeight(a.value) - variantWeight(b.value)),
    }
  }, [all, filters])

  const sorted = useMemo(() => {
    const arr = all.filter(l => matches(l, filters))
    if (sort === 'price-asc' || sort === 'price-desc') {
      const dir = sort === 'price-asc' ? 1 : -1
      arr.sort((a, b) => {
        if (a.price_cents == null) return 1
        if (b.price_cents == null) return -1
        return (a.price_cents - b.price_cents) * dir
      })
    } else if (sort === 'name') {
      arr.sort((a, b) => a.display_name.localeCompare(b.display_name))
    } else {
      // Featured: cards that look like something first — a photo, then a price.
      arr.sort((a, b) => {
        const img = Number(!!b.image_url) - Number(!!a.image_url)
        if (img) return img
        return Number(b.price_cents != null) - Number(a.price_cents != null)
      })
    }
    return arr
  }, [all, filters, sort])

  const brandCount = useMemo(() => new Set(all.map(l => l.scraped_brand).filter(Boolean)).size, [all])
  const activeCount = brand.size + subtype.size + variant.size + (price ? 1 : 0)
  const sortLabel = SORTS_NO_LOCATION.find(o => o.key === sort)?.label ?? 'Featured'
  const c = categoryStyle(category).color
  const label = categoryName(category)

  function clearAll() {
    setBrand(new Set()); setSubtype(new Set()); setVariant(new Set()); setPrice(null)
  }

  const groups: SheetGroup[] = [
    { key: 'subtype', title: 'Subcategory', facet: facets.subtype, sel: subtype, onToggle: v => setSubtype(p => toggled(p, v)) },
    { key: 'variant', title: 'Weight / Size', facet: facets.variant, sel: variant, onToggle: v => setVariant(p => toggled(p, v)), capitalize: false },
    { key: 'brand', title: 'Brand', facet: facets.brand, sel: brand, onToggle: v => setBrand(p => toggled(p, v)) },
  ]

  const toolbar = (
    <BrowseToolbar
      activeCount={activeCount}
      sortLabel={sortLabel}
      onOpenSheet={() => setSheet(true)}
      onClear={clearAll}
      quickRail={(carried ?? [category]).map(cat => (
        <FacetChip
          key={cat}
          label={categoryName(cat)}
          icon={<CategoryIcon category={cat} size={15} color={category === cat ? undefined : t.text3} />}
          capitalize={false}
          active={category === cat}
          color={categoryStyle(cat).color}
          // In place: switching aisles is a filter, not a step Back retraces.
          onPress={() => router.setParams({ aisle: cat })}
        />
      ))}
      activeChips={(
        <>
          {price ? <ActiveChip label={priceRangeLabel(price)} capitalize={false} onRemove={() => setPrice(null)} /> : null}
          {[...subtype].map(v => <ActiveChip key={'s' + v} label={v} onRemove={() => setSubtype(p => toggled(p, v))} />)}
          {[...brand].map(v => <ActiveChip key={'b' + v} label={v} onRemove={() => setBrand(p => toggled(p, v))} />)}
          {[...variant].map(v => <ActiveChip key={'v' + v} label={v} capitalize={false} onRemove={() => setVariant(p => toggled(p, v))} />)}
        </>
      )}
    />
  )

  let body = null
  if (loading) body = <GridSkeleton />
  else if (error) body = <FeedState error={error} onRetry={aisle.refresh} style={{ flex: 0, minHeight: 300 }} />
  else if (all.length === 0) {
    body = (
      <FeedState
        empty={`No ${label.toLowerCase()} in stock`}
        hint="Check back soon — menus update regularly."
        icon="package"
        style={{ flex: 0, minHeight: 300 }}
      />
    )
  } else if (sorted.length === 0) {
    body = (
      <FeedState
        empty="No matches"
        hint={search ? `Nothing matches “${search}” with these filters.` : 'Try removing a filter or widening the price range.'}
        icon="search"
        style={{ flex: 0, minHeight: 240 }}
      />
    )
  }

  return (
    <>
      <BrowseList<DispensaryListing>
        listRef={listRef}
        color={c}
        decoration={
          <View pointerEvents="none" style={{ position: 'absolute', right: -26, top: -18, opacity: 0.2 }}>
            <CategoryIcon category={category} size={168} strokeWidth={0.75} />
          </View>
        }
        hero={
          <>
            <BackButton />
            <View style={{ marginTop: 18 }}>
              <HeroTitle size={34}>{label}</HeroTitle>
              <Text numberOfLines={1} style={cs.store}>{store.name}</Text>
              {!loading && !error && all.length > 0 ? (
                <Stats
                  color={c}
                  style={{ marginTop: 9 }}
                  stats={[
                    { value: all.length, one: 'product', many: 'products' },
                    { value: brandCount, one: 'brand', many: 'brands' },
                  ]}
                />
              ) : null}
            </View>
            <View style={{ marginTop: 16 }}>
              <SearchField value={search} onChange={setSearch} placeholder={`Search ${label.toLowerCase()}…`} />
            </View>
          </>
        }
        toolbar={toolbar}
        status={!loading && !error && all.length > 0 ? <Count shown={sorted.length} total={all.length} /> : null}
        items={sorted}
        keyOf={l => l.id}
        renderCard={(l, width) => (
          <BrowseCard
            item={toCard(l)}
            color={c}
            suppressSubtype={category}
            width={width}
            onPress={() => openListing(store.id, l.id)}
            footer={<MarketNote market={l.market} priceCents={l.price_cents} />}
            action={store.accepts_pickup ? <CartCorner listing={l} store={store} /> : undefined}
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

function Count({ shown, total }: { shown: number; total: number }) {
  return (
    <View style={cs.row}>
      <Text style={cs.count}>
        {shown} {shown === 1 ? 'product' : 'products'}
        {shown !== total ? <Text style={{ color: t.text3 }}> of {total}</Text> : null}
      </Text>
    </View>
  )
}

const cs = StyleSheet.create({
  store: { fontFamily: fonts.sans, fontSize: font.size.small + 1, color: t.text2, marginTop: 4 },
  row: { paddingTop: 14, paddingHorizontal: 16, paddingBottom: 4 },
  count: {
    fontFamily: fonts.mono, fontSize: font.size.caption, color: t.text2,
    textTransform: 'uppercase', letterSpacing: 0.66, fontVariant: ['tabular-nums'],
  },
})
