import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import DispensaryListings from './DispensaryListings'

type PortalDispensary = {
  id: string
  name: string
  slug: string
  address: string | null
  lat: number
  lng: number
  website_url: string | null
}

interface Props {
  activeDispensaryId?: string | null
  onProductClick?: (productId: string) => void
}

export default function DispensaryMap({ activeDispensaryId, onProductClick }: Props) {
  const navigate = useNavigate()
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstanceRef = useRef<any>(null)
  const [dispensaries, setDispensaries] = useState<PortalDispensary[]>([])
  const [selected, setSelected] = useState<PortalDispensary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.portal.getDispensaries()
      .then(setDispensaries)
      .catch(() => setError('Failed to load dispensaries'))
  }, [])

  useEffect(() => {
    if (!mapRef.current || dispensaries.length === 0) return
    if (mapInstanceRef.current) return

    import('leaflet').then(L => {
      delete (L.Icon.Default.prototype as any)._getIconUrl
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      })

      const center: [number, number] = [
        dispensaries.reduce((s, d) => s + d.lat, 0) / dispensaries.length,
        dispensaries.reduce((s, d) => s + d.lng, 0) / dispensaries.length,
      ]

      const map = L.map(mapRef.current!, { zoomControl: false }).setView(center, 14)
      mapInstanceRef.current = map

      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap © CARTO',
        maxZoom: 19,
      }).addTo(map)

      L.control.zoom({ position: 'bottomright' }).addTo(map)

      dispensaries.forEach(d => {
        const marker = L.marker([d.lat, d.lng])
          .addTo(map)
          .bindTooltip(d.name, { permanent: false, direction: 'top' })
        marker.on('click', () => setSelected(d))
      })
    })

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove()
        mapInstanceRef.current = null
      }
    }
  }, [dispensaries])

  const activeDispensary = activeDispensaryId
    ? dispensaries.find(d => d.id === activeDispensaryId) ?? null
    : null

  const containerStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    position: 'relative',
    background: '#0a0a0a',
  }

  // Show listings sub-view when a dispensary is active in the URL
  if (activeDispensary) {
    return (
      <DispensaryListings
        dispensaryId={activeDispensary.id}
        dispensaryName={activeDispensary.name}
        onBack={() => navigate(-1)}
        onProductClick={onProductClick}
      />
    )
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

      {/* Bottom sheet */}
      {selected && (
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

      {dispensaries.length === 0 && !error && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: '#0a0a0a',
        }}>
          <span style={{ color: '#333', fontSize: 14 }}>Loading map…</span>
        </div>
      )}
    </div>
  )
}
