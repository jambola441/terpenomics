import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { CartItem, DispensaryListing } from '../types'
import { t, radius, font, categoryColor, categoryLabel, alpha } from '../theme'
import { useScrollMemory } from '../utils/browseState'
import { boroughColor } from '../utils/boroughs'
import { Pressable, Pill, FeedState, Skeleton, ProductImage, StoreBullet } from './ui'
import { Icon, CategoryIcon } from './Icon'
import { MarketNote, PhotoCorner } from './browse'
import { aislePath, listingPath } from '../utils/storePaths'

function formatPrice(cents: number | null) {
  if (cents == null) return null
  return `$${(cents / 100).toFixed(2)}`
}

const CATEGORIES = ['flower', 'preroll', 'vaporizers', 'edible', 'concentrate', 'tinctures', 'topical', 'merch', 'other']

/** Categories in the store's usual order, any unknown ones after. */
export function inShelfOrder(names: string[]): string[] {
  const known = CATEGORIES.filter(c => names.includes(c))
  return [...known, ...names.filter(n => !CATEGORIES.includes(n))]
}


interface Props {
  dispensaryId: string
  dispensaryName: string
  dispensarySlug?: string
  dispensaryAddress?: string | null
  dispensaryLat?: number | null
  dispensaryLng?: number | null
  dispensaryLogoUrl?: string | null
  dispensaryBannerUrl?: string | null
  acceptsPickup?: boolean
  onBack: () => void
  /** The tab the store was opened from; its aisles and listings stay there. */
  section?: string
  /** Names where Back goes ("Map", "Home"). */
  backLabel?: string
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
  acceptsPickup = false, onBack, section = 'map', backLabel = 'Map', onAddToCart, cart = [],
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
  const LIMIT = 100
  /** Cards per category rail on the store page. */
  const RAIL = 10

  // What the store has in stock, by category: the strip shows these, and the
  // page draws one rail each. Fetched once per store and shared by both.
  const [shelf, setShelf] = useState<{ name: string; count: number }[] | null>(null)
  const optionsRef = useRef<{ id: string; promise: ReturnType<typeof api.portal.getDispensaryFilterOptions> } | null>(null)
  function filterOptions() {
    if (optionsRef.current?.id !== dispensaryId) {
      optionsRef.current = { id: dispensaryId, promise: api.portal.getDispensaryFilterOptions(dispensaryId) }
    }
    return optionsRef.current.promise
  }
  useEffect(() => {
    let live = true
    filterOptions().then(o => { if (live) setShelf(o.categories ?? null) }).catch(() => {})
    return () => { live = false }
    // filterOptions reads dispensaryId itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispensaryId])
  const shelfCount = useMemo(() => new Map((shelf ?? []).map(c => [c.name, c.count])), [shelf])

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
    setListings([])
    load()
    // load reads search and dispensaryId itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, dispensaryId])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      if (search) {
        setListings(await api.portal.getDispensaryListings(dispensaryId, { q: search, limit: LIMIT, offset: 0 }))
        return
      }
      // One rail per category the store carries, each with its own first
      // ten. A single 100-row page used to fill up with one category at a big
      // store, and the others never appeared at all.
      const options = await filterOptions()
      // An API from before categories were added: one page, as it used to be.
      if (!options.categories) {
        setListings(await api.portal.getDispensaryListings(dispensaryId, { limit: LIMIT, offset: 0 }))
        return
      }
      setShelf(options.categories)
      const rails = await Promise.all(options.categories.map(c =>
        api.portal.getDispensaryListings(dispensaryId, { category: c.name, limit: RAIL, offset: 0 })))
      setListings(rails.flat())
    } catch {
      optionsRef.current = null // let Try again ask afresh
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
      <div key={l.id} style={{ position: 'relative', width: 132, flexShrink: 0, scrollSnapAlign: 'start', display: 'flex' }}>
      <Pressable
        onClick={() => navigate(listingPath(section, dispensaryId, l.id))}
        style={{
          flex: 1, minWidth: 0,
          background: t.surface1, borderRadius: radius.lg, border: `1px solid ${t.border}`,
          overflow: 'hidden', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ position: 'relative' }}>
          {/* Square, and the width of the card. This frame used to be a fixed
              110px band with its own copy of the fallback logic; ProductImage
              is the same frame every other product shot on the portal uses. */}
          <ProductImage src={l.image_url} alt={l.display_name} category={cat} radius="0" />
        </div>
        <div style={{ padding: '9px 9px 11px', flex: 1 }}>
          {price && <div className="num" style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout, marginBottom: 3 }}>{price}</div>}
          <div style={{
            color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small, lineHeight: 1.3,
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          } as React.CSSProperties}>
            {l.display_name}
          </div>
          {catColor && l.variant && (
            <div style={{ color: t.text3, fontFamily: font.family.mono, fontSize: font.size.caption, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.variant}</div>
          )}

          {/* The half a store's own menu cannot answer: is this a good price? */}
          <MarketNote market={l.market} priceCents={l.price_cents} style={{ marginTop: 5 }} />
        </div>
      </Pressable>
      {/* Beside the card rather than inside its button (see PhotoCorner). */}
      {acceptsPickup && onAddToCart && (
        <PhotoCorner>
          <button
            aria-label={cartQty > 0 ? `Add another ${l.display_name}, ${cartQty} in cart` : `Add ${l.display_name} to cart`}
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
              width: 36, height: 36, borderRadius: '50%',
              background: cartQty > 0 ? t.bg : t.accent,
              border: cartQty > 0 ? `1.5px solid ${t.accent}` : 'none',
              cursor: 'pointer', padding: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: font.family.mono, fontSize: 12, fontWeight: font.weight.medium,
              color: cartQty > 0 ? t.accent : t.accentInk,
              boxShadow: 'var(--e-2)', flexShrink: 0,
              transition: `background var(--t-fast), transform var(--t-fast)`,
            } as React.CSSProperties}
          >
            {cartQty > 0 ? cartQty : <Icon name="plus" size={16} strokeWidth={2.25} />}
          </button>
        </PhotoCorner>
      )}
      </div>
    )
  }

  // The store wears its borough's line colour, as its bullet does on the map.
  const line = boroughColor(dispensaryAddress)

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>

      {/* Banner */}
      <div style={{ position: 'relative', height: 160, background: t.surface1 }}>
        {dispensaryBannerUrl ? (
          <img src={dispensaryBannerUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
        ) : (
          <div style={{ width: '100%', height: '100%', background: `linear-gradient(150deg, ${alpha(line, 0.28)} 0%, ${alpha(line, 0.06)} 55%, ${t.surface1} 100%)` }} />
        )}
        <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(to bottom, rgba(12, 15, 13, 0.1) 0%, ${t.bg} 100%)` }} />
        <button
          onClick={onBack}
          style={{
            position: 'absolute', top: 'calc(14px + env(safe-area-inset-top, 0px))', left: 14,
            background: 'rgba(12, 15, 13, 0.55)', border: '1px solid rgba(242, 240, 233, 0.12)',
            backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)', borderRadius: radius.pill, color: t.text1,
            fontSize: font.size.small + 1, fontWeight: font.weight.medium, padding: '7px 14px 7px 10px', cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: 6,
          }}
        ><Icon name="arrow-left" size={16} /> {backLabel}</button>
      </div>

      {/* Identity block */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: -34, marginBottom: 18, position: 'relative', zIndex: 1, padding: '0 16px' }}>
        {dispensaryLogoUrl ? (
          <div style={{
            width: 68, height: 68, borderRadius: '50%', border: `3px solid ${t.bg}`,
            overflow: 'hidden', background: t.surface2, marginBottom: 12, boxShadow: 'var(--e-2)',
          }}>
            <img src={dispensaryLogoUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          </div>
        ) : (
          <StoreBullet
            name={dispensaryName}
            address={dispensaryAddress}
            size={68}
            style={{ border: `3px solid ${t.bg}`, boxShadow: 'var(--e-2)', marginBottom: 12, boxSizing: 'content-box' }}
          />
        )}
        <h1 style={{
          color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold,
          fontSize: font.size.hero - 2, lineHeight: 1.12, margin: '0 0 8px', textAlign: 'center', letterSpacing: '-0.02em',
        }}>
          {dispensaryName}
        </h1>
        {(dispensaryAddress || distanceMi != null) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
            {dispensaryAddress && (
              <span style={{ color: t.text2, fontSize: font.size.small + 1, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <Icon name="pin" size={14} color={t.text3} /> {dispensaryAddress}
              </span>
            )}
            {distanceMi != null && <span className="num" style={{ color: t.text3, fontSize: font.size.small + 1 }}>· {distanceMi < 0.1 ? '< 0.1' : distanceMi.toFixed(1)} mi away</span>}
          </div>
        )}
        {acceptsPickup ? (
          <Pill color={t.success} size="md"><Icon name="bag" size={12} strokeWidth={2} />Pickup orders</Pill>
        ) : (
          <Pill size="md">In store only</Pill>
        )}
      </div>

      {/* Sticky search */}
      <div style={{ position: 'sticky', top: 0, zIndex: 10, background: 'rgba(12, 15, 13, 0.9)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderBottom: `1px solid ${t.border}`, padding: '8px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ position: 'relative', flex: 1, display: 'flex' }}>
          <Icon name="search" size={16} color={t.text3} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
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
              border: `1px solid ${searchFocus ? t.accentDim : t.border}`,
              boxShadow: searchFocus ? 'var(--ring)' : 'none',
              borderRadius: radius.md, color: t.text1, fontSize: font.size.body, padding: '10px 13px 10px 36px', outline: 'none',
              transition: `border-color var(--t-fast), box-shadow var(--t-fast)`,
            }}
          />
          </div>
          {search && (
            <button
              onClick={() => { setSearchInput(''); setSearchParams(prev => { const n = new URLSearchParams(prev); n.delete('q'); return n }, { replace: true }) }}
              aria-label="Clear search"
              style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.md, color: t.text2, width: 42, height: 42, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
            ><Icon name="close" size={16} /></button>
          )}
        </div>
      </div>

      {/* Category icon strip: only what this store carries. */}
      {shelf && shelf.length > 0 && (
      <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 0, padding: '16px 8px 8px' }}>
        {inShelfOrder(shelf.map(c => c.name)).map(cat => {
          const c = categoryColor(cat)
          return (
            <Pressable
              key={cat}
              onClick={() => navigate(aislePath(section, dispensaryId, cat))}
              style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, flexShrink: 0, padding: '0 9px' }}
            >
              <div style={{
                width: 54, height: 54, borderRadius: radius.lg,
                background: alpha(c, 0.1), border: `1px solid ${alpha(c, 0.26)}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <CategoryIcon category={cat} size={24} strokeWidth={1.6} />
              </div>
              <span style={{ color: t.text2, fontSize: font.size.caption, fontWeight: font.weight.medium, whiteSpace: 'nowrap' }}>{categoryLabel(cat)}</span>
            </Pressable>
          )
        })}
      </div>
      )}

      {/* Aisle rows */}
      {loading ? (
        <AisleSkeleton />
      ) : error ? (
        <FeedState kind="error" message={error} onRetry={load} />
      ) : listingsByCategory.size === 0 ? (
        <FeedState kind="empty" message="Nothing found" hint={search ? `No menu items match “${search}”.` : 'This menu has no items right now.'} icon="search" />
      ) : (
        <div style={{ paddingBottom: 80 }}>
          {[...listingsByCategory.entries()].map(([catKey, items]) => {
            const c = categoryColor(catKey)
            return (
              <div key={catKey} style={{ marginBottom: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 16px 11px' }}>
                  <span style={{ color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold, fontSize: font.size.heading, letterSpacing: '-0.015em', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <CategoryIcon category={catKey} size={19} color={c} />
                    {categoryLabel(catKey)}
                  </span>
                  <button
                    onClick={() => navigate(aislePath(section, dispensaryId, catKey))}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.semibold, padding: '2px 0', display: 'flex', alignItems: 'center', gap: 2 }}
                  >
                    See all{!search && shelfCount.get(catKey) ? ` ${shelfCount.get(catKey)}` : ''} <Icon name="chevron-right" size={15} />
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
