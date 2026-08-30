/* ============================================================================
   BrowseScreen — the machinery every "browse a set of products" page shares.

   A category page and a brand page ask the same question of different slices of
   the catalogue, so they should offer the same tools: search, facets with live
   counts, a distance radius, a price range, and a sort. They did not — the
   category page had all of it and the brand page had a row of category chips —
   because each screen carried its own copy of the filter engine and only one
   copy ever got the work.

   Now the engine lives here and the pages supply three things: their items,
   their hero, and which facets apply to them. A brand page has no use for a
   brand facet; a category page has no use for a category facet. Everything else
   is identical, which is the point.

   `browse.tsx` holds the individual controls this assembles; this file holds
   the behaviour that connects them.
   ========================================================================== */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { t, font } from '../theme'
import {
  readEnum, readNumber, readRange, readSet, useFilterParams, useScrollMemory,
  writeOne, writeRange, writeSet,
} from '../utils/browseState'
import { FeedState } from './ui'
import {
  ActiveChip, BrowseCard, BrowseGrid, BrowseToolbar, FacetChip, FilterSheet, GridSkeleton,
  SORTS, SORTS_NO_LOCATION, SORT_KEYS, SearchField, formatDollarsShort,
  haversineMi, variantWeight,
  type SheetGroup, type SortKey,
} from './browse'

/* ── What a page hands over ───────────────────────────────────────────────── */

/** One store's copy of a product, flattened from whatever shape the endpoint
 *  used. The category endpoint indexes into a store table and the brand
 *  endpoint inlines the store; neither difference matters up here. */
export type BrowseOffering = {
  storeName: string
  lat: number | null
  lng: number | null
  priceCents: number | null
}

export type BrowseItem = {
  /** The product key, as the product page is addressed by. */
  key: string
  name: string
  brand: string | null
  category: string | null
  subtype: string | null
  strain: string | null
  variant: string | null
  imageUrl: string | null
  minPriceCents: number | null
  maxPriceCents: number | null
  dispensaryCount: number
  offerings: BrowseOffering[]
}

export type FacetKey = 'category' | 'subtype' | 'brand' | 'variant'

const FACET_TITLES: Record<FacetKey, string> = {
  category: 'Category',
  subtype: 'Subtype',
  brand: 'Brand',
  variant: 'Weight / Size',
}

/** Sizes read naturally in size order; everything else reads best by how much
 *  of the set it covers. */
const FACET_SORTS: Record<FacetKey, (a: Facet, b: Facet) => number> = {
  category: (a, b) => b.count - a.count,
  subtype: (a, b) => b.count - a.count,
  brand: (a, b) => b.count - a.count,
  variant: (a, b) => variantWeight(a.value) - variantWeight(b.value),
}

type Facet = { value: string; count: number }

/** An item plus the facts derived from where the shopper is standing. */
type Enriched = {
  item: BrowseItem
  closestDist: number | null
  closestStore: string | null
  cheapestStore: string | null
  /** Lowercased haystack for the search box. */
  haystack: string
}

type Filters = {
  search: string
  facets: Record<FacetKey, Set<string>>
  radiusMi: number | null
  price: [number, number] | null
}

function matches(e: Enriched, f: Filters, except?: FacetKey | 'price' | 'radius'): boolean {
  if (f.search && !e.haystack.includes(f.search)) return false

  for (const key of Object.keys(f.facets) as FacetKey[]) {
    if (except === key) continue
    const selected = f.facets[key]
    if (!selected.size) continue
    const value = e.item[key]
    if (!value || !selected.has(value)) return false
  }

  if (except !== 'radius' && f.radiusMi != null) {
    // Only meaningful with a fix on the shopper's position; closestDist is null
    // without one.
    if (e.closestDist == null || e.closestDist > f.radiusMi) return false
  }
  if (except !== 'price' && f.price) {
    const p = e.item.minPriceCents
    // Unpriced products can't satisfy a narrowed range — drop them rather
    // than guess.
    if (p == null || p < f.price[0] || p > f.price[1]) return false
  }
  return true
}

interface Props {
  items: BrowseItem[]
  loading: boolean
  error: string | null

  /** Accent for chips, stats and cards. */
  color: string
  /** Which facets this slice of the catalogue can be narrowed by. The first
   *  doubles as the quick rail above the results. */
  facets: readonly FacetKey[]

  /** Rendered above the search field, inside the hero block. */
  hero: ReactNode
  heroBackground: string
  /** Sits behind the hero — the oversized glyph or logo. */
  heroDecoration?: ReactNode

  searchPlaceholder: string
  /** Changing this clears the controls: a different brand or category has
   *  different facets, so carrying a selection over would filter to nothing. */
  resetKey: string

  /** How many the page holds before filtering, for "12 of 340". */
  totalCount: number
  truncated?: boolean
  /** A subtype equal to this is the page's own subject and reads as noise on
   *  the card — "flower" on every card of the flower category. */
  suppressSubtype?: string

  emptyMessage: string
  emptyHint?: string
  emptyIcon?: string

  onOpen: (item: BrowseItem) => void
}

export default function BrowseScreen({
  items, loading, error, color, facets, hero, heroBackground, heroDecoration,
  searchPlaceholder, resetKey, totalCount, truncated, suppressSubtype,
  emptyMessage, emptyHint, emptyIcon, onOpen,
}: Props) {
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [locationDenied, setLocationDenied] = useState(false)

  // Seeded from the URL so that coming back from a product restores the screen
  // the shopper left, rather than an empty one.
  const [initialParams] = useSearchParams()
  const [search, setSearch] = useState(() => initialParams.get('q') ?? '')
  const [searchFocus, setSearchFocus] = useState(false)
  const [selected, setSelected] = useState<Record<FacetKey, Set<string>>>(() => ({
    category: readSet(initialParams, 'category'),
    subtype: readSet(initialParams, 'subtype'),
    brand: readSet(initialParams, 'brand'),
    variant: readSet(initialParams, 'variant'),
  }))
  const [radiusMi, setRadiusMi] = useState<number | null>(() => readNumber(initialParams, 'radius'))
  const [price, setPrice] = useState<[number, number] | null>(() => readRange(initialParams, 'price'))
  const [sort, setSort] = useState<SortKey>(() => readEnum(initialParams, 'sort', SORT_KEYS, 'featured'))
  const [sheet, setSheet] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)

  useFilterParams({
    q: writeOne(search),
    // Only the facets this screen offers: a stale key from another screen would
    // otherwise sit in the URL filtering nothing.
    category: facets.includes('category') ? writeSet(selected.category) : [],
    subtype: facets.includes('subtype') ? writeSet(selected.subtype) : [],
    brand: facets.includes('brand') ? writeSet(selected.brand) : [],
    variant: facets.includes('variant') ? writeSet(selected.variant) : [],
    radius: writeOne(radiusMi),
    price: writeRange(price),
    sort: sort === 'featured' ? [] : [sort],
  })
  useScrollMemory(scrollRef, !loading && items.length > 0)

  // Skipped on mount, where the controls came from the URL.
  const previousKey = useRef(resetKey)
  useEffect(() => {
    if (previousKey.current === resetKey) return
    previousKey.current = resetKey
    setSearch('')
    setSelected({ category: new Set(), subtype: new Set(), brand: new Set(), variant: new Set() })
    setRadiusMi(null); setPrice(null); setSort('featured')
    scrollRef.current?.scrollTo({ top: 0 })
  }, [resetKey])

  useEffect(() => {
    if (!navigator.geolocation) { setLocationDenied(true); return }
    navigator.geolocation.getCurrentPosition(
      pos => setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setLocationDenied(true),
    )
  }, [])

  const hasLocation = userPos != null

  // Resolve each item's closest and cheapest store once per position change.
  const enriched = useMemo<Enriched[]>(() => items.map(item => {
    let closestDist = Infinity
    let closestStore: string | null = null
    let cheapestStore: string | null = null
    let cheapestPrice = Infinity

    for (const offering of item.offerings) {
      if (offering.priceCents != null && offering.priceCents < cheapestPrice) {
        cheapestPrice = offering.priceCents
        cheapestStore = offering.storeName
      }
      if (userPos && offering.lat != null && offering.lng != null) {
        const d = haversineMi(userPos.lat, userPos.lng, offering.lat, offering.lng)
        if (d < closestDist) { closestDist = d; closestStore = offering.storeName }
      }
    }

    return {
      item,
      closestDist: closestStore ? closestDist : null,
      closestStore,
      cheapestStore,
      haystack: [item.name, item.brand, item.category, item.subtype, item.strain, item.variant]
        .filter(Boolean).join(' ').toLowerCase(),
    }
  }), [items, userPos])

  // Full price span across the page — the bounds of the range slider.
  const priceBounds = useMemo<[number, number] | null>(() => {
    const prices = enriched
      .map(e => e.item.minPriceCents)
      .filter((p): p is number => p != null)
    if (prices.length < 2) return null
    const lo = Math.min(...prices)
    const hi = Math.max(...prices)
    return hi > lo ? [lo, hi] : null
  }, [enriched])

  const filters: Filters = {
    search: search.trim().toLowerCase(),
    facets: selected,
    radiusMi,
    price,
  }

  // Every derived list depends on the same inputs; one signature keeps the
  // memos honest without listing six dependencies four times.
  const filterSignature = JSON.stringify([
    filters.search,
    (Object.keys(selected) as FacetKey[]).map(k => [...selected[k]]),
    radiusMi,
    price,
  ])

  /** Facet options with counts that respect every *other* active filter. */
  const facetOptions = useMemo(() => {
    const out = {} as Record<FacetKey, Facet[]>
    for (const key of facets) {
      const counts = new Map<string, number>()
      for (const e of enriched) {
        if (!matches(e, filters, key)) continue
        const value = e.item[key]
        if (!value) continue
        counts.set(value, (counts.get(value) ?? 0) + 1)
      }
      out[key] = [...counts.entries()]
        .map(([value, count]) => ({ value, count }))
        .sort(FACET_SORTS[key])
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enriched, facets, filterSignature])

  const filtered = useMemo(
    () => enriched.filter(e => matches(e, filters)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enriched, filterSignature],
  )

  const sorted = useMemo(() => {
    const arr = [...filtered]
    if (sort === 'price-asc' || sort === 'price-desc') {
      const dir = sort === 'price-asc' ? 1 : -1
      arr.sort((a, b) => {
        const pa = a.item.minPriceCents
        const pb = b.item.minPriceCents
        if (pa == null) return 1
        if (pb == null) return -1
        return (pa - pb) * dir
      })
    } else if (sort === 'nearest') {
      arr.sort((a, b) => (a.closestDist ?? Infinity) - (b.closestDist ?? Infinity))
    } else if (sort === 'name') {
      arr.sort((a, b) => a.item.name.localeCompare(b.item.name))
    } else {
      // Featured: things that make a good card first — a photo, then breadth of
      // availability, then the server's ordering as the tiebreak.
      arr.sort((a, b) => {
        const img = Number(!!b.item.imageUrl) - Number(!!a.item.imageUrl)
        if (img) return img
        return b.item.dispensaryCount - a.item.dispensaryCount
      })
    }
    return arr
  }, [filtered, sort])

  // Drop a nearest sort / radius filter that location permission can't support.
  useEffect(() => {
    if (hasLocation) return
    if (sort === 'nearest') setSort('featured')
    if (radiusMi != null) setRadiusMi(null)
  }, [hasLocation, sort, radiusMi])

  function toggle(key: FacetKey, value: string) {
    setSelected(prev => {
      const next = new Set(prev[key])
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return { ...prev, [key]: next }
    })
  }

  function clearAll() {
    setSelected({ category: new Set(), subtype: new Set(), brand: new Set(), variant: new Set() })
    setRadiusMi(null)
    setPrice(null)
  }

  const activeCount =
    facets.reduce((n, key) => n + selected[key].size, 0)
    + (radiusMi != null ? 1 : 0)
    + (price ? 1 : 0)

  const sorts = hasLocation ? SORTS : SORTS_NO_LOCATION
  const sortLabel = (SORTS.find(s => s.key === sort) ?? SORTS[0]).label

  const [quickKey] = facets
  const quickFacet = facetOptions[quickKey] ?? []

  const groups: SheetGroup[] = facets.map(key => ({
    key,
    title: FACET_TITLES[key],
    facet: facetOptions[key] ?? [],
    sel: selected[key],
    onToggle: (value: string) => toggle(key, value),
    capitalize: key !== 'variant',
  }))

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{
        position: 'relative',
        background: heroBackground,
        padding: 'calc(env(safe-area-inset-top, 0px) + 16px) 16px 18px',
        overflow: 'hidden',
      }}>
        {heroDecoration}
        {hero}
        <div style={{ position: 'relative', marginTop: 16 }}>
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder={searchPlaceholder}
            focused={searchFocus}
            onFocus={() => setSearchFocus(true)}
            onBlur={() => setSearchFocus(false)}
          />
        </div>
      </div>

      {/* ── Sticky controls ──────────────────────────────────────────────── */}
      <BrowseToolbar
        activeCount={activeCount}
        sortLabel={sortLabel}
        onOpenSheet={() => setSheet(true)}
        onClear={clearAll}
        quickRail={quickFacet.length > 1 && (
          <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '10px 14px 10px' }}>
            <FacetChip
              label="All"
              active={selected[quickKey].size === 0}
              color={color}
              onClick={() => setSelected(prev => ({ ...prev, [quickKey]: new Set() }))}
            />
            {quickFacet.map(f => (
              <FacetChip
                key={f.value}
                label={f.value}
                count={f.count}
                active={selected[quickKey].has(f.value)}
                color={color}
                capitalize={quickKey !== 'variant'}
                onClick={() => toggle(quickKey, f.value)}
              />
            ))}
          </div>
        )}
        activeChips={<>
          {radiusMi != null && (
            <ActiveChip label={`Within ${radiusMi} mi`} capitalize={false} onRemove={() => setRadiusMi(null)} />
          )}
          {price && (
            <ActiveChip
              label={`${formatDollarsShort(price[0])}–${formatDollarsShort(price[1])}`}
              capitalize={false}
              onRemove={() => setPrice(null)}
            />
          )}
          {facets.flatMap(key => [...selected[key]].map(value => (
            <ActiveChip
              key={key + value}
              label={value}
              capitalize={key !== 'variant'}
              onRemove={() => toggle(key, value)}
            />
          )))}
        </>}
      />

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      {loading ? (
        <GridSkeleton />
      ) : error ? (
        <FeedState kind="error" message={error} />
      ) : items.length === 0 ? (
        <FeedState kind="empty" message={emptyMessage} hint={emptyHint} icon={emptyIcon} />
      ) : (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, padding: '14px 16px 4px',
          }}>
            <span style={{ color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium }}>
              {sorted.length} {sorted.length === 1 ? 'product' : 'products'}
              {sorted.length !== totalCount && <span style={{ color: t.text4 }}> of {totalCount}</span>}
            </span>
            {truncated && (
              <span style={{ color: t.text4, fontSize: font.size.caption }}>showing top matches</span>
            )}
          </div>

          {!hasLocation && (
            <div style={{ color: t.text3, fontSize: font.size.caption, padding: '2px 18px 0' }}>
              📍 {locationDenied
                ? 'Turn on location to filter and sort by distance'
                : 'Finding your location to show distances…'}
            </div>
          )}

          {sorted.length === 0 ? (
            <FeedState
              kind="empty"
              message="No matches"
              hint={search
                ? `Nothing matches “${search}” with these filters.`
                : 'Try widening the distance or price range.'}
              icon="🔍"
              style={{ minHeight: 260 }}
            />
          ) : (
            <BrowseGrid items={sorted}>
              {e => (
                <BrowseCard
                  key={e.item.key}
                  item={{
                    name: e.item.name,
                    brand: e.item.brand,
                    category: e.item.category,
                    subtype: e.item.subtype,
                    variant: e.item.variant,
                    imageUrl: e.item.imageUrl,
                    priceCents: e.item.minPriceCents,
                    multiPriced: e.item.minPriceCents != null
                      && e.item.maxPriceCents != null
                      && e.item.maxPriceCents > e.item.minPriceCents,
                    dispensaryCount: e.item.dispensaryCount,
                    distanceMi: e.closestDist,
                    storeName: e.closestStore ?? e.cheapestStore,
                  }}
                  color={color}
                  suppressSubtype={suppressSubtype}
                  onOpen={() => onOpen(e.item)}
                />
              )}
            </BrowseGrid>
          )}
        </>
      )}

      <FilterSheet
        open={sheet}
        onClose={() => setSheet(false)}
        resultCount={sorted.length}
        color={color}
        sort={sort}
        onSort={setSort}
        sorts={sorts}
        distance={{ hasLocation, radiusMi, onRadius: setRadiusMi }}
        priceBounds={priceBounds}
        price={price}
        onPrice={setPrice}
        groups={groups}
        onClear={clearAll}
        activeCount={activeCount}
      />
    </div>
  )
}
