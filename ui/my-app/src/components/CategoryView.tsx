/* ============================================================================
   CategoryView — one category, across every store.

   The filter engine lives in BrowseScreen; this file is the adapter: fetch the
   category, flatten its products into the shape that screen works over, and
   draw the hero. The brand page is the same file with a different fetch.
   ========================================================================== */

import { useEffect, useState } from 'react'
import api from '../api/client'
import type { PortalCategoryDetail } from '../types'
import { t, categoryColor, categoryLabel, alpha } from '../theme'
import { Dot, Stat } from './browse'
import { BackButton, PageTitle } from './ui'
import { CategoryIcon } from './Icon'
import BrowseScreen, { type BrowseItem } from './BrowseScreen'

/** The category endpoint sends its stores once and has offerings index into
 *  that table; BrowseScreen wants each offering to carry its own store. */
function toItems(data: PortalCategoryDetail): BrowseItem[] {
  return data.products.map(product => ({
    key: product.key,
    name: product.name,
    brand: product.brand,
    category: product.category,
    subtype: product.subtype,
    strain: product.strain,
    variant: product.variant,
    imageUrl: product.image_url,
    minPriceCents: product.min_price_cents,
    maxPriceCents: product.max_price_cents,
    dispensaryCount: product.dispensary_count,
    offerings: product.offerings.flatMap(offering => {
      const store = data.dispensaries[offering.dispensary_index]
      if (!store) return []
      return [{
        storeName: store.name,
        lat: store.lat,
        lng: store.lng,
        priceCents: offering.price_cents,
      }]
    }),
  }))
}

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

  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setData(null)

    api.portal.getCategory(categoryName)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setError('Failed to load this category') })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [categoryName, attempt])

  const c = categoryColor(categoryName)

  return (
    <BrowseScreen
      items={data ? toItems(data) : []}
      loading={loading}
      error={error}
      onRetry={() => setAttempt(n => n + 1)}
      color={c}
      // No category facet: every product here is already this category.
      facets={['subtype', 'brand', 'variant']}
      resetKey={categoryName}
      searchPlaceholder={`Search ${categoryLabel(categoryName).toLowerCase()}…`}
      totalCount={data?.product_count ?? 0}
      truncated={data?.truncated}
      suppressSubtype={categoryName}
      emptyMessage={`No ${categoryLabel(categoryName).toLowerCase()} in stock`}
      emptyHint="Check back soon — menus update regularly."
      emptyIcon={<CategoryIcon category={categoryName} size={22} />}
      onOpen={item => onOpenProduct(item.brand ?? null, item.key)}
      heroBackground={`linear-gradient(165deg, ${alpha(c, 0.22)} 0%, ${alpha(c, 0.06)} 50%, ${t.bg} 100%)`}
      heroDecoration={
        /* The category glyph as a specimen drawing, bled off the right edge */
        <CategoryIcon
          category={categoryName}
          size={168}
          strokeWidth={0.75}
          style={{ position: 'absolute', right: -26, top: -18, opacity: 0.2, pointerEvents: 'none' }}
        />
      }
      hero={<>
        <BackButton onClick={onBack} glass />

        <div style={{ position: 'relative', marginTop: 18 }}>
          <PageTitle size={34}>{categoryLabel(categoryName)}</PageTitle>

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
      </>}
    />
  )
}
