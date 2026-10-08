import { useEffect, useMemo, useRef, useState } from 'react'
import { useMatch, useNavigate } from 'react-router-dom'
import api from '../api/client'
import DispensaryListings from './DispensaryListings'
import AisleView from './AisleView'
import type { CartItem, PortalDispensary } from '../types'
import { t, radius, font, alpha } from '../theme'
import { FeedState, Spinner, Label, StoreBullet, storeInitial } from './ui'
import { Icon } from './Icon'
import { boroughOf, boroughColor, colorForBorough, boroughLabel, type Borough } from '../utils/boroughs'
import { tileConfig } from '../utils/mapTiles'

const NYC: [number, number] = [40.7128, -74.006]

/** Roughly half the store sheet's height — how far below the selected store
 *  the map centres so the bullet lands above the sheet rather than behind it. */
const SHEET_PAN_OFFSET = 110

interface Props {
  activeDispensaryId?: string | null
  onAddToCart?: (item: CartItem) => void
  cart?: CartItem[]
}

/** A store's map bullet: an MTA-style disc in its borough's line colour.
 *  Built as a divIcon so the pins inherit the design tokens instead of
 *  pulling Leaflet's blue marker PNGs off a CDN. */
function pinIcon(L: any, d: PortalDispensary, active: boolean) {
  const cls = active ? 'nyc-pin nyc-pin--active' : 'nyc-pin'
  return L.divIcon({
    html:
      `<div class="${cls}" style="--pin:${boroughColor(d.address)}">` +
      `<span class="nyc-pin__disc">${storeInitial(d.name)}</span>` +
      `</div>`,
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 17],
    tooltipAnchor: [0, -14],
  })
}

/** Pins closer than this on screen are drawn as one count bubble. A pin's
 *  target is 44px, so two any closer steal each other's taps. */
const CLUSTER_PX = 44
/** From here in, stores are a block or more apart; every pin is its own. */
const CLUSTER_UNTIL_ZOOM = 16

/** The stores whose pins would overlap at the map's current zoom, grouped.
 *  `apart` (the selected store) always gets a pin of its own, so it never
 *  disappears into a bubble. Greedy and in list order, so the same zoom
 *  gives the same groups. */
function clusterStores(map: any, stores: PortalDispensary[], apart: string | null): PortalDispensary[][] {
  const zoom = map.getZoom()
  if (zoom >= CLUSTER_UNTIL_ZOOM) return stores.map(d => [d])
  const groups: { x: number; y: number; members: PortalDispensary[] }[] = []
  for (const d of stores) {
    const p = map.project([d.lat!, d.lng!], zoom)
    const near = d.id === apart ? undefined : groups.find(g =>
      g.members[0].id !== apart && Math.hypot(g.x - p.x, g.y - p.y) < CLUSTER_PX)
    if (near) near.members.push(d)
    else groups.push({ x: p.x, y: p.y, members: [d] })
  }
  return groups.map(g => g.members)
}

/** A bubble standing in for overlapping stores: their count, in their
 *  borough's colour when they share one. */
function clusterIcon(L: any, members: PortalDispensary[]) {
  const boroughs = new Set(members.map(d => boroughOf(d.address)))
  const color = boroughs.size === 1 ? colorForBorough([...boroughs][0]) : colorForBorough(null)
  const size = members.length >= 10 ? 40 : 36
  return L.divIcon({
    html: `<div class="nyc-cluster" style="--pin:${color}"><span class="nyc-cluster__disc">${members.length}</span></div>`,
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    tooltipAnchor: [0, -size / 2],
  })
}

/** Click, and Enter or Space once focused. Leaflet makes a marker a focusable
 *  role="button" but never turns a key into a click, so without this a
 *  keyboard could reach a pin and not open it. */
function onActivate(marker: any, fn: () => void) {
  marker.on('click', fn)
  marker.on('keydown', (e: any) => {
    const key = e.originalEvent?.key
    if (key !== 'Enter' && key !== ' ') return
    e.originalEvent.preventDefault()
    fn()
  })
}

/** Tooltip content as text: Leaflet sets a string as HTML, and store names
 *  come from scraped menus. */
function tipText(text: string) {
  const el = document.createElement('span')
  el.textContent = text
  return el
}

/** "Housing Works, Union Square and 3 more" */
function clusterNames(members: PortalDispensary[]) {
  const named = members.slice(0, 2).map(d => d.name).join(', ')
  return members.length > 2 ? `${named} and ${members.length - 2} more` : named
}

/** A small colour-coded borough chip, shared by the sheet and the store list. */
function BoroughChip({ borough, style }: { borough: Borough | null; style?: React.CSSProperties }) {
  const color = colorForBorough(borough)
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: alpha(color, 0.16), border: `1px solid ${alpha(color, 0.4)}`,
      borderRadius: radius.pill, padding: '3px 9px 3px 7px',
      color, fontFamily: font.family.mono, fontSize: font.size.caption, fontWeight: font.weight.medium,
      letterSpacing: '0.06em', textTransform: 'uppercase', whiteSpace: 'nowrap',
      ...style,
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {boroughLabel(borough)}
    </span>
  )
}

export default function DispensaryMap({ activeDispensaryId, onAddToCart, cart = [] }: Props) {
  const navigate = useNavigate()
  const matchAisle = useMatch('/portal/map/:dispensaryId/aisle/:category')
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstanceRef = useRef<any>(null)
  const LRef = useRef<any>(null)
  // The layer the pins live on, and its markers by the stores they stand for
  // (one id for a pin, several for a bubble), so a redraw keeps the markers
  // that didn't change -- and keyboard focus on them.
  const layerRef = useRef<any>(null)
  const markersRef = useRef<Map<string, any>>(new Map())
  const [zoom, setZoom] = useState<number | null>(null)
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

  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    setError(null)
    setLoadingDispensaries(true)
    api.portal.getDispensaries()
      .then(data => {
        setDispensaries(data)
        setLoadingDispensaries(false)
      })
      .catch(() => {
        setError('Failed to load dispensaries')
        setLoadingDispensaries(false)
      })
  }, [attempt])

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

      layerRef.current = L.layerGroup().addTo(map)
      map.on('zoomend', () => setZoom(map.getZoom()))
      setZoom(map.getZoom())
      setMapReady(true)
    })

    // Leaflet only notices window resizes. The container also changes height
    // when the cart bar comes and goes, so tell the map, or its tiles and
    // centre drift from what's on screen.
    const container = mapRef.current
    const resize = new ResizeObserver(() => mapInstanceRef.current?.invalidateSize())
    resize.observe(container)

    return () => {
      resize.disconnect()
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove()
        mapInstanceRef.current = null
        LRef.current = null
        layerRef.current = null
        markersRef.current = new Map()
      }
    }
  }, [tiles])

  const located = useMemo(() => dispensaries.filter(d => d.lat != null && d.lng != null), [dispensaries])

  // Frame every store rather than averaging to a point that may fit none.
  useEffect(() => {
    const L = LRef.current, map = mapInstanceRef.current
    if (!mapReady || !L || !map || located.length === 0) return
    map.fitBounds(
      L.latLngBounds(located.map(d => [d.lat!, d.lng!] as [number, number])),
      { padding: [56, 56], maxZoom: 15 },
    )
  }, [mapReady, located])

  // Pins, with stores that would overlap at this zoom drawn as one bubble.
  // Overlapping 30px pins used to leave a sliver of each to tap. A bubble
  // zooms in on its stores; past CLUSTER_UNTIL_ZOOM every store has its pin.
  const selectedId = selected?.id ?? null
  useEffect(() => {
    const L = LRef.current, map = mapInstanceRef.current, layer = layerRef.current
    if (!mapReady || !L || !map || !layer) return

    const old = markersRef.current
    const next = new Map<string, any>()
    for (const members of clusterStores(map, located, selectedId)) {
      const key = members.map(d => d.id).join(',')
      let marker = old.get(key)
      old.delete(key)
      if (members.length === 1) {
        const d = members[0]
        const active = d.id === selectedId
        if (!marker) {
          marker = L.marker([d.lat!, d.lng!], { icon: pinIcon(L, d, active), title: d.name })
            .addTo(layer)
            .bindTooltip(tipText(d.name), { direction: 'top', className: 'nyc-tip', offset: [0, -2] })
          onActivate(marker, () => setSelected(d))
        } else {
          marker.setIcon(pinIcon(L, d, active))
        }
        marker.setZIndexOffset(active ? 1000 : 0)
      } else if (!marker) {
        const bounds = L.latLngBounds(members.map(d => [d.lat!, d.lng!] as [number, number]))
        marker = L.marker(bounds.getCenter(), {
          icon: clusterIcon(L, members),
          title: `${members.length} stores here. Zoom in`,
        })
          .addTo(layer)
          .bindTooltip(tipText(clusterNames(members)), { direction: 'top', className: 'nyc-tip', offset: [0, -2] })
        const bubble = marker
        onActivate(bubble, () => {
          // The bubble goes once the map zooms; hand keyboard focus to the map
          // first, so the next Tab moves through the stores it opened up.
          if (bubble.getElement()?.contains(document.activeElement)) {
            map.getContainer().focus({ preventScroll: true })
          }
          // Far enough in to pull them apart, at least two steps.
          const fit = map.getBoundsZoom(bounds.pad(0.5))
          const to = Math.min(Math.max(fit, map.getZoom() + 2), CLUSTER_UNTIL_ZOOM)
          map.setView(bounds.getCenter(), to, { animate: !window.matchMedia('(prefers-reduced-motion: reduce)').matches })
        })
      }
      next.set(key, marker)
    }
    old.forEach(m => m.remove())
    markersRef.current = next
  }, [mapReady, located, zoom, selectedId])

  // Bring the selected store into view: into the strip of map the sheet
  // doesn't cover, rather than dead centre, which drops it behind the sheet
  // on a short screen.
  useEffect(() => {
    const map = mapInstanceRef.current
    if (selected?.lat != null && selected.lng != null && map) {
      const z = map.getZoom()
      const point = map.project([selected.lat, selected.lng], z).add([0, SHEET_PAN_OFFSET])
      map.panTo(map.unproject(point, z), { animate: true })
    }
  }, [selected])

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
    // The shell sets --chrome-bottom to clear its fixed bars, including the
    // cart bar when there is one, so the sheets' buttons are never under it.
    height: 'calc(100dvh - var(--chrome-bottom, 64px))',
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
    return <div style={containerStyle}><FeedState kind="error" message={error} style={{ height: '100%' }} onRetry={() => setAttempt(n => n + 1)} /></div>
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
          background: 'linear-gradient(rgba(12, 15, 13, 0.62), transparent)',
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
                  background: 'rgba(12, 15, 13, 0.8)', border: `1px solid ${alpha(color, 0.45)}`,
                  backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
                  borderRadius: radius.pill, padding: '5px 10px 5px 8px',
                  color: t.text1, fontSize: font.size.caption, fontWeight: font.weight.semibold,
                  letterSpacing: '0.02em', boxShadow: 'var(--e-1)',
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                {boroughLabel(borough)}
                <span className="num" style={{ color: t.text3, fontFamily: font.family.mono, fontWeight: font.weight.medium }}>{count}</span>
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
              <div style={{ color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold, fontSize: font.size.heading + 2, marginBottom: 6, letterSpacing: '-0.015em', lineHeight: 1.15 }}>
                {selected.name}
              </div>
              {selected.address && (
                <div style={{ color: t.text2, fontSize: font.size.small + 1, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <Icon name="pin" size={14} color={t.text3} /> {selected.address}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button
                  onClick={() => navigate('/portal/map/' + selected.id)}
                  style={{
                    background: t.accent, border: 'none', borderRadius: radius.md,
                    color: t.accentInk, fontSize: font.size.small + 2, fontWeight: font.weight.bold,
                    padding: '10px 14px 10px 16px', cursor: 'pointer',
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                  }}
                >
                  View menu <Icon name="arrow-right" size={16} strokeWidth={2} />
                </button>
                {selected.website_url && (
                  <a
                    href={selected.website_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6, background: 'transparent',
                      border: `1px solid ${t.borderStrong}`, borderRadius: radius.md,
                      color: t.text1, fontSize: font.size.small + 2, fontWeight: font.weight.medium,
                      padding: '10px 14px', textDecoration: 'none',
                    }}
                  >
                    Website <Icon name="arrow-up-right" size={15} />
                  </a>
                )}
              </div>
            </div>
            <button
              onClick={() => setSelected(null)}
              aria-label="Close"
              style={{
                background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.pill,
                color: t.text2, width: 34, height: 34,
                cursor: 'pointer', marginLeft: 12, flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            ><Icon name="close" size={16} /></button>
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
                <StoreBullet name={d.name} address={d.address} size={28} />
                <div style={{ minWidth: 0 }}>
                  <div style={{ color: t.text1, fontSize: font.size.body, fontWeight: font.weight.semibold }}>{d.name}</div>
                  {d.address && <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>{d.address}</div>}
                </div>
              </div>
              <Icon name="chevron-right" size={18} color={t.text3} style={{ marginLeft: 12 }} />
            </div>
          ))}
        </div>
      )}

      {loadingDispensaries && (
        <div style={{
          position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(12, 15, 13, 0.82)', border: `1px solid ${t.border}`, backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
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
