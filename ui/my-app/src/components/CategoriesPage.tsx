/* ============================================================================
   CategoriesPage — browse the shelf by category.

   Categories are a short, stable list, so this is a plain grid: no paging, no
   search box, no sort control. Everything the endpoint returns fits on screen,
   and adding machinery for a dozen rows would be noise.
   ========================================================================== */

import { useEffect, useState } from 'react'
import api from '../api/client'
import type { PortalCategory } from '../types'
import { t, radius, font, categoryColor, categoryLabel, alpha } from '../theme'
import { FeedState, Pressable, Skeleton } from './ui'
import ShopHeader from './ShopHeader'
import { CategoryIcon } from './Icon'

interface Props {
  onOpenCategory: (name: string) => void
}

export default function CategoriesPage({ onOpenCategory }: Props) {
  const [categories, setCategories] = useState<PortalCategory[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    setError(null)
    api.portal.getCategories()
      .then(setCategories)
      .catch(() => setError('Could not load categories.'))
  }, [attempt])

  if (error) {
    return (
      <div style={{ height: '100dvh', background: t.bg }}>
        <FeedState kind="error" message={error} style={{ height: '100%' }} onRetry={() => setAttempt(n => n + 1)} />
      </div>
    )
  }

  const total = categories?.reduce((sum, c) => sum + c.listing_count, 0) ?? 0

  return (
    <div style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      <ShopHeader
        active="categories"
        sub={categories === null
          ? 'Shop by what you’re after'
          : `${total.toLocaleString()} listings across ${categories.length} categories`}
      />

      {categories === null ? (
        <CategoryGridSkeleton />
      ) : categories.length === 0 ? (
        <FeedState kind="empty" message="No categories yet" icon="package" style={{ padding: '48px 16px' }} />
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
          gap: 12,
          padding: '16px 16px 28px',
        }}>
          {categories.map(category => {
            const color = categoryColor(category.name)
            return (
              <Pressable
                key={category.name}
                onClick={() => onOpenCategory(category.name)}
                lift
                style={{
                  position: 'relative',
                  background: `linear-gradient(155deg, ${alpha(color, 0.14)} 0%, ${alpha(color, 0.04)} 60%), ${t.surface1}`,
                  border: `1px solid ${alpha(color, 0.22)}`,
                  borderRadius: radius.xl,
                  overflow: 'hidden',
                  textAlign: 'left',
                  padding: '16px 14px 14px',
                  minHeight: 132,
                  display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                }}
              >
                {/* The glyph twice: small as the label's icon, large and faint
                    as a specimen drawing bled off the corner. */}
                <CategoryIcon
                  category={category.name}
                  size={92}
                  strokeWidth={1}
                  style={{ position: 'absolute', right: -14, bottom: -12, opacity: 0.16, pointerEvents: 'none' }}
                />
                <span style={{
                  width: 36, height: 36, borderRadius: radius.md,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  background: alpha(color, 0.14), border: `1px solid ${alpha(color, 0.3)}`,
                }}>
                  <CategoryIcon category={category.name} size={20} />
                </span>
                <div style={{ position: 'relative', marginTop: 18 }}>
                  <div style={{
                    color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold,
                    fontSize: font.size.title + 1, letterSpacing: '-0.01em', marginBottom: 2,
                  }}>
                    {categoryLabel(category.name)}
                  </div>
                  <div className="num" style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.caption }}>
                    {category.listing_count.toLocaleString()} listings
                  </div>
                </div>
              </Pressable>
            )
          })}
        </div>
      )}
    </div>
  )
}

function CategoryGridSkeleton() {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
      gap: 12,
      padding: '16px',
    }}>
      {Array.from({ length: 8 }, (_, i) => (
        <Skeleton key={i} height={132} radius={radius.xl} />
      ))}
    </div>
  )
}
