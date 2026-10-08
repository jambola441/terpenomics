import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { CartItem, DispensaryListing } from '../types'
import { t, font, categoryColor, categoryLabel, alpha } from '../theme'
import { BackButton, FeedState, PageTitle } from './ui'
import { Icon, CategoryIcon } from './Icon'
import {
  ActiveChip, BrowseCard, BrowseToolbar, Dot, FacetChip, FilterSheet, MarketNote,
  GridSkeleton, SORTS_NO_LOCATION, SORT_KEYS, SearchField, Stat, formatDollarsShort, variantWeight,
  type BrowseCardItem, type SheetGroup, type SortKey,
} from './browse'
import {
  readEnum, readRange, readSet, useFilterParams, useScrollMemory, writeOne, writeRange, writeSet,
} from '../utils/browseState'

import { inShelfOrder } from './DispensaryListings'

type Filters = {
  search: string
  brand: Set<string>
  subtype: Set<string>
  variant: Set<string>
  /** Inclusive cents range, or null when the shopper hasn't narrowed it. */
  price: [number, number] | null
}

type FacetKey = 'brand' | 'subtype' | 'variant'

/** The listing field each facet reads. */
const FACET_FIELD: Record<FacetKey, 'scraped_brand' | 'subtype' | 'variant'> = {
  brand: 'scraped_brand',
  subtype: 'subtype',
  variant: 'variant',
}

/** Does a listing survive the filter set? `except` skips one facet, for counting. */
function matches(l: DispensaryListing, f: Filters, except?: FacetKey | 'price'): boolean {
  if (f.search) {
    const hay = [l.display_name, l.scraped_name, l.scraped_brand, l.strain, l.subtype]
      .filter(Boolean).join(' ').toLowerCase()
    if (!hay.includes(f.search)) return false
  }
  if (except !== 'brand' && f.brand.size && !(l.scraped_brand && f.brand.has(l.scraped_brand))) return false
  if (except !== 'subtype' && f.subtype.size && !(l.subtype && f.subtype.has(l.subtype))) return false
  if (except !== 'variant' && f.variant.size && !(l.variant && f.variant.has(l.variant))) return false
  if (except !== 'price' && f.price) {
    const p = l.price_cents
    // Unpriced listings can't satisfy a narrowed range — drop them rather than guess.
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
    // One listing is one price — never a "from" range.
    multiPriced: false,
    // A single store, so the card's availability footer stays quiet.
    dispensaryCount: 1,
    // One dispensary means distance is a property of the store, not the item.
    distanceMi: null,
    storeName: null,
  }
}

interface Props {
  dispensaryId: string
  dispensaryName: string
  dispensarySlug?: string
  category: string
  acceptsPickup?: boolean
  onAddToCart?: (item: CartItem) => void
  cart?: CartItem[]
}

export default function AisleView({
  dispensaryId, dispensaryName, dispensarySlug = '', category,
  acceptsPickup = false, onAddToCart, cart = [],
}: Props) {
  const navigate = useNavigate()
  // The aisles this store has stock in; the switcher offers only those, so no
  // chip leads to "No tinctures in stock".
  const [carried, setCarried] = useState<string[] | null>(null)
  useEffect(() => {
    let live = true
    api.portal.getDispensaryFilterOptions(dispensaryId)
      .then(o => { if (live && o.categories) setCarried(inShelfOrder(o.categories.map(c => c.name))) })
      .catch(() => { if (live) setCarried(null) })
    return () => { live = false }
  }, [dispensaryId])
  // Back to wherever the shopper came from (the store, Home, a listing),
  // rather than pushing the store page on top: that used to loop store ->
  // aisle -> store -> aisle. Opened from a link, there is nothing to go back
  // to, so it goes to the store.
  const goBack = () => {
    if ((window.history.state?.idx ?? 0) > 0) navigate(-1)
    else navigate(`/portal/map/${dispensaryId}`, { replace: true })
  }
  const [all, setAll] = useState<DispensaryListing[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Seeded from the URL: a Back from a listing must land on the aisle the
  // shopper had narrowed, not a fresh one.
  const [initialParams] = useSearchParams()
  const [search, setSearch] = useState(() => initialParams.get('q') ?? '')
  const [searchFocus, setSearchFocus] = useState(false)
  const [brand, setBrand] = useState<Set<string>>(() => readSet(initialParams, 'brand'))
  const [subtype, setSubtype] = useState<Set<string>>(() => readSet(initialParams, 'subtype'))
  const [variant, setVariant] = useState<Set<string>>(() => readSet(initialParams, 'variant'))
  const [price, setPrice] = useState<[number, number] | null>(() => readRange(initialParams, 'price'))
  const [sort, setSort] = useState<SortKey>(() => readEnum(initialParams, 'sort', SORT_KEYS, 'featured'))
  const [sheet, setSheet] = useState(false)

  const c = categoryColor(category)
  const scrollRef = useRef<HTMLDivElement>(null)

  useFilterParams({
    q: writeOne(search),
    brand: writeSet(brand),
    subtype: writeSet(subtype),
    variant: writeSet(variant),
    price: writeRange(price),
    sort: sort === 'featured' ? [] : [sort],
  })
  useScrollMemory(scrollRef, all.length > 0)
  const previousAisle = useRef(dispensaryId + '/' + category)

  // Load the whole aisle once (paginated; API caps limit at 100), then
  // filter/sort/facet entirely on the client for instant UX.
  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setAll([])
    // Only a move to a different aisle clears the controls; on the mount that
    // follows a Back they came from the URL and must stand.
    if (previousAisle.current !== dispensaryId + '/' + category) {
      previousAisle.current = dispensaryId + '/' + category
      setSearch(''); setBrand(new Set()); setSubtype(new Set()); setVariant(new Set())
      setPrice(null); setSort('featured')
      scrollRef.current?.scrollTo({ top: 0 })
    }

    ;(async () => {
      const PAGE = 100
      const MAX = 1000 // safety cap
      const acc: DispensaryListing[] = []
      try {
        for (let offset = 0; offset < MAX; offset += PAGE) {
          const page = await api.portal.getDispensaryListings(dispensaryId, { category, limit: PAGE, offset })
          if (cancelled) return
          acc.push(...page)
          if (page.length < PAGE) break
        }
        if (!cancelled) setAll(acc)
      } catch {
        if (!cancelled) setError('Failed to load')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [dispensaryId, category, attempt])

  const filters: Filters = { search: search.trim().toLowerCase(), brand, subtype, variant, price }

  // Full price span across the aisle — the bounds of the range slider.
  const priceBounds = useMemo<[number, number] | null>(() => {
    const prices = all.map(l => l.price_cents).filter((p): p is number => p != null)
    if (prices.length < 2) return null
    const lo = Math.min(...prices)
    const hi = Math.max(...prices)
    return hi > lo ? [lo, hi] : null
  }, [all])

  /** Facet options with counts that respect every *other* active filter. */
  function facetFor(key: FacetKey) {
    const field = FACET_FIELD[key]
    const counts = new Map<string, number>()
    for (const l of all) {
      if (!matches(l, filters, key)) continue
      const v = l[field]
      if (!v) continue
      counts.set(v, (counts.get(v) ?? 0) + 1)
    }
    return [...counts.entries()].map(([value, count]) => ({ value, count }))
  }

  const brandFacet = useMemo(
    () => facetFor('brand').sort((a, b) => b.count - a.count),
    [all, search, brand, subtype, variant, price],
  )
  const subtypeFacet = useMemo(
    () => facetFor('subtype').sort((a, b) => b.count - a.count),
    [all, search, brand, subtype, variant, price],
  )
  const variantFacet = useMemo(
    () => facetFor('variant').sort((a, b) => variantWeight(a.value) - variantWeight(b.value)),
    [all, search, brand, subtype, variant, price],
  )

  const filtered = useMemo(
    () => all.filter(l => matches(l, filters)),
    [all, search, brand, subtype, variant, price],
  )

  const sorted = useMemo(() => {
    const arr = [...filtered]
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
      // Featured: listings that make a good card first — a photo, then a price.
      arr.sort((a, b) => {
        const img = Number(!!b.image_url) - Number(!!a.image_url)
        if (img) return img
        return Number(b.price_cents != null) - Number(a.price_cents != null)
      })
    }
    return arr
  }, [filtered, sort])

  const brandCount = useMemo(
    () => new Set(all.map(l => l.scraped_brand).filter(Boolean)).size,
    [all],
  )

  const activeCount = brand.size + subtype.size + variant.size + (price ? 1 : 0)
  const sortLabel = SORTS_NO_LOCATION.find(s => s.key === sort)!.label

  function toggle(setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) {
    setter(prev => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  function clearAll() {
    setBrand(new Set()); setSubtype(new Set()); setVariant(new Set()); setPrice(null)
  }

  const groups: SheetGroup[] = [
    { key: 'subtype', title: 'Subcategory', facet: subtypeFacet, sel: subtype, onToggle: v => toggle(setSubtype, v) },
    { key: 'variant', title: 'Weight / Size', facet: variantFacet, sel: variant, onToggle: v => toggle(setVariant, v), capitalize: false },
    { key: 'brand', title: 'Brand', facet: brandFacet, sel: brand, onToggle: v => toggle(setBrand, v) },
  ]

  /** The add-to-cart affordance overlaid on a card's image. */
  function cartAction(l: DispensaryListing) {
    if (!acceptsPickup || !onAddToCart) return undefined
    const cartQty = cart.filter(i => i.listingId === l.id).reduce((s, i) => s + i.quantity, 0)
    return (
      <button
        aria-label={cartQty > 0 ? `Add another ${l.display_name}, ${cartQty} in cart` : `Add ${l.display_name} to cart`}
        onClick={e => {
          e.stopPropagation()
          onAddToCart({
            listingId: l.id, dispensaryId, dispensarySlug, dispensaryName,
            name: l.display_name, brand: l.scraped_brand ?? null,
            variant: l.variant ?? null, price_cents: l.price_cents ?? null,
            url: l.url ?? null, image_url: l.image_url ?? null, quantity: 1,
          })
        }}
        style={{
          width: 36, height: 36, borderRadius: '50%',
          background: cartQty > 0 ? t.bg : t.accent,
          border: cartQty > 0 ? `1.5px solid ${t.accent}` : 'none', padding: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: font.family.mono, fontSize: 13, fontWeight: font.weight.medium,
          color: cartQty > 0 ? t.accent : t.accentInk,
          boxShadow: 'var(--e-2)',
          transition: 'background var(--t-fast)',
        }}
      >
        {cartQty > 0 ? cartQty : <Icon name="plus" size={17} strokeWidth={2.25} />}
      </button>
    )
  }

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{
        position: 'relative',
        background: `linear-gradient(165deg, ${alpha(c, 0.22)} 0%, ${alpha(c, 0.06)} 50%, ${t.bg} 100%)`,
        padding: 'calc(env(safe-area-inset-top, 0px) + 16px) 16px 18px',
        overflow: 'hidden',
      }}>
        {/* The category glyph as a specimen drawing, bled off the right edge */}
        <CategoryIcon
          category={category}
          size={168}
          strokeWidth={0.75}
          style={{ position: 'absolute', right: -26, top: -18, opacity: 0.2, pointerEvents: 'none' }}
        />

        <BackButton onClick={goBack} glass />

        <div style={{ position: 'relative', marginTop: 18 }}>
          <PageTitle size={34}>{categoryLabel(category)}</PageTitle>

          {dispensaryName && (
            <div style={{
              color: t.text2, fontSize: font.size.small + 1, marginTop: 4,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {dispensaryName}
            </div>
          )}

          {!loading && !error && all.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 9, flexWrap: 'wrap' }}>
              <Stat value={all.length} label={all.length === 1 ? 'product' : 'products'} color={c} />
              <Dot />
              <Stat value={brandCount} label={brandCount === 1 ? 'brand' : 'brands'} color={c} />
            </div>
          )}
        </div>

        <div style={{ position: 'relative', marginTop: 16 }}>
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder={`Search ${categoryLabel(category).toLowerCase()}…`}
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
        quickRail={
          /* Aisle switcher — jump to another category in the same dispensary */
          <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '10px 14px 10px' }}>
            {(carried ?? [category]).map(cat => (
              <FacetChip
                key={cat}
                label={categoryLabel(cat)}
                icon={<CategoryIcon category={cat} size={15} color={category === cat ? undefined : t.text3} />}
                capitalize={false}
                active={category === cat}
                color={categoryColor(cat)}
                // Replace: switching aisles is a filter, not a step Back should retrace.
                onClick={() => navigate(`/portal/map/${dispensaryId}/aisle/${encodeURIComponent(cat)}`, { replace: true })}
              />
            ))}
          </div>
        }
        activeChips={<>
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
        <FeedState kind="error" message={error} onRetry={() => setAttempt(n => n + 1)} />
      ) : all.length === 0 ? (
        <FeedState
          kind="empty"
          message={`No ${categoryLabel(category).toLowerCase()} in stock`}
          hint="Check back soon — menus update regularly."
          icon={<CategoryIcon category={category} size={22} />}
        />
      ) : (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, padding: '14px 16px 4px',
          }}>
            <span style={{ color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium }}>
              {sorted.length} {sorted.length === 1 ? 'product' : 'products'}
              {sorted.length !== all.length && <span style={{ color: t.text4 }}> of {all.length}</span>}
            </span>
          </div>

          {sorted.length === 0 ? (
            <FeedState
              kind="empty"
              message="No matches"
              hint={search
                ? `Nothing matches “${search}” with these filters.`
                : 'Try removing a filter or widening the price range.'}
              icon="search"
              style={{ minHeight: 240 }}
            />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '10px 12px 96px' }}>
              {sorted.map(l => (
                <BrowseCard
                  key={l.id}
                  item={toCard(l)}
                  color={c}
                  suppressSubtype={category}
                  action={cartAction(l)}
                  // One store, so there is nothing to say about where else to
                  // buy -- but plenty to say about whether this is the price to
                  // pay. Same line as the store page this aisle opened from.
                  footer={<MarketNote market={l.market} priceCents={l.price_cents} />}
                  onOpen={() => navigate(`/portal/map/${dispensaryId}/listings/${l.id}`)}
                />
              ))}
            </div>
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
