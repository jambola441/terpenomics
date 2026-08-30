import { useEffect, useMemo, useRef, useState } from 'react'
import { useMatch, useNavigate } from 'react-router-dom'
import api from '../api/client'
import DispensaryListings from './DispensaryListings'
import AisleView from './AisleView'
import type { CartItem, PortalDispensary } from '../types'
import { t, radius, font, alpha } from '../theme'
import { FeedState, Spinner, Label } from './ui'
import { boroughOf, boroughColor, colorForBorough, boroughLabel, type Borough } from '../utils/boroughs'
import { tileConfig } from '../utils/mapTiles'

const NYC: [number, number] = [40.7128, -74.006]

/** Roughly half the store sheet's height — how far below the selected store
 *  the map centres so the bullet lands above the sheet rather than behind it. */
const SHEET_PAN_OFFSET = 110

interface Props {
  activeDispensaryId?: string | null
  onProductClick?: (productId: string) => void
  onAddToCart?: (item: CartItem) => void
  cart?: CartItem[]
}

/** First letter/digit of a store name — the glyph inside its subway bullet. */
function initial(name: string): string {
  const match = name.match(/[a-z0-9]/i)
  return (match ? match[0] : '•').toUpperCase()
}

/** A store's map bullet: an MTA-style disc in its borough's line colour.
 *  Built as a divIcon so the pins inherit the design tokens instead of
 *  pulling Leaflet's blue marker PNGs off a CDN. */
function pinIcon(L: any, d: PortalDispensary, active: boolean) {
  const cls = active ? 'nyc-pin nyc-pin--active' : 'nyc-pin'
  return L.divIcon({
    html:
      `<div class="${cls}" style="--pin:${boroughColor(d.address)}">` +
      `<span class="nyc-pin__disc">${initial(d.name)}</span>` +
      `</div>`,
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 17],
    tooltipAnchor: [0, -14],
  })
}

/** A small colour-coded borough chip, shared by the sheet and the store list. */
function BoroughChip({ borough, style }: { borough: Borough | null; style?: React.CSSProperties }) {
  const color = colorForBorough(borough)
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: alpha(color, 0.16), border: `1px solid ${alpha(color, 0.4)}`,
      borderRadius: radius.pill, padding: '3px 9px 3px 7px',
      color, fontSize: font.size.caption, fontWeight: font.weight.bold,
      letterSpacing: '0.02em', textTransform: 'uppercase', whiteSpace: 'nowrap',
      ...style,
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {boroughLabel(borough)}
    </span>
  )
}

export default function DispensaryMap({ activeDispensaryId, onProductClick, onAddToCart, cart = [] }: Props) {
  const navigate = useNavigate()
  const matchAisle = useMatch('/portal/map/:dispensaryId/aisle/:category')
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstanceRef = useRef<any>(null)
  const LRef = useRef<any>(null)
  const markersRef = useRef<Record<string, any>>({})
  const tiles = useMemo(() => tileConfig(), [])
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
        setDispensaries(data)
        setLoadingDispensaries(false)
      })
      .catch(() => {
        setError('Failed to load dispensaries')
        setLoadingDispensaries(false)
      })
  }, [])

  // Initialize Leaflet as soon as the container is ready — NYC center, no markers yet
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return

    import('leaflet').then(L => {
      if (mapInstanceRef.current) return

      const map = L.map(mapRef.current!, { zoomControl: false }).setView(NYC, 12)
      mapInstanceRef.current = map
      LRef.current = L

      // Two panes: the colour basemap is toned to dusk by the provider's
      // filter, and label tiles (when the provider has them) sit above it
      // untouched so street names stay crisp.
      const basePane = map.createPane('nycBase')
      basePane.style.zIndex = '200'
      basePane.classList.add('nyc-base-pane')

      const labelsPane = map.createPane('nycLabels')
      labelsPane.style.zIndex = '250'
      labelsPane.classList.add('nyc-labels-pane')

      basePane.style.filter = tiles.filter

      L.tileLayer(tiles.baseUrl, {
        attribution: tiles.attribution,
        maxZoom: 19,
        detectRetina: tiles.retina,
        pane: 'nycBase',
      }).addTo(map)

      if (tiles.labelsUrl) {
        L.tileLayer(tiles.labelsUrl, {
          maxZoom: 19,
          detectRetina: tiles.retina,
          pane: 'nycLabels',
        }).addTo(map)
      }

      // Bottom-right would sit under the store sheet, so the zoom rides top-right.
      L.control.zoom({ position: 'topright' }).addTo(map)

      setMapReady(true)
    })

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove()
        mapInstanceRef.current = null
        LRef.current = null
        markersRef.current = {}
      }
    }
  }, [tiles])

  // Add markers once both map and dispensaries are ready
  useEffect(() => {
    if (!mapReady || !LRef.current || dispensaries.length === 0) return

    const L = LRef.current
    const map = mapInstanceRef.current!
    const coorded = dispensaries.filter(d => d.lat != null && d.lng != null)
    if (coorded.length === 0) return

    const layer = L.layerGroup().addTo(map)
    markersRef.current = {}

    coorded.forEach(d => {
      const marker = L.marker([d.lat!, d.lng!], {
        icon: pinIcon(L, d, false),
        title: d.name,
      })
        .addTo(layer)
        .bindTooltip(d.name, { direction: 'top', className: 'nyc-tip', offset: [0, -2] })
      marker.on('click', () => setSelected(d))
      markersRef.current[d.id] = marker
    })

    // Frame every store rather than averaging to a point that may fit none.
    map.fitBounds(
      L.latLngBounds(coorded.map(d => [d.lat!, d.lng!] as [number, number])),
      { padding: [56, 56], maxZoom: 15 },
    )

    return () => {
      layer.remove()
      markersRef.current = {}
    }
  }, [mapReady, dispensaries])

  // Re-skin bullets when the selection changes, and bring the store into view.
  useEffect(() => {
    const L = LRef.current
    if (!L) return

    dispensaries.forEach(d => {
      const marker = markersRef.current[d.id]
      if (!marker) return
      const active = selected?.id === d.id
      marker.setIcon(pinIcon(L, d, active))
      marker.setZIndexOffset(active ? 1000 : 0)
    })

    // Pan the store into the strip of map the sheet doesn't cover, rather than
    // to dead centre — centring drops it behind the sheet on a short screen.
    const map = mapInstanceRef.current
    if (selected?.lat != null && selected.lng != null && map) {
      const zoom = map.getZoom()
      const point = map.project([selected.lat, selected.lng], zoom).add([0, SHEET_PAN_OFFSET])
      map.panTo(map.unproject(point, zoom), { animate: true })
    }
  }, [selected, dispensaries])

  const activeDispensary = activeDispensaryId
    ? dispensaries.find(d => d.id === activeDispensaryId) ?? null
    : null

  // Borough breakdown for the legend — only boroughs we actually serve.
  const boroughCounts = useMemo(() => {
    const counts = new Map<Borough | null, number>()
    dispensaries.forEach(d => {
      const b = boroughOf(d.address)
      counts.set(b, (counts.get(b) ?? 0) + 1)
    })
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [dispensaries])

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

  const selectedBorough = selected ? boroughOf(selected.address) : null

  return (
    <div className={tiles.light ? 'nyc-map nyc-map--light' : 'nyc-map'} style={containerStyle}>
      <div ref={mapRef} style={{ width: '100%', height: '100%' }} />

      {/* Scrim so the legend keeps contrast over bright blocks. A light basemap
          already contrasts with the dark chips, so it only runs on dark ones. */}
      {!tiles.light && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 96, zIndex: 500,
          background: `linear-gradient(${alpha('#07090f', 0.62)}, transparent)`,
          pointerEvents: 'none',
        }} />
      )}

      {/* Borough legend */}
      {!loadingDispensaries && boroughCounts.length > 0 && !activeDispensary && (
        <div style={{
          position: 'absolute', top: 14, left: 14, zIndex: 600,
          display: 'flex', flexWrap: 'wrap', gap: 6, maxWidth: 'calc(100% - 76px)',
        }}>
          {boroughCounts.map(([borough, count]) => {
            const color = colorForBorough(borough)
            return (
              <span
                key={borough ?? 'nyc'}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  background: alpha('#0b0d14', 0.78), border: `1px solid ${alpha(color, 0.45)}`,
                  backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
                  borderRadius: radius.pill, padding: '5px 10px 5px 8px',
                  color: t.text1, fontSize: font.size.caption, fontWeight: font.weight.semibold,
                  letterSpacing: '0.02em', boxShadow: 'var(--e-1)',
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                {boroughLabel(borough)}
                <span style={{ color: t.text3, fontWeight: font.weight.bold }}>{count}</span>
              </span>
            )
          })}
        </div>
      )}

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
        <div style={{ ...sheetBase, padding: '0 20px 28px', borderTop: `2px solid ${boroughColor(selected.address)}` }}>
          <Handle />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', paddingTop: 14 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <BoroughChip borough={selectedBorough} style={{ marginBottom: 8 }} />
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
              <div style={{ display: 'flex', alignItems: 'center', gap: 11, minWidth: 0 }}>
                <span style={{
                  width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                  background: boroughColor(d.address), color: '#fff',
                  fontSize: font.size.small, fontWeight: font.weight.heavy,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>{initial(d.name)}</span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ color: t.text1, fontSize: font.size.body, fontWeight: font.weight.semibold }}>{d.name}</div>
                  {d.address && <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>{d.address}</div>}
                </div>
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
