import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api/client'
import type { PortalProduct } from '../types'
import { t, font, categoryColor, alpha } from '../theme'
import { FeedState } from './ui'
import {
  readEnum, readRange, readSet, useFilterParams, useScrollMemory, writeOne, writeRange, writeSet,
} from '../utils/browseState'
import {
  ActiveChip, BrowseCard, BrowseGrid, BrowseToolbar, Dot, FacetChip, FilterSheet, GridSkeleton,
  SORTS_NO_LOCATION, SORT_KEYS, SearchField, Stat, formatDollarsShort, productKey, variantWeight,
  type BrowseCardItem, type SheetGroup, type SortKey,
} from './browse'

/** How many rows to pull before we stop and tell the shopper to narrow down. */
const PAGE = 200
const MAX_ROWS = 1000

/** Named server-side like every other listing surface, so search results and
 *  the pages they open agree on what a product is called. */
function displayName(p: PortalProduct): string {
  return p.display_name
}

type Filters = {
  category: Set<string>
  subtype: Set<string>
  brand: Set<string>
  variant: Set<string>
  price: [number, number] | null
}

type FacetKey = 'category' | 'subtype' | 'brand' | 'variant'

/** Does a row survive the filter set? `except` skips one facet, for counting. */
function matches(p: PortalProduct, f: Filters, except?: FacetKey | 'price'): boolean {
  if (except !== 'category' && f.category.size && !(p.category && f.category.has(p.category))) return false
  if (except !== 'subtype' && f.subtype.size && !(p.subtype && f.subtype.has(p.subtype))) return false
  if (except !== 'brand' && f.brand.size && !(p.brand && f.brand.has(p.brand))) return false
  if (except !== 'variant' && f.variant.size && !(p.variant && f.variant.has(p.variant))) return false
  if (except !== 'price' && f.price) {
    const v = p.min_price_cents
    // Unpriced products can't satisfy a narrowed range — drop them rather than guess.
    if (v == null || v < f.price[0] || v > f.price[1]) return false
  }
  return true
}

function toCard(p: PortalProduct): BrowseCardItem {
  return {
    name: displayName(p),
    brand: p.brand,
    category: p.category,
    subtype: p.subtype,
    variant: p.variant,
    // The `products` view aggregates listings and carries no image; the card
    // falls back to the category plate, same as every other browse surface.
    imageUrl: null,
    priceCents: p.min_price_cents,
    multiPriced: p.min_price_cents != null && p.max_price_cents != null && p.max_price_cents > p.min_price_cents,
    dispensaryCount: p.dispensary_count,
    // The aggregate rows carry no coordinates, so search can't show distance.
    distanceMi: null,
    storeName: null,
  }
}

interface Props {
  /** Pre-filter to one category, from `/portal/search?category=…`. */
  initialCategory?: string | null
  /** Open the product page. `brand` is null for unbranded rows, which reach the
   *  same page as any other -- the key identifies them. */
  onOpenProduct: (brand: string | null, key: string) => void
}

export default function SearchView({ initialCategory, onOpenProduct }: Props) {
  const [rows, setRows] = useState<PortalProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [truncated, setTruncated] = useState(false)

  // Seeded from the URL so returning from a product restores the search the
  // shopper left, rather than an empty one.
  const [initialParams] = useSearchParams()
  const [input, setInput] = useState(() => initialParams.get('q') ?? '')
  const [query, setQuery] = useState(() => initialParams.get('q') ?? '')
  const [searchFocus, setSearchFocus] = useState(false)

  const [category, setCategory] = useState<Set<string>>(
    () => readSet(initialParams, 'category'),
  )
  const [subtype, setSubtype] = useState<Set<string>>(() => readSet(initialParams, 'subtype'))
  const [brand, setBrand] = useState<Set<string>>(() => readSet(initialParams, 'brand'))
  const [variant, setVariant] = useState<Set<string>>(() => readSet(initialParams, 'variant'))
  const [price, setPrice] = useState<[number, number] | null>(() => readRange(initialParams, 'price'))
  const [sort, setSort] = useState<SortKey>(() => readEnum(initialParams, 'sort', SORT_KEYS, 'featured'))
  const [sheet, setSheet] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const previousQuery = useRef(query)

  useFilterParams({
    q: writeOne(input),
    category: writeSet(category),
    subtype: writeSet(subtype),
    brand: writeSet(brand),
    variant: writeSet(variant),
    price: writeRange(price),
    sort: sort === 'featured' ? [] : [sort],
  })
  useScrollMemory(scrollRef, !loading && rows.length > 0)

  // A category arriving from a deep link after mount (tapping a category tile).
  const previousInitial = useRef(initialCategory)
  useEffect(() => {
    if (previousInitial.current === initialCategory) return
    previousInitial.current = initialCategory
    setCategory(new Set(initialCategory ? [initialCategory] : []))
  }, [initialCategory])

  // Debounce typing so we aren't firing a request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setQuery(input.trim()), 250)
    return () => clearTimeout(id)
  }, [input])

  // Page through the matches so the client-side facet counts describe the whole
  // result set, not just the first slice.
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setTruncated(false)
    if (previousQuery.current !== query) {
      previousQuery.current = query
      scrollRef.current?.scrollTo({ top: 0 })
    }

    ;(async () => {
      const acc: PortalProduct[] = []
      try {
        for (let offset = 0; offset < MAX_ROWS; offset += PAGE) {
          const page = await api.portal.getProducts({ q: query || undefined, limit: PAGE, offset })
          if (cancelled) return
          acc.push(...page)
          if (page.length < PAGE) break
        }
        if (cancelled) return
        setRows(acc)
        setTruncated(acc.length >= MAX_ROWS)
      } catch {
        if (!cancelled) setError('Failed to load products')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [query])

  const filters: Filters = { category, subtype, brand, variant, price }

  const priceBounds = useMemo<[number, number] | null>(() => {
    const prices = rows.map(p => p.min_price_cents).filter((v): v is number => v != null)
    if (prices.length < 2) return null
    const lo = Math.min(...prices)
    const hi = Math.max(...prices)
    return hi > lo ? [lo, hi] : null
  }, [rows])

  /** Facet options with counts that respect every *other* active filter. */
  function facetFor(key: FacetKey) {
    const counts = new Map<string, number>()
    for (const p of rows) {
      if (!matches(p, filters, key)) continue
      const v = p[key]
      if (!v) continue
      counts.set(v, (counts.get(v) ?? 0) + 1)
    }
    return [...counts.entries()].map(([value, count]) => ({ value, count }))
  }

  const categoryFacet = useMemo(
    () => facetFor('category').sort((a, b) => b.count - a.count),
    [rows, category, subtype, brand, variant, price],
  )
  const subtypeFacet = useMemo(
    () => facetFor('subtype').sort((a, b) => b.count - a.count),
    [rows, category, subtype, brand, variant, price],
  )
  const brandFacet = useMemo(
    () => facetFor('brand').sort((a, b) => b.count - a.count),
    [rows, category, subtype, brand, variant, price],
  )
  const variantFacet = useMemo(
    () => facetFor('variant').sort((a, b) => variantWeight(a.value) - variantWeight(b.value)),
    [rows, category, subtype, brand, variant, price],
  )

  const filtered = useMemo(
    () => rows.filter(p => matches(p, filters)),
    [rows, category, subtype, brand, variant, price],
  )

  const sorted = useMemo(() => {
    const arr = [...filtered]
    if (sort === 'price-asc' || sort === 'price-desc') {
      const dir = sort === 'price-asc' ? 1 : -1
      arr.sort((a, b) => {
        const pa = a.min_price_cents
        const pb = b.min_price_cents
        if (pa == null) return 1
        if (pb == null) return -1
        return (pa - pb) * dir
      })
    } else if (sort === 'name') {
      arr.sort((a, b) => displayName(a).localeCompare(displayName(b)))
    } else {
      // Featured: in stock first, then the products carried in the most places.
      arr.sort((a, b) => {
        const stock = Number(b.any_in_stock) - Number(a.any_in_stock)
        if (stock) return stock
        return b.dispensary_count - a.dispensary_count
      })
    }
    return arr
  }, [filtered, sort])

  const activeCount = category.size + subtype.size + brand.size + variant.size + (price ? 1 : 0)
  const sortLabel = SORTS_NO_LOCATION.find(s => s.key === sort)!.label

  // Colour the page by the category being browsed, once it's the only one.
  const c = category.size === 1 ? categoryColor([...category][0]) : 'var(--accent)'

  function toggle(setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) {
    setter(prev => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  function clearAll() {
    setCategory(new Set()); setSubtype(new Set()); setBrand(new Set()); setVariant(new Set())
    setPrice(null)
  }

  function openProduct(p: PortalProduct) {
    // A row's identity is the same five-part key the product endpoint takes, so
    // every result opens a product page. Unbranded rows used to be bounced back
    // to a category listing instead, which read as the tap doing nothing.
    onOpenProduct(p.brand ?? null, productKey(p))
  }

  const groups: SheetGroup[] = [
    { key: 'category', title: 'Category', facet: categoryFacet, sel: category, onToggle: v => toggle(setCategory, v) },
    { key: 'subtype', title: 'Subtype', facet: subtypeFacet, sel: subtype, onToggle: v => toggle(setSubtype, v) },
    { key: 'variant', title: 'Weight / Size', facet: variantFacet, sel: variant, onToggle: v => toggle(setVariant, v), capitalize: false },
    { key: 'brand', title: 'Brand', facet: brandFacet, sel: brand, onToggle: v => toggle(setBrand, v) },
  ]

  const brandCount = useMemo(() => new Set(rows.map(p => p.brand).filter(Boolean)).size, [rows])

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{
        position: 'relative',
        background: `linear-gradient(160deg, ${alpha('#a8e063', 0.22)} 0%, ${alpha('#a8e063', 0.06)} 45%, ${t.bg} 100%)`,
        padding: 'calc(env(safe-area-inset-top, 0px) + 20px) 16px 18px',
        overflow: 'hidden',
      }}>
        <div aria-hidden style={{
          position: 'absolute', right: -16, top: -20, fontSize: 132, lineHeight: 1,
          opacity: 0.10, transform: 'rotate(-12deg)', pointerEvents: 'none', userSelect: 'none',
        }}>
          🔍
        </div>

        <div style={{ position: 'relative' }}>
          <div style={{
            color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero + 4,
            letterSpacing: '-0.03em', lineHeight: 1.05,
          }}>
            Search
          </div>

          {!loading && !error && rows.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 9, flexWrap: 'wrap' }}>
              <Stat value={rows.length} label={rows.length === 1 ? 'product' : 'products'} color={t.accent} />
              <Dot />
              <Stat value={brandCount} label={brandCount === 1 ? 'brand' : 'brands'} color={t.accent} />
              <Dot />
              <Stat
                value={categoryFacet.length}
                label={categoryFacet.length === 1 ? 'category' : 'categories'}
                color={t.accent}
              />
            </div>
          )}
        </div>

        <div style={{ position: 'relative', marginTop: 16 }}>
          <SearchField
            value={input}
            onChange={setInput}
            placeholder="Search products, brands, strains…"
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
        quickRail={categoryFacet.length > 1 && (
          /* Quick category rail — the first cut shoppers make when searching */
          <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '10px 14px 10px' }}>
            <FacetChip label="All" active={category.size === 0} color="var(--accent)" onClick={() => setCategory(new Set())} />
            {categoryFacet.map(f => (
              <FacetChip
                key={f.value}
                label={f.value}
                count={f.count}
                active={category.has(f.value)}
                color={categoryColor(f.value)}
                onClick={() => toggle(setCategory, f.value)}
              />
            ))}
          </div>
        )}
        activeChips={<>
          {price && (
            <ActiveChip
              label={`${formatDollarsShort(price[0])}–${formatDollarsShort(price[1])}`}
              capitalize={false}
              onRemove={() => setPrice(null)}
            />
          )}
          {[...category].map(v => <ActiveChip key={'c' + v} label={v} onRemove={() => toggle(setCategory, v)} />)}
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
      ) : rows.length === 0 ? (
        <FeedState
          kind="empty"
          message="No products found"
          hint={query ? `Nothing matches “${query}”.` : 'Try a different search.'}
          icon="🔍"
        />
      ) : (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, padding: '14px 16px 4px',
          }}>
            <span style={{ color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium }}>
              {sorted.length} {sorted.length === 1 ? 'product' : 'products'}
              {sorted.length !== rows.length && <span style={{ color: t.text4 }}> of {rows.length}</span>}
            </span>
            {truncated && (
              <span style={{ color: t.text4, fontSize: font.size.caption }}>refine to see more</span>
            )}
          </div>

          {sorted.length === 0 ? (
            <FeedState
              kind="empty"
              message="No matches"
              hint={query
                ? `Nothing matches “${query}” with these filters.`
                : 'Try removing a filter or widening the price range.'}
              icon="🔍"
              style={{ minHeight: 260 }}
            />
          ) : (
            <BrowseGrid items={sorted} resetKey={query}>
              {p => (
                <BrowseCard
                  key={productKey(p) + '|' + (p.brand ?? '')}
                  item={toCard(p)}
                  color={categoryColor(p.category)}
                  suppressSubtype={p.category}
                  onOpen={() => openProduct(p)}
                />
              )}
            </BrowseGrid>
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
        sorts={SORTS_NO_LOCATION}
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
