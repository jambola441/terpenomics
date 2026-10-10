import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import type { PortalProductDetail, PortalBrandProduct, ListingDetail } from '../types'
import { t, radius, font, categoryLabel } from '../theme'
import { useFlag } from '../hooks/useFlag'
import { LINE_MIN_PRODUCTS, nameWithinLine } from './BrowseScreen'
import {
  Pressable, CategoryTag, ClassificationTag, DetailBlock, CollapsibleBlock, SpecRow,
  BackButton, FeedState, ProductImage, TerpeneProfile, Label,
} from './ui'
import { Icon } from './Icon'
import { haversineMi, formatDist, formatDollars } from '../utils/format'

interface ProductViewProps {
  /** The brand that scopes the key, or null for an unbranded product. */
  brandName: string | null
  productKey: string
  onBack: () => void
  onListingClick: (dispensaryId: string, listingId: string) => void
  /** The brand page, optionally already narrowed to a category or a line. */
  onOpenBrand: (brand: string, filter?: { category?: string; line?: string }) => void
  onOpenProduct: (brand: string, productKey: string) => void
}

export default function ProductView({
  brandName, productKey, onBack, onListingClick, onOpenBrand, onOpenProduct,
}: ProductViewProps) {
  const [product, setProduct] = useState<PortalProductDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [detail, setDetail] = useState<ListingDetail | null>(null)

  // One product, not the whole brand: this page used to download every product
  // a brand makes just to pick one out of it, and had nothing at all to fetch
  // for a product with no brand.
  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    setLoading(true)
    setError(null)
    api.portal.getProductDetail(productKey, brandName)
      .then(setProduct)
      .catch(() => setError('Failed to load product'))
      .finally(() => setLoading(false))
  }, [brandName, productKey, attempt])

  useEffect(() => {
    navigator.geolocation?.getCurrentPosition(pos => {
      setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude })
    })
  }, [])

  // The rest of this product's line, for the breadcrumb and the More in this
  // line row (flag `lines`). Its own small request rather than the whole brand.
  const linesOn = useFlag('lines')
  const lineBrand = product?.brand ?? null
  const lineName = product?.product_line ?? null
  const [lineProducts, setLineProducts] = useState<PortalBrandProduct[] | null>(null)
  useEffect(() => {
    setLineProducts(null)
    if (!linesOn || !lineBrand || !lineName) return
    let cancelled = false
    api.portal.getBrandLine(lineBrand, lineName)
      .then(l => { if (!cancelled) setLineProducts(l.products) })
      .catch(() => { /* the row and the line crumb are extras */ })
    return () => { cancelled = true }
  }, [linesOn, lineBrand, lineName])
  // A "line" of one or two products is often a flavour or effect name: no
  // crumb and no row for those, the same bar the brand page's filter uses.
  const lineIsReal = lineProducts != null && lineProducts.length >= LINE_MIN_PRODUCTS
  const moreInLine = lineIsReal
    ? lineProducts.filter(p => p.key !== productKey)
      .sort((a, b) => b.dispensary_count - a.dispensary_count)
      .slice(0, 12)
    : []

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
      // Somewhere you can buy it today comes before somewhere you can't.
      if (a.offering.in_stock !== b.offering.in_stock) return a.offering.in_stock ? -1 : 1
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

  // Lowest and average among stores that have it in stock: a price you can't
  // pay isn't the lowest price. Everything, if nobody has it right now.
  const stocked = (product?.offerings ?? []).filter(o => o.in_stock)
  const priced = stocked.length ? stocked : (product?.offerings ?? [])
  const prices = priced.map(o => o.price_cents).filter((p): p is number => p != null)
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '18px 16px 8px' }}>
        <BackButton onClick={onBack} />
        {/* The header draws before the fetch resolves, and an unbranded product
            never gets a brand line at all. */}
        {product?.brand && (linesOn ? (
          <nav aria-label="Breadcrumb" style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flexWrap: 'wrap' }}>
            <Crumb label={product.brand} onClick={() => onOpenBrand(product.brand!)} />
            {product.category && <>
              <CrumbSeparator />
              <Crumb
                label={categoryLabel(product.category)}
                onClick={() => onOpenBrand(product.brand!, { category: product.category! })}
              />
            </>}
            {lineIsReal && lineName && <>
              <CrumbSeparator />
              <Crumb label={lineName} current onClick={() => onOpenBrand(product.brand!, { line: lineName })} />
            </>}
          </nav>
        ) : (
          <div style={{ color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium }}>{product.brand}</div>
        ))}
      </div>

      {loading ? (
        <FeedState kind="loading" message="Loading…" />
      ) : error ? (
        <FeedState kind="error" message={error} onRetry={() => setAttempt(n => n + 1)} />
      ) : !product ? (
        <FeedState kind="empty" message="Product not found" icon="package" />
      ) : (
        <>
          {/* Product hero */}
          <div style={{ display: 'flex', gap: 16, padding: '8px 16px 16px', alignItems: 'center' }}>
            <ProductImage
              src={product.image_url}
              alt={product.name}
              category={product.category}
              height={96}
              pad={8}
              style={{ width: 96, flexShrink: 0 }}
            />
            <div style={{ minWidth: 0, flex: 1 }}>
              <h1 style={{
                color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold,
                fontSize: font.size.display, lineHeight: 1.15, letterSpacing: '-0.02em', margin: 0,
              }}>
                {product.name}
              </h1>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                {product.category && <CategoryTag category={product.category} />}
                {classification && <ClassificationTag classification={classification} />}
                {product.variant && <span style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.caption }}>{product.variant}</span>}
              </div>
              {minPrice != null && (
                <div className="num" style={{ color: t.text2, fontSize: font.size.small + 1, marginTop: 8 }}>
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
                    <div className="num" style={{ color: cell.accent ? t.success : t.text1, fontWeight: font.weight.bold, fontSize: font.size.title }}>{cell.value}</div>
                    <div style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.micro + 0.5, marginTop: 3, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{cell.label}</div>
                  </div>
                ))}
              </div>
              {savings > 0 && (
                <div style={{ color: t.success, fontSize: font.size.small, fontWeight: font.weight.medium, marginTop: 10, textAlign: 'center' }}>
                  Save up to {formatDollars(savings)} by choosing the lowest-priced store
                </div>
              )}
            </div>
          )}

          {/* Where to buy comes first: it is what the page is for. Lab data
              and details follow for anyone weighing it up. */}
          {/* Availability heading */}
          <div style={{ padding: '8px 16px 4px' }}>
            <Label style={{ marginBottom: 2 }}>Where to buy</Label>
            <div style={{ color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold, fontSize: font.size.heading, letterSpacing: '-0.015em' }}>
              {product.dispensary_count === 1
                ? 'Available at 1 dispensary'
                : `Available at ${product.dispensary_count} dispensaries`}
            </div>
          </div>
          {!userPos && (
            <div style={{ color: t.text3, fontSize: font.size.caption, padding: '2px 16px 6px', display: 'flex', alignItems: 'center', gap: 5 }}>
              <Icon name="locate" size={13} /> Turn on location to sort by distance
            </div>
          )}

          {/* Dispensary list */}
          <div style={{ padding: '4px 16px 22px', display: 'flex', flexDirection: 'column', gap: 10 }}>
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
                    <div style={{ color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.callout, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {o.dispensary_name}
                    </div>
                    <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
                      {dist != null && <><Icon name="pin" size={12} /><span className="num">{formatDist(dist)}</span><span aria-hidden>·</span></>}
                      <span style={{ color: o.in_stock ? t.success : t.warning }}>{o.in_stock ? 'In stock' : 'Out of stock'}</span>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
                    {o.price_cents != null && (
                      <div className="num" style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout }}>{formatDollars(o.price_cents)}</div>
                    )}
                    {isCheapest && (
                      <div style={{ color: t.success, fontFamily: font.family.mono, fontSize: font.size.micro + 0.5, textTransform: 'uppercase', letterSpacing: '0.06em' }}>lowest</div>
                    )}
                  </div>
                  <Icon name="chevron-right" size={18} color={t.text3} />
                </Pressable>
              )
            })}
          </div>

          {/* The rest of the line, for "what else is in it?" */}
          {moreInLine.length > 0 && lineBrand && lineName && (
            <div style={{ padding: '0 0 22px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, padding: '0 16px 10px' }}>
                <Label style={{ marginBottom: 0 }}>More in {lineName}</Label>
                <button
                  onClick={() => onOpenBrand(lineBrand, { line: lineName })}
                  style={{
                    border: 'none', background: 'none', padding: '6px 0', cursor: 'pointer',
                    color: t.text2, fontSize: font.size.small, display: 'inline-flex', alignItems: 'center', gap: 2,
                  }}
                >
                  All {lineProducts!.length} <Icon name="chevron-right" size={14} />
                </button>
              </div>
              <div className="no-scrollbar" style={{ display: 'flex', gap: 12, overflowX: 'auto', padding: '0 16px' }}>
                {moreInLine.map(p => (
                  <Pressable
                    key={p.key}
                    onClick={() => onOpenProduct(lineBrand, p.key)}
                    style={{ width: 128, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 6 }}
                  >
                    <ProductImage src={p.image_url} alt={p.name} category={p.category} height={112} pad={8} />
                    {p.min_price_cents != null && (
                      <div className="num" style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout }}>
                        {formatDollars(p.min_price_cents)}
                      </div>
                    )}
                    <div style={{ color: t.text1, fontSize: font.size.small + 1, lineHeight: 1.25 }}>
                      {nameWithinLine(p.name, lineName)}
                    </div>
                    <div className="num" style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.micro + 0.5, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      {[p.variant, `${p.dispensary_count} ${p.dispensary_count === 1 ? 'store' : 'stores'}`].filter(Boolean).join(' · ')}
                    </div>
                  </Pressable>
                ))}
              </div>
            </div>
          )}

          {/* Cannabinoids */}
          {cannabinoids.length > 0 && (
            <DetailBlock title="Cannabinoids" style={{ padding: '0 16px 18px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(84px, 1fr))', gap: 8 }}>
                {cannabinoids.map((c, i) => (
                  <div key={`${c.name}-${i}`} style={{
                    background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.md,
                    padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 4,
                  }}>
                    <div className="num" style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, letterSpacing: '-0.01em' }}>
                      {c.percent != null ? `${c.percent}%` : '—'}
                    </div>
                    <div style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.caption, letterSpacing: '0.04em' }}>{c.name}</div>
                  </div>
                ))}
              </div>
            </DetailBlock>
          )}

          {/* Terpenes */}
          {terpenes.length > 0 && (
            <DetailBlock title="Terpene profile" style={{ padding: '0 16px 22px' }}>
              <TerpeneProfile terpenes={terpenes} />
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
          <div style={{ height: 28 }} />

        </>
      )}
    </div>
  )
}

/** One step of the breadcrumb. The last one names where the product sits. */
function Crumb({ label, current = false, onClick }: { label: string; current?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        border: 'none', background: 'none', padding: '6px 0', cursor: 'pointer', minWidth: 0,
        color: current ? t.text1 : t.text2,
        fontSize: font.size.small + 1,
        fontWeight: current ? font.weight.semibold : font.weight.medium,
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 160,
      }}
    >
      {label}
    </button>
  )
}

function CrumbSeparator() {
  return <span aria-hidden style={{ color: t.text4, fontSize: font.size.small + 1 }}>›</span>
}
