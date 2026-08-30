import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api/client'
import type {
  PortalCategoryDetail, PortalCategoryDispensary, PortalCategoryOffering, PortalCategoryProduct,
} from '../types'
import { t, font, categoryColor, alpha } from '../theme'
import {
  readEnum, readNumber, readRange, readSet, useFilterParams, useScrollMemory,
  writeOne, writeRange, writeSet,
} from '../utils/browseState'
import { FeedState } from './ui'
import {
  BrowseCard, BrowseGrid, BrowseToolbar, CATEGORY_EMOJI, Dot, FacetChip, FilterSheet, GridSkeleton,
  SORTS, SORT_KEYS, SearchField, Stat, ActiveChip, formatDollarsShort, haversineMi, productKey, variantWeight,
  type BrowseCardItem, type SheetGroup, type SortKey,
} from './browse'
import { useDebounced } from '../hooks/useDebounced'

/* ── Product enrichment ───────────────────────────────────────────────────── */

/** An offering resolved against the response's store table. */
type Placed = {
  offering: PortalCategoryOffering
  store: PortalCategoryDispensary
}

/** A product plus the location/price facts derived from its offerings. */
type EnrichedProduct = {
  product: PortalCategoryProduct
  closest: Placed | null
  closestDist: number | null
  cheapest: Placed | null
  /** Haystack for the in-category search box. */
  haystack: string
}

type Filters = {
  search: string
  subtype: Set<string>
  brand: Set<string>
  variant: Set<string>
  radiusMi: number | null
  /** Inclusive cents range, or null when the shopper hasn't narrowed it. */
  price: [number, number] | null
}

type FacetKey = 'subtype' | 'brand' | 'variant'

/** Does a product survive the filter set? `except` skips one facet, for counting. */
function matches(e: EnrichedProduct, f: Filters, except?: FacetKey | 'price' | 'radius'): boolean {
  if (f.search && !e.haystack.includes(f.search)) return false
  if (except !== 'subtype' && f.subtype.size && !(e.product.subtype && f.subtype.has(e.product.subtype))) return false
  if (except !== 'brand' && f.brand.size && !(e.product.brand && f.brand.has(e.product.brand))) return false
  if (except !== 'variant' && f.variant.size && !(e.product.variant && f.variant.has(e.product.variant))) return false
  if (except !== 'radius' && f.radiusMi != null) {
    // Only meaningful with a fix on the shopper's position; closestDist is null without one.
    if (e.closestDist == null || e.closestDist > f.radiusMi) return false
  }
  if (except !== 'price' && f.price) {
    const p = e.product.min_price_cents
    // Unpriced products can't satisfy a narrowed range — drop them rather than guess.
    if (p == null || p < f.price[0] || p > f.price[1]) return false
  }
  return true
}

function toCard(e: EnrichedProduct): BrowseCardItem {
  const p = e.product
  const store = (e.closest ?? e.cheapest)?.store ?? null
  return {
    name: p.name,
    brand: p.brand,
    category: p.category,
    subtype: p.subtype,
    variant: p.variant,
    imageUrl: p.image_url,
    priceCents: p.min_price_cents,
    multiPriced: p.min_price_cents != null && p.max_price_cents != null && p.max_price_cents > p.min_price_cents,
    dispensaryCount: p.dispensary_count,
    distanceMi: e.closestDist,
    storeName: store?.name ?? null,
  }
}

/* ── Screen ───────────────────────────────────────────────────────────────── */

interface Props {
  categoryName: string
  onBack: () => void
  /** Open the product page. `brand` is null for unbranded products, which have
   *  the same page as any other -- the key identifies them. */
  onOpenProduct: (brand: string | null, key: string) => void
}

export default function CategoryView({ categoryName, onBack, onOpenProduct }: Props) {
  const [data, setData] = useState<PortalCategoryDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [locationDenied, setLocationDenied] = useState(false)

  // Seeded from the URL so that coming back from a product restores the screen
  // the shopper left, rather than an empty one.
  const [initialParams] = useSearchParams()
  const [search, setSearch] = useState(() => initialParams.get('q') ?? '')
  const [searchFocus, setSearchFocus] = useState(false)
  const [subtype, setSubtype] = useState<Set<string>>(() => readSet(initialParams, 'subtype'))
  const [brand, setBrand] = useState<Set<string>>(() => readSet(initialParams, 'brand'))
  const [variant, setVariant] = useState<Set<string>>(() => readSet(initialParams, 'variant'))
  const [radiusMi, setRadiusMi] = useState<number | null>(() => readNumber(initialParams, 'radius'))
  const [price, setPrice] = useState<[number, number] | null>(() => readRange(initialParams, 'price'))
  const [sort, setSort] = useState<SortKey>(() => readEnum(initialParams, 'sort', SORT_KEYS, 'featured'))
  const [sheet, setSheet] = useState(false)

  // Typing re-filters the whole category and recounts every facet, so drive
  // that off the settled value rather than the keystroke. The field itself
  // stays on `search` and responds immediately.
  const settledSearch = useDebounced(search)

  const c = categoryColor(categoryName)
  const emoji = CATEGORY_EMOJI[categoryName] ?? '📦'
  const scrollRef = useRef<HTMLDivElement>(null)

  useFilterParams({
    q: writeOne(settledSearch),
    subtype: writeSet(subtype),
    brand: writeSet(brand),
    variant: writeSet(variant),
    radius: writeOne(radiusMi),
    price: writeRange(price),
    sort: sort === 'featured' ? [] : [sort],
  })
  useScrollMemory(scrollRef, data != null)

  // Load the category.
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setData(null)

    api.portal.getCategory(categoryName)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setError('Failed to load this category') })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [categoryName])

  // Moving to a different category clears the controls — its facets are not
  // this one's. Skipped on mount, where the controls came from the URL.
  const previousCategory = useRef(categoryName)
  useEffect(() => {
    if (previousCategory.current === categoryName) return
    previousCategory.current = categoryName
    setSearch(''); setSubtype(new Set()); setBrand(new Set()); setVariant(new Set())
    setRadiusMi(null); setPrice(null); setSort('featured')
    scrollRef.current?.scrollTo({ top: 0 })
  }, [categoryName])

  useEffect(() => {
    if (!navigator.geolocation) { setLocationDenied(true); return }
    navigator.geolocation.getCurrentPosition(
      pos => setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setLocationDenied(true),
    )
  }, [])

  const hasLocation = userPos != null

  // Resolve each product's closest and cheapest offering once per position change.
  const enriched = useMemo<EnrichedProduct[]>(() => {
    if (!data) return []
    const stores = data.dispensaries
    return data.products.map(product => {
      let closest: Placed | null = null
      let closestDist = Infinity
      let cheapest: Placed | null = null

      for (const o of product.offerings) {
        const store = stores[o.dispensary_index]
        if (!store) continue
        if (o.price_cents != null
          && (cheapest == null || o.price_cents < cheapest.offering.price_cents!)) {
          cheapest = { offering: o, store }
        }
        if (userPos && store.lat != null && store.lng != null) {
          const d = haversineMi(userPos.lat, userPos.lng, store.lat, store.lng)
          if (d < closestDist) { closestDist = d; closest = { offering: o, store } }
        }
      }

      return {
        product,
        closest,
        closestDist: closest ? closestDist : null,
        cheapest,
        haystack: [product.name, product.brand, product.subtype, product.strain, product.variant]
          .filter(Boolean).join(' ').toLowerCase(),
      }
    })
  }, [data, userPos])

  // Full price span across the category — the bounds of the range slider.
  // Folded rather than spread into Math.min/max: a category can hold tens of
  // thousands of prices, and that many arguments overflows the call stack.
  const priceBounds = useMemo<[number, number] | null>(() => {
    let lo = Infinity
    let hi = -Infinity
    let seen = 0
    for (const e of enriched) {
      const p = e.product.min_price_cents
      if (p == null) continue
      seen++
      if (p < lo) lo = p
      if (p > hi) hi = p
    }
    if (seen < 2 || hi <= lo) return null
    return [lo, hi]
  }, [enriched])

  const filters: Filters = { search: settledSearch.trim().toLowerCase(), subtype, brand, variant, radiusMi, price }

  /** Facet options with counts that respect every *other* active filter. */
  function facetFor(key: FacetKey) {
    const counts = new Map<string, number>()
    for (const e of enriched) {
      if (!matches(e, filters, key)) continue
      const v = e.product[key]
      if (!v) continue
      counts.set(v, (counts.get(v) ?? 0) + 1)
    }
    return [...counts.entries()].map(([value, count]) => ({ value, count }))
  }

  const subtypeFacet = useMemo(
    () => facetFor('subtype').sort((a, b) => b.count - a.count),
    [enriched, settledSearch, subtype, brand, variant, radiusMi, price],
  )
  const brandFacet = useMemo(
    () => facetFor('brand').sort((a, b) => b.count - a.count),
    [enriched, settledSearch, subtype, brand, variant, radiusMi, price],
  )
  const variantFacet = useMemo(
    () => facetFor('variant').sort((a, b) => variantWeight(a.value) - variantWeight(b.value)),
    [enriched, settledSearch, subtype, brand, variant, radiusMi, price],
  )

  const filtered = useMemo(
    () => enriched.filter(e => matches(e, filters)),
    [enriched, settledSearch, subtype, brand, variant, radiusMi, price],
  )

  const sorted = useMemo(() => {
    const arr = [...filtered]
    if (sort === 'price-asc' || sort === 'price-desc') {
      const dir = sort === 'price-asc' ? 1 : -1
      arr.sort((a, b) => {
        const pa = a.product.min_price_cents
        const pb = b.product.min_price_cents
        if (pa == null) return 1
        if (pb == null) return -1
        return (pa - pb) * dir
      })
    } else if (sort === 'nearest') {
      arr.sort((a, b) => (a.closestDist ?? Infinity) - (b.closestDist ?? Infinity))
    } else if (sort === 'name') {
      arr.sort((a, b) => a.product.name.localeCompare(b.product.name))
    } else {
      // Featured: things that make a good card first — a photo, then breadth of
      // availability, then the server's brand/name ordering as the tiebreak.
      arr.sort((a, b) => {
        const img = Number(!!b.product.image_url) - Number(!!a.product.image_url)
        if (img) return img
        return b.product.dispensary_count - a.product.dispensary_count
      })
    }
    return arr
  }, [filtered, sort])

  const activeCount =
    subtype.size + brand.size + variant.size + (radiusMi != null ? 1 : 0) + (price ? 1 : 0)
  const sortLabel = SORTS.find(s => s.key === sort)!.label

  function toggle(setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) {
    setter(prev => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  function clearAll() {
    setSubtype(new Set()); setBrand(new Set()); setVariant(new Set())
    setRadiusMi(null); setPrice(null)
  }

  function openProduct(e: EnrichedProduct) {
    // Every card leads to the same place. This used to fork on whether the
    // product had a brand, so an unbranded one dropped the shopper into one
    // store's shelf -- a different screen, in a different section, reached by
    // the same tap.
    onOpenProduct(e.product.brand ?? null, productKey(e.product))
  }

  // Drop a nearest sort / radius filter that location permission can't support.
  useEffect(() => {
    if (hasLocation) return
    if (sort === 'nearest') setSort('featured')
    if (radiusMi != null) setRadiusMi(null)
  }, [hasLocation, sort, radiusMi])

  const groups: SheetGroup[] = [
    { key: 'subtype', title: 'Subtype', facet: subtypeFacet, sel: subtype, onToggle: v => toggle(setSubtype, v) },
    { key: 'variant', title: 'Weight / Size', facet: variantFacet, sel: variant, onToggle: v => toggle(setVariant, v), capitalize: false },
    { key: 'brand', title: 'Brand', facet: brandFacet, sel: brand, onToggle: v => toggle(setBrand, v) },
  ]

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{
        position: 'relative',
        background: `linear-gradient(160deg, ${alpha(c, 0.30)} 0%, ${alpha(c, 0.08)} 45%, ${t.bg} 100%)`,
        padding: 'calc(env(safe-area-inset-top, 0px) + 16px) 16px 18px',
        overflow: 'hidden',
      }}>
        {/* Oversized category glyph, bled off the right edge */}
        <div aria-hidden style={{
          position: 'absolute', right: -18, top: -14, fontSize: 132, lineHeight: 1,
          opacity: 0.13, transform: 'rotate(-12deg)', pointerEvents: 'none', userSelect: 'none',
        }}>
          {emoji}
        </div>

        <button
          onClick={onBack}
          aria-label="Back"
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 36, height: 36, borderRadius: '50%',
            background: alpha('#000', 0.35), border: `1px solid ${t.border}`,
            color: t.text1, fontSize: 19, lineHeight: 1, padding: 0,
            backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          }}
        >
          ←
        </button>

        <div style={{ position: 'relative', marginTop: 16 }}>
          <div style={{
            color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero + 4,
            letterSpacing: '-0.03em', lineHeight: 1.05, textTransform: 'capitalize',
          }}>
            {categoryName}
          </div>

          {data && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 9, flexWrap: 'wrap' }}>
              <Stat value={data.product_count} label={data.product_count === 1 ? 'product' : 'products'} color={c} />
              <Dot />
              <Stat value={data.brand_count} label={data.brand_count === 1 ? 'brand' : 'brands'} color={c} />
              <Dot />
              <Stat
                value={data.dispensary_count}
                label={data.dispensary_count === 1 ? 'dispensary' : 'dispensaries'}
                color={c}
              />
            </div>
          )}
        </div>

        <div style={{ position: 'relative', marginTop: 16 }}>
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder={`Search ${categoryName}…`}
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
        quickRail={subtypeFacet.length > 1 && (
          /* Quick subtype rail — the filter shoppers reach for first */
          <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '10px 14px 10px' }}>
            <FacetChip label="All" active={subtype.size === 0} color={c} onClick={() => setSubtype(new Set())} />
            {subtypeFacet.map(f => (
              <FacetChip
                key={f.value}
                label={f.value}
                count={f.count}
                active={subtype.has(f.value)}
                color={c}
                onClick={() => toggle(setSubtype, f.value)}
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
          {[...subtype].map(v => <ActiveChip key={'s' + v} label={v} onRemove={() => toggle(setSubtype, v)} />)}
          {[...brand].map(v => <ActiveChip key={'b' + v} label={v} onRemove={() => toggle(setBrand, v)} />)}
          {[...variant].map(v => <ActiveChip key={'v' + v} label={v} capitalize={false} onRemove={() => toggle(setVariant, v)} />)}
        </>}
      />

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      {loading ? (
        <GridSkeleton />
      ) : error ? (
        <FeedState kind="error" message={error} />
      ) : !data || data.products.length === 0 ? (
        <FeedState
          kind="empty"
          message={`No ${categoryName} in stock`}
          hint="Check back soon — menus update regularly."
          icon={emoji}
        />
      ) : (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, padding: '14px 16px 4px',
          }}>
            <span style={{ color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium }}>
              {sorted.length} {sorted.length === 1 ? 'product' : 'products'}
              {sorted.length !== data.product_count && (
                <span style={{ color: t.text4 }}> of {data.product_count}</span>
              )}
            </span>
            {data.truncated && (
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
            <BrowseGrid
              items={sorted}
              keyOf={e => e.product.key}
              render={e => (
                <BrowseCard
                  item={toCard(e)}
                  color={c}
                  suppressSubtype={categoryName}
                  onOpen={() => openProduct(e)}
                />
              )}
            />
          )}
        </>
      )}

      {/* ── Filter & sort sheet ──────────────────────────────────────────── */}
      <FilterSheet
        open={sheet}
        onClose={() => setSheet(false)}
        resultCount={sorted.length}
        color={c}
        sort={sort}
        onSort={setSort}
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
