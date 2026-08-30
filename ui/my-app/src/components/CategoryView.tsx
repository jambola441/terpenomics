/* ============================================================================
   CategoryView — one category, across every store.

   The filter engine lives in BrowseScreen; this file is the adapter: fetch the
   category, flatten its products into the shape that screen works over, and
   draw the hero. The brand page is the same file with a different fetch.
   ========================================================================== */

import { useEffect, useState } from 'react'
import api from '../api/client'
import type { PortalCategoryDetail } from '../types'
import { t, font, categoryColor, alpha } from '../theme'
import { CATEGORY_EMOJI, Dot, Stat } from './browse'
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

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setData(null)

    api.portal.getCategory(categoryName)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setError('Failed to load this category') })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [categoryName])

  const c = categoryColor(categoryName)
  const emoji = CATEGORY_EMOJI[categoryName] ?? '📦'

  return (
    <BrowseScreen
      items={data ? toItems(data) : []}
      loading={loading}
      error={error}
      color={c}
      // No category facet: every product here is already this category.
      facets={['subtype', 'brand', 'variant']}
      resetKey={categoryName}
      searchPlaceholder={`Search ${categoryName}…`}
      totalCount={data?.product_count ?? 0}
      truncated={data?.truncated}
      suppressSubtype={categoryName}
      emptyMessage={`No ${categoryName} in stock`}
      emptyHint="Check back soon — menus update regularly."
      emptyIcon={emoji}
      onOpen={item => onOpenProduct(item.brand ?? null, item.key)}
      heroBackground={`linear-gradient(160deg, ${alpha(c, 0.30)} 0%, ${alpha(c, 0.08)} 45%, ${t.bg} 100%)`}
      heroDecoration={
        /* Oversized category glyph, bled off the right edge */
        <div aria-hidden style={{
          position: 'absolute', right: -18, top: -14, fontSize: 132, lineHeight: 1,
          opacity: 0.13, transform: 'rotate(-12deg)', pointerEvents: 'none', userSelect: 'none',
        }}>
          {emoji}
        </div>
      }
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
      </>}
    />
  )
}
