import { useEffect, useRef, useState } from 'react'
import api from '../api/client'
import type { DispensaryListing } from '../types'

const CATEGORY_COLORS: Record<string, string> = {
  flower: '#4caf50',
  cart: '#2196f3',
  vaporizers: '#2196f3',
  edible: '#ff9800',
  concentrate: '#9c27b0',
  preroll: '#00bcd4',
  tincture: '#8bc34a',
  tinctures: '#8bc34a',
  topical: '#f44336',
  merch: '#607d8b',
  other: '#9e9e9e',
}

const CATEGORY_EMOJI: Record<string, string> = {
  flower: '🌸',
  vaporizers: '💨',
  cart: '💨',
  edible: '🍬',
  concentrate: '💎',
  preroll: '🌿',
  tinctures: '🧪',
  topical: '🧴',
  merch: '🛍️',
  other: '📦',
}

function formatPrice(cents: number | null) {
  if (cents == null) return null
  return `$${(cents / 100).toFixed(2)}`
}

const CATEGORIES = ['flower', 'preroll', 'vaporizers', 'edible', 'concentrate', 'tinctures', 'topical', 'merch', 'other']

interface Props {
  dispensaryId: string
  dispensaryName: string
  onBack: () => void
  onProductClick?: (productId: string) => void
}

export default function DispensaryListings({ dispensaryId, dispensaryName, onBack, onProductClick }: Props) {
  const [listings, setListings] = useState<DispensaryListing[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(true)
  const [category, setCategory] = useState<string | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const offset = useRef(0)
  const LIMIT = 50

  useEffect(() => {
    offset.current = 0
    setListings([])
    setHasMore(true)
    load(true)
  }, [category, search])

  async function load(reset = false) {
    if (reset) setLoading(true)
    else setLoadingMore(true)
    setError(null)
    try {
      const data = await api.portal.getDispensaryListings(dispensaryId, {
        category: category ?? undefined,
        q: search || undefined,
        limit: LIMIT,
        offset: offset.current,
      })
      setListings(prev => reset ? data : [...prev, ...data])
      setHasMore(data.length === LIMIT)
      offset.current += data.length
    } catch {
      setError('Failed to load listings')
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }

  const containerStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    display: 'flex',
    flexDirection: 'column',
    background: '#0a0a0a',
  }

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button
            onClick={onBack}
            style={{
              background: '#1a1a1a', border: '1px solid #333', borderRadius: 20,
              color: '#888', fontSize: 13, padding: '5px 12px', cursor: 'pointer',
            }}
          >
            ← Map
          </button>
          <div style={{ color: '#fff', fontWeight: 700, fontSize: 16, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {dispensaryName}
          </div>
        </div>

        {/* Search */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') setSearch(searchInput) }}
            placeholder="Search menu…"
            style={{
              flex: 1, background: '#1a1a1a', border: '1px solid #2a2a2a',
              borderRadius: 10, color: '#fff', fontSize: 14, padding: '9px 12px', outline: 'none',
            }}
          />
          {search && (
            <button
              onClick={() => { setSearchInput(''); setSearch('') }}
              style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: 10, color: '#666', fontSize: 13, padding: '0 12px', cursor: 'pointer' }}
            >✕</button>
          )}
        </div>

        {/* Category chips */}
        <div style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 10 }}>
          {[null, ...CATEGORIES].map(cat => {
            const active = category === cat
            const color = cat ? (CATEGORY_COLORS[cat] ?? '#9e9e9e') : '#a8e063'
            return (
              <button
                key={cat ?? 'all'}
                onClick={() => setCategory(cat)}
                style={{
                  flexShrink: 0,
                  padding: '5px 12px',
                  borderRadius: 20,
                  border: `1px solid ${active ? color : '#2a2a2a'}`,
                  background: active ? color + '22' : 'transparent',
                  color: active ? color : '#555',
                  fontSize: 12,
                  fontWeight: active ? 700 : 400,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                {cat ? `${CATEGORY_EMOJI[cat] ?? ''} ${cat}` : 'All'}
              </button>
            )
          })}
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
            <span style={{ color: '#333', fontSize: 14 }}>Loading…</span>
          </div>
        ) : error ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
            <span style={{ color: '#f44336', fontSize: 14 }}>{error}</span>
          </div>
        ) : listings.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
            <span style={{ color: '#333', fontSize: 14 }}>Nothing found</span>
          </div>
        ) : (
          <div style={{ padding: '0 12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {listings.map(l => {
              const cat = l.scraped_category ?? 'other'
              const catColor = CATEGORY_COLORS[cat] ?? '#9e9e9e'
              const price = formatPrice(l.price_cents)
              const clickable = !!l.product_id && !!onProductClick

              return (
                <div
                  key={l.id}
                  onClick={() => clickable && onProductClick!(l.product_id!)}
                  style={{
                    background: '#111',
                    borderRadius: 12,
                    padding: '12px 14px',
                    border: '1px solid #1a1a1a',
                    cursor: clickable ? 'pointer' : 'default',
                    display: 'flex',
                    gap: 12,
                    alignItems: 'flex-start',
                  }}
                >
                  {/* Thumbnail */}
                  {l.image_url && (
                    <div style={{
                      width: 56, height: 56, borderRadius: 8, overflow: 'hidden',
                      flexShrink: 0, background: '#1a1a1a',
                    }}>
                      <img
                        src={l.image_url}
                        alt={l.scraped_name ?? ''}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                    </div>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, flex: 1, minWidth: 0 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ color: '#f1f5f9', fontWeight: 600, fontSize: 14, marginBottom: 2 }}>
                        {l.scraped_name ?? '—'}
                      </div>
                      {l.scraped_brand && (
                        <div style={{ color: '#555', fontSize: 12, marginBottom: 6 }}>{l.scraped_brand}</div>
                      )}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        <span style={{
                          background: catColor + '22', border: `1px solid ${catColor}`,
                          color: catColor, fontSize: 9, fontWeight: 700,
                          padding: '2px 7px', borderRadius: 20,
                          textTransform: 'uppercase', letterSpacing: '0.05em',
                        }}>
                          {cat}
                        </span>
                        {l.variant && (
                          <span style={{ background: '#1a1a1a', color: '#555', fontSize: 10, padding: '2px 7px', borderRadius: 20 }}>
                            {l.variant}
                          </span>
                        )}
                        {l.terpenes.length > 0 && l.terpenes.slice(0, 3).map(t => (
                          <span key={t.name} style={{ background: '#1a1a1a', color: '#666', fontSize: 10, padding: '2px 7px', borderRadius: 20 }}>
                            {t.name}{t.percent != null ? ` ${t.percent.toFixed(1)}%` : ''}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      {price && (
                        <div style={{ color: '#a8e063', fontWeight: 700, fontSize: 15 }}>{price}</div>
                      )}
                      {l.url && (
                        <a
                          href={l.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          style={{ color: '#334155', fontSize: 11, textDecoration: 'none', display: 'block', marginTop: 4 }}
                        >
                          Order →
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}

            {hasMore && (
              <button
                onClick={() => load(false)}
                disabled={loadingMore}
                style={{
                  background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 10,
                  color: '#555', fontSize: 13, padding: '12px', cursor: 'pointer', width: '100%',
                }}
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
