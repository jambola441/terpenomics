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
  dispensaryAddress?: string | null
  dispensaryLat?: number
  dispensaryLng?: number
  dispensaryLogoUrl?: string | null
  dispensaryBannerUrl?: string | null
  acceptsPickup?: boolean
  onBack: () => void
  onAddToCart?: (item: CartItem) => void
  cart?: CartItem[]
}

function haversineMi(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 3958.8
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

export default function DispensaryListings({
  dispensaryId, dispensaryName, dispensarySlug = '', dispensaryAddress,
  dispensaryLat, dispensaryLng, dispensaryLogoUrl, dispensaryBannerUrl,
  acceptsPickup = false, onBack, onAddToCart, cart = [],
}: Props) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [listings, setListings] = useState<DispensaryListing[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchInput, setSearchInput] = useState(() => searchParams.get('q') ?? '')
  const [distanceMi, setDistanceMi] = useState<number | null>(null)
  const offset = useRef(0)
  const LIMIT = 100

  const search = searchParams.get('q') ?? ''

  const listingsByCategory = useMemo(() => {
    const map = new Map<string, DispensaryListing[]>()
    for (const l of listings) {
      const key = l.scraped_category ?? 'other'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(l)
    }
    const sorted = new Map<string, DispensaryListing[]>()
    for (const cat of CATEGORIES) {
      if (map.has(cat)) sorted.set(cat, map.get(cat)!)
    }
    for (const [k, v] of map) {
      if (!sorted.has(k)) sorted.set(k, v)
    }
    return sorted
  }, [listings])

  useEffect(() => {
    if (dispensaryLat == null || dispensaryLng == null) return
    navigator.geolocation?.getCurrentPosition(pos => {
      setDistanceMi(haversineMi(pos.coords.latitude, pos.coords.longitude, dispensaryLat, dispensaryLng))
    })
  }, [dispensaryLat, dispensaryLng])

  useEffect(() => {
    offset.current = 0
    setListings([])
    load()
  }, [search])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.portal.getDispensaryListings(dispensaryId, {
        q: search || undefined,
        limit: LIMIT,
        offset: 0,
      })
      setListings(data)
    } catch {
      setError('Failed to load menu')
    } finally {
      setLoading(false)
    }
  }

  function renderCard(l: DispensaryListing) {
    const cat = l.scraped_category ?? 'other'
    const catColor = CATEGORY_COLORS[cat] ?? '#9e9e9e'
    const price = formatPrice(l.price_cents)
    const cartQty = cart.filter(i => i.listingId === l.id).reduce((s, i) => s + i.quantity, 0)

    return (
      <div
        key={l.id}
        onClick={() => navigate(`/portal/map/${dispensaryId}/listings/${l.id}`)}
        style={{
          width: 130, flexShrink: 0,
          background: '#111', borderRadius: 14, border: '1px solid #1a1a1a',
          cursor: 'pointer', overflow: 'hidden', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ position: 'relative', height: 110, background: catColor + '11', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {l.image_url ? (
            <img
              src={l.image_url}
              alt={l.scraped_name ?? ''}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          ) : (
            <span style={{ fontSize: 32, opacity: 0.4 }}>{CATEGORY_EMOJI[cat] ?? '📦'}</span>
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
          {price && <div style={{ color: '#a8e063', fontWeight: 700, fontSize: 12, marginBottom: 2 }}>{price}</div>}
          <div style={{
            color: '#f1f5f9', fontWeight: 600, fontSize: 12, lineHeight: 1.3,
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          } as React.CSSProperties}>
            {l.scraped_name ?? '—'}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: '#0a0a0a' }}>

      {/* Banner */}
      <div style={{ position: 'relative', height: 160, background: '#111' }}>
        {dispensaryBannerUrl ? (
          <img src={dispensaryBannerUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
        ) : (
          <div style={{ width: '100%', height: '100%', background: 'linear-gradient(135deg, #1a2a1a 0%, #0f1f0f 100%)' }} />
        )}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(0,0,0,0.2) 0%, rgba(0,0,0,0.5) 100%)' }} />
        <button
          onClick={onBack}
          style={{
            position: 'absolute', top: 12, left: 12,
            background: 'rgba(0,0,0,0.55)', border: '1px solid rgba(255,255,255,0.15)',
            backdropFilter: 'blur(8px)', borderRadius: 20, color: '#fff',
            fontSize: 13, padding: '6px 14px', cursor: 'pointer',
          }}
        >← Map</button>
      </div>

      {/* Identity block */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: -32, marginBottom: 16, position: 'relative', zIndex: 1, padding: '0 16px' }}>
        <div style={{
          width: 64, height: 64, borderRadius: 16, border: '2px solid #222',
          overflow: 'hidden', background: '#1a1a1a', display: 'flex',
          alignItems: 'center', justifyContent: 'center', marginBottom: 10,
        }}>
          {dispensaryLogoUrl ? (
            <img src={dispensaryLogoUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            <span style={{ color: '#a8e063', fontWeight: 800, fontSize: 26 }}>
              {dispensaryName.charAt(0).toUpperCase()}
            </span>
          )}
        </div>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 20, lineHeight: 1.2, marginBottom: 6, textAlign: 'center' }}>
          {dispensaryName}
        </div>
        {(dispensaryAddress || distanceMi != null) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
            {dispensaryAddress && <span style={{ color: '#555', fontSize: 12 }}>📍 {dispensaryAddress}</span>}
            {distanceMi != null && <span style={{ color: '#444', fontSize: 12 }}>· {distanceMi < 0.1 ? '< 0.1' : distanceMi.toFixed(1)} mi away</span>}
          </div>
        )}
        {acceptsPickup ? (
          <span style={{ background: '#1a2a10', border: '1px solid #2a4a1a', color: '#6abf2e', fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 20 }}>
            🛒 Pickup orders
          </span>
        ) : (
          <span style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', color: '#555', fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 20 }}>
            In store only
          </span>
        )}
      </div>

      {/* Sticky search */}
      <div style={{ position: 'sticky', top: 0, zIndex: 10, background: '#0a0a0a', borderBottom: '1px solid #161616', padding: '8px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') setSearchParams(prev => {
                const next = new URLSearchParams(prev)
                if (searchInput) next.set('q', searchInput)
                else next.delete('q')
                return next
              }, { replace: true })
            }}
            placeholder="Search menu…"
            style={{ flex: 1, background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 10, color: '#fff', fontSize: 14, padding: '9px 12px', outline: 'none' }}
          />
          {search && (
            <button
              onClick={() => { setSearchInput(''); setSearchParams(prev => { const n = new URLSearchParams(prev); n.delete('q'); return n }, { replace: true }) }}
              style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: 10, color: '#666', fontSize: 13, padding: '0 12px', height: 38, cursor: 'pointer' }}
            >✕</button>
          )}
        </div>
      </div>

      {/* Category icon strip */}
      <div style={{ display: 'flex', overflowX: 'auto', gap: 0, padding: '16px 12px 8px', scrollbarWidth: 'none' } as React.CSSProperties}>
        {CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => navigate(`/portal/map/${dispensaryId}/aisle/${encodeURIComponent(cat)}`)}
            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer', padding: '0 10px' }}
          >
            <div style={{
              width: 52, height: 52, borderRadius: '50%',
              background: '#161616', border: '1px solid #222',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 22,
            }}>
              {CATEGORY_EMOJI[cat] ?? '📦'}
            </div>
            <span style={{ color: '#888', fontSize: 10, whiteSpace: 'nowrap' }}>{cat}</span>
          </button>
        ))}
      </div>

      {/* Aisle rows */}
      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: '#333', fontSize: 14 }}>Loading…</span>
        </div>
      ) : error ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: '#f44336', fontSize: 14 }}>{error}</span>
        </div>
      ) : listingsByCategory.size === 0 ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: '#333', fontSize: 14 }}>Nothing found</span>
        </div>
      ) : (
        <div style={{ paddingBottom: 80 }}>
          {[...listingsByCategory.entries()].map(([catKey, items]) => (
            <div key={catKey} style={{ marginBottom: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 16px 10px' }}>
                <span style={{ color: '#e0e0e0', fontWeight: 700, fontSize: 15 }}>
                  {CATEGORY_EMOJI[catKey] ?? ''} {catKey}
                </span>
                <button
                  onClick={() => navigate(`/portal/map/${dispensaryId}/aisle/${encodeURIComponent(catKey)}`)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#a8e063', fontSize: 13, fontWeight: 600, padding: '2px 0', display: 'flex', alignItems: 'center', gap: 3 }}
                >
                  See all <span style={{ fontSize: 15 }}>→</span>
                </button>
              </div>
              <div style={{ display: 'flex', overflowX: 'auto', gap: 10, padding: '0 16px 12px', scrollbarWidth: 'none' } as React.CSSProperties}>
                {items.slice(0, 10).map(l => renderCard(l))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
