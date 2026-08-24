import { useEffect, useMemo, useRef, useState } from 'react'
import api from '../api/client'
import type { PortalBrandOffering, PortalCategoryDetail, PortalCategoryProduct } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { Pressable, FeedState, Skeleton, Label, ProductImage } from './ui'

/* ── Constants ────────────────────────────────────────────────────────────── */

const CATEGORY_EMOJI: Record<string, string> = {
  flower: '🌸', vaporizers: '💨', cart: '💨', edible: '🍬', concentrate: '💎',
  preroll: '🌿', tincture: '🧪', tinctures: '🧪', topical: '🧴', merch: '🛍️', other: '📦',
}

type SortKey = 'featured' | 'nearest' | 'price-asc' | 'price-desc' | 'name'

const SORTS: { key: SortKey; label: string; needsLocation?: boolean }[] = [
  { key: 'featured', label: 'Featured' },
  { key: 'nearest', label: 'Nearest', needsLocation: true },
  { key: 'price-asc', label: 'Price: Low → High' },
  { key: 'price-desc', label: 'Price: High → Low' },
  { key: 'name', label: 'Name A–Z' },
]

/** Radius options in miles. `null` = no distance limit. */
const RADII: { value: number | null; label: string }[] = [
  { value: null, label: 'Any' },
  { value: 2, label: '2 mi' },
  { value: 5, label: '5 mi' },
  { value: 10, label: '10 mi' },
  { value: 25, label: '25 mi' },
]

/* ── Helpers ──────────────────────────────────────────────────────────────── */

function haversineMi(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 3958.8
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function formatDist(mi: number) {
  return mi < 0.1 ? '< 0.1 mi' : `${mi.toFixed(1)} mi`
}

function formatDollars(cents: number) {
  return `$${(cents / 100).toFixed(2)}`
}

/** Whole dollars, for the price slider readout where cents are noise. */
function formatDollarsShort(cents: number) {
  return `$${Math.round(cents / 100)}`
}

/** Parse a variant like "3.5g" / "100mg" / "1 oz" into grams for natural ordering. */
function variantWeight(v: string): number {
  const m = v.match(/([\d.]+)\s*(g|mg|oz)?/i)
  if (!m) return Number.MAX_SAFE_INTEGER
  let n = parseFloat(m[1])
  const unit = (m[2] || 'g').toLowerCase()
  if (unit === 'mg') n /= 1000
  if (unit === 'oz') n *= 28.3495
  return n
}

/* ── Product enrichment ───────────────────────────────────────────────────── */

/** A product plus the location/price facts derived from its offerings. */
type EnrichedProduct = {
  product: PortalCategoryProduct
  closest: PortalBrandOffering | null
  closestDist: number | null
  cheapest: PortalBrandOffering | null
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

/* ── Screen ───────────────────────────────────────────────────────────────── */

interface Props {
  categoryName: string
  onBack: () => void
  /** Open the shared brand-product view for a product that has a brand. */
  onOpenBrandProduct: (brand: string, productKey: string) => void
  /** Fallback for unbranded products: jump straight to a specific listing. */
  onOpenListing: (dispensaryId: string, listingId: string) => void
}

export default function CategoryView({ categoryName, onBack, onOpenBrandProduct, onOpenListing }: Props) {
  const [data, setData] = useState<PortalCategoryDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [locationDenied, setLocationDenied] = useState(false)

  const [search, setSearch] = useState('')
  const [searchFocus, setSearchFocus] = useState(false)
  const [subtype, setSubtype] = useState<Set<string>>(new Set())
  const [brand, setBrand] = useState<Set<string>>(new Set())
  const [variant, setVariant] = useState<Set<string>>(new Set())
  const [radiusMi, setRadiusMi] = useState<number | null>(null)
  const [price, setPrice] = useState<[number, number] | null>(null)
  const [sort, setSort] = useState<SortKey>('featured')
  const [sheet, setSheet] = useState(false)

  const c = categoryColor(categoryName)
  const emoji = CATEGORY_EMOJI[categoryName] ?? '📦'
  const scrollRef = useRef<HTMLDivElement>(null)

  // Load the category, resetting every control when the category changes.
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setData(null)
    setSearch(''); setSubtype(new Set()); setBrand(new Set()); setVariant(new Set())
    setRadiusMi(null); setPrice(null); setSort('featured')
    scrollRef.current?.scrollTo({ top: 0 })

    api.portal.getCategory(categoryName)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setError('Failed to load this category') })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
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
    return data.products.map(product => {
      let closest: PortalBrandOffering | null = null
      let closestDist = Infinity
      let cheapest: PortalBrandOffering | null = null

      for (const o of product.offerings) {
        if (o.price_cents != null && (cheapest == null || o.price_cents < cheapest.price_cents!)) {
          cheapest = o
        }
        if (userPos && o.lat != null && o.lng != null) {
          const d = haversineMi(userPos.lat, userPos.lng, o.lat, o.lng)
          if (d < closestDist) { closestDist = d; closest = o }
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
  const priceBounds = useMemo<[number, number] | null>(() => {
    const prices = enriched
      .map(e => e.product.min_price_cents)
      .filter((p): p is number => p != null)
    if (prices.length < 2) return null
    const lo = Math.min(...prices)
    const hi = Math.max(...prices)
    return hi > lo ? [lo, hi] : null
  }, [enriched])

  const filters: Filters = { search: search.trim().toLowerCase(), subtype, brand, variant, radiusMi, price }

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
    [enriched, search, subtype, brand, variant, radiusMi, price],
  )
  const brandFacet = useMemo(
    () => facetFor('brand').sort((a, b) => b.count - a.count),
    [enriched, search, subtype, brand, variant, radiusMi, price],
  )
  const variantFacet = useMemo(
    () => facetFor('variant').sort((a, b) => variantWeight(a.value) - variantWeight(b.value)),
    [enriched, search, subtype, brand, variant, radiusMi, price],
  )

  const filtered = useMemo(
    () => enriched.filter(e => matches(e, filters)),
    [enriched, search, subtype, brand, variant, radiusMi, price],
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
    const p = e.product
    if (p.brand) {
      // The brand product view keys on category|subtype|product_line|strain|variant.
      const brandKey = [p.category, p.subtype, p.product_line, p.strain, p.variant]
        .map(v => v == null ? '' : String(v)).join('|')
      onOpenBrandProduct(p.brand, brandKey)
      return
    }
    const o = e.closest ?? e.cheapest ?? p.offerings[0]
    if (o) onOpenListing(o.dispensary_id, o.listing_id)
  }

  // Drop a nearest sort / radius filter that location permission can't support.
  useEffect(() => {
    if (hasLocation) return
    if (sort === 'nearest') setSort('featured')
    if (radiusMi != null) setRadiusMi(null)
  }, [hasLocation, sort, radiusMi])

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

        {/* Search */}
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <svg
              width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden
              style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', color: t.text3 }}
            >
              <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" />
            </svg>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              onFocus={() => setSearchFocus(true)}
              onBlur={() => setSearchFocus(false)}
              placeholder={`Search ${categoryName}…`}
              style={{
                width: '100%', background: alpha('#000', 0.32),
                border: `1px solid ${searchFocus ? t.accent : t.border}`,
                boxShadow: searchFocus ? 'var(--ring)' : 'none',
                borderRadius: radius.pill, color: t.text1, fontSize: font.size.body,
                padding: '11px 14px 11px 34px', outline: 'none',
                backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
                transition: 'border-color var(--t-fast), box-shadow var(--t-fast)',
              }}
            />
          </div>
          {search && (
            <button
              onClick={() => setSearch('')}
              aria-label="Clear search"
              style={{
                background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.pill,
                color: t.text3, fontSize: 13, height: 42, padding: '0 14px', flexShrink: 0,
              }}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* ── Sticky controls ──────────────────────────────────────────────── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 10,
        background: 'rgba(11,11,13,0.92)',
        backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
        borderBottom: `1px solid ${t.border}`,
      }}>
        {/* Quick subtype rail — the filter shoppers reach for first */}
        {subtypeFacet.length > 1 && (
          <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '10px 14px 2px' }}>
            <FacetChip
              label="All"
              active={subtype.size === 0}
              color={c}
              onClick={() => setSubtype(new Set())}
            />
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

        {/* Filter / sort bar */}
        <div className="no-scrollbar" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', overflowX: 'auto' }}>
          <button
            onClick={() => setSheet(true)}
            style={{
              flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '8px 14px', borderRadius: radius.pill,
              background: activeCount ? 'var(--accent-tint)' : t.surface2,
              border: `1px solid ${activeCount ? t.accent : t.border}`,
              color: activeCount ? t.accent : t.text2,
              fontSize: font.size.small + 1, fontWeight: font.weight.semibold,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden style={{ flexShrink: 0 }}>
              <path d="M3 5h18v2l-7 7v5l-4 2v-7L3 7z" />
            </svg>
            Filters{activeCount ? ` · ${activeCount}` : ''}
          </button>

          <button
            onClick={() => setSheet(true)}
            style={{
              flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', borderRadius: radius.pill,
              background: t.surface2, border: `1px solid ${t.border}`,
              color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium,
            }}
          >
            {sortLabel} <span style={{ color: t.text3 }}>▾</span>
          </button>

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
          {activeCount > 0 && (
            <button
              onClick={clearAll}
              style={{
                flexShrink: 0, background: 'none', border: 'none', color: t.text3,
                fontSize: font.size.small, whiteSpace: 'nowrap', textDecoration: 'underline',
              }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

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
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '10px 12px 96px' }}>
              {sorted.map(e => (
                <ProductCard
                  key={e.product.key}
                  item={e}
                  categoryName={categoryName}
                  color={c}
                  onOpen={() => openProduct(e)}
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
        hasLocation={hasLocation}
        radiusMi={radiusMi}
        onRadius={setRadiusMi}
        priceBounds={priceBounds}
        price={price}
        onPrice={setPrice}
        subtypeFacet={subtypeFacet}
        brandFacet={brandFacet}
        variantFacet={variantFacet}
        subtypeSel={subtype}
        brandSel={brand}
        variantSel={variant}
        onToggleSubtype={v => toggle(setSubtype, v)}
        onToggleBrand={v => toggle(setBrand, v)}
        onToggleVariant={v => toggle(setVariant, v)}
        onClear={clearAll}
        activeCount={activeCount}
      />
    </div>
  )
}

/* ── Hero stat ────────────────────────────────────────────────────────────── */

function Stat({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <span style={{ color: t.text2, fontSize: font.size.small + 1 }}>
      <span style={{ color, fontWeight: font.weight.bold }}>{value.toLocaleString()}</span> {label}
    </span>
  )
}

function Dot() {
  return <span aria-hidden style={{ color: t.text4, fontSize: font.size.small }}>·</span>
}

/* ── Product card ─────────────────────────────────────────────────────────── */

function ProductCard({ item, categoryName, color, onOpen }: {
  item: EnrichedProduct
  categoryName: string
  color: string
  onOpen: () => void
}) {
  const { product, closest, closestDist, cheapest } = item
  const price = product.min_price_cents
  const multiPriced = price != null && product.max_price_cents != null && product.max_price_cents > price
  const store = closest ?? cheapest ?? product.offerings[0] ?? null
  const showSubtype = product.subtype && product.subtype.toLowerCase() !== categoryName.toLowerCase()

  return (
    <Pressable
      onClick={onOpen}
      lift
      style={{
        background: t.surface1, borderRadius: radius.lg, border: `1px solid ${t.border}`,
        overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}
    >
      <div style={{ position: 'relative' }}>
        <ProductImage src={product.image_url} alt={product.name} category={product.category} radius="0" pad={12} />

        {product.variant && (
          <span style={{
            position: 'absolute', top: 8, left: 8,
            background: alpha('#000', 0.62), color: '#fff',
            backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
            fontSize: font.size.micro, fontWeight: font.weight.bold,
            padding: '3px 8px', borderRadius: radius.pill,
          }}>
            {product.variant}
          </span>
        )}

        {closestDist != null && (
          <span style={{
            position: 'absolute', top: 8, right: 8,
            background: alpha('#000', 0.62), color: t.accent,
            backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
            fontSize: font.size.micro, fontWeight: font.weight.bold,
            padding: '3px 8px', borderRadius: radius.pill,
          }}>
            {formatDist(closestDist)}
          </span>
        )}
      </div>

      <div style={{ padding: '10px 11px 12px', flex: 1, display: 'flex', flexDirection: 'column' }}>
        {price != null ? (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 4 }}>
            {multiPriced && (
              <span style={{ color: t.text4, fontSize: font.size.micro, fontWeight: font.weight.semibold }}>from</span>
            )}
            <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: font.size.callout }}>
              {formatDollars(price)}
            </span>
          </div>
        ) : (
          <div style={{ color: t.text4, fontSize: font.size.caption, marginBottom: 4 }}>Price not listed</div>
        )}

        <div style={{
          color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small + 1, lineHeight: 1.3,
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        } as React.CSSProperties}>
          {product.name}
        </div>

        {product.brand && (
          <div style={{
            color: t.text3, fontSize: font.size.caption, marginTop: 3,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {product.brand}
          </div>
        )}

        {showSubtype && (
          <div style={{ marginTop: 8 }}>
            <span style={{
              background: alpha(color, 0.13), color, border: `1px solid ${alpha(color, 0.3)}`,
              fontSize: font.size.micro, fontWeight: font.weight.bold,
              padding: '2px 8px', borderRadius: radius.pill,
              textTransform: 'capitalize', letterSpacing: '0.03em',
            }}>
              {product.subtype}
            </span>
          </div>
        )}

        {/* Availability footer, pinned to the bottom so cards align in the grid */}
        <div style={{
          marginTop: 'auto', paddingTop: 8, color: t.text3, fontSize: font.size.micro,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {product.dispensary_count > 1
            ? `📍 At ${product.dispensary_count} dispensaries`
            : store
              ? store.dispensary_name
              : '—'}
        </div>
      </div>
    </Pressable>
  )
}

/* ── Chips ────────────────────────────────────────────────────────────────── */

function ActiveChip({ label, onRemove, capitalize = true }: {
  label: string
  onRemove: () => void
  /** Off for labels that carry their own casing — "Within 10 mi", "$20–$60". */
  capitalize?: boolean
}) {
  return (
    <span style={{
      flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 5,
      background: 'var(--accent-tint)', border: `1px solid ${alpha('#a8e063', 0.4)}`, color: t.accent,
      fontSize: font.size.small, fontWeight: font.weight.semibold,
      padding: '5px 6px 5px 11px', borderRadius: radius.pill,
      whiteSpace: 'nowrap', maxWidth: 170, textTransform: capitalize ? 'capitalize' : 'none',
    }}>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      <button
        onClick={onRemove}
        aria-label={`Remove ${label}`}
        style={{ background: 'none', border: 'none', color: t.accent, fontSize: 14, lineHeight: 1, padding: '0 2px', flexShrink: 0 }}
      >
        ✕
      </button>
    </span>
  )
}

function FacetChip({ label, count, active, color, onClick, disabled = false, capitalize = true }: {
  label: string
  count?: number
  active: boolean
  color: string
  onClick: () => void
  disabled?: boolean
  /** Off for labels that carry their own casing — units, sizes, sort phrases. */
  capitalize?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        flexShrink: 0, whiteSpace: 'nowrap', textTransform: capitalize ? 'capitalize' : 'none',
        fontSize: font.size.small + 1, fontWeight: active ? font.weight.bold : font.weight.medium,
        padding: '8px 13px', borderRadius: radius.pill,
        background: active ? alpha(color, 0.16) : t.surface2,
        border: `1px solid ${active ? color : t.border}`,
        color: disabled ? t.text4 : active ? color : t.text2,
        opacity: disabled ? 0.5 : 1,
        display: 'inline-flex', alignItems: 'center', gap: 6,
        transition: 'all var(--t-fast)',
      }}
    >
      {label}
      {count != null && (
        <span style={{ color: active ? color : t.text4, fontWeight: font.weight.semibold, fontSize: font.size.caption }}>
          {count}
        </span>
      )}
    </button>
  )
}

/* ── Price range slider ───────────────────────────────────────────────────── */

function PriceRange({ bounds, value, onChange, color }: {
  bounds: [number, number]
  value: [number, number] | null
  onChange: (v: [number, number] | null) => void
  color: string
}) {
  const [min, max] = bounds
  // Step in whole dollars, scaled so the slider stays usable over a wide span.
  const step = Math.max(100, Math.round((max - min) / 100 / 100) * 100)
  const [lo, hi] = value ?? bounds
  const pct = (v: number) => ((v - min) / (max - min)) * 100

  function set(next: [number, number]) {
    const clamped: [number, number] = [Math.max(min, next[0]), Math.min(max, next[1])]
    if (clamped[0] <= min && clamped[1] >= max) onChange(null)
    else onChange(clamped)
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
        <Label>Price</Label>
        <span style={{ color: value ? color : t.text3, fontSize: font.size.small + 1, fontWeight: font.weight.semibold }}>
          {formatDollarsShort(lo)} – {formatDollarsShort(hi)}{hi >= max ? '+' : ''}
        </span>
      </div>

      <div className="range-dual" style={{ margin: '0 12px' }}>
        {/* Track */}
        <div style={{
          position: 'absolute', left: 0, right: 0, top: '50%', height: 4, marginTop: -2,
          background: t.surface3, borderRadius: 2,
        }} />
        {/* Selected span */}
        <div style={{
          position: 'absolute', top: '50%', height: 4, marginTop: -2,
          left: `${pct(lo)}%`, right: `${100 - pct(hi)}%`,
          background: color, borderRadius: 2,
        }} />
        <input
          type="range"
          aria-label="Minimum price"
          min={min} max={max} step={step} value={lo}
          onChange={e => set([Math.min(Number(e.target.value), hi - step), hi])}
        />
        <input
          type="range"
          aria-label="Maximum price"
          min={min} max={max} step={step} value={hi}
          onChange={e => set([lo, Math.max(Number(e.target.value), lo + step)])}
        />
      </div>
    </div>
  )
}

/* ── Filter & sort sheet ──────────────────────────────────────────────────── */

function FilterSheet({
  open, onClose, resultCount, color, sort, onSort, hasLocation, radiusMi, onRadius,
  priceBounds, price, onPrice, subtypeFacet, brandFacet, variantFacet,
  subtypeSel, brandSel, variantSel, onToggleSubtype, onToggleBrand, onToggleVariant,
  onClear, activeCount,
}: {
  open: boolean
  onClose: () => void
  resultCount: number
  color: string
  sort: SortKey
  onSort: (s: SortKey) => void
  hasLocation: boolean
  radiusMi: number | null
  onRadius: (r: number | null) => void
  priceBounds: [number, number] | null
  price: [number, number] | null
  onPrice: (p: [number, number] | null) => void
  subtypeFacet: { value: string; count: number }[]
  brandFacet: { value: string; count: number }[]
  variantFacet: { value: string; count: number }[]
  subtypeSel: Set<string>
  brandSel: Set<string>
  variantSel: Set<string>
  onToggleSubtype: (v: string) => void
  onToggleBrand: (v: string) => void
  onToggleVariant: (v: string) => void
  onClear: () => void
  activeCount: number
}) {
  // Close on Escape while the sheet is up.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      {open && (
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, background: alpha('#000', 0.6), zIndex: 2200, backdropFilter: 'blur(2px)' }}
        />
      )}

      <div
        role="dialog"
        aria-label="Filter and sort"
        aria-hidden={!open}
        style={{
          position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 2300,
          background: t.surface1, borderTop: `1px solid ${t.border}`,
          borderRadius: `${radius['2xl']} ${radius['2xl']} 0 0`, boxShadow: 'var(--e-3)',
          transform: open ? 'translateY(0)' : 'translateY(100%)',
          visibility: open ? 'visible' : 'hidden',
          transition: 'transform 0.34s cubic-bezier(0.32,0.72,0,1), visibility 0.34s',
          maxHeight: '86dvh', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: t.surface3 }} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px 4px' }}>
          <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, letterSpacing: '-0.01em' }}>
            Filter &amp; sort
          </div>
          {activeCount > 0 && (
            <button onClick={onClear} style={{ background: 'none', border: 'none', color: t.text3, fontSize: font.size.small + 1 }}>
              Clear all
            </button>
          )}
        </div>

        <div style={{ overflowY: 'auto', padding: '14px 20px 8px', display: 'flex', flexDirection: 'column', gap: 22 }}>
          {/* Sort */}
          <div>
            <Label style={{ marginBottom: 10 }}>Sort</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {SORTS.map(s => (
                <FacetChip
                  key={s.key}
                  label={s.label}
                  active={sort === s.key}
                  color="var(--accent)"
                  disabled={!!s.needsLocation && !hasLocation}
                  onClick={() => onSort(s.key)}
                />
              ))}
            </div>
          </div>

          {/* Distance */}
          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
              <Label>Distance</Label>
              {!hasLocation && (
                <span style={{ color: t.text4, fontSize: font.size.caption }}>Location off</span>
              )}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {RADII.map(r => (
                <FacetChip
                  key={r.label}
                  label={r.label}
                  active={radiusMi === r.value}
                  color="var(--accent)"
                  disabled={!hasLocation}
                  capitalize={false}
                  onClick={() => onRadius(r.value)}
                />
              ))}
            </div>
          </div>

          {/* Price */}
          {priceBounds && (
            <PriceRange bounds={priceBounds} value={price} onChange={onPrice} color="var(--accent)" />
          )}

          {subtypeFacet.length > 1 && (
            <FacetGroup title="Subtype" facet={subtypeFacet} sel={subtypeSel} color={color} onToggle={onToggleSubtype} />
          )}
          {variantFacet.length > 1 && (
            <FacetGroup title="Weight / Size" facet={variantFacet} sel={variantSel} color={color} onToggle={onToggleVariant} capitalize={false} />
          )}
          {brandFacet.length > 1 && (
            <FacetGroup title="Brand" facet={brandFacet} sel={brandSel} color={color} onToggle={onToggleBrand} />
          )}
        </div>

        <div style={{ padding: '12px 20px', borderTop: `1px solid ${t.border}` }}>
          <button
            onClick={onClose}
            style={{
              width: '100%', background: t.accent, border: 'none', borderRadius: radius.lg,
              color: 'var(--accent-ink)', fontWeight: font.weight.bold, fontSize: font.size.callout,
              padding: 14, boxShadow: 'var(--e-1)',
            }}
          >
            Show {resultCount} {resultCount === 1 ? 'product' : 'products'}
          </button>
        </div>
        <div style={{ height: 'env(safe-area-inset-bottom, 0px)' }} />
      </div>
    </>
  )
}

function FacetGroup({ title, facet, sel, color, onToggle, capitalize = true }: {
  title: string
  facet: { value: string; count: number }[]
  sel: Set<string>
  color: string
  onToggle: (v: string) => void
  capitalize?: boolean
}) {
  return (
    <div>
      <Label style={{ marginBottom: 10 }}>{title}</Label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {facet.map(f => (
          <FacetChip
            key={f.value}
            label={f.value}
            count={f.count}
            active={sel.has(f.value)}
            color={color}
            capitalize={capitalize}
            onClick={() => onToggle(f.value)}
          />
        ))}
      </div>
    </div>
  )
}

/* ── Skeleton ─────────────────────────────────────────────────────────────── */

function GridSkeleton() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '18px 12px 80px' }}>
      {[0, 1, 2, 3, 4, 5].map(i => (
        <div key={i} style={{ background: t.surface1, borderRadius: radius.lg, border: `1px solid ${t.border}`, overflow: 'hidden' }}>
          <Skeleton height={0} radius="0" style={{ aspectRatio: '1 / 1', height: 'auto' }} />
          <div style={{ padding: '10px 11px 12px' }}>
            <Skeleton width="45%" height={14} style={{ marginBottom: 8 }} />
            <Skeleton width="90%" height={12} style={{ marginBottom: 6 }} />
            <Skeleton width="55%" height={11} />
          </div>
        </div>
      ))}
    </div>
  )
}
