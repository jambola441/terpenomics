// The filter & sort sheet, the twin of the web's FilterSheet (components/browse.tsx):
// sort, distance (where offerings carry coordinates), a price range and the
// page's facets with live counts, then "Show N products". On iOS it is a
// native page sheet, so it drags down to close like any other.

import { useRef, useState } from 'react'
import { Modal, Pressable, ScrollView, StyleSheet, Text, View, type GestureResponderEvent } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { formatDollarsShort } from '@web/utils/format'
import {
  RADII, SORTS, clampPrice, priceStep,
  type Facet, type SortKey, type SortOption,
} from '@web/utils/browseLogic'
import { Button, Label } from '@/components/ui'
import { FacetChip } from './controls'
import { t, font, fonts } from '@/lib/theme'

/** One toggleable facet section in the sheet. */
export type SheetGroup = {
  key: string
  title: string
  facet: Facet[]
  sel: Set<string>
  onToggle: (v: string) => void
  capitalize?: boolean
}

/** Distance section config; omit entirely on screens without coordinates. */
export type SheetDistance = {
  hasLocation: boolean
  radiusMi: number | null
  onRadius: (r: number | null) => void
}

export default function FilterSheet({
  open, onClose, resultCount, color, sort, onSort, sorts = SORTS,
  distance, priceBounds, price, onPrice, groups, onClear, activeCount,
}: {
  open: boolean
  onClose: () => void
  resultCount: number
  color: string
  sort: SortKey
  onSort: (s: SortKey) => void
  sorts?: SortOption[]
  distance?: SheetDistance
  priceBounds: [number, number] | null
  price: [number, number] | null
  onPrice: (p: [number, number] | null) => void
  groups: SheetGroup[]
  onClear: () => void
  activeCount: number
}) {
  const insets = useSafeAreaInsets()
  const [dragging, setDragging] = useState(false)
  return (
    <Modal
      visible={open}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <View style={s.sheet}>
        <View style={s.handleRow}><View style={s.handle} /></View>

        <View style={s.head}>
          <Text style={s.title} accessibilityRole="header">Filter &amp; sort</Text>
          {activeCount > 0 ? (
            <Pressable onPress={onClear} accessibilityRole="button" hitSlop={8}>
              <Text style={s.clearAll}>Clear all</Text>
            </Pressable>
          ) : null}
        </View>

        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={s.content}
          scrollEnabled={!dragging}
        >
          <View>
            <Label style={s.label}>Sort</Label>
            <View style={s.wrap}>
              {sorts.map(o => (
                <FacetChip
                  key={o.key}
                  label={o.label}
                  active={sort === o.key}
                  color={t.accent}
                  disabled={!!o.needsLocation && !distance?.hasLocation}
                  onPress={() => onSort(o.key)}
                />
              ))}
            </View>
          </View>

          {distance ? (
            <View>
              <View style={s.labelRow}>
                <Label>Distance</Label>
                {!distance.hasLocation ? <Text style={s.note}>Location off</Text> : null}
              </View>
              <View style={s.wrap}>
                {RADII.map(r => (
                  <FacetChip
                    key={r.label}
                    label={r.label}
                    active={distance.radiusMi === r.value}
                    color={t.accent}
                    disabled={!distance.hasLocation}
                    capitalize={false}
                    onPress={() => distance.onRadius(r.value)}
                  />
                ))}
              </View>
            </View>
          ) : null}

          {priceBounds ? (
            <PriceRange bounds={priceBounds} value={price} onChange={onPrice} color={t.accent} onDragging={setDragging} />
          ) : null}

          {groups.filter(g => g.facet.length > 1).map(g => (
            <View key={g.key}>
              <Label style={s.label}>{g.title}</Label>
              <View style={s.wrap}>
                {g.facet.map(f => (
                  <FacetChip
                    key={f.value}
                    label={f.value}
                    count={f.count}
                    active={g.sel.has(f.value)}
                    color={color}
                    capitalize={g.capitalize}
                    onPress={() => g.onToggle(f.value)}
                  />
                ))}
              </View>
            </View>
          ))}
        </ScrollView>

        <View style={[s.foot, { paddingBottom: 12 + insets.bottom }]}>
          <Button title={`Show ${resultCount} ${resultCount === 1 ? 'product' : 'products'}`} onPress={onClose} />
        </View>
      </View>
    </Modal>
  )
}

/* ── Price range: two thumbs on one track ─────────────────────────────────── */

const THUMB = 28

function PriceRange({ bounds, value, onChange, color, onDragging }: {
  bounds: [number, number]
  value: [number, number] | null
  onChange: (v: [number, number] | null) => void
  color: string
  /** The sheet stops scrolling while a thumb is held. */
  onDragging: (dragging: boolean) => void
}) {
  const [min, max] = bounds
  const step = priceStep(bounds)
  const [lo, hi] = value ?? bounds
  const [trackWidth, setTrackWidth] = useState(0)
  const pct = (v: number) => (v - min) / (max - min)

  // Where a drag started: the thumb's value and the finger's x.
  const drag = useRef<{ value: number; x: number } | null>(null)

  function start(which: 'lo' | 'hi', x: number) {
    drag.current = { value: which === 'lo' ? lo : hi, x }
    onDragging(true)
  }
  function move(which: 'lo' | 'hi', x: number) {
    if (!drag.current || !trackWidth) return
    const raw = drag.current.value + ((x - drag.current.x) / trackWidth) * (max - min)
    const snapped = Math.round((raw - min) / step) * step + min
    const next: [number, number] = which === 'lo'
      ? [Math.min(snapped, hi - step), hi]
      : [lo, Math.max(raw >= max ? max : snapped, lo + step)]
    onChange(clampPrice(next, bounds))
  }
  function end() {
    drag.current = null
    onDragging(false)
  }

  return (
    <View>
      <View style={s.labelRow}>
        <Label>Price</Label>
        <Text style={[s.readout, { color: value ? color : t.text2 }]}>
          {formatDollarsShort(lo)} – {formatDollarsShort(hi)}{hi >= max ? '+' : ''}
        </Text>
      </View>
      <View
        style={s.rangeBox}
        onLayout={e => setTrackWidth(e.nativeEvent.layout.width - THUMB)}
      >
        <View style={s.track} />
        <View
          style={[s.span, {
            backgroundColor: color,
            left: THUMB / 2 + pct(lo) * trackWidth,
            width: Math.max(0, (pct(hi) - pct(lo)) * trackWidth),
          }]}
        />
        <Thumb
          label="Minimum price"
          value={formatDollarsShort(lo)}
          left={pct(lo) * trackWidth}
          onStart={x => start('lo', x)}
          onMove={x => move('lo', x)}
          onEnd={end}
          onStep={d => onChange(clampPrice([Math.min(lo + d * step, hi - step), hi], bounds))}
        />
        <Thumb
          label="Maximum price"
          value={formatDollarsShort(hi)}
          left={pct(hi) * trackWidth}
          onStart={x => start('hi', x)}
          onMove={x => move('hi', x)}
          onEnd={end}
          onStep={d => onChange(clampPrice([lo, Math.max(hi + d * step, lo + step)], bounds))}
        />
      </View>
    </View>
  )
}

/** One draggable thumb; VoiceOver adjusts it a step at a time. */
function Thumb({ label, value, left, onStart, onMove, onEnd, onStep }: {
  label: string
  value: string
  left: number
  onStart: (x: number) => void
  onMove: (x: number) => void
  onEnd: () => void
  onStep: (direction: 1 | -1) => void
}) {
  return (
    <View
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderTerminationRequest={() => false}
      onResponderGrant={(e: GestureResponderEvent) => onStart(e.nativeEvent.pageX)}
      onResponderMove={(e: GestureResponderEvent) => onMove(e.nativeEvent.pageX)}
      onResponderRelease={onEnd}
      onResponderTerminate={onEnd}
      hitSlop={10}
      accessible
      accessibilityRole="adjustable"
      accessibilityLabel={label}
      accessibilityValue={{ text: value }}
      accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
      onAccessibilityAction={e => onStep(e.nativeEvent.actionName === 'increment' ? 1 : -1)}
      style={[s.thumb, { left }]}
    />
  )
}

const s = StyleSheet.create({
  sheet: { flex: 1, backgroundColor: t.surface1 },
  handleRow: { alignItems: 'center', paddingTop: 10 },
  handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: t.surface3 },
  head: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingTop: 12, paddingHorizontal: 20, paddingBottom: 4,
  },
  title: {
    fontFamily: fonts.display, fontSize: font.size.heading, letterSpacing: -0.3, color: t.text1,
  },
  clearAll: {
    fontFamily: fonts.sans, fontSize: font.size.small + 1, color: t.text2, textDecorationLine: 'underline',
  },
  content: { paddingTop: 14, paddingHorizontal: 20, paddingBottom: 8, gap: 22 },
  label: { marginBottom: 10 },
  labelRow: {
    flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10,
  },
  note: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  readout: { fontFamily: fonts.mono, fontSize: font.size.small + 1, fontVariant: ['tabular-nums'] },
  rangeBox: { height: THUMB + 8, justifyContent: 'center', marginHorizontal: 4 },
  track: {
    position: 'absolute', left: THUMB / 2, right: THUMB / 2, height: 4, borderRadius: 2,
    backgroundColor: t.surface3,
  },
  span: { position: 'absolute', height: 4, borderRadius: 2 },
  thumb: {
    position: 'absolute', width: THUMB, height: THUMB, borderRadius: THUMB / 2,
    backgroundColor: t.text1, borderWidth: 1, borderColor: t.borderStrong,
    shadowColor: '#000', shadowOpacity: 0.35, shadowRadius: 3, shadowOffset: { width: 0, height: 1 },
  },
  foot: { paddingTop: 12, paddingHorizontal: 20, borderTopWidth: 1, borderTopColor: t.border },
})
