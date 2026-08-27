/* ============================================================================
   BrandsPage — browse every brand.

   The home feed's brand rail only ever showed the top two dozen by listing
   count, which is fine as a rail and useless as a way to find a specific brand.
   This pages through all of them, searchable, with an A–Z sort for when the
   shopper knows the name and a popularity sort for when they don't.
   ========================================================================== */

import { useEffect, useRef, useState } from 'react'
import api from '../api/client'
import type { PortalBrand } from '../types'
import { t, radius, font, alpha } from '../theme'
import { FeedState, Pressable, Skeleton } from './ui'
import { SearchField } from './browse'

const PAGE = 48

type Sort = 'listings' | 'name'

interface Props {
  onOpenBrand: (name: string) => void
}

export default function BrandsPage({ onOpenBrand }: Props) {
  const [brands, setBrands] = useState<PortalBrand[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [exhausted, setExhausted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)
  const [sort, setSort] = useState<Sort>('listings')

  // Debounced: the brand list is a grouped aggregate, so a request per keystroke
  // is a scan per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setQuery(input.trim()), 250)
    return () => clearTimeout(id)
  }, [input])

  useEffect(() => {
    let live = true
    setLoading(true)
    setExhausted(false)
    api.portal.getBrands({ q: query || undefined, sort, limit: PAGE })
      .then(rows => {
        if (!live) return
        setBrands(rows)
        setExhausted(rows.length < PAGE)
      })
      .catch(() => { if (live) setError('Could not load brands.') })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [query, sort])

  function loadMore() {
    if (loadingMore || exhausted || loading) return
    setLoadingMore(true)
    api.portal.getBrands({ q: query || undefined, sort, limit: PAGE, offset: brands.length })
      .then(rows => {
        setBrands(prev => [...prev, ...rows])
        if (rows.length < PAGE) setExhausted(true)
      })
      .catch(() => setExhausted(true))
      .finally(() => setLoadingMore(false))
  }

  // Load the next page when the sentinel scrolls into view. The observer is
  // built once and reads the current loadMore through a ref, so a re-render mid
  // scroll does not tear down and re-arm it.
  const sentinel = useRef<HTMLDivElement>(null)
  const loadMoreRef = useRef(loadMore)
  loadMoreRef.current = loadMore
  useEffect(() => {
    const node = sentinel.current
    if (!node) return
    const observer = new IntersectionObserver(entries => {
      if (entries[0]?.isIntersecting) loadMoreRef.current()
    }, { rootMargin: '400px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [loading])

  if (error) {
    return (
      <div style={{ height: '100dvh', background: t.bg }}>
        <FeedState kind="error" message={error} style={{ height: '100%' }} />
      </div>
    )
  }

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: '22px 16px 6px' }}>
        <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero, letterSpacing: '-0.02em' }}>
          Brands
        </div>
        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
          Every brand stocked across the stores we track
        </div>
      </div>

      <div style={{ padding: '12px 16px 0' }}>
        <SearchField
          value={input}
          onChange={setInput}
          placeholder="Search brands"
          focused={focused}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
        />
      </div>

      <div style={{ display: 'flex', gap: 8, padding: '12px 16px 4px' }}>
        <SortChip label="Most stocked" active={sort === 'listings'} onClick={() => setSort('listings')} />
        <SortChip label="A–Z" active={sort === 'name'} onClick={() => setSort('name')} />
      </div>

      {loading ? (
        <BrandGridSkeleton />
      ) : brands.length === 0 ? (
        <FeedState
          kind="empty"
          message={query ? `No brands matching "${query}"` : 'No brands yet'}
          hint={query ? 'Try a shorter search.' : undefined}
          icon="🏷️"
          style={{ padding: '48px 16px' }}
        />
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(104px, 1fr))',
            gap: 12,
            padding: '14px 16px 0',
          }}>
            {brands.map(brand => (
              <Pressable
                key={brand.name}
                onClick={() => onOpenBrand(brand.name)}
                lift
                style={{
                  background: t.surface1, border: `1px solid ${t.border}`,
                  borderRadius: radius.lg, padding: '14px 10px 12px',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 9,
                }}
              >
                <div style={{
                  width: 62, height: 62, borderRadius: '50%', overflow: 'hidden', flexShrink: 0,
                  background: t.surface2, border: `1px solid ${t.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {brand.image_url ? (
                    <img
                      src={brand.image_url}
                      alt={brand.name}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  ) : (
                    <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: 22 }}>
                      {brand.name.charAt(0).toUpperCase()}
                    </span>
                  )}
                </div>
                <div style={{
                  color: t.text1, fontSize: font.size.caption + 1, fontWeight: font.weight.semibold,
                  textAlign: 'center', lineHeight: 1.25, width: '100%',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {brand.name}
                </div>
                <div style={{ color: t.text3, fontSize: font.size.caption }}>
                  {brand.listing_count.toLocaleString()}
                </div>
              </Pressable>
            ))}
          </div>

          <div ref={sentinel} style={{ height: 1 }} />
          <div style={{ padding: '18px 16px 28px', textAlign: 'center', color: t.text3, fontSize: font.size.small }}>
            {loadingMore ? 'Loading more…' : exhausted ? `${brands.length.toLocaleString()} brands` : ''}
          </div>
        </>
      )}
    </div>
  )
}

function SortChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        cursor: 'pointer', whiteSpace: 'nowrap',
        fontSize: font.size.small, fontWeight: active ? font.weight.bold : font.weight.medium,
        padding: '7px 13px', borderRadius: radius.pill,
        background: active ? alpha(t.accent, 0.14) : t.surface2,
        border: `1px solid ${active ? t.accent : t.border}`,
        color: active ? t.accent : t.text3,
        transition: 'all var(--t-fast)',
      }}
    >
      {label}
    </button>
  )
}

function BrandGridSkeleton() {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(104px, 1fr))',
      gap: 12,
      padding: '14px 16px',
    }}>
      {Array.from({ length: 12 }, (_, i) => (
        <div key={i} style={{
          background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg,
          padding: '14px 10px 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 9,
        }}>
          <Skeleton width={62} height={62} radius="50%" />
          <Skeleton width="80%" height={11} />
          <Skeleton width={26} height={9} />
        </div>
      ))}
    </div>
  )
}
