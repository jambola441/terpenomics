/* ============================================================================
   ShopHeader — the top of the Shop tab: one way into search, and a switch
   between browsing by category and by brand.

   Shop, Brands and Search used to be three tabs doing one job (find a
   product). They are one tab now, and this is what ties them together.
   ========================================================================== */

import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { t, radius, font } from '../theme'
import { PageTitle } from './ui'
import { Icon } from './Icon'

export default function ShopHeader({ active, sub }: {
  active: 'categories' | 'brands'
  sub?: ReactNode
}) {
  const navigate = useNavigate()
  const views = [
    { key: 'categories', label: 'Categories', to: '/portal/categories' },
    { key: 'brands', label: 'Brands', to: '/portal/brands' },
  ] as const

  return (
    <div style={{ padding: 'calc(env(safe-area-inset-top, 0px) + 26px) 16px 0' }}>
      <PageTitle sub={sub}>Shop</PageTitle>

      {/* Looks like a field, opens Search with the real one focused. */}
      <button
        onClick={() => navigate('/portal/search')}
        style={{
          width: '100%', minHeight: 46, marginTop: 14, boxSizing: 'border-box',
          display: 'flex', alignItems: 'center', gap: 10, padding: '0 14px',
          background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.md,
          color: t.text4, fontSize: font.size.callout, textAlign: 'left', cursor: 'text',
        }}
      >
        <Icon name="search" size={18} color={t.text3} />
        Search products, brands, strains
      </button>

      <div role="tablist" aria-label="Browse by" style={{
        display: 'flex', gap: 2, marginTop: 12, padding: 3,
        background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.md,
      }}>
        {views.map(v => {
          const selected = v.key === active
          return (
            <button
              key={v.key}
              role="tab"
              aria-selected={selected}
              // A switch between two views of one tab, not a step to go Back through.
              onClick={() => { if (!selected) navigate(v.to, { replace: true }) }}
              style={{
                flex: 1, minHeight: 36, cursor: 'pointer', border: 'none',
                background: selected ? t.surface3 : 'transparent',
                boxShadow: selected ? 'var(--e-1)' : 'none', borderRadius: radius.sm,
                color: selected ? t.text1 : t.text3,
                fontSize: font.size.small + 1, fontWeight: selected ? font.weight.semibold : font.weight.medium,
              }}
            >
              {v.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
