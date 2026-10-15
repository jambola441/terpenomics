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
import BrowseScreen from './BrowseScreen'
import { CATEGORY_FACETS, categoryItems } from '../utils/browseLogic'

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
      items={data ? categoryItems(data) : []}
      loading={loading}
      error={error}
      onRetry={() => setAttempt(n => n + 1)}
      color={c}
      // No category facet: every product here is already this category.
      facets={CATEGORY_FACETS}
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
