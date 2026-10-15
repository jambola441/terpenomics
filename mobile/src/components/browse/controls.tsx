// The browse screens' small controls, the twins of the web's components/browse.tsx:
// the hero's backdrop, back button, title and stats, the search field, the
// facet and active-filter chips, the sticky toolbar, the Shelves/Grid switch
// and the loading grid. BrowseScreen and the search screen assemble them.

import { useState, type ReactNode } from 'react'
import {
  Pressable, ScrollView, StyleSheet, Text, TextInput, View, useWindowDimensions,
  type StyleProp, type ViewStyle,
} from 'react-native'
import { router } from 'expo-router'
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg'
import { alpha } from '@web/design/tokens'
import { Icon, type IconName } from '@/components/Icon'
import { t, font, fonts, radius, space } from '@/lib/theme'

/* ── Hero ─────────────────────────────────────────────────────────────────── */

/** The hero's wash: the page's colour fading into the ground at 165°, as the
 *  web's `linear-gradient(165deg, c 22%, c 6%, bg)`. */
export function HeroBackdrop({ color, strength = 0.22 }: { color: string; strength?: number }) {
  return (
    <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
      <Defs>
        {/* 165° from the top: down and a little to the right. */}
        <LinearGradient id="hero" x1="0" y1="0" x2="0.27" y2="1">
          <Stop offset="0" stopColor={color} stopOpacity={strength} />
          <Stop offset="0.5" stopColor={color} stopOpacity={strength * (0.06 / 0.22)} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </LinearGradient>
      </Defs>
      <Rect x="0" y="0" width="100%" height="100%" fill="url(#hero)" />
    </Svg>
  )
}

/** The status bar's strip, tinted like the top of the hero so the two read as
 *  one surface; the toolbar sticks just under it. */
export function StatusStrip({ height, color, strength = 0.22 }: { height: number; color: string; strength?: number }) {
  return (
    <View style={{ height, backgroundColor: t.bg }}>
      <View style={[StyleSheet.absoluteFill, { backgroundColor: alpha(color, strength) }]} />
    </View>
  )
}

/** The web's glass BackButton. */
export function BackButton() {
  return (
    <Pressable
      onPress={() => router.back()}
      accessibilityRole="button"
      accessibilityLabel="Back"
      hitSlop={8}
      style={({ pressed }) => [s.back, pressed && { backgroundColor: t.surface3 }]}
    >
      <Icon name="arrow-left" size={18} color={t.text1} />
    </Pressable>
  )
}

/** The hero's Fraunces title (34 on the category and search pages). */
export function HeroTitle({ children, size = 30 }: { children: ReactNode; size?: number }) {
  return (
    <Text
      accessibilityRole="header"
      style={{
        fontFamily: fonts.display, fontSize: size, lineHeight: Math.round(size * 1.12),
        letterSpacing: Math.round(size * -0.02 * 100) / 100, color: t.text1,
      }}
    >
      {children}
    </Text>
  )
}

/** "1,204 products · 88 brands · 31 dispensaries": the number in the page's hue. */
export function Stats({ stats, color, style }: {
  stats: { value: number; one: string; many: string }[]
  color: string
  style?: StyleProp<ViewStyle>
}) {
  return (
    <View style={[s.stats, style]}>
      {stats.map((st, i) => (
        <View key={st.many} style={s.stat}>
          {i > 0 ? <Text style={s.dot} accessibilityElementsHidden>·</Text> : null}
          <Text style={s.statLabel}>
            <Text style={[s.statValue, { color }]}>{st.value.toLocaleString()}</Text>
            {' '}{st.value === 1 ? st.one : st.many}
          </Text>
        </View>
      ))}
    </View>
  )
}

/* ── Search field ─────────────────────────────────────────────────────────── */

export function SearchField({ value, onChange, placeholder, autoFocus }: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  autoFocus?: boolean
}) {
  const [focused, setFocused] = useState(false)
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <View style={{ flex: 1, justifyContent: 'center' }}>
        <Icon name="search" size={16} color={t.text3} style={{ position: 'absolute', left: 12, zIndex: 1 }} />
        <TextInput
          value={value}
          onChangeText={onChange}
          placeholder={placeholder}
          placeholderTextColor={t.text4}
          autoFocus={autoFocus}
          autoCorrect={false}
          autoCapitalize="none"
          returnKeyType="search"
          clearButtonMode="never"
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          accessibilityLabel={placeholder}
          style={[s.input, focused && { borderColor: t.accentDim }]}
        />
      </View>
      {value ? (
        <Pressable
          onPress={() => onChange('')}
          accessibilityRole="button"
          accessibilityLabel="Clear search"
          style={({ pressed }) => [s.clear, pressed && { backgroundColor: t.surface3 }]}
        >
          <Icon name="close" size={16} color={t.text2} />
        </Pressable>
      ) : null}
    </View>
  )
}

/* ── Chips ────────────────────────────────────────────────────────────────── */

/** Upper-case each word's first letter and leave the rest alone, as CSS
 *  `text-transform: capitalize` does on the web. RN's `textTransform` on iOS
 *  also lower-cases the rest ("MFNY" → "Mfny"), and it is visual only, so
 *  VoiceOver read the raw lower-case value; changing the string fixes both. */
export function capitalizeWords(label: string): string {
  return label.replace(/(^|[\s/(-])(\p{Ll})/gu, (_, sep: string, ch: string) => sep + ch.toUpperCase())
}

export function FacetChip({ label, icon, count, active, color, onPress, disabled = false, capitalize = true }: {
  label: string
  icon?: ReactNode
  count?: number
  active: boolean
  color: string
  onPress: () => void
  disabled?: boolean
  /** Off for labels that carry their own casing — units, sizes, sort phrases. */
  capitalize?: boolean
}) {
  const shown = capitalize ? capitalizeWords(label) : label
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ selected: active, disabled }}
      accessibilityLabel={count != null ? `${shown}, ${count}` : shown}
      style={[
        s.chip,
        active
          ? { backgroundColor: alpha(color, 0.12), borderColor: alpha(color, 0.6) }
          : { backgroundColor: t.surface2, borderColor: t.border },
        disabled && { opacity: 0.5 },
      ]}
    >
      {icon}
      <Text
        numberOfLines={1}
        style={{
          fontFamily: active ? fonts.sansSemibold : fonts.sansMedium,
          fontSize: font.size.small + 1,
          color: disabled ? t.text4 : active ? color : t.text2,
        }}
      >
        {shown}
      </Text>
      {count != null ? (
        <Text style={[s.count, { color: active ? color : t.text3 }]}>{count}</Text>
      ) : null}
    </Pressable>
  )
}

export function ActiveChip({ label, onRemove, capitalize = true }: {
  label: string
  onRemove: () => void
  capitalize?: boolean
}) {
  const shown = capitalize ? capitalizeWords(label) : label
  return (
    <Pressable
      onPress={onRemove}
      accessibilityRole="button"
      accessibilityLabel={`Remove ${shown}`}
      style={s.activeChip}
    >
      <Text numberOfLines={1} style={s.activeText}>
        {shown}
      </Text>
      <Icon name="close" size={13} color={t.accent} strokeWidth={2.25} />
    </Pressable>
  )
}

/* ── Sticky toolbar ───────────────────────────────────────────────────────── */

/** The bar that sticks under the hero: an optional quick-filter rail, then the
 *  Filters and sort buttons, the removable active-filter chips and Clear. */
export function BrowseToolbar({ quickRail, activeCount, sortLabel, onOpenSheet, activeChips, onClear }: {
  quickRail?: ReactNode
  activeCount: number
  sortLabel: string
  onOpenSheet: () => void
  activeChips?: ReactNode
  onClear: () => void
}) {
  return (
    <View style={s.toolbar}>
      {quickRail ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ gap: 8, paddingHorizontal: 14, paddingVertical: 10 }}
        >
          {quickRail}
        </ScrollView>
      ) : (
        <View style={{ height: 10 }} />
      )}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ gap: 8, paddingHorizontal: 14, paddingBottom: 10, alignItems: 'center' }}
      >
        <Pressable
          onPress={onOpenSheet}
          accessibilityRole="button"
          accessibilityLabel={activeCount ? `Filters, ${activeCount} on` : 'Filters'}
          style={[
            s.toolButton,
            activeCount
              ? { backgroundColor: t.accentTint, borderColor: t.accentDim }
              : { backgroundColor: t.surface2, borderColor: t.border },
          ]}
        >
          <Icon name="filters" size={15} color={activeCount ? t.accent : t.text1} />
          <Text style={[s.toolText, { fontFamily: fonts.sansSemibold, color: activeCount ? t.accent : t.text1 }]}>
            Filters{activeCount ? ` · ${activeCount}` : ''}
          </Text>
        </Pressable>
        <Pressable
          onPress={onOpenSheet}
          accessibilityRole="button"
          accessibilityLabel={`Sort: ${sortLabel}`}
          style={[s.toolButton, { backgroundColor: t.surface2, borderColor: t.border }]}
        >
          <Icon name="sort" size={14} color={t.text3} />
          <Text style={s.toolText}>{sortLabel}</Text>
        </Pressable>
        {activeChips}
        {activeCount > 0 ? (
          <Pressable onPress={onClear} accessibilityRole="button" hitSlop={6}>
            <Text style={s.clearText}>Clear</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </View>
  )
}

/* ── Shelves / Grid switch ────────────────────────────────────────────────── */

export type BrowseView = 'shelves' | 'grid'

export function ViewSwitch({ view, onChange }: { view: BrowseView; onChange: (v: BrowseView) => void }) {
  const options: { key: BrowseView; label: string; icon: IconName }[] = [
    { key: 'shelves', label: 'Shelves', icon: 'list' },
    { key: 'grid', label: 'Grid', icon: 'grid' },
  ]
  return (
    <View style={s.switch} accessibilityRole="radiogroup" accessibilityLabel="Layout">
      {options.map(o => {
        const active = view === o.key
        return (
          <Pressable
            key={o.key}
            onPress={() => onChange(o.key)}
            accessibilityRole="radio"
            accessibilityState={{ selected: active }}
            style={[s.switchOption, active && { backgroundColor: t.surface3 }]}
          >
            <Icon name={o.icon} size={13} color={active ? t.text1 : t.text3} />
            <Text style={{
              fontFamily: active ? fonts.sansSemibold : fonts.sansMedium,
              fontSize: font.size.caption, color: active ? t.text1 : t.text3,
            }}
            >
              {o.label}
            </Text>
          </Pressable>
        )
      })}
    </View>
  )
}

/* ── Loading grid ─────────────────────────────────────────────────────────── */

export const GRID_GUTTER = 12
export const GRID_GAP = 10

/** Width of one card in the two-column grid. */
export function useGridCardWidth(): number {
  const { width } = useWindowDimensions()
  return Math.floor((width - GRID_GUTTER * 2 - GRID_GAP) / 2)
}

export function GridSkeleton() {
  const w = useGridCardWidth()
  return (
    <View style={s.skeleton} accessibilityLabel="Loading" accessibilityRole="progressbar">
      {[0, 1, 2, 3, 4, 5].map(i => (
        <View key={i} style={[s.skeletonCard, { width: w }]}>
          <View style={{ width: w - 2, height: w - 2, backgroundColor: t.surface2 }} />
          <View style={{ padding: 11, gap: 7 }}>
            <View style={[s.bar, { width: '45%', height: 14 }]} />
            <View style={[s.bar, { width: '90%', height: 12 }]} />
            <View style={[s.bar, { width: '55%', height: 11 }]} />
          </View>
        </View>
      ))}
    </View>
  )
}

const s = StyleSheet.create({
  back: {
    width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center',
    backgroundColor: alpha(t.bg, 0.55), borderWidth: 1, borderColor: t.border,
  },
  stats: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: 8, rowGap: 4 },
  stat: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { fontFamily: fonts.sans, fontSize: font.size.small, color: t.text4 },
  statLabel: { fontFamily: fonts.sans, fontSize: font.size.small + 1, color: t.text3 },
  statValue: { fontFamily: fonts.monoMedium, fontVariant: ['tabular-nums'] },
  input: {
    height: 44, paddingLeft: 36, paddingRight: 14,
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
    fontFamily: fonts.sans, fontSize: font.size.callout, color: t.text1,
  },
  clear: {
    width: 44, height: 44, alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingVertical: 8, paddingHorizontal: 13, borderRadius: radius.pill, borderWidth: 1,
  },
  count: { fontFamily: fonts.mono, fontSize: font.size.caption, fontVariant: ['tabular-nums'] },
  activeChip: {
    flexDirection: 'row', alignItems: 'center', gap: 5, maxWidth: 190,
    paddingVertical: 6, paddingLeft: 11, paddingRight: 8, borderRadius: radius.pill,
    backgroundColor: t.accentTint, borderWidth: 1, borderColor: t.accentDim,
  },
  activeText: { flexShrink: 1, fontFamily: fonts.sansSemibold, fontSize: font.size.small, color: t.accent },
  // Opaque: cards scrolling under it showed through at 96%.
  toolbar: { backgroundColor: t.bg, borderBottomWidth: 1, borderBottomColor: t.border },
  toolButton: {
    flexDirection: 'row', alignItems: 'center', gap: 7,
    paddingVertical: 8, paddingHorizontal: 14, borderRadius: radius.pill, borderWidth: 1,
  },
  toolText: { fontFamily: fonts.sansMedium, fontSize: font.size.small + 1, color: t.text1 },
  clearText: {
    fontFamily: fonts.sans, fontSize: font.size.small, color: t.text2,
    textDecorationLine: 'underline', paddingHorizontal: 2,
  },
  switch: {
    flexDirection: 'row', gap: 2, padding: 2, flexShrink: 0,
    backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  switchOption: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingVertical: 5, paddingHorizontal: 9, borderRadius: radius.sm,
  },
  skeleton: {
    flexDirection: 'row', flexWrap: 'wrap', gap: GRID_GAP,
    paddingTop: 18, paddingHorizontal: GRID_GUTTER, paddingBottom: space[8],
  },
  skeletonCard: {
    backgroundColor: t.surface1, borderRadius: radius.lg, borderWidth: 1, borderColor: t.border, overflow: 'hidden',
  },
  bar: { backgroundColor: t.surface2, borderRadius: radius.xs },
})
