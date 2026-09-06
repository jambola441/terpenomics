import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import type { PortalProductDetail, ListingDetail } from '../types'
import { t, radius, font } from '../theme'
import {
  Pressable, CategoryTag, ClassificationTag, DetailBlock, CollapsibleBlock, SpecRow,
} from './ui'
import { haversineMi, formatDist, formatDollars } from '../utils/format'

interface ProductViewProps {
  /** The brand that scopes the key, or null for an unbranded product. */
  brandName: string | null
  productKey: string
  onBack: () => void
  onListingClick: (dispensaryId: string, listingId: string) => void
}

export default function ProductView({ brandName, productKey, onBack, onListingClick }: ProductViewProps) {
  const [product, setProduct] = useState<PortalProductDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [detail, setDetail] = useState<ListingDetail | null>(null)

  // One product, not the whole brand: this page used to download every product
  // a brand makes just to pick one out of it, and had nothing at all to fetch
  // for a product with no brand.
  useEffect(() => {
    setLoading(true)
    setError(null)
    api.portal.getProductDetail(productKey, brandName)
      .then(setProduct)
      .catch(() => setError('Failed to load product'))
      .finally(() => setLoading(false))
  }, [brandName, productKey])

  useEffect(() => {
    navigator.geolocation?.getCurrentPosition(pos => {
      setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude })
    })
  }, [])

  // Pull richer attributes (description, classification, terpenes, cannabinoids)
  // from a representative listing — the cheapest offering carrying this product.
  useEffect(() => {
    setDetail(null)
    if (!product || product.offerings.length === 0) return
    const rep = [...product.offerings]
      .filter(o => o.price_cents != null)
      .sort((a, b) => (a.price_cents! - b.price_cents!))[0] ?? product.offerings[0]
    let cancelled = false
    api.portal.getListing(rep.dispensary_id, rep.listing_id)
      .then(d => { if (!cancelled) setDetail(d) })
      .catch(() => { /* detail is best-effort */ })
    return () => { cancelled = true }
  }, [product])

  // All dispensaries carrying this product, with distance, sorted by distance (or price)
  const offerings = useMemo(() => {
    if (!product) return []
    const withDist = product.offerings.map(o => ({
      offering: o,
      dist: (userPos && o.lat != null && o.lng != null)
        ? haversineMi(userPos.lat, userPos.lng, o.lat, o.lng)
        : null,
    }))
    withDist.sort((a, b) => {
      if (a.dist != null && b.dist != null) return a.dist - b.dist
      if (a.dist != null) return -1
      if (b.dist != null) return 1
      // no location: cheapest first
      const pa = a.offering.price_cents
      const pb = b.offering.price_cents
      if (pa == null) return 1
      if (pb == null) return -1
      return pa - pb
    })
    return withDist
  }, [product, userPos])

  const prices = (product?.offerings ?? []).map(o => o.price_cents).filter((p): p is number => p != null)
  const minPrice = prices.length ? Math.min(...prices) : null
  const maxPrice = prices.length ? Math.max(...prices) : null
  const avgPrice = prices.length ? Math.round(prices.reduce((s, p) => s + p, 0) / prices.length) : null
  const savings = (minPrice != null && maxPrice != null) ? maxPrice - minPrice : 0

  const classification = detail?.classification ?? null
  const strain = product?.strain ?? detail?.strain ?? null
  const subtype = product?.subtype ?? detail?.subtype ?? null
  const productLine = product?.product_line ?? detail?.product_line ?? null
  const description = detail?.description ?? null
  const cannabinoids = detail?.cannabinoids ?? []
  const terpenes = detail?.terpenes ?? []
  const hasSpecs = !!(strain || subtype || productLine || product?.variant || classification)

  return (
    <div style={{ height: '100dvh', overflowY: 'auto', background: t.bg }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '20px 16px 8px' }}>
        <button
          onClick={onBack}
          style={{ background: 'none', border: 'none', color: t.accent, fontSize: 24, cursor: 'pointer', padding: 0, lineHeight: 1 }}
        >
          ‹
        </button>
        {/* The header draws before the fetch resolves, and an unbranded product
            never gets a brand line at all. */}
        {product?.brand && (
          <div style={{ color: t.text3, fontSize: font.size.small, fontWeight: font.weight.semibold }}>{product.brand}</div>
        )}
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: t.text3, fontSize: 14 }}>Loading…</span>
        </div>
      ) : error ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: t.danger, fontSize: 14 }}>{error}</span>
        </div>
      ) : !product ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: t.text3, fontSize: 14 }}>Product not found</span>
        </div>
      ) : (
        <>
          {/* Product hero */}
          <div style={{ display: 'flex', gap: 16, padding: '8px 16px 16px', alignItems: 'center' }}>
            <div style={{
              width: 88, height: 88, borderRadius: radius.lg, overflow: 'hidden', flexShrink: 0,
              background: t.tile, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {product.image_url
                ? <img src={product.image_url} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 8, boxSizing: 'border-box' }}
                    onError={ev => { (ev.target as HTMLImageElement).style.display = 'none' }} />
                : <span style={{ fontSize: 32, opacity: 0.6 }}>🌿</span>}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.heading, lineHeight: 1.15 }}>
                {product.name}
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 7, flexWrap: 'wrap' }}>
                {product.category && <CategoryTag category={product.category} />}
                {classification && <ClassificationTag classification={classification} />}
                {product.variant && <span style={{ color: t.text3, fontSize: font.size.caption }}>{product.variant}</span>}
              </div>
              {minPrice != null && (
                <div style={{ color: t.text2, fontSize: font.size.small, marginTop: 8 }}>
                  {minPrice === maxPrice
                    ? formatDollars(minPrice)
                    : `${formatDollars(minPrice)} – ${formatDollars(maxPrice!)}`}
                </div>
              )}
            </div>
          </div>

          {/* Price insights */}
          {minPrice != null && (
            <div style={{ padding: '0 16px 18px' }}>
              <div style={{
                display: 'flex', background: t.surface1, border: `1px solid ${t.border}`,
                borderRadius: radius.lg, overflow: 'hidden',
              }}>
                {[
                  { label: 'Lowest', value: formatDollars(minPrice), accent: true },
                  { label: 'Average', value: avgPrice != null ? formatDollars(avgPrice) : '—', accent: false },
                  { label: 'Highest', value: maxPrice != null ? formatDollars(maxPrice) : '—', accent: false },
                ].map((cell, i) => (
                  <div key={cell.label} style={{
                    flex: 1, padding: '12px 8px', textAlign: 'center',
                    borderLeft: i > 0 ? `1px solid ${t.border}` : 'none',
                  }}>
                    <div style={{ color: cell.accent ? t.accent : t.text1, fontWeight: font.weight.heavy, fontSize: font.size.callout }}>{cell.value}</div>
                    <div style={{ color: t.text3, fontSize: font.size.micro, marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{cell.label}</div>
                  </div>
                ))}
              </div>
              {savings > 0 && (
                <div style={{ color: t.accent, fontSize: font.size.caption, fontWeight: font.weight.semibold, marginTop: 8, textAlign: 'center' }}>
                  Save up to {formatDollars(savings)} by choosing the lowest-priced store
                </div>
              )}
            </div>
          )}

          {/* Cannabinoids */}
          {cannabinoids.length > 0 && (
            <DetailBlock title="Cannabinoids" style={{ padding: '0 16px 18px' }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {cannabinoids.map((c, i) => (
                  <div key={`${c.name}-${i}`} style={{
                    background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.md,
                    padding: '8px 12px', minWidth: 64,
                  }}>
                    <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.body }}>
                      {c.percent != null ? `${c.percent}%` : '—'}
                    </div>
                    <div style={{ color: t.text3, fontSize: font.size.micro, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{c.name}</div>
                  </div>
                ))}
              </div>
            </DetailBlock>
          )}

          {/* Terpenes */}
          {terpenes.length > 0 && (
            <DetailBlock title="Terpenes" style={{ padding: '0 16px 18px' }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {terpenes.map((tp, i) => (
                  <span key={`${tp.name}-${i}`} style={{
                    background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.pill,
                    padding: '6px 12px', color: t.text2, fontSize: font.size.small,
                  }}>
                    {tp.name}{tp.percent != null ? ` · ${tp.percent}%` : ''}
                  </span>
                ))}
              </div>
            </DetailBlock>
          )}

          {/* Specs */}
          {hasSpecs && (
            <DetailBlock title="Details" style={{ padding: '0 16px 18px' }}>
              <div>
                {strain && <SpecRow label="Strain" value={strain} />}
                {classification && <SpecRow label="Type" value={classification} />}
                {subtype && <SpecRow label="Form" value={subtype} />}
                {productLine && <SpecRow label="Product line" value={productLine} />}
                {product.variant && <SpecRow label="Size" value={product.variant} />}
              </div>
            </DetailBlock>
          )}

          {/* Description */}
          {description && (
            <CollapsibleBlock title="Product Description" style={{ padding: '0 16px 18px' }}>
              <p style={{ color: t.text2, fontSize: font.size.small, lineHeight: 1.6, margin: 0, whiteSpace: 'pre-wrap' }}>
                {description}
              </p>
            </CollapsibleBlock>
          )}

          {/* Availability heading */}
          <div style={{ color: t.text2, fontWeight: font.weight.bold, fontSize: font.size.callout, padding: '8px 16px 4px' }}>
            {product.dispensary_count === 1
              ? 'Available at 1 dispensary'
              : `Available at ${product.dispensary_count} dispensaries`}
          </div>
          {!userPos && (
            <div style={{ color: t.text3, fontSize: font.size.caption, padding: '0 16px 6px' }}>
              📍 Turn on location to sort by distance
            </div>
          )}

          {/* Dispensary list */}
          <div style={{ padding: '4px 16px 92px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {offerings.map(({ offering: o, dist }) => {
              const isCheapest = o.price_cents != null && o.price_cents === minPrice && minPrice !== maxPrice
              return (
                <Pressable
                  key={o.listing_id}
                  onClick={() => onListingClick(o.dispensary_id, o.listing_id)}
                  style={{
                    background: t.surface1, borderRadius: radius.lg, padding: 14, display: 'flex', gap: 12,
                    alignItems: 'center', border: `1px solid ${t.border}`,
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {o.dispensary_name}
                    </div>
                    <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 3 }}>
                      {dist != null ? `📍 ${formatDist(dist)}` : (o.in_stock ? 'In stock' : 'Out of stock')}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
                    {o.price_cents != null && (
                      <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.callout }}>{formatDollars(o.price_cents)}</div>
                    )}
                    {isCheapest && (
                      <div style={{ color: t.accent, fontSize: font.size.micro, fontWeight: font.weight.semibold }}>lowest</div>
                    )}
                  </div>
                  <span style={{ color: t.text4, fontSize: 18, marginLeft: 2 }}>›</span>
                </Pressable>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
