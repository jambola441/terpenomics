/* ============================================================================
   BrandView — one brand, across every store.

   The same screen as the category page, over a different slice of the
   catalogue: it had a row of category chips and a sort row while the category
   page had search, faceted filters with live counts, a distance radius and a
   price range. Both pages ask the same question, so both now run the same
   engine — the only difference is which facets apply. A brand page has no use
   for a brand facet; it gets a category one instead.
   ========================================================================== */

import { useEffect, useState } from 'react'
import api from '../api/client'
import type { PortalBrandDetail } from '../types'
import { t, font, alpha } from '../theme'
import { Dot, Stat } from './browse'
import BrowseScreen, { type BrowseItem } from './BrowseScreen'

/** The brand endpoint inlines each offering's store, and every product is this
 *  brand's — the page's own subject rather than a field on the row. */
function toItems(data: PortalBrandDetail): BrowseItem[] {
  return data.products.map(product => ({
    key: product.key,
    name: product.name,
    brand: data.name,
    category: product.category,
    subtype: product.subtype,
    strain: product.strain,
    variant: product.variant,
    imageUrl: product.image_url,
    minPriceCents: product.min_price_cents,
    // The brand endpoint aggregates to a single price, so a card here never
    // shows a "from" range the way a category card can.
    maxPriceCents: null,
    dispensaryCount: product.dispensary_count,
    offerings: product.offerings.map(offering => ({
      storeName: offering.dispensary_name,
      lat: offering.lat,
      lng: offering.lng,
      priceCents: offering.price_cents,
    })),
  }))
}

interface Props {
  brandName: string
  onBack: () => void
  onOpenProduct: (productKey: string) => void
}

export default function BrandView({ brandName, onBack, onOpenProduct }: Props) {
  const [data, setData] = useState<PortalBrandDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setData(null)

    api.portal.getBrand(brandName)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setError('Failed to load this brand') })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [brandName])

  const c = t.accent

  return (
    <BrowseScreen
      items={data ? toItems(data) : []}
      loading={loading}
      error={error}
      color={c}
      // Category leads, in place of the brand facet the category page has:
      // it is the one thing that varies across a brand's whole range.
      facets={['category', 'subtype', 'variant']}
      resetKey={brandName}
      searchPlaceholder={`Search ${brandName}…`}
      totalCount={data?.product_count ?? 0}
      emptyMessage={`Nothing from ${brandName} in stock`}
      emptyHint="Check back soon — menus update regularly."
      emptyIcon="🏷️"
      onOpen={item => onOpenProduct(item.key)}
      heroBackground={`linear-gradient(160deg, ${alpha('#a8e063', 0.22)} 0%, ${alpha('#a8e063', 0.06)} 45%, ${t.bg} 100%)`}
      hero={<>
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

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 16 }}>
          <div style={{
            width: 58, height: 58, borderRadius: '50%', flexShrink: 0, overflow: 'hidden',
            background: t.surface2, border: `1px solid ${t.border}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {data?.image_url ? (
              <img
                src={data.image_url}
                alt={brandName}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            ) : (
              <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: 24 }}>
                {brandName.charAt(0).toUpperCase()}
              </span>
            )}
          </div>

          <div style={{ minWidth: 0 }}>
            <div style={{
              color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero,
              letterSpacing: '-0.02em', lineHeight: 1.1,
            }}>
              {brandName}
            </div>
            {data && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 7, flexWrap: 'wrap' }}>
                <Stat value={data.product_count} label={data.product_count === 1 ? 'product' : 'products'} color={c} />
                <Dot />
                <Stat
                  value={data.dispensary_count}
                  label={data.dispensary_count === 1 ? 'dispensary' : 'dispensaries'}
                  color={c}
                />
              </div>
            )}
          </div>
        </div>
      </>}
    />
  )
}
