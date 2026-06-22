import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { PortalBrand, PortalCategory } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { Pressable, Skeleton, Pill } from './ui'

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

  const railStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateRows: 'repeat(2, auto)',
    gridAutoFlow: 'column',
    overflowX: 'auto',
    gap: 12,
    padding: '0 16px 6px',
    scrollSnapType: 'x proximity',
  }

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>

      {/* Header */}
      <div style={{ padding: '22px 16px 6px' }}>
        <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero, letterSpacing: '-0.02em' }}>
          Explore
        </div>
        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
          Discover dispensaries, brands &amp; products near you
        </div>
      </div>

      {loading ? (
        <LoadingSkeleton />
      ) : (
        <>
          {/* ── Dispensaries near you ── */}
          <Section title="Dispensaries near you">
            <div className="no-scrollbar" style={{ ...railStyle, gridAutoColumns: 162 }}>
              {sortedDispensaries.map(d => {
                const dist = (userPos && d.lat != null && d.lng != null)
                  ? haversineMi(userPos.lat, userPos.lng, d.lat, d.lng)
                  : null
                const banner = d.banner_url || d.logo_url
                return (
                  <Pressable
                    key={d.id}
                    onClick={() => navigate('/portal/map/' + d.id)}
                    lift
                    style={{
                      scrollSnapAlign: 'start',
                      background: t.surface1,
                      borderRadius: radius.lg,
                      border: `1px solid ${t.border}`,
                      overflow: 'hidden',
                    }}
                  >
                    {/* Photo area */}
                    <div style={{
                      height: 92,
                      background: banner ? t.surface2 : `linear-gradient(135deg, ${alpha('#a8e063', 0.16)} 0%, ${t.surface2} 70%)`,
                      position: 'relative',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      {banner ? (
                        <img
                          src={banner}
                          alt=""
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                        />
                      ) : (
                        <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: 34, letterSpacing: '-0.02em' }}>
                          {d.name.charAt(0).toUpperCase()}
                        </span>
                      )}
                    </div>
                    {/* Info */}
                    <div style={{ padding: '10px 11px 11px' }}>
                      <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.small + 1, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {d.name}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: t.text2, fontSize: font.size.caption, marginBottom: 7 }}>
                        <span style={{ color: t.accent }}>★</span> 4.5
                        {dist != null && <span style={{ color: t.text3 }}>· {formatDist(dist)}</span>}
                      </div>
                      {d.accepts_pickup ? (
                        <Pill color={categoryColor('flower')} tone="category">🛒 Pickup</Pill>
                      ) : (
                        <Pill>In-store only</Pill>
                      )}
                    </div>
                  </Pressable>
                )
              })}
            </div>
          </Section>

          {/* ── Brands ── */}
          {brands.length > 0 && (
            <Section title="Brands">
              <div className="no-scrollbar" style={{ ...railStyle, gridAutoColumns: 92 }}>
                {brands.map(b => (
                  <Pressable
                    key={b.name}
                    onClick={() => navigate('/portal/brands/' + encodeURIComponent(b.name))}
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7 }}
                  >
                    <div style={{
                      width: 72, height: 72, borderRadius: '50%',
                      background: t.surface2, border: `1px solid ${t.border}`,
                      boxShadow: 'inset 0 0 0 2px rgba(255,255,255,0.02)',
                      overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    }}>
                      {b.image_url ? (
                        <img src={b.image_url} alt={b.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                      ) : (
                        <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: 24 }}>
                          {b.name.charAt(0).toUpperCase()}
                        </span>
                      )}
                    </div>
                    <span style={{
                      color: t.text2, fontSize: font.size.caption, fontWeight: font.weight.medium, textAlign: 'center', lineHeight: 1.2,
                      width: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {b.name}
                    </span>
                  </Pressable>
                ))}
              </div>
            </Section>
          )}

          {/* ── Shop by category ── */}
          {categories.length > 0 && (
            <Section title="Shop by category">
              <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 12, padding: '0 16px 6px', scrollSnapType: 'x proximity' }}>
                {categories.map(c => {
                  const color = categoryColor(c.name)
                  const emoji = CATEGORY_EMOJI[c.name] ?? '📦'
                  return (
                    <Pressable
                      key={c.name}
                      onClick={() => navigate('/portal/search?category=' + encodeURIComponent(c.name))}
                      style={{
                        width: 144, flexShrink: 0, scrollSnapAlign: 'start',
                        background: alpha(color, 0.10), border: `1px solid ${alpha(color, 0.28)}`,
                        borderRadius: radius.xl, overflow: 'hidden',
                      }}
                    >
                      <div style={{ position: 'relative', height: 92 }}>
                        {c.image_url ? (
                          <img src={c.image_url} alt={c.name} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', opacity: 0.6 }}
                            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                        ) : (
                          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 40 }}>
                            {emoji}
                          </div>
                        )}
                        <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(to bottom, transparent 30%, ${alpha('#000', 0.55)} 100%)` }} />
                      </div>
                      <div style={{ padding: '9px 12px 12px' }}>
                        <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.small + 1, textTransform: 'capitalize', marginBottom: 3 }}>{c.name}</div>
                        <div style={{ color, fontSize: font.size.caption, fontWeight: font.weight.semibold }}>{c.listing_count.toLocaleString()} listings</div>
                      </div>
                    </Pressable>
                  )
                })}
              </div>
            </Section>
          )}

          <div style={{ height: 28 }} />
        </>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, letterSpacing: '-0.01em', padding: '18px 16px 11px' }}>{title}</div>
      {children}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ padding: '18px 16px 11px' }}><Skeleton width={170} height={18} /></div>
      <div className="no-scrollbar" style={{ display: 'flex', gap: 12, padding: '0 16px', overflow: 'hidden' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ width: 162, flexShrink: 0 }}>
            <Skeleton height={92} radius={radius.lg} />
            <div style={{ padding: '10px 2px' }}>
              <Skeleton width="80%" height={13} style={{ marginBottom: 8 }} />
              <Skeleton width="55%" height={11} />
            </div>
          </div>
        ))}
      </div>
      <div style={{ padding: '24px 16px 11px' }}><Skeleton width={120} height={18} /></div>
      <div style={{ display: 'flex', gap: 16, padding: '0 16px' }}>
        {[0, 1, 2, 3].map(i => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7 }}>
            <Skeleton width={72} height={72} radius="50%" />
            <Skeleton width={52} height={10} />
          </div>
        ))}
      </div>
    </div>
  )
}
