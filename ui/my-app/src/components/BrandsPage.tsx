/* ============================================================================
   BrandsPage — browse every brand.

   The home feed's brand rail only ever showed the top two dozen by listing
   count, which is fine as a rail and useless as a way to find a specific brand.
   This pages through all of them, searchable, with an A–Z sort for when the
   shopper knows the name and a popularity sort for when they don't.
   ========================================================================== */

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api/client'
import type { PortalBrand } from '../types'
import { t, radius, font } from '../theme'
import { BrandMark, FeedState, Pressable, Skeleton } from './ui'
import ShopHeader from './ShopHeader'
import { SearchField } from './browse'
import { readEnum, useFilterParams, useScrollMemory, writeOne } from '../utils/browseState'

const PAGE = 48

const SORTS = ['listings', 'name'] as const
type Sort = typeof SORTS[number]

interface Props {
  onOpenBrand: (name: string) => void
}

export default function BrandsPage({ onOpenBrand }: Props) {
  const [brands, setBrands] = useState<PortalBrand[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [exhausted, setExhausted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [initialParams] = useSearchParams()
  const [input, setInput] = useState(() => initialParams.get('q') ?? '')
  const [query, setQuery] = useState(() => initialParams.get('q') ?? '')
  const [focused, setFocused] = useState(false)
  const [sort, setSort] = useState<Sort>(() => readEnum(initialParams, 'sort', SORTS, 'listings'))
  const scrollRef = useRef<HTMLDivElement>(null)

  useFilterParams({
    q: writeOne(input),
    sort: sort === 'listings' ? [] : [sort],
  })
  useScrollMemory(scrollRef, brands.length > 0)

  // Debounced: the brand list is a grouped aggregate, so a request per keystroke
  // is a scan per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setQuery(input.trim()), 250)
    return () => clearTimeout(id)
  }, [input])

  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
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
  }, [query, sort, attempt])

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
        <FeedState kind="error" message={error} style={{ height: '100%' }} onRetry={() => setAttempt(n => n + 1)} />
      </div>
    )
  }

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      <ShopHeader active="brands" sub="Every brand stocked across the stores we track" />

      <div style={{ padding: '12px 16px 0' }}>
        <SearchField
          value={input}
          onChange={setInput}
          placeholder="Filter brands"
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
          icon="tag"
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
                <BrandMark name={brand.name} imageUrl={brand.logo_url ?? brand.image_url} size={64} />
                <div style={{
                  color: t.text1, fontSize: font.size.caption + 1, fontWeight: font.weight.semibold,
                  textAlign: 'center', lineHeight: 1.25, width: '100%',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {brand.name}
                </div>
                <div className="num" style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.micro + 0.5 }}>
                  {brand.listing_count.toLocaleString()} listed
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
        fontSize: font.size.small, fontWeight: active ? font.weight.semibold : font.weight.medium,
        padding: '7px 13px', borderRadius: radius.pill,
        background: active ? t.accentTint : t.surface2,
        border: `1px solid ${active ? t.accentDim : t.border}`,
        color: active ? t.accent : t.text2,
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
          <Skeleton width={64} height={64} radius={radius.lg} />
          <Skeleton width="80%" height={11} />
          <Skeleton width={26} height={9} />
        </div>
      ))}
    </div>
  )
}
