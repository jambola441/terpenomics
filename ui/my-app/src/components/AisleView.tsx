import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { CartItem, DispensaryListing } from '../types'

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
  dispensarySlug?: string
  category: string
  acceptsPickup?: boolean
  onAddToCart?: (item: CartItem) => void
  cart?: CartItem[]
}

export default function AisleView({
  dispensaryId, dispensaryName, dispensarySlug = '', category,
  acceptsPickup = false, onAddToCart, cart = [],
}: Props) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [listings, setListings] = useState<DispensaryListing[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(true)
  const [searchInput, setSearchInput] = useState(() => searchParams.get('q') ?? '')
  const offset = useRef(0)
  const LIMIT = 50

  const variant = searchParams.get('variant')
  const search = searchParams.get('q') ?? ''

  // Variant chips — derived from listings but locked once a variant is selected,
  // so selecting a chip doesn't cause the others to disappear
  const [lockedVariants, setLockedVariants] = useState<string[]>([])
  const variantsFromListings = useMemo(
    () => [...new Set(listings.map(l => l.variant).filter(Boolean) as string[])],
    [listings]
  )
  useEffect(() => {
    if (!variant && variantsFromListings.length > 0) {
      setLockedVariants(variantsFromListings)
    }
  }, [variant, variantsFromListings])
  const chipVariants = lockedVariants.length > 0 ? lockedVariants : variantsFromListings

  const listingsByVariant = useMemo(() => {
    const map = new Map<string, DispensaryListing[]>()
    for (const l of listings) {
      const key = l.variant ?? ''
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(l)
    }
    const sorted = new Map<string, DispensaryListing[]>()
    for (const [k, v] of map) {
      if (k !== '') sorted.set(k, v)
    }
    if (map.has('')) sorted.set('', map.get('')!)
    return sorted
  }, [listings])

  function setFilter(updates: Record<string, string | null>) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      for (const [k, v] of Object.entries(updates)) {
        if (v != null) next.set(k, v)
        else next.delete(k)
      }
      return next
    }, { replace: true })
  }

  useEffect(() => {
    offset.current = 0
    setListings([])
    setHasMore(true)
    load(true)
  }, [category, variant, search])

  async function load(reset = false) {
    if (reset) setLoading(true)
    else setLoadingMore(true)
    setError(null)
    try {
      const data = await api.portal.getDispensaryListings(dispensaryId, {
        category,
        variant: variant ?? undefined,
        q: search || undefined,
        limit: LIMIT,
        offset: offset.current,
      })
      setListings(prev => reset ? data : [...prev, ...data])
      setHasMore(data.length === LIMIT)
      offset.current += data.length
    } catch {
      setError('Failed to load')
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }

  function renderCard(l: DispensaryListing, compact = false) {
    const cat = l.scraped_category ?? 'other'
    const catColor = CATEGORY_COLORS[cat] ?? '#9e9e9e'
    const price = formatPrice(l.price_cents)
    const cartQty = cart.filter(i => i.listingId === l.id).reduce((s, i) => s + i.quantity, 0)
    const imgH = compact ? 110 : 130

    return (
      <div
        key={l.id}
        onClick={() => navigate(`/portal/map/${dispensaryId}/listings/${l.id}`)}
        style={{
          background: '#111', borderRadius: 14, border: '1px solid #1a1a1a',
          cursor: 'pointer', overflow: 'hidden', display: 'flex', flexDirection: 'column',
          ...(compact ? { width: 130, flexShrink: 0 } : {}),
        }}
      >
        <div style={{ position: 'relative', height: imgH, background: catColor + '11', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {l.image_url ? (
            <img src={l.image_url} alt={l.scraped_name ?? ''} style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            <span style={{ fontSize: compact ? 28 : 32, opacity: 0.4 }}>{CATEGORY_EMOJI[cat] ?? '📦'}</span>
          )}
          {acceptsPickup && onAddToCart && (
            <button
              onClick={e => {
                e.stopPropagation()
                onAddToCart({
                  listingId: l.id, dispensaryId, dispensarySlug, dispensaryName,
                  name: l.scraped_name ?? '—', brand: l.scraped_brand ?? null,
                  variant: l.variant ?? null, price_cents: l.price_cents ?? null,
                  url: l.url ?? null, image_url: l.image_url ?? null, quantity: 1,
                })
              }}
              style={{
                position: 'absolute', bottom: 8, right: 8,
                width: 30, height: 30, borderRadius: '50%',
                background: cartQty > 0 ? '#a8e063' : '#fff',
                border: 'none', cursor: 'pointer', padding: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700, color: '#0a0a0a',
                boxShadow: '0 2px 8px rgba(0,0,0,0.35)', flexShrink: 0,
              } as React.CSSProperties}
            >
              {cartQty > 0 ? cartQty : (
                <span style={{ position: 'relative', width: 9, height: 9, display: 'block' }}>
                  <span style={{ position: 'absolute', top: '50%', left: 0, right: 0, height: 2, marginTop: -1, background: '#0a0a0a', borderRadius: 1 }} />
                  <span style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 2, marginLeft: -1, background: '#0a0a0a', borderRadius: 1 }} />
                </span>
              )}
            </button>
          )}
        </div>
        <div style={{ padding: '8px 8px 10px', flex: 1 }}>
          {price && <div style={{ color: '#a8e063', fontWeight: 700, fontSize: compact ? 12 : 14, marginBottom: 2 }}>{price}</div>}
          <div style={{
            color: '#f1f5f9', fontWeight: 600, fontSize: compact ? 12 : 13, lineHeight: 1.3, marginBottom: 2,
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          } as React.CSSProperties}>
            {l.scraped_name ?? '—'}
          </div>
          {l.variant && !compact && <div style={{ color: '#555', fontSize: 11 }}>{l.variant}</div>}
        </div>
      </div>
    )
  }

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: '#0a0a0a' }}>

      {/* Sticky header: back+search / aisle tabs / variant chips */}
      <div style={{ position: 'sticky', top: 0, zIndex: 10, background: '#0a0a0a', borderBottom: '1px solid #161616' }}>

        {/* Row 1: back button + search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px' }}>
          <button
            onClick={() => navigate(`/portal/map/${dispensaryId}`)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#666', fontSize: 20, padding: '0 4px 0 0', lineHeight: 1, flexShrink: 0 }}
          >←</button>
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') setFilter({ q: searchInput || null }) }}
            placeholder={`Search ${category}…`}
            style={{ flex: 1, background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 10, color: '#fff', fontSize: 14, padding: '9px 12px', outline: 'none' }}
          />
          {search && (
            <button
              onClick={() => { setSearchInput(''); setFilter({ q: null }) }}
              style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: 10, color: '#666', fontSize: 13, padding: '0 12px', height: 38, cursor: 'pointer', flexShrink: 0 }}
            >✕</button>
          )}
        </div>

        {/* Row 2: aisle tabs */}
        <div style={{ display: 'flex', overflowX: 'auto', scrollbarWidth: 'none', borderBottom: '1px solid #1a1a1a' } as React.CSSProperties}>
          {CATEGORIES.map(cat => {
            const active = category === cat
            return (
              <button
                key={cat}
                onClick={() => navigate(`/portal/map/${dispensaryId}/aisle/${encodeURIComponent(cat)}`)}
                style={{
                  flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer',
                  padding: '10px 14px 9px', whiteSpace: 'nowrap',
                  color: active ? '#a8e063' : '#555',
                  fontSize: 13, fontWeight: active ? 700 : 400,
                  borderBottom: `2px solid ${active ? '#a8e063' : 'transparent'}`,
                  marginBottom: -1,
                }}
              >
                {cat}
              </button>
            )
          })}
        </div>

        {/* Row 3: variant chips */}
        {chipVariants.length > 0 && (
          <div style={{ display: 'flex', overflowX: 'auto', gap: 6, padding: '8px 16px', scrollbarWidth: 'none' } as React.CSSProperties}>
            {chipVariants.map(v => {
              const active = variant === v
              return (
                <button
                  key={v}
                  onClick={() => setFilter({ variant: active ? null : v })}
                  style={{
                    flexShrink: 0, padding: '5px 13px', borderRadius: 6,
                    border: `1px solid ${active ? '#a8e063' : '#252525'}`,
                    background: active ? '#a8e06322' : '#161616',
                    color: active ? '#a8e063' : '#666',
                    fontSize: 12, fontWeight: active ? 700 : 400,
                    cursor: 'pointer', whiteSpace: 'nowrap',
                  }}
                >
                  {v}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Content */}
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
      ) : !variant ? (
        /* Variant section rows */
        <div style={{ paddingBottom: 80 }}>
          {[...listingsByVariant.entries()].map(([variantKey, items]) => (
            <div key={variantKey || '__none__'} style={{ marginBottom: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 16px 10px' }}>
                <span style={{ color: '#e0e0e0', fontWeight: 700, fontSize: 15 }}>{variantKey || 'Other'}</span>
                <button
                  onClick={() => setFilter({ variant: variantKey || null })}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#a8e063', fontSize: 13, fontWeight: 600, padding: '2px 0', display: 'flex', alignItems: 'center', gap: 3 }}
                >
                  See all <span style={{ fontSize: 15 }}>→</span>
                </button>
              </div>
              <div style={{ display: 'flex', overflowX: 'auto', gap: 10, padding: '0 16px 12px', scrollbarWidth: 'none' } as React.CSSProperties}>
                {items.slice(0, 10).map(l => renderCard(l, true))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* 2-col grid for selected variant */
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '12px 12px 80px' }}>
          {listings.map(l => renderCard(l, false))}
          {hasMore && (
            <button
              onClick={() => load(false)}
              disabled={loadingMore}
              style={{ gridColumn: '1 / -1', background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 10, color: '#555', fontSize: 13, padding: '12px', cursor: 'pointer' }}
            >
              {loadingMore ? 'Loading…' : 'Load more'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
