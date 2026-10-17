import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ActivityIndicator, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import MapView, { Marker, type Region } from 'react-native-maps'
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import type { PointsProgram, PortalDispensary, PortalPartner, PortalPartnerLocation } from '@web/types'
import { alpha } from '@web/design/tokens'
import { boroughColor, boroughLabel, boroughOf, colorForBorough, type Borough } from '@web/utils/boroughs'
import { openStatus } from '@web/utils/hours'
import { formatDist, haversineMi } from '@web/utils/format'
import { directionsUrl } from '@web/utils/partnerPlaces'
import { earnLine } from '@web/utils/pointsProgram'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { openStore } from '@/lib/products'
import { useKnownPosition } from '@/components/partners'
import { useLocationStatus } from '@/lib/position'
import { FeedState, Label, StoreBullet } from '@/components/ui'
import { Icon } from '@/components/Icon'
import { t, font, fonts, radius, type } from '@/lib/theme'

type Spot = { partner: PortalPartner; location: PortalPartnerLocation }

/** Pins closer than this on screen are drawn as one count bubble: a pin's
 *  target is 44pt, so two any closer steal each other's taps (as on the web). */
const CLUSTER_PT = 44
/** About the web's zoom 16: stores a block or more apart, every pin its own. */
const CLUSTER_UNTIL_DELTA = 0.012

/** The stores whose pins would overlap in this region, grouped, the way the
 *  web's clusterStores does: greedy and in list order, so the same view gives
 *  the same groups, and the selected store always keeps a pin of its own.
 *  Screen position is linear in the region, which holds at city scale. */
function clusterStores(stores: PortalDispensary[], region: Region, width: number, height: number, apart: string | null) {
  if (region.longitudeDelta <= CLUSTER_UNTIL_DELTA) return stores.map(d => [d])
  const left = region.longitude - region.longitudeDelta / 2
  const top = region.latitude + region.latitudeDelta / 2
  const groups: { x: number; y: number; members: PortalDispensary[] }[] = []
  for (const d of stores) {
    const x = ((d.lng! - left) / region.longitudeDelta) * width
    const y = ((top - d.lat!) / region.latitudeDelta) * height
    const near = d.id === apart ? undefined : groups.find(g =>
      g.members[0].id !== apart && Math.hypot(g.x - x, g.y - y) < CLUSTER_PT)
    if (near) near.members.push(d)
    else groups.push({ x, y, members: [d] })
  }
  return groups.map(g => g.members)
}

/** Lower Manhattan at about the web's zoom 12, before the stores load. */
const NYC: Region = { latitude: 40.7128, longitude: -74.006, latitudeDelta: 0.16, longitudeDelta: 0.16 }

/**
 * The Map tab: the web's DispensaryMap on Apple Maps. Every store as its
 * borough-coloured bullet, partner stores (where purchases earn points) as
 * resin drops, the borough legend led by an Earn points switch, and a sheet
 * for the pin you tap. `?show=partners&spot=<location>` opens on one partner
 * store, as the web's links do.
 */
export default function MapTab() {
  const insets = useSafeAreaInsets()
  const params = useLocalSearchParams<{ show?: string; spot?: string }>()
  const pos = useKnownPosition()
  const locationOff = useLocationStatus() === 'off'
  const map = useRef<MapView>(null)

  const stores = useFetch('dispensaries', () => api.portal.getDispensaries())
  // The map works without partners: a failure leaves the stores alone.
  const partners = useFetch('partners', () => api.portal.getPartners().catch(() => null))
  const program: PointsProgram | null = partners.data?.program ?? null

  const [earnOnly, setEarnOnly] = useState(params.show === 'partners')
  const [selected, setSelected] = useState<PortalDispensary | null>(null)
  const [spot, setSpot] = useState<Spot | null>(null)
  // What the map shows, for grouping pins that would overlap.
  const [region, setRegion] = useState<Region>(NYC)
  const [size, setSize] = useState({ width: 0, height: 0 })

  const placed = useMemo(() => (stores.data ?? []).filter(d => d.lat != null && d.lng != null), [stores.data])
  const groups = useMemo(
    () => (size.width ? clusterStores(placed, region, size.width, size.height, selected?.id ?? null) : placed.map(d => [d])),
    [placed, region, size, selected],
  )
  const unplaced = useMemo(() => (stores.data ?? []).filter(d => d.lat == null || d.lng == null), [stores.data])
  const spots = useMemo<Spot[]>(() => (partners.data?.partners ?? []).flatMap(partner => partner.locations
    .filter(location => location.lat != null && location.lng != null)
    .map(location => ({ partner, location }))), [partners.data])

  const boroughCounts = useMemo(() => {
    const counts = new Map<Borough | null, number>()
    for (const d of stores.data ?? []) {
      const b = boroughOf(d.address)
      counts.set(b, (counts.get(b) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [stores.data])

  // A link to one partner store opens it, with partners only. Picked up once
  // the partners arrive, and again if the tab is opened with a new spot.
  const [handledSpot, setHandledSpot] = useState<string | null>(null)
  if (params.spot && params.spot !== handledSpot && spots.length) {
    const found = spots.find(s => s.location.id === params.spot)
    setHandledSpot(params.spot)
    if (found) {
      setEarnOnly(true)
      setSelected(null)
      setSpot(found)
    }
  }

  // Clear of the legend at the top and the sheet and nav at the bottom.
  const edgePadding = { top: insets.top + 90, right: 56, bottom: 200, left: 56 }

  /** Frame these pins: one is centred above where its sheet sits, close enough
   *  to see the street; several are fitted inside the padding. */
  function frame(coords: { latitude: number; longitude: number }[], animated: boolean) {
    const m = map.current
    if (!m || !coords.length) return
    if (coords.length === 1) {
      const [c] = coords
      // Altitude (Apple Maps) and zoom (Google) both, so either provider lands
      // at street level rather than keeping the city-wide zoom.
      m.animateCamera(
        { center: { latitude: c.latitude - 0.004, longitude: c.longitude }, altitude: 3500, zoom: 14 },
        { duration: animated ? 350 : 0 },
      )
    } else {
      m.fitToCoordinates(coords, { edgePadding, animated })
    }
  }

  const storeCoords = useMemo(() => placed.map(d => ({ latitude: d.lat!, longitude: d.lng! })), [placed])
  const spotCoords = useMemo(
    () => spots.map(sp => ({ latitude: sp.location.lat!, longitude: sp.location.lng! })),
    [spots],
  )

  // A partner store opened by link may be far from the stores (outside the
  // city). The move waits until the tab is on screen and the map is ready: a
  // camera call made while the tab was still switching in was dropped, and the
  // map stayed on the city.
  const [mapReady, setMapReady] = useState(false)

  // Fit every store once they are in, as the web does after its first load,
  // unless the tab was opened on one partner store. It waits for the map to be
  // ready and laid out: a fit made before then used the wrong frame, and
  // pins landed under the tab bar and off the right edge.
  const fitted = useRef(false)
  useEffect(() => {
    if (fitted.current || !mapReady || !size.width || !storeCoords.length || params.spot) return
    fitted.current = true
    const id = setTimeout(() => frame(storeCoords, false), 50)
    return () => clearTimeout(id)
    // frame reads the map ref and the insets; these are what it waits on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, size.width, storeCoords, params.spot])

  const [isFocused, setFocused] = useState(false)
  useFocusEffect(useCallback(() => {
    setFocused(true)
    return () => setFocused(false)
  }, []))
  const flown = useRef<string | null>(null)
  useEffect(() => {
    if (!mapReady || !isFocused || !spot || !params.spot || spot.location.id !== params.spot) return
    if (flown.current === params.spot) return
    flown.current = params.spot
    fitted.current = true
    const target = { latitude: spot.location.lat!, longitude: spot.location.lng! }
    const id = setTimeout(() => frame([target], true), 250)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, isFocused, spot, params.spot])

  // Centre the tapped pin above where its sheet will sit.
  function focus(lat: number, lng: number) {
    map.current?.animateCamera({ center: { latitude: lat - 0.006, longitude: lng } }, { duration: 350 })
  }

  /** Earn points on frames the partner stores; off, every store again. */
  function toggleEarn() {
    const on = !earnOnly
    setEarnOnly(on)
    if (on) setSelected(null)
    else setSpot(null)
    frame(on ? spotCoords : storeCoords, true)
  }

  if (stores.error && !stores.data) {
    return <FeedState error="Failed to load dispensaries" onRetry={stores.refresh} style={{ paddingTop: insets.top }} />
  }

  const showList = !stores.loading && unplaced.length > 0 && !selected && !spot && !earnOnly

  return (
    <View style={{ flex: 1, backgroundColor: t.bg }}>
      <MapView
        ref={map}
        style={StyleSheet.absoluteFill}
        initialRegion={NYC}
        userInterfaceStyle="dark"
        showsUserLocation={pos != null}
        showsPointsOfInterests={false}
        showsCompass={false}
        toolbarEnabled={false}
        onMapReady={() => setMapReady(true)}
        onLayout={e => setSize({ width: e.nativeEvent.layout.width, height: e.nativeEvent.layout.height })}
        onRegionChangeComplete={setRegion}
        onPress={e => {
          // A tap on the map itself, not a pin, closes the sheet.
          if (e.nativeEvent.action !== 'marker-press') { setSelected(null); setSpot(null) }
        }}
      >
        {!earnOnly && groups.map(members => {
          if (members.length > 1) {
            // A bubble for overlapping stores: their count, in their borough's
            // colour when they share one. A tap zooms in until they part.
            const boroughs = new Set(members.map(d => boroughOf(d.address)))
            const color = colorForBorough(boroughs.size === 1 ? [...boroughs][0] : null)
            const named = members.slice(0, 2).map(d => d.name).join(', ')
            return (
              <Marker
                key={`c:${members.map(d => d.id).join(',')}`}
                coordinate={{
                  latitude: members.reduce((n, d) => n + d.lat!, 0) / members.length,
                  longitude: members.reduce((n, d) => n + d.lng!, 0) / members.length,
                }}
                tracksViewChanges={false}
                zIndex={5}
                onPress={() => map.current?.fitToCoordinates(
                  members.map(d => ({ latitude: d.lat!, longitude: d.lng! })),
                  { edgePadding: { top: insets.top + 120, right: 90, bottom: 240, left: 90 }, animated: true },
                )}
                accessibilityLabel={`${members.length} stores: ${named}${members.length > 2 ? ` and ${members.length - 2} more` : ''}`}
              >
                <View style={[s.cluster, { borderColor: color, width: members.length >= 10 ? 40 : 36, height: members.length >= 10 ? 40 : 36 }]}>
                  <Text style={s.clusterText}>{members.length}</Text>
                </View>
              </Marker>
            )
          }
          const [d] = members
          const active = selected?.id === d.id
          return (
            <Marker
              key={`${d.id}${active ? ':on' : ''}`}
              identifier={d.id}
              coordinate={{ latitude: d.lat!, longitude: d.lng! }}
              tracksViewChanges={false}
              zIndex={active ? 10 : 1}
              onPress={() => { setSpot(null); setSelected(d); focus(d.lat!, d.lng!) }}
              accessibilityLabel={d.name}
            >
              <View style={[s.pinRing, active && s.pinRingActive]}>
                <StoreBullet name={d.name} address={d.address} size={active ? 34 : 26} />
              </View>
            </Marker>
          )
        })}
        {spots.map(sp => {
          const active = spot?.location.id === sp.location.id
          return (
            <Marker
              key={`${sp.location.id}${active ? ':on' : ''}`}
              identifier={sp.location.id}
              coordinate={{ latitude: sp.location.lat!, longitude: sp.location.lng! }}
              tracksViewChanges={false}
              zIndex={active ? 10 : 2}
              onPress={() => { setSelected(null); setSpot(sp); focus(sp.location.lat!, sp.location.lng!) }}
              accessibilityLabel={`${sp.partner.name}, partner store`}
            >
              <View style={[s.drop, active && s.dropActive]}>
                <Icon name="drop" size={active ? 16 : 13} color={t.accentInk} strokeWidth={2.25} />
              </View>
            </Marker>
          )
        })}
      </MapView>

      {/* Borough legend, led by the partner-stores switch */}
      {!stores.loading && (boroughCounts.length > 0 || spots.length > 0) ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={[s.legend, { top: insets.top + 10 }]}
          contentContainerStyle={{ gap: 6, paddingHorizontal: 14 }}
        >
          {spots.length > 0 ? (
            <Pressable
              onPress={toggleEarn}
              accessibilityRole="switch"
              accessibilityState={{ checked: earnOnly }}
              accessibilityLabel="Earn points: show only partner stores"
              style={[s.chip, earnOnly
                ? { backgroundColor: t.accent, borderColor: t.accent }
                : { borderColor: alpha(t.accent, 0.55) }]}
            >
              <Icon name="drop" size={13} strokeWidth={2} color={earnOnly ? t.accentInk : t.accent} />
              <Text style={[s.chipText, earnOnly && { color: t.accentInk }]}>Earn points</Text>
              <Text style={[s.chipCount, earnOnly && { color: t.accentInk }]}>{spots.length}</Text>
            </Pressable>
          ) : null}
          {!earnOnly && boroughCounts.map(([borough, count]) => {
            const color = colorForBorough(borough)
            return (
              <View key={borough ?? 'nyc'} style={[s.chip, { borderColor: alpha(color, 0.45) }]}>
                <View style={[s.dot, { backgroundColor: color }]} />
                <Text style={s.chipText}>{boroughLabel(borough)}</Text>
                <Text style={s.chipCount}>{count}</Text>
              </View>
            )
          })}
        </ScrollView>
      ) : null}

      {locationOff && !selected && !spot && !showList ? (
        <View style={[s.loading, { top: undefined, bottom: 16 }]} pointerEvents="none">
          <Icon name="locate" size={13} color={t.text3} />
          <Text style={[type.meta, { color: t.text2 }]}>Turn on location to see where you are</Text>
        </View>
      ) : null}
      {stores.loading ? (
        <View style={[s.loading, { top: insets.top + 14 }]}>
          <ActivityIndicator size="small" color={t.text3} />
          <Text style={[type.meta, { color: t.text2, fontSize: font.size.small + 1 }]}>Loading stores…</Text>
        </View>
      ) : null}

      {selected ? (
        <StoreSheet
          store={selected}
          distanceMi={pos && selected.lat != null && selected.lng != null ? haversineMi(pos.lat, pos.lng, selected.lat, selected.lng) : null}
          onClose={() => setSelected(null)}
        />
      ) : null}
      {spot && !selected ? <PartnerSheet spot={spot} program={program} onClose={() => setSpot(null)} /> : null}

      {showList ? (
        <View style={[s.sheet, { maxHeight: '42%' }]}>
          <Handle />
          <Label style={{ marginTop: 14, marginBottom: 12 }}>Stores</Label>
          <ScrollView>
            {(stores.data ?? []).map(d => (
              <Pressable key={d.id} onPress={() => openStore(d.id)} accessibilityRole="button" style={s.listRow}>
                <StoreBullet name={d.name} address={d.address} size={28} />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={type.bodyStrong}>{d.name}</Text>
                  {d.address ? <Text style={[type.meta, { marginTop: 2 }]}>{d.address}</Text> : null}
                </View>
                <Icon name="chevron-right" size={18} color={t.text3} />
              </Pressable>
            ))}
          </ScrollView>
        </View>
      ) : null}
    </View>
  )
}

function Handle() {
  return (
    <View style={{ alignItems: 'center', paddingTop: 10 }}>
      <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: t.surface3 }} />
    </View>
  )
}

function CloseButton({ onPress }: { onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel="Close" hitSlop={6} style={s.close}>
      <Icon name="close" size={16} color={t.text2} />
    </Pressable>
  )
}

/** A small colour-coded borough chip. */
function BoroughChip({ borough }: { borough: Borough | null }) {
  const color = colorForBorough(borough)
  return (
    <View style={[s.borough, { backgroundColor: alpha(color, 0.16), borderColor: alpha(color, 0.4) }]}>
      <View style={[s.dot, { width: 7, height: 7, backgroundColor: color }]} />
      <Text style={[type.label, { color }]}>{boroughLabel(borough)}</Text>
    </View>
  )
}

function StoreSheet({ store, distanceMi, onClose }: { store: PortalDispensary; distanceMi: number | null; onClose: () => void }) {
  return (
    <View style={[s.sheet, { borderTopWidth: 2, borderTopColor: boroughColor(store.address) }]}>
      <Handle />
      <View style={s.sheetBody}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <BoroughChip borough={boroughOf(store.address)} />
          <Text style={s.sheetTitle}>{store.name}</Text>
          {store.address ? (
            <View style={s.address}>
              <Icon name="pin" size={14} color={t.text3} />
              <Text style={[type.meta, { color: t.text2, fontSize: font.size.small + 1, flexShrink: 1 }]}>
                {store.address}{distanceMi != null ? ` · ${formatDist(distanceMi)}` : ''}
              </Text>
            </View>
          ) : null}
          <View style={s.actions}>
            <SheetButton primary label="View menu" icon="arrow-right" onPress={() => openStore(store.id)} />
            {store.website_url ? (
              <SheetButton label="Website" icon="arrow-up-right" onPress={() => Linking.openURL(store.website_url!)} />
            ) : null}
          </View>
        </View>
        <CloseButton onPress={onClose} />
      </View>
    </View>
  )
}

/** What a partner store pin opens: which business, open now, what it earns,
 *  and the way to its page or to the door. */
function PartnerSheet({ spot, program, onClose }: { spot: Spot; program: PointsProgram | null; onClose: () => void }) {
  const { partner, location } = spot
  const status = openStatus(location.hours, location.timezone)
  const directions = directionsUrl(location, Platform.OS === 'ios')
  return (
    <View style={[s.sheet, { borderTopWidth: 2, borderTopColor: t.accent }]}>
      <Handle />
      <View style={s.sheetBody}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={[s.borough, { backgroundColor: t.accentTint, borderColor: t.accentDim }]}>
            <Icon name="drop" size={12} color={t.accent} strokeWidth={2} />
            <Text style={[type.label, { color: t.accent }]}>Partner store{partner.category ? ` · ${partner.category}` : ''}</Text>
          </View>
          <Text style={s.sheetTitle}>{partner.name}</Text>
          {location.address ? (
            <View style={s.address}>
              <Icon name="pin" size={14} color={t.text3} />
              <Text style={[type.meta, { color: t.text2, fontSize: font.size.small + 1, flexShrink: 1 }]}>{location.address}</Text>
            </View>
          ) : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
            {status ? (
              <Text style={{ fontFamily: fonts.sansMedium, fontSize: font.size.small + 1, color: status.open ? t.success : t.text3 }}>{status.text}</Text>
            ) : null}
            {program ? (
              <Text style={{ fontFamily: fonts.sansSemibold, fontSize: font.size.small + 1, color: t.accent }}>{earnLine(program)}</Text>
            ) : null}
          </View>
          <View style={[s.actions, { marginTop: 16 }]}>
            <SheetButton
              primary
              label="View store"
              icon="arrow-right"
              onPress={() => router.push({ pathname: '/partners/[slug]', params: { slug: partner.slug } })}
            />
            {directions ? <SheetButton label="Directions" icon="navigate" onPress={() => Linking.openURL(directions)} /> : null}
          </View>
        </View>
        <CloseButton onPress={onClose} />
      </View>
    </View>
  )
}

function SheetButton({ label, icon, primary = false, onPress }: {
  label: string
  icon: 'arrow-right' | 'arrow-up-right' | 'navigate'
  primary?: boolean
  onPress: () => void
}) {
  const ink = primary ? t.accentInk : t.text1
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [
        s.sheetButton,
        primary
          ? { backgroundColor: pressed ? t.accentStrong : t.accent }
          : { borderWidth: 1, borderColor: t.borderStrong, backgroundColor: pressed ? t.surface2 : 'transparent' },
      ]}
    >
      {icon === 'navigate' ? <Icon name="navigate" size={15} color={ink} /> : null}
      <Text style={{ fontFamily: primary ? fonts.sansBold : fonts.sansMedium, fontSize: font.size.small + 2, color: ink }}>{label}</Text>
      {icon !== 'navigate' ? <Icon name={icon} size={primary ? 16 : 15} color={ink} strokeWidth={primary ? 2 : 1.75} /> : null}
    </Pressable>
  )
}

const GLASS = 'rgba(12, 15, 13, 0.82)'

const s = StyleSheet.create({
  pinRing: { borderRadius: 20, borderWidth: 2, borderColor: t.bg },
  pinRingActive: { borderColor: t.text1 },
  cluster: {
    borderRadius: 20, borderWidth: 3, alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.surface1,
    shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 4, shadowOffset: { width: 0, height: 2 },
  },
  clusterText: { fontFamily: fonts.monoMedium, fontSize: font.size.small + 1, color: t.text1 },
  drop: {
    width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.accent, borderWidth: 2, borderColor: t.bg,
  },
  dropActive: { width: 34, height: 34, borderRadius: 17, borderColor: t.text1 },
  legend: { position: 'absolute', left: 0, right: 0, flexGrow: 0 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 30,
    paddingVertical: 5, paddingLeft: 8, paddingRight: 10, borderRadius: radius.pill,
    backgroundColor: GLASS, borderWidth: 1,
  },
  chipText: { fontFamily: fonts.sansSemibold, fontSize: font.size.caption, color: t.text1 },
  chipCount: { fontFamily: fonts.monoMedium, fontSize: font.size.caption, color: t.text3 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  loading: {
    position: 'absolute', alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 9,
    paddingVertical: 8, paddingHorizontal: 16, borderRadius: radius.pill,
    backgroundColor: GLASS, borderWidth: 1, borderColor: t.border,
  },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: 20, paddingBottom: 24,
    backgroundColor: t.surface1, borderTopLeftRadius: radius['2xl'], borderTopRightRadius: radius['2xl'],
    shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 16, shadowOffset: { width: 0, height: -4 },
  },
  sheetBody: { flexDirection: 'row', alignItems: 'flex-start', paddingTop: 14 },
  sheetTitle: {
    fontFamily: fonts.display, fontSize: font.size.heading + 2, lineHeight: 26, color: t.text1,
    letterSpacing: -0.3, marginTop: 8, marginBottom: 6,
  },
  address: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 16 },
  sheetButton: {
    flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: radius.md,
    paddingVertical: 10, paddingHorizontal: 14,
  },
  close: {
    width: 34, height: 34, borderRadius: 17, marginLeft: 12, alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border,
  },
  borough: {
    flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 5,
    paddingVertical: 3, paddingLeft: 7, paddingRight: 9, borderRadius: radius.pill, borderWidth: 1,
  },
  listRow: {
    flexDirection: 'row', alignItems: 'center', gap: 11, paddingVertical: 11,
    borderBottomWidth: 1, borderBottomColor: t.border,
  },
})
