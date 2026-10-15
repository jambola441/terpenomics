import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api/client'
import type { PortalProduct } from '../types'
import { t, font, categoryColor, categoryLabel, alpha, raw } from '../theme'
import { FeedState, PageTitle } from './ui'
import { Icon, CategoryIcon } from './Icon'
import {
  readEnum, readRange, readSet, useFilterParams, useScrollMemory, writeOne, writeRange, writeSet,
} from '../utils/browseState'
import {
  ActiveChip, BrowseCard, BrowseGrid, BrowseToolbar, Dot, FacetChip, FilterSheet, GridSkeleton,
  SearchField, Stat, type SheetGroup,
} from './browse'
import {
  SEARCH_MAX_ROWS, SEARCH_PAGE, SORTS_NO_LOCATION, SORT_KEYS, priceBoundsOf, priceRangeLabel, productKey, searchCard,
  searchFacet, searchMatches, searchRowKey, searchSort, sortLabelOf, toggled,
  type SearchFacetKey, type SearchFilters, type SortKey,
} from '../utils/browseLogic'

/** How many rows to pull before we stop and tell the shopper to narrow down. */
const PAGE = SEARCH_PAGE
const MAX_ROWS = SEARCH_MAX_ROWS

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
  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)
  // Later pages still arriving after the first is on screen.
  const [loadingMore, setLoadingMore] = useState(false)

  // Seeded from the URL so returning from a product restores the search the
  // shopper left, rather than an empty one.
  const [initialParams] = useSearchParams()
  const [input, setInput] = useState(() => initialParams.get('q') ?? '')
  // Arriving from Shop's search box, the shopper meant to type: focus the
  // field. Not when a link brought a query or a category with it.
  const [focusOnOpen] = useState(() => !initialParams.get('q') && !initialCategory)
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
  // result set, not just the first slice. The first page goes on screen as soon
  // as it lands and the rest join it as they arrive; waiting for all of them
  // (up to five round trips) used to hold the skeleton for seconds.
  useEffect(() => {
    let cancelled = false
    setLoading(true); setLoadingMore(false); setError(null); setTruncated(false)
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
          const more = page.length === PAGE && acc.length < MAX_ROWS
          setRows([...acc])
          setLoading(false)
          setLoadingMore(more)
          if (!more) break
        }
        if (cancelled) return
        setTruncated(acc.length >= MAX_ROWS)
      } catch {
        if (cancelled) return
        // A later page failing still leaves the first ones worth showing.
        if (acc.length) setLoadingMore(false)
        else { setError('Failed to load products'); setLoading(false) }
      }
    })()

    return () => { cancelled = true }
  }, [query, attempt])

  const filters: SearchFilters = { category, subtype, brand, variant, price }

  const priceBounds = useMemo(() => priceBoundsOf(rows.map(p => p.min_price_cents)), [rows])

  /** Facet options with counts that respect every *other* active filter. */
  function facetFor(key: SearchFacetKey) {
    return searchFacet(rows, filters, key)
  }

  const categoryFacet = useMemo(
    () => facetFor('category'),
    [rows, category, subtype, brand, variant, price],
  )
  const subtypeFacet = useMemo(
    () => facetFor('subtype'),
    [rows, category, subtype, brand, variant, price],
  )
  const brandFacet = useMemo(
    () => facetFor('brand'),
    [rows, category, subtype, brand, variant, price],
  )
  const variantFacet = useMemo(
    () => facetFor('variant'),
    [rows, category, subtype, brand, variant, price],
  )

  const filtered = useMemo(
    () => rows.filter(p => searchMatches(p, filters)),
    [rows, category, subtype, brand, variant, price],
  )

  const sorted = useMemo(() => searchSort(filtered, sort), [filtered, sort])

  const activeCount = category.size + subtype.size + brand.size + variant.size + (price ? 1 : 0)
  const sortLabel = sortLabelOf(sort)

  // Colour the page by the category being browsed, once it's the only one.
  const c = category.size === 1 ? categoryColor([...category][0]) : 'var(--accent)'

  function toggle(setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) {
    setter(prev => toggled(prev, value))
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
    <div ref={scrollRef} style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{
        position: 'relative',
        background: `linear-gradient(165deg, ${alpha(raw.accent, 0.14)} 0%, ${alpha(raw.accent, 0.04)} 50%, ${t.bg} 100%)`,
        padding: 'calc(env(safe-area-inset-top, 0px) + 24px) 16px 18px',
        overflow: 'hidden',
      }}>
        <Icon
          name="search"
          size={168}
          strokeWidth={0.75}
          color={t.accent}
          style={{ position: 'absolute', right: -30, top: -26, opacity: 0.12, pointerEvents: 'none' }}
        />

        <div style={{ position: 'relative' }}>
          <PageTitle size={34}>Search</PageTitle>

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
            autoFocus={focusOnOpen}
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
                label={categoryLabel(f.value)}
                icon={<CategoryIcon category={f.value} size={15} color={category.has(f.value) ? undefined : t.text3} />}
                capitalize={false}
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
              label={priceRangeLabel(price)}
              capitalize={false}
              onRemove={() => setPrice(null)}
            />
          )}
          {[...category].map(v => <ActiveChip key={'c' + v} label={categoryLabel(v)} onRemove={() => toggle(setCategory, v)} />)}
          {[...subtype].map(v => <ActiveChip key={'s' + v} label={v} onRemove={() => toggle(setSubtype, v)} />)}
          {[...brand].map(v => <ActiveChip key={'b' + v} label={v} onRemove={() => toggle(setBrand, v)} />)}
          {[...variant].map(v => <ActiveChip key={'v' + v} label={v} capitalize={false} onRemove={() => toggle(setVariant, v)} />)}
        </>}
      />

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      {loading ? (
        <GridSkeleton />
      ) : error ? (
        <FeedState kind="error" message={error} onRetry={() => setAttempt(n => n + 1)} />
      ) : rows.length === 0 ? (
        <FeedState
          kind="empty"
          message="No products found"
          hint={query ? `Nothing matches “${query}”.` : 'Try a different search.'}
          icon="search"
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
              {loadingMore && <span style={{ color: t.text4 }}> · loading more…</span>}
            </span>
            {truncated && (
              <span style={{ color: t.text3, fontSize: font.size.caption }}>refine to see more</span>
            )}
          </div>

          {sorted.length === 0 ? (
            <FeedState
              kind="empty"
              message="No matches"
              hint={query
                ? `Nothing matches “${query}” with these filters.`
                : 'Try removing a filter or widening the price range.'}
              icon="search"
              style={{ minHeight: 260 }}
            />
          ) : (
            <BrowseGrid items={sorted} resetKey={query}>
              {p => (
                <BrowseCard
                  key={searchRowKey(p)}
                  item={searchCard(p)}
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
