import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { CartItem, DispensaryListing } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { useScrollMemory } from '../utils/browseState'
import { Pressable, Pill, FeedState, Skeleton, ProductImage } from './ui'
import { MarketNote } from './browse'

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
  const [searchFocus, setSearchFocus] = useState(false)
  const [distanceMi, setDistanceMi] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  useScrollMemory(scrollRef, listings.length > 0)
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
    const catColor = categoryColor(cat)
    const price = formatPrice(l.price_cents)
    const cartQty = cart.filter(i => i.listingId === l.id).reduce((s, i) => s + i.quantity, 0)

    return (
      <Pressable
        key={l.id}
        onClick={() => navigate(`/portal/map/${dispensaryId}/listings/${l.id}`)}
        style={{
          width: 132, flexShrink: 0, scrollSnapAlign: 'start',
          background: t.surface1, borderRadius: radius.lg, border: `1px solid ${t.border}`,
          overflow: 'hidden', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ position: 'relative' }}>
          {/* Square, and the width of the card. This frame used to be a fixed
              110px band with its own copy of the fallback logic; ProductImage
              is the same frame every other product shot on the portal uses. */}
          <ProductImage src={l.image_url} alt={l.display_name} category={cat} radius="0" />

          {acceptsPickup && onAddToCart && (
            <button
              aria-label="Add to cart"
              onClick={e => {
                e.stopPropagation()
                onAddToCart({
                  listingId: l.id, dispensaryId, dispensarySlug, dispensaryName,
                  name: l.display_name, brand: l.scraped_brand ?? null,
                  variant: l.variant ?? null, price_cents: l.price_cents ?? null,
                  url: l.url ?? null, image_url: l.image_url ?? null, quantity: 1,
                })
              }}
              style={{
                position: 'absolute', bottom: 8, right: 8,
                width: 30, height: 30, borderRadius: '50%',
                background: cartQty > 0 ? t.accent : '#fff',
                border: 'none', cursor: 'pointer', padding: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700, color: '#0a0a0a',
                boxShadow: '0 2px 10px rgba(0,0,0,0.45)', flexShrink: 0,
                transition: `background var(--t-fast), transform var(--t-fast)`,
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
        <div style={{ padding: '9px 9px 11px', flex: 1 }}>
          {price && <div style={{ color: t.accent, fontWeight: font.weight.bold, fontSize: font.size.small + 1, marginBottom: 3 }}>{price}</div>}
          <div style={{
            color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small, lineHeight: 1.3,
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          } as React.CSSProperties}>
            {l.display_name}
          </div>
          {catColor && l.variant && (
            <div style={{ color: t.text3, fontSize: font.size.caption, marginTop: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.variant}</div>
          )}

          {/* The half a store's own menu cannot answer: is this a good price? */}
          <MarketNote market={l.market} priceCents={l.price_cents} style={{ marginTop: 5 }} />
        </div>
      </Pressable>
    )
  }

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>

      {/* Banner */}
      <div style={{ position: 'relative', height: 160, background: t.surface1 }}>
        {dispensaryBannerUrl ? (
          <img src={dispensaryBannerUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
        ) : (
          <div style={{ width: '100%', height: '100%', background: `linear-gradient(135deg, ${alpha('#a8e063', 0.18)} 0%, ${t.surface1} 72%)` }} />
        )}
        <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(to bottom, ${alpha('#000', 0.15)} 0%, ${t.bg} 100%)` }} />
        <button
          onClick={onBack}
          style={{
            position: 'absolute', top: 14, left: 14,
            background: alpha('#000', 0.5), border: `1px solid ${alpha('#fff', 0.15)}`,
            backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', borderRadius: radius.pill, color: '#fff',
            fontSize: font.size.small, fontWeight: font.weight.medium, padding: '7px 14px', cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: 5,
          }}
        >← Map</button>
      </div>

      {/* Identity block */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: -34, marginBottom: 18, position: 'relative', zIndex: 1, padding: '0 16px' }}>
        <div style={{
          width: 66, height: 66, borderRadius: radius.xl, border: `2px solid ${t.bg}`,
          overflow: 'hidden', background: t.surface2, display: 'flex',
          alignItems: 'center', justifyContent: 'center', marginBottom: 12,
          boxShadow: 'var(--e-2)',
        }}>
          {dispensaryLogoUrl ? (
            <img src={dispensaryLogoUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: 26 }}>
              {dispensaryName.charAt(0).toUpperCase()}
            </span>
          )}
        </div>
        <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.heading, lineHeight: 1.2, marginBottom: 7, textAlign: 'center', letterSpacing: '-0.01em' }}>
          {dispensaryName}
        </div>
        {(dispensaryAddress || distanceMi != null) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap', justifyContent: 'center' }}>
            {dispensaryAddress && <span style={{ color: t.text3, fontSize: font.size.small }}>📍 {dispensaryAddress}</span>}
            {distanceMi != null && <span style={{ color: t.text4, fontSize: font.size.small }}>· {distanceMi < 0.1 ? '< 0.1' : distanceMi.toFixed(1)} mi away</span>}
          </div>
        )}
        {acceptsPickup ? (
          <Pill color={categoryColor('flower')} tone="category" size="md">🛒 Pickup orders</Pill>
        ) : (
          <Pill size="md">In store only</Pill>
        )}
      </div>

      {/* Sticky search */}
      <div style={{ position: 'sticky', top: 0, zIndex: 10, background: alpha('#0b0b0d', 0.86), backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderBottom: `1px solid ${t.border}`, padding: '8px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onFocus={() => setSearchFocus(true)}
            onBlur={() => setSearchFocus(false)}
            onKeyDown={e => {
              if (e.key === 'Enter') setSearchParams(prev => {
                const next = new URLSearchParams(prev)
                if (searchInput) next.set('q', searchInput)
                else next.delete('q')
                return next
              }, { replace: true })
            }}
            placeholder="Search menu…"
            style={{
              flex: 1, background: t.surface2,
              border: `1px solid ${searchFocus ? t.accent : t.border}`,
              boxShadow: searchFocus ? 'var(--ring)' : 'none',
              borderRadius: radius.md, color: t.text1, fontSize: font.size.body, padding: '10px 13px', outline: 'none',
              transition: `border-color var(--t-fast), box-shadow var(--t-fast)`,
            }}
          />
          {search && (
            <button
              onClick={() => { setSearchInput(''); setSearchParams(prev => { const n = new URLSearchParams(prev); n.delete('q'); return n }, { replace: true }) }}
              style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.md, color: t.text3, fontSize: 13, padding: '0 12px', height: 40, cursor: 'pointer' }}
            >✕</button>
          )}
        </div>
      </div>

      {/* Category icon strip */}
      <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 0, padding: '16px 8px 8px' }}>
        {CATEGORIES.map(cat => {
          const c = categoryColor(cat)
          return (
            <Pressable
              key={cat}
              onClick={() => navigate(`/portal/map/${dispensaryId}/aisle/${encodeURIComponent(cat)}`)}
              style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, flexShrink: 0, padding: '0 9px' }}
            >
              <div style={{
                width: 52, height: 52, borderRadius: '50%',
                background: alpha(c, 0.12), border: `1px solid ${alpha(c, 0.3)}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 22,
              }}>
                {CATEGORY_EMOJI[cat] ?? '📦'}
              </div>
              <span style={{ color: t.text2, fontSize: font.size.micro, fontWeight: font.weight.medium, whiteSpace: 'nowrap', textTransform: 'capitalize' }}>{cat}</span>
            </Pressable>
          )
        })}
      </div>

      {/* Aisle rows */}
      {loading ? (
        <AisleSkeleton />
      ) : error ? (
        <FeedState kind="error" message={error} />
      ) : listingsByCategory.size === 0 ? (
        <FeedState kind="empty" message="Nothing found" hint={search ? `No menu items match “${search}”.` : 'This menu has no items right now.'} icon="🔍" />
      ) : (
        <div style={{ paddingBottom: 80 }}>
          {[...listingsByCategory.entries()].map(([catKey, items]) => {
            const c = categoryColor(catKey)
            return (
              <div key={catKey} style={{ marginBottom: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 16px 11px' }}>
                  <span style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout, letterSpacing: '-0.01em', display: 'inline-flex', alignItems: 'center', gap: 7, textTransform: 'capitalize' }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: c, display: 'inline-block' }} />
                    {catKey}
                  </span>
                  <button
                    onClick={() => navigate(`/portal/map/${dispensaryId}/aisle/${encodeURIComponent(catKey)}`)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.accent, fontSize: font.size.small, fontWeight: font.weight.semibold, padding: '2px 0', display: 'flex', alignItems: 'center', gap: 4 }}
                  >
                    See all <span aria-hidden>→</span>
                  </button>
                </div>
                <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 10, padding: '0 16px 12px', scrollSnapType: 'x proximity' }}>
                  {items.slice(0, 10).map(l => renderCard(l))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function AisleSkeleton() {
  return (
    <div style={{ paddingBottom: 80 }}>
      {[0, 1].map(row => (
        <div key={row} style={{ marginBottom: 6 }}>
          <div style={{ padding: '18px 16px 11px' }}><Skeleton width={110} height={15} /></div>
          <div style={{ display: 'flex', gap: 10, padding: '0 16px', overflow: 'hidden' }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{ width: 132, flexShrink: 0, background: 'var(--surface-1)', borderRadius: radius.lg, border: `1px solid ${t.border}`, overflow: 'hidden' }}>
                <Skeleton height={0} radius="0" style={{ aspectRatio: '1 / 1', height: 'auto' }} />
                <div style={{ padding: '9px 9px 11px' }}>
                  <Skeleton width="45%" height={12} style={{ marginBottom: 7 }} />
                  <Skeleton width="90%" height={11} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
