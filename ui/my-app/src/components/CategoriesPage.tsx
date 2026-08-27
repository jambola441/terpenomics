/* ============================================================================
   CategoriesPage — browse the shelf by category.

   Categories are a short, stable list, so this is a plain grid: no paging, no
   search box, no sort control. Everything the endpoint returns fits on screen,
   and adding machinery for a dozen rows would be noise.
   ========================================================================== */

import { useEffect, useState } from 'react'
import api from '../api/client'
import type { PortalCategory } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { FeedState, Pressable, Skeleton } from './ui'
import { CATEGORY_EMOJI } from './browse'

interface Props {
  onOpenCategory: (name: string) => void
}

export default function CategoriesPage({ onOpenCategory }: Props) {
  const [categories, setCategories] = useState<PortalCategory[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.portal.getCategories()
      .then(setCategories)
      .catch(() => setError('Could not load categories.'))
  }, [])

  if (error) {
    return (
      <div style={{ height: '100dvh', background: t.bg }}>
        <FeedState kind="error" message={error} style={{ height: '100%' }} />
      </div>
    )
  }

  const total = categories?.reduce((sum, c) => sum + c.listing_count, 0) ?? 0

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: '22px 16px 6px' }}>
        <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero, letterSpacing: '-0.02em' }}>
          Categories
        </div>
        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
          {categories === null
            ? 'Shop by what you’re after'
            : `${total.toLocaleString()} listings across ${categories.length} categories`}
        </div>
      </div>

      {categories === null ? (
        <CategoryGridSkeleton />
      ) : categories.length === 0 ? (
        <FeedState kind="empty" message="No categories yet" icon="📦" style={{ padding: '48px 16px' }} />
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
          gap: 12,
          padding: '16px 16px 28px',
        }}>
          {categories.map(category => {
            const color = categoryColor(category.name)
            const emoji = CATEGORY_EMOJI[category.name] ?? '📦'
            return (
              <Pressable
                key={category.name}
                onClick={() => onOpenCategory(category.name)}
                lift
                style={{
                  background: alpha(color, 0.10),
                  border: `1px solid ${alpha(color, 0.28)}`,
                  borderRadius: radius.xl,
                  overflow: 'hidden',
                  textAlign: 'left',
                }}
              >
                <div style={{ position: 'relative', height: 96 }}>
                  {category.image_url ? (
                    <img
                      src={category.image_url}
                      alt={category.name}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', opacity: 0.6 }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  ) : (
                    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 42 }}>
                      {emoji}
                    </div>
                  )}
                  <div style={{
                    position: 'absolute', inset: 0,
                    background: `linear-gradient(to bottom, transparent 30%, ${alpha('#000', 0.55)} 100%)`,
                  }} />
                </div>
                <div style={{ padding: '10px 12px 13px' }}>
                  <div style={{
                    color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.small + 1,
                    textTransform: 'capitalize', marginBottom: 3,
                  }}>
                    {category.name}
                  </div>
                  <div style={{ color, fontSize: font.size.caption, fontWeight: font.weight.semibold }}>
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
        <div key={i}>
          <Skeleton height={96} radius={radius.xl} />
          <div style={{ padding: '10px 2px' }}>
            <Skeleton width="60%" height={12} style={{ marginBottom: 7 }} />
            <Skeleton width="40%" height={10} />
          </div>
        </div>
      ))}
    </div>
  )
}
