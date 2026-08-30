import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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

/** Zoom to settle on when recentring on the user — street level, but never
 *  pulling them back out if they're already closer in. */
const LOCATE_ZOOM = 15

type LocateState =
  | 'idle'        // never asked, or the last error has aged out
  | 'locating'    // waiting on the first fix
  | 'tracking'    // we have a fix and the watch is live
  | 'denied'      // the user said no
  | 'insecure'    // geolocation needs https and this isn't
  | 'failed'      // timeout, no signal, or the API is missing

/** iOS's navigation arrow: outlined when we have a fix but the user has panned
 *  away, filled while the map is following them. */
function LocateGlyph({ filled }: { filled: boolean }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M21 3 3 10.5l7.8 2.7L13.5 21 21 3z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const LOCATE_MESSAGES: Partial<Record<LocateState, string>> = {
  denied: 'Location permission denied',
  insecure: 'Location needs an https connection',
  failed: "Couldn't get your location",
}

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

  // Current location. `following` is whether the map recentres on each fix —
  // the user panning away turns it off, the way iOS hollows out the arrow.
  const [userPosition, setUserPosition] = useState<{ lat: number; lng: number; accuracy: number } | null>(null)
  const [locateState, setLocateState] = useState<LocateState>('idle')
  const [following, setFollowing] = useState(false)
  const [locateHost, setLocateHost] = useState<HTMLElement | null>(null)
  const watchIdRef = useRef<number | null>(null)
  const meRef = useRef<{ dot: any; halo: any } | null>(null)
  // The geolocation callback outlives the render it was created in, so it reads
  // the ref rather than a captured `following`.
  const followingRef = useRef(false)

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

      // An empty Leaflet control so the locate button stacks under the zoom bar
      // on Leaflet's terms; React renders the button itself into it, which keeps
      // the button's state in React rather than in imperative DOM updates.
      const LocateHost = L.Control.extend({
        onAdd() {
          const el = L.DomUtil.create('div', 'leaflet-bar nyc-locate')
          L.DomEvent.disableClickPropagation(el)
          L.DomEvent.disableScrollPropagation(el)
          return el
        },
      })
      const locateControl = new LocateHost({ position: 'topright' })
      locateControl.addTo(map)
      setLocateHost(locateControl.getContainer() ?? null)

      // A drag is the user taking the wheel — stop yanking the map back.
      map.on('dragstart', () => {
        followingRef.current = false
        setFollowing(false)
      })

      setMapReady(true)
    })

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove()
        mapInstanceRef.current = null
        LRef.current = null
        markersRef.current = {}
        meRef.current = null
        setLocateHost(null)
      }
    }
  }, [tiles])

  // Release the geolocation watch when the map goes away.
  useEffect(() => () => {
    if (watchIdRef.current != null) {
      navigator.geolocation.clearWatch(watchIdRef.current)
      watchIdRef.current = null
    }
  }, [])

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
    // Opening a store is a deliberate move away from the user, so stop
    // following them too, or the next fix would drag the map straight back.
    const map = mapInstanceRef.current
    if (selected) {
      followingRef.current = false
      setFollowing(false)
    }
    if (selected?.lat != null && selected.lng != null && map) {
      const zoom = map.getZoom()
      const point = map.project([selected.lat, selected.lng], zoom).add([0, SHEET_PAN_OFFSET])
      map.panTo(map.unproject(point, zoom), { animate: true })
    }
  }, [selected, dispensaries])

  // Draw (and then move) the blue dot and its accuracy halo. Updating the two
  // layers in place rather than rebuilding them keeps a high-accuracy watch,
  // which can fire every second or so, from churning the map.
  useEffect(() => {
    const L = LRef.current
    const map = mapInstanceRef.current
    if (!L || !map || !mapReady) return

    if (!userPosition) {
      meRef.current?.halo.remove()
      meRef.current?.dot.remove()
      meRef.current = null
      return
    }

    const { lat, lng, accuracy } = userPosition
    if (meRef.current) {
      meRef.current.halo.setLatLng([lat, lng]).setRadius(accuracy)
      meRef.current.dot.setLatLng([lat, lng])
      return
    }

    meRef.current = {
      halo: L.circle([lat, lng], {
        radius: accuracy,
        className: 'nyc-accuracy',
        interactive: false,
      }).addTo(map),
      dot: L.marker([lat, lng], {
        icon: L.divIcon({
          html: '<div class="nyc-me"><span class="nyc-me__dot"></span></div>',
          className: '',
          iconSize: [22, 22],
          iconAnchor: [11, 11],
        }),
        interactive: false,
        keyboard: false,
        zIndexOffset: 900,
      }).addTo(map),
    }
  }, [userPosition, mapReady])

  const centreOnUser = useCallback((lat: number, lng: number) => {
    const map = mapInstanceRef.current
    if (!map) return
    map.setView([lat, lng], Math.max(map.getZoom(), LOCATE_ZOOM), { animate: true })
  }, [])

  const handleLocate = useCallback(() => {
    if (!mapInstanceRef.current) return

    // Browsers expose the API off a secure origin but every call fails, so say
    // what's actually wrong instead of reporting a generic failure.
    if (!('geolocation' in navigator)) return setLocateState('failed')
    if (!window.isSecureContext) return setLocateState('insecure')

    followingRef.current = true
    setFollowing(true)

    // Already have a fix — recentre now; the live watch keeps it honest.
    if (userPosition) centreOnUser(userPosition.lat, userPosition.lng)
    else setLocateState('locating')

    if (watchIdRef.current != null) return

    watchIdRef.current = navigator.geolocation.watchPosition(
      pos => {
        const next = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }
        setUserPosition(next)
        setLocateState('tracking')
        if (followingRef.current) centreOnUser(next.lat, next.lng)
      },
      err => {
        setLocateState(err.code === err.PERMISSION_DENIED ? 'denied' : 'failed')
        followingRef.current = false
        setFollowing(false)
        if (watchIdRef.current != null) {
          navigator.geolocation.clearWatch(watchIdRef.current)
          watchIdRef.current = null
        }
      },
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 15_000 },
    )
  }, [centreOnUser, userPosition])

  // Let a failure notice age out so the button reads as retryable again.
  useEffect(() => {
    if (!LOCATE_MESSAGES[locateState]) return
    const id = setTimeout(() => setLocateState(userPosition ? 'tracking' : 'idle'), 5000)
    return () => clearTimeout(id)
  }, [locateState, userPosition])

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

      {/* Locate button — rendered into the Leaflet control Leaflet stacked
          under the zoom bar, so it inherits the control chrome and spacing. */}
      {locateHost && createPortal(
        <button
          type="button"
          onClick={handleLocate}
          aria-label="Show my location"
          aria-pressed={following}
          title={locateState === 'denied' ? 'Location permission is blocked' : 'Show my location'}
          className={[
            'nyc-locate__btn',
            following ? 'is-following' : '',
            locateState === 'denied' || locateState === 'insecure' ? 'is-denied' : '',
          ].filter(Boolean).join(' ')}
        >
          {locateState === 'locating'
            ? <Spinner size={15} />
            : <LocateGlyph filled={following} />}
        </button>,
        locateHost,
      )}

      {/* Legend and the locate notice share one column so a wrapped legend can
          never end up underneath the notice. */}
      {!activeDispensary && (
        <div style={{
          position: 'absolute', top: 14, left: 14, zIndex: 600,
          display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 8,
          maxWidth: 'calc(100% - 76px)',
        }}>
        {!loadingDispensaries && boroughCounts.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
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

        {/* Why locating didn't work — brief, then it ages out */}
        {LOCATE_MESSAGES[locateState] && (
          <div style={{
            background: alpha('#0b0d14', 0.86), border: `1px solid ${t.border}`,
            backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
            borderRadius: radius.pill, padding: '7px 14px',
            color: t.text2, fontSize: font.size.small + 1, boxShadow: 'var(--e-1)',
          }}>
            {LOCATE_MESSAGES[locateState]}
          </div>
        )}
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
