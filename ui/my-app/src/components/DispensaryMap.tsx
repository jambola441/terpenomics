import { useEffect, useRef, useState } from 'react'
import { useMatch, useNavigate } from 'react-router-dom'
import api from '../api/client'
import DispensaryListings from './DispensaryListings'
import AisleView from './AisleView'
import type { CartItem } from '../types'
import { t, radius, font, alpha } from '../theme'
import { FeedState, Spinner, Label } from './ui'

const BROOKLYN: [number, number] = [40.6782, -73.9442]

type PortalDispensary = {
  id: string
  name: string
  slug: string
  address: string | null
  lat: number | null
  lng: number | null
  website_url: string | null
  /** Whether this store takes orders — drives every add-to-cart affordance. */
  accepts_pickup: boolean
}

interface Props {
  activeDispensaryId?: string | null
  onProductClick?: (productId: string) => void
  onAddToCart?: (item: CartItem) => void
  cart?: CartItem[]
}

export default function DispensaryMap({ activeDispensaryId, onProductClick, onAddToCart, cart = [] }: Props) {
  const navigate = useNavigate()
  const matchAisle = useMatch('/portal/map/:dispensaryId/aisle/:category')
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstanceRef = useRef<any>(null)
  const LRef = useRef<any>(null)
  const [dispensaries, setDispensaries] = useState<PortalDispensary[]>([])
  const [loadingDispensaries, setLoadingDispensaries] = useState(true)
  const [mapReady, setMapReady] = useState(false)
  const [selected, setSelected] = useState<PortalDispensary | null>(null)
  const [error, setError] = useState<string | null>(null)

  const aisleDispensaryId = matchAisle?.params.dispensaryId ?? null
  const aisleCategory = matchAisle?.params.category ?? null
  const aisleDispensary = aisleDispensaryId
    ? dispensaries.find(d => d.id === aisleDispensaryId) ?? null
    : null

  useEffect(() => {
    api.portal.getDispensaries()
      .then(data => {
        setDispensaries(data as PortalDispensary[])
        setLoadingDispensaries(false)
      })
      .catch(() => {
        setError('Failed to load dispensaries')
        setLoadingDispensaries(false)
      })
  }, [])

  // Initialize Leaflet as soon as the container is ready — Brooklyn center, no markers yet
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return

    import('leaflet').then(L => {
      if (mapInstanceRef.current) return

      delete (L.Icon.Default.prototype as any)._getIconUrl
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      })

      const map = L.map(mapRef.current!, { zoomControl: false }).setView(BROOKLYN, 13)
      mapInstanceRef.current = map
      LRef.current = L

      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap © CARTO',
        maxZoom: 19,
      }).addTo(map)

      L.control.zoom({ position: 'bottomright' }).addTo(map)

      setMapReady(true)
    })

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove()
        mapInstanceRef.current = null
        LRef.current = null
      }
    }
  }, [])

  // Add markers once both map and dispensaries are ready
  useEffect(() => {
    if (!mapReady || !LRef.current || dispensaries.length === 0) return

    const L = LRef.current
    const map = mapInstanceRef.current!
    const coorded = dispensaries.filter(d => d.lat != null && d.lng != null)

    if (coorded.length > 0) {
      const center: [number, number] = [
        coorded.reduce((s, d) => s + d.lat!, 0) / coorded.length,
        coorded.reduce((s, d) => s + d.lng!, 0) / coorded.length,
      ]
      map.setView(center, 14)

      coorded.forEach(d => {
        const marker = L.marker([d.lat!, d.lng!])
          .addTo(map)
          .bindTooltip(d.name, { permanent: false, direction: 'top' })
        marker.on('click', () => setSelected(d))
      })
    }
  }, [mapReady, dispensaries])

  const activeDispensary = activeDispensaryId
    ? dispensaries.find(d => d.id === activeDispensaryId) ?? null
    : null

  const containerStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    position: 'relative',
    background: t.bg,
  }

  const sheetBase: React.CSSProperties = {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    background: t.surface1, borderTop: `1px solid ${t.border}`,
    borderRadius: `${radius.xl} ${radius.xl} 0 0`, zIndex: 1000,
    boxShadow: 'var(--e-3)', animation: 'ds-fade-in 0.24s ease',
  }

  function Handle() {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 10 }}>
        <div style={{ width: 36, height: 4, borderRadius: 2, background: t.surface3 }} />
      </div>
    )
  }

  if (error) {
    return <div style={containerStyle}><FeedState kind="error" message={error} style={{ height: '100%' }} /></div>
  }

  return (
    <div style={containerStyle}>
      <div ref={mapRef} style={{ width: '100%', height: '100%' }} />

      {/* Store home overlay */}
      {activeDispensary && !aisleDispensary && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 2000, background: t.bg, overflowY: 'auto' }}>
          <DispensaryListings
            dispensaryId={activeDispensary.id}
            dispensaryName={activeDispensary.name}
            dispensarySlug={activeDispensary.slug}
            dispensaryAddress={activeDispensary.address}
            dispensaryLat={activeDispensary.lat}
            dispensaryLng={activeDispensary.lng}
            dispensaryLogoUrl={null}
            dispensaryBannerUrl={null}
            acceptsPickup={activeDispensary.accepts_pickup}
            onBack={() => navigate(-1)}
            onAddToCart={onAddToCart}
            cart={cart}
          />
        </div>
      )}

      {/* Aisle overlay */}
      {aisleDispensary && aisleCategory && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 2000, background: t.bg, overflowY: 'auto' }}>
          <AisleView
            dispensaryId={aisleDispensary.id}
            dispensaryName={aisleDispensary.name}
            dispensarySlug={aisleDispensary.slug}
            category={aisleCategory}
            acceptsPickup={aisleDispensary.accepts_pickup}
            onAddToCart={onAddToCart}
            cart={cart}
          />
        </div>
      )}

      {/* Bottom sheet */}
      {selected && !activeDispensary && (
        <div style={{ ...sheetBase, padding: '0 20px 28px' }}>
          <Handle />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', paddingTop: 14 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, marginBottom: 4, letterSpacing: '-0.01em' }}>
                {selected.name}
              </div>
              {selected.address && (
                <div style={{ color: t.text3, fontSize: font.size.small + 1, marginBottom: 14 }}>
                  📍 {selected.address}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button
                  onClick={() => navigate('/portal/map/' + selected.id)}
                  style={{
                    background: t.accent, border: 'none', borderRadius: radius.sm,
                    color: '#0a0a0a', fontSize: font.size.small + 1, fontWeight: font.weight.bold,
                    padding: '9px 16px', cursor: 'pointer', boxShadow: 'var(--e-1)',
                  }}
                >
                  View menu →
                </button>
                {selected.website_url && (
                  <a
                    href={selected.website_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-block', background: t.surface2,
                      border: `1px solid ${t.border}`, borderRadius: radius.sm,
                      color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium,
                      padding: '9px 16px', textDecoration: 'none',
                    }}
                  >
                    Website
                  </a>
                )}
              </div>
            </div>
            <button
              onClick={() => setSelected(null)}
              aria-label="Close"
              style={{
                background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.pill,
                color: t.text3, fontSize: 16, width: 32, height: 32,
                cursor: 'pointer', marginLeft: 12, flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >✕</button>
          </div>
        </div>
      )}

      {/* Dispensaries without map coords: show as list at bottom */}
      {!loadingDispensaries && dispensaries.filter(d => d.lat == null).length > 0 && !selected && !activeDispensary && (
        <div style={{ ...sheetBase, padding: '0 20px 28px', maxHeight: '42%', overflowY: 'auto' }}>
          <Handle />
          <Label style={{ margin: '14px 0 12px' }}>Stores</Label>
          {dispensaries.map(d => (
            <div
              key={d.id}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 0', borderBottom: `1px solid ${t.border}`, cursor: 'pointer' }}
              onClick={() => navigate('/portal/map/' + d.id)}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ color: t.text1, fontSize: font.size.body, fontWeight: font.weight.semibold }}>{d.name}</div>
                {d.address && <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>{d.address}</div>}
              </div>
              <span style={{ color: t.accent, fontSize: font.size.small + 1, fontWeight: font.weight.bold, marginLeft: 12 }}>→</span>
            </div>
          ))}
        </div>
      )}

      {loadingDispensaries && (
        <div style={{
          position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
          background: alpha('#000', 0.7), border: `1px solid ${t.border}`, backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          borderRadius: radius.pill, padding: '8px 16px', zIndex: 999,
          display: 'flex', alignItems: 'center', gap: 9,
        }}>
          <Spinner size={14} />
          <span style={{ color: t.text2, fontSize: font.size.small + 1 }}>Loading stores…</span>
        </div>
      )}
    </div>
  )
}
