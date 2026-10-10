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
import { t, alpha, raw } from '../theme'
import { Dot, Stat } from './browse'
import { BackButton, BrandMark, PageTitle } from './ui'
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

  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setData(null)

    api.portal.getBrand(brandName)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setError('Failed to load this brand') })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [brandName, attempt])

  const c = t.accent

  return (
    <BrowseScreen
      items={data ? toItems(data) : []}
      loading={loading}
      error={error}
      onRetry={() => setAttempt(n => n + 1)}
      color={c}
      // Category leads, in place of the brand facet the category page has:
      // it is the one thing that varies across a brand's whole range.
      facets={['category', 'subtype', 'variant']}
      resetKey={brandName}
      searchPlaceholder={`Search ${brandName}…`}
      totalCount={data?.product_count ?? 0}
      emptyMessage={`Nothing from ${brandName} in stock`}
      emptyHint="Check back soon — menus update regularly."
      emptyIcon="tag"
      onOpen={item => onOpenProduct(item.key)}
      heroBackground={`linear-gradient(165deg, ${alpha(raw.accent, 0.16)} 0%, ${alpha(raw.accent, 0.04)} 50%, ${t.bg} 100%)`}
      hero={<>
        <BackButton onClick={onBack} glass />

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 18 }}>
          <BrandMark name={brandName} imageUrl={data?.logo_url ?? data?.image_url} size={60} />

          <div style={{ minWidth: 0 }}>
            <PageTitle>{brandName}</PageTitle>
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
