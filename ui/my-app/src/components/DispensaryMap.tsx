import { useEffect, useRef, useState } from 'react'
import { useMatch, useNavigate } from 'react-router-dom'
import api from '../api/client'
import DispensaryListings from './DispensaryListings'
import AisleView from './AisleView'
import type { CartItem } from '../types'

const BROOKLYN: [number, number] = [40.6782, -73.9442]

type PortalDispensary = {
  id: string
  name: string
  slug: string
  address: string | null
  lat: number | null
  lng: number | null
  website_url: string | null
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
    background: '#0a0a0a',
  }

  if (error) {
    return (
      <div style={{ ...containerStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#f44336', fontSize: 14 }}>{error}</span>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div ref={mapRef} style={{ width: '100%', height: '100%' }} />

      {/* Store home overlay */}
      {activeDispensary && !aisleDispensary && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 2000, background: '#0a0a0a', overflowY: 'auto' }}>
          <DispensaryListings
            dispensaryId={activeDispensary.id}
            dispensaryName={activeDispensary.name}
            dispensarySlug={activeDispensary.slug}
            dispensaryAddress={activeDispensary.address}
            dispensaryLat={activeDispensary.lat}
            dispensaryLng={activeDispensary.lng}
            dispensaryLogoUrl={null}
            dispensaryBannerUrl={null}
            acceptsPickup={false}
            onBack={() => navigate(-1)}
            onAddToCart={onAddToCart}
            cart={cart}
          />
        </div>
      )}

      {/* Aisle overlay */}
      {aisleDispensary && aisleCategory && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 2000, background: '#0a0a0a', overflowY: 'auto' }}>
          <AisleView
            dispensaryId={aisleDispensary.id}
            dispensaryName={aisleDispensary.name}
            dispensarySlug={aisleDispensary.slug}
            category={aisleCategory}
            acceptsPickup={false}
            onAddToCart={onAddToCart}
            cart={cart}
          />
        </div>
      )}

      {/* Bottom sheet */}
      {selected && !activeDispensary && (
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: '#111', borderTop: '1px solid #222',
          borderRadius: '16px 16px 0 0', padding: '20px 20px 28px', zIndex: 1000,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: '#fff', fontWeight: 700, fontSize: 17, marginBottom: 4 }}>
                {selected.name}
              </div>
              {selected.address && (
                <div style={{ color: '#666', fontSize: 13, marginBottom: 14 }}>
                  📍 {selected.address}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button
                  onClick={() => navigate('/portal/map/' + selected.id)}
                  style={{
                    background: '#a8e063', border: 'none', borderRadius: 8,
                    color: '#0a0a0a', fontSize: 13, fontWeight: 700,
                    padding: '8px 16px', cursor: 'pointer',
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
                      display: 'inline-block', background: '#1a1a1a',
                      border: '1px solid #333', borderRadius: 8,
                      color: '#888', fontSize: 13, fontWeight: 500,
                      padding: '8px 16px', textDecoration: 'none',
                    }}
                  >
                    Website
                  </a>
                )}
              </div>
            </div>
            <button
              onClick={() => setSelected(null)}
              style={{
                background: '#1a1a1a', border: '1px solid #333', borderRadius: 20,
                color: '#888', fontSize: 13, padding: '4px 10px',
                cursor: 'pointer', marginLeft: 12, flexShrink: 0,
              }}
            >✕</button>
          </div>
        </div>
      )}

      {/* Dispensaries without map coords: show as list at bottom */}
      {!loadingDispensaries && dispensaries.filter(d => d.lat == null).length > 0 && !selected && !activeDispensary && (
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: '#111', borderTop: '1px solid #222',
          borderRadius: '16px 16px 0 0', padding: '16px 20px 28px', zIndex: 1000,
          maxHeight: '40%', overflowY: 'auto',
        }}>
          <div style={{ color: '#555', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>
            Stores
          </div>
          {dispensaries.map(d => (
            <div
              key={d.id}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid #1a1a1a', cursor: 'pointer' }}
              onClick={() => navigate('/portal/map/' + d.id)}
            >
              <div>
                <div style={{ color: '#fff', fontSize: 14, fontWeight: 600 }}>{d.name}</div>
                {d.address && <div style={{ color: '#555', fontSize: 12, marginTop: 2 }}>{d.address}</div>}
              </div>
              <span style={{ color: '#a8e063', fontSize: 13, fontWeight: 700, marginLeft: 12 }}>→</span>
            </div>
          ))}
        </div>
      )}

      {loadingDispensaries && (
        <div style={{
          position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(0,0,0,0.7)', borderRadius: 20, padding: '8px 16px', zIndex: 999,
        }}>
          <span style={{ color: '#555', fontSize: 13 }}>Loading stores…</span>
        </div>
      )}
    </div>
  )
}
