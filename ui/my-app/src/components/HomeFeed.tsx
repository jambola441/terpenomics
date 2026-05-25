import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { PortalBrand, PortalCategory } from '../types'

const CATEGORY_COLORS: Record<string, string> = {
  flower: '#4caf50',
  vaporizers: '#2196f3',
  cart: '#2196f3',
  edible: '#ff9800',
  concentrate: '#9c27b0',
  preroll: '#00bcd4',
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

type PortalDispensary = {
  id: string
  name: string
  slug: string
  address: string | null
  lat: number | null
  lng: number | null
  website_url: string | null
  accepts_pickup: boolean
  logo_url: string | null
  banner_url: string | null
}

function haversineMi(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 3958.8
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function formatDist(mi: number) {
  return mi < 0.1 ? '< 0.1 mi' : `${mi.toFixed(1)} mi`
}

export default function HomeFeed() {
  const navigate = useNavigate()
  const [dispensaries, setDispensaries] = useState<PortalDispensary[]>([])
  const [brands, setBrands] = useState<PortalBrand[]>([])
  const [categories, setCategories] = useState<PortalCategory[]>([])
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.portal.getDispensaries(),
      api.portal.getBrands(),
      api.portal.getCategories(),
    ]).then(([d, b, c]) => {
      setDispensaries(d as PortalDispensary[])
      setBrands(b)
      setCategories(c)
      setLoading(false)
    }).catch(() => setLoading(false))

    navigator.geolocation?.getCurrentPosition(pos => {
      setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude })
    })
  }, [])

  const sortedDispensaries = useMemo(() => {
    if (!userPos) return dispensaries
    return [...dispensaries].sort((a, b) => {
      if (a.lat == null || a.lng == null) return 1
      if (b.lat == null || b.lng == null) return -1
      return haversineMi(userPos.lat, userPos.lng, a.lat, a.lng)
        - haversineMi(userPos.lat, userPos.lng, b.lat, b.lng)
    })
  }, [dispensaries, userPos])

  const gridStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateRows: 'repeat(2, auto)',
    gridAutoFlow: 'column',
    overflowX: 'auto',
    gap: 10,
    padding: '0 16px 4px',
    scrollbarWidth: 'none',
  }

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: '#0a0a0a' }}>

      {/* Header */}
      <div style={{ padding: '20px 16px 8px' }}>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 22 }}>Explore</div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: '#333', fontSize: 14 }}>Loading…</span>
        </div>
      ) : (
        <>
          {/* ── Dispensaries near you ── */}
          <Section title="Dispensaries near you">
            <div style={{ ...gridStyle, gridAutoColumns: 155 }}>
              {sortedDispensaries.map(d => {
                const dist = (userPos && d.lat != null && d.lng != null)
                  ? haversineMi(userPos.lat, userPos.lng, d.lat, d.lng)
                  : null
                return (
                  <div
                    key={d.id}
                    onClick={() => navigate('/portal/map/' + d.id)}
                    style={{ cursor: 'pointer', background: '#111', borderRadius: 14, border: '1px solid #1a1a1a', overflow: 'hidden' }}
                  >
                    {/* Photo area */}
                    <div style={{ height: 90, background: '#1a1a1a', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {d.banner_url || d.logo_url ? (
                        <img
                          src={d.banner_url ?? d.logo_url ?? ''}
                          alt=""
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                        />
                      ) : (
                        <span style={{ color: '#a8e063', fontWeight: 800, fontSize: 32 }}>
                          {d.name.charAt(0).toUpperCase()}
                        </span>
                      )}
                    </div>
                    {/* Info */}
                    <div style={{ padding: '8px 10px 10px' }}>
                      <div style={{ color: '#f1f5f9', fontWeight: 700, fontSize: 13, marginBottom: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {d.name}
                      </div>
                      <div style={{ color: '#666', fontSize: 11, marginBottom: 5 }}>
                        ⭐ 4.5{dist != null ? ` · ${formatDist(dist)}` : ''}
                      </div>
                      <div style={{
                        display: 'inline-block', fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 20,
                        background: d.accepts_pickup ? '#1a2a10' : '#1a1a1a',
                        border: `1px solid ${d.accepts_pickup ? '#2a4a1a' : '#2a2a2a'}`,
                        color: d.accepts_pickup ? '#6abf2e' : '#444',
                      }}>
                        {d.accepts_pickup ? '🛒 Pickup' : 'In-store only'}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </Section>

          {/* ── Brands ── */}
          {brands.length > 0 && (
            <Section title="Brands">
              <div style={{ ...gridStyle, gridAutoColumns: 90 }}>
                {brands.map(b => (
                  <div key={b.name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <div style={{
                      width: 72, height: 72, borderRadius: '50%',
                      background: '#1a1a1a', border: '1px solid #252525',
                      overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    }}>
                      {b.image_url ? (
                        <img src={b.image_url} alt={b.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                      ) : (
                        <span style={{ color: '#a8e063', fontWeight: 800, fontSize: 22 }}>
                          {b.name.charAt(0).toUpperCase()}
                        </span>
                      )}
                    </div>
                    <span style={{
                      color: '#888', fontSize: 10, textAlign: 'center', lineHeight: 1.2,
                      width: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {b.name}
                    </span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* ── Shop by category ── */}
          {categories.length > 0 && (
            <Section title="Shop by category">
              <div style={{ display: 'flex', overflowX: 'auto', gap: 10, padding: '0 16px 4px', scrollbarWidth: 'none' } as React.CSSProperties}>
                {categories.map(c => {
                  const color = CATEGORY_COLORS[c.name] ?? '#9e9e9e'
                  const emoji = CATEGORY_EMOJI[c.name] ?? '📦'
                  return (
                    <div
                      key={c.name}
                      onClick={() => navigate('/portal/map')}
                      style={{
                        width: 140, flexShrink: 0, cursor: 'pointer',
                        background: color + '14', border: `1px solid ${color}30`,
                        borderRadius: 16, overflow: 'hidden', position: 'relative',
                      }}
                    >
                      {c.image_url ? (
                        <img src={c.image_url} alt={c.name} style={{ width: '100%', height: 90, objectFit: 'cover', display: 'block', opacity: 0.5 }}
                          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                      ) : (
                        <div style={{ height: 90, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 40 }}>
                          {emoji}
                        </div>
                      )}
                      <div style={{ padding: '8px 12px 12px' }}>
                        <div style={{ color: '#fff', fontWeight: 700, fontSize: 13, textTransform: 'capitalize', marginBottom: 2 }}>{c.name}</div>
                        <div style={{ color: color, fontSize: 11 }}>{c.listing_count.toLocaleString()} listings</div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </Section>
          )}

          <div style={{ height: 24 }} />
        </>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ color: '#fff', fontWeight: 700, fontSize: 16, padding: '16px 16px 10px' }}>{title}</div>
      {children}
    </div>
  )
}
