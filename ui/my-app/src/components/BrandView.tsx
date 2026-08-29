import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api/client'
import type { PortalBrandDetail, PortalBrandProduct, PortalBrandOffering } from '../types'
import { t, radius, font, alpha, categoryColor } from '../theme'
import { FeedState, Pressable, CategoryTag } from './ui'
import { haversineMi, formatDist, formatDollars } from '../utils/format'
import { readEnum, readOne, useFilterParams, useScrollMemory, writeOne } from '../utils/browseState'

function FilterChip({ label, active, onClick, color }: {
  label: string
  active: boolean
  onClick: () => void
  color?: string
}) {
  const accent = color ?? '#a8e063'
  return (
    <button
      onClick={onClick}
      style={{
        flexShrink: 0,
        cursor: 'pointer',
        whiteSpace: 'nowrap',
        textTransform: 'capitalize',
        fontSize: font.size.small,
        fontWeight: active ? font.weight.bold : font.weight.medium,
        padding: '6px 12px',
        borderRadius: radius.pill,
        background: active ? alpha(accent, 0.14) : t.surface2,
        border: `1px solid ${active ? accent : t.border}`,
        color: active ? accent : t.text3,
        transition: `all var(--t-fast)`,
      }}
    >
      {label}
    </button>
  )
}

interface BrandViewProps {
  brandName: string
  onBack: () => void
  onOpenProduct: (productKey: string) => void
}

const BRAND_SORTS = ['featured', 'nearest', 'price-asc', 'price-desc'] as const
type BrandSort = typeof BRAND_SORTS[number]

type EnrichedProduct = {
  product: PortalBrandProduct
  closest: PortalBrandOffering | null
  closestDist: number | null
  cheapest: PortalBrandOffering | null
  cheapestDist: number | null
}

export default function BrandView({ brandName, onBack, onOpenProduct }: BrandViewProps) {
  const [brand, setBrand] = useState<PortalBrandDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [initialParams] = useSearchParams()
  const [category, setCategory] = useState<string | null>(() => readOne(initialParams, 'category'))
  const [sort, setSort] = useState<BrandSort>(
    () => readEnum(initialParams, 'sort', BRAND_SORTS, 'featured'),
  )
  const scrollRef = useRef<HTMLDivElement>(null)

  useFilterParams({
    category: writeOne(category),
    sort: sort === 'featured' ? [] : [sort],
  })
  useScrollMemory(scrollRef, brand != null)
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)

  // Moving to a different brand clears the controls — its categories are not
  // this one's. Skipped on the mount that follows a Back, where they came from
  // the URL and clearing them would throw away the shopper's place.
  const previousBrand = useRef(brandName)
  useEffect(() => {
    if (previousBrand.current === brandName) return
    previousBrand.current = brandName
    setCategory(null)
    setSort('featured')
    scrollRef.current?.scrollTo({ top: 0 })
  }, [brandName])

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.portal.getBrand(brandName)
      .then(setBrand)
      .catch(() => setError('Failed to load brand'))
      .finally(() => setLoading(false))
  }, [brandName])

  useEffect(() => {
    navigator.geolocation?.getCurrentPosition(pos => {
      setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude })
    })
  }, [])

  // Category facets with product counts, ordered by frequency
  const categoryFacets = useMemo(() => {
    if (!brand) return [] as { name: string; count: number }[]
    const counts = new Map<string, number>()
    for (const p of brand.products) {
      if (p.category) counts.set(p.category, (counts.get(p.category) ?? 0) + 1)
    }
    return [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
  }, [brand])

  // For each product, resolve the closest in-stock offering and the cheapest one
  const enriched = useMemo<EnrichedProduct[]>(() => {
    if (!brand) return []
    return brand.products.map(product => {
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
      const cheapestDist = (userPos && cheapest?.lat != null && cheapest?.lng != null)
        ? haversineMi(userPos.lat, userPos.lng, cheapest.lat, cheapest.lng)
        : null
      return {
        product,
        closest,
        closestDist: closest ? closestDist : null,
        cheapest,
        cheapestDist,
      }
    })
  }, [brand, userPos])

  const visibleProducts = useMemo(() => {
    const filtered = category
      ? enriched.filter(e => e.product.category === category)
      : enriched
    const sorted = [...filtered]
    if (sort === 'price-asc' || sort === 'price-desc') {
      const dir = sort === 'price-asc' ? 1 : -1
      sorted.sort((a, b) => {
        const pa = a.product.min_price_cents
        const pb = b.product.min_price_cents
        if (pa == null) return 1
        if (pb == null) return -1
        return (pa - pb) * dir
      })
    } else if (sort === 'nearest') {
      sorted.sort((a, b) => (a.closestDist ?? Infinity) - (b.closestDist ?? Infinity))
    }
    return sorted
  }, [enriched, category, sort])

  return (
    <div ref={scrollRef} style={{ height: '100dvh', overflowY: 'auto', background: t.bg }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '20px 16px 12px' }}>
        <button
          onClick={onBack}
          aria-label="Back"
          style={{ background: 'none', border: 'none', color: t.accent, fontSize: 26, cursor: 'pointer', padding: 0, lineHeight: 1 }}
        >
          ‹
        </button>
        <div style={{
          width: 56, height: 56, borderRadius: '50%', background: t.surface2, border: `1px solid ${t.border}`,
          overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          {brand?.image_url ? (
            <img src={brand.image_url} alt={brandName} style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: 22 }}>
              {brandName.charAt(0).toUpperCase()}
            </span>
          )}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.heading, letterSpacing: '-0.01em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {brandName}
          </div>
          {brand && (
            <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
              {brand.product_count} product{brand.product_count !== 1 ? 's' : ''} · {brand.dispensary_count} dispensar{brand.dispensary_count !== 1 ? 'ies' : 'y'}
            </div>
          )}
        </div>
      </div>

      {/* Filter / sort toolbar */}
      {brand && brand.products.length > 0 && (
        <div style={{ position: 'sticky', top: 0, zIndex: 5, background: 'rgba(11,11,13,0.86)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', paddingBottom: 4 }}>
          {/* Category chips */}
          {categoryFacets.length > 1 && (
            <div style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '4px 16px 8px', scrollbarWidth: 'none' } as React.CSSProperties}>
              <FilterChip label="All" active={category === null} onClick={() => setCategory(null)} />
              {categoryFacets.map(f => (
                <FilterChip
                  key={f.name}
                  label={`${f.name} ${f.count}`}
                  color={categoryColor(f.name)}
                  active={category === f.name}
                  onClick={() => setCategory(category === f.name ? null : f.name)}
                />
              ))}
            </div>
          )}
          {/* Sort row */}
          <div style={{ display: 'flex', gap: 8, padding: '0 16px 6px', overflowX: 'auto', scrollbarWidth: 'none' } as React.CSSProperties}>
            <FilterChip label="Featured" active={sort === 'featured'} onClick={() => setSort('featured')} />
            {userPos && <FilterChip label="Nearest" active={sort === 'nearest'} onClick={() => setSort('nearest')} />}
            <FilterChip label="Price ↑" active={sort === 'price-asc'} onClick={() => setSort('price-asc')} />
            <FilterChip label="Price ↓" active={sort === 'price-desc'} onClick={() => setSort('price-desc')} />
          </div>
        </div>
      )}

      {loading ? (
        <FeedState kind="loading" message="Loading…" />
      ) : error ? (
        <FeedState kind="error" message={error} />
      ) : !brand || brand.products.length === 0 ? (
        <FeedState kind="empty" message="No products in stock" icon="🌿" />
      ) : visibleProducts.length === 0 ? (
        <FeedState kind="empty" message="No products in this category" icon="🔍" style={{ minHeight: 160 }} />
      ) : (
        <div style={{ padding: '4px 16px 92px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {!userPos && (
            <div style={{ color: t.text3, fontSize: font.size.caption, padding: '0 2px 2px' }}>
              📍 Turn on location to see distances and nearest stores
            </div>
          )}
          {visibleProducts.map((e) => (
            <BrandProductCard key={e.product.key} item={e} hasLocation={!!userPos} onOpen={() => onOpenProduct(e.product.key)} />
          ))}
        </div>
      )}
    </div>
  )
}

// One product row: closest in-stock store + price, plus the lowest price elsewhere
function BrandProductCard({ item, hasLocation, onOpen }: {
  item: EnrichedProduct
  hasLocation: boolean
  onOpen: () => void
}) {
  const { product, closest, closestDist, cheapest, cheapestDist } = item

  // The store we surface first: prefer the closest, else the cheapest
  const primary = closest ?? cheapest
  const otherCount = product.dispensary_count - 1
  // Show the "lowest price" line only when it's a genuinely cheaper, different store
  const showLowest =
    cheapest != null &&
    cheapest.price_cents != null &&
    primary != null &&
    cheapest.listing_id !== primary.listing_id &&
    (primary.price_cents == null || cheapest.price_cents < primary.price_cents)

  return (
    <Pressable
      onClick={onOpen}
      style={{
        background: t.surface1, borderRadius: radius.lg, padding: 14, display: 'flex', gap: 14,
        alignItems: 'center', border: `1px solid ${t.border}`,
      }}
    >
      {/* Thumbnail */}
      <div style={{
        width: 54, height: 54, borderRadius: radius.md, overflow: 'hidden', flexShrink: 0,
        background: t.tile, display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.06)',
      }}>
        {product.image_url
          ? <img src={product.image_url} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 6, boxSizing: 'border-box' }}
              onError={ev => { (ev.target as HTMLImageElement).style.display = 'none' }} />
          : <span style={{ fontSize: 20, opacity: 0.6 }}>🌿</span>}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {product.name}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 5, flexWrap: 'wrap' }}>
          {product.category && <CategoryTag category={product.category} />}
          {product.variant && (
            <span style={{ color: t.text3, fontSize: font.size.caption }}>{product.variant}</span>
          )}
        </div>

        {/* Closest store line */}
        {closest ? (
          <div style={{ color: t.text2, fontSize: font.size.small, marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            <span style={{ color: t.accent }}>📍 {closestDist != null ? formatDist(closestDist) : ''}</span>
            {' · '}{closest.dispensary_name}
          </div>
        ) : primary ? (
          <div style={{ color: t.text2, fontSize: font.size.small, marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {primary.dispensary_name}
          </div>
        ) : null}

        {/* Availability across dispensaries */}
        <div style={{
          color: otherCount > 0 ? t.accent : t.text3,
          fontSize: font.size.caption, marginTop: 3,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {otherCount > 0
            ? `Also at ${otherCount} other dispensar${otherCount === 1 ? 'y' : 'ies'}`
            : 'Only at this dispensary'}
        </div>
      </div>

      {/* Price column */}
      <div style={{ textAlign: 'right', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
        {primary?.price_cents != null && (
          <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.callout }}>{formatDollars(primary.price_cents)}</div>
        )}
        {showLowest && (
          <div style={{ color: t.accent, fontSize: font.size.micro, fontWeight: font.weight.semibold, whiteSpace: 'nowrap' }}>
            Low {formatDollars(cheapest!.price_cents!)}
            {hasLocation && cheapestDist != null ? ` · ${formatDist(cheapestDist)}` : ''}
          </div>
        )}
        {!showLowest && cheapest?.price_cents != null && product.dispensary_count > 1 && (
          <div style={{ color: t.text3, fontSize: font.size.micro }}>best price</div>
        )}
      </div>
    </Pressable>
  )
}
