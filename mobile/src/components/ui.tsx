// Small presentational primitives shared across the app — the twins of the
// web portal's components/ui.tsx, so both platforms read as one product:
// feed states, buttons, the product plate, mono-caps pills, subway bullets for
// stores and strain types, and the terpene profile. Colours are roles from
// lib/theme (which reads @web/design/tokens); text uses the type presets.

import { useState, type ReactNode } from 'react'
import {
  ActivityIndicator, Pressable, StyleSheet, Text, View,
  type StyleProp, type TextStyle, type ViewStyle,
} from 'react-native'
import { Image } from 'expo-image'
import { formatDollars } from '@web/utils/format'
import { alpha, categories, categoryStyle, strains, terpeneStyle } from '@web/design/tokens'
import { boroughColor, NYC_COLOR } from '@web/utils/boroughs'
import { CategoryIcon, Icon, type IconName } from './Icon'
import { t, radius, space, font, fonts, type } from '@/lib/theme'

/** DESIGN.md: inputs and buttons take radius 8–10; buttons sit at 10. */
const BUTTON_RADIUS = 10

/* ── FeedState — loading / error / empty, so every screen fails the same way ── */

export function FeedState({ loading, error, empty, hint, icon, onRetry, style }: {
  loading?: boolean
  error?: string | null
  empty?: string | null
  /** A quieter second line under the message. */
  hint?: string | null
  /** Glyph in the disc; defaults to `alert` for errors and `leaf` when empty. */
  icon?: IconName
  onRetry?: () => void
  style?: StyleProp<ViewStyle>
}) {
  if (loading) {
    return (
      <View style={[styles.center, style]}>
        <ActivityIndicator color={t.text3} />
      </View>
    )
  }
  const message = error || empty
  if (!message) return null
  const failed = !!error
  return (
    <View style={[styles.center, style]}>
      <View
        style={[
          s.disc,
          failed
            ? { backgroundColor: t.dangerTint, borderColor: t.dangerEdge }
            : { backgroundColor: t.surface2, borderColor: t.border },
        ]}
      >
        <Icon name={icon ?? (failed ? 'alert' : 'leaf')} size={22} color={failed ? t.danger : t.text3} />
      </View>
      <Text style={[s.feedMessage, failed && { color: t.danger }]}>{message}</Text>
      {hint ? <Text style={s.feedHint}>{hint}</Text> : null}
      {failed && onRetry ? (
        <Button title="Try again" icon="refresh" variant="secondary" onPress={onRetry} style={{ marginTop: space[3] }} />
      ) : null}
    </View>
  )
}

/* ── Button — resin primary, hairline secondary, ember danger ───────────────── */

export function Button({ title, onPress, disabled, loading, variant = 'primary', icon, style }: {
  title: string
  onPress: () => void
  disabled?: boolean
  loading?: boolean
  variant?: 'primary' | 'secondary' | 'danger'
  icon?: IconName
  style?: StyleProp<ViewStyle>
}) {
  const primary = variant === 'primary'
  const ink = primary ? t.accentInk : variant === 'danger' ? t.danger : t.text1
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!(disabled || loading), busy: !!loading }}
      style={({ pressed }) => [
        s.button,
        primary
          ? { backgroundColor: pressed ? t.accentStrong : t.accent }
          : {
              borderWidth: 1,
              borderColor: variant === 'danger' ? t.dangerEdge : t.borderStrong,
              backgroundColor: pressed ? t.surface2 : 'transparent',
            },
        (disabled || loading) && { opacity: 0.45 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={ink} />
      ) : (
        <View style={s.buttonInner}>
          {icon ? <Icon name={icon} size={18} color={ink} strokeWidth={2} /> : null}
          <Text style={[type.button, { color: ink, fontFamily: primary ? fonts.sansBold : fonts.sansSemibold }]}>
            {title}
          </Text>
        </View>
      )}
    </Pressable>
  )
}

/* ── Price — paper white, tabular ──────────────────────────────────────────── */

export function Price({ cents, style }: { cents: number | null | undefined; style?: StyleProp<TextStyle> }) {
  return <Text style={[type.price, style]}>{cents == null ? '—' : formatDollars(cents)}</Text>
}

/* ── ProductImage — the light plate product photos sit on ──────────────────── */

/** Photos sit on a light square plate, as on the web. With no photo (or one
 *  that fails to load) the category's glyph is sketched on the plate instead
 *  of a stock photo of some other product. */
export function ProductImage({ uri, size, category, radius: r }: {
  uri: string | null | undefined
  size: number
  category?: string | null
  radius?: number
}) {
  const [failed, setFailed] = useState<string | null>(null)
  const showPhoto = !!uri && failed !== uri
  const pad = size >= 120 ? 10 : 4
  return (
    <View
      style={[
        s.plate,
        { width: size, height: size, borderRadius: r ?? (size >= 120 ? radius.lg : radius.md) },
      ]}
    >
      {showPhoto ? (
        <Image
          source={{ uri }}
          style={{ width: size - pad * 2, height: size - pad * 2 }}
          contentFit="contain"
          onError={() => setFailed(uri)}
        />
      ) : (
        <CategoryIcon
          category={category}
          color={t.tileInk}
          strokeWidth={1.25}
          size={Math.max(24, Math.min(56, Math.round(size * 0.32)))}
          style={{ opacity: 0.55 }}
        />
      )}
    </View>
  )
}

/* ── SectionTitle — Fraunces 20, with an optional quiet "See all ›" ─────────── */

export function SectionTitle({ children, action, onAction, style }: {
  children: ReactNode
  action?: string
  onAction?: () => void
  style?: StyleProp<ViewStyle>
}) {
  return (
    <View style={[s.sectionHeader, style]}>
      <Text style={[type.title, { flexShrink: 1 }]} numberOfLines={1} accessibilityRole="header">
        {children}
      </Text>
      {action && onAction ? (
        <Pressable onPress={onAction} hitSlop={8} style={s.sectionAction} accessibilityRole="button">
          <Text style={type.link}>{action}</Text>
          <Icon name="chevron-right" size={15} color={t.text2} />
        </Pressable>
      ) : null}
    </View>
  )
}

/* ── Label — the mono eyebrow ──────────────────────────────────────────────── */

export function Label({ children, style }: { children: ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[type.label, style]}>{children}</Text>
}

/* ── Pill — mono caps tag: tinted fill at 10%, edge at 36% ──────────────────── */

export type Tone = 'neutral' | 'accent' | 'success' | 'danger' | 'warning' | 'info'

const TONES: Record<Exclude<Tone, 'neutral'>, { fg: string; bg: string; edge: string }> = {
  accent: { fg: t.accent, bg: t.accentTint, edge: alpha(t.accent, 0.36) },
  success: { fg: t.success, bg: t.successTint, edge: t.successEdge },
  danger: { fg: t.danger, bg: t.dangerTint, edge: t.dangerEdge },
  warning: { fg: t.warning, bg: t.warningTint, edge: t.warningEdge },
  info: { fg: t.info, bg: t.infoTint, edge: t.infoEdge },
}

export function Pill({ children, color, tone = 'neutral', icon, size = 'sm', style }: {
  children: ReactNode
  /** An explicit hue (e.g. a category's); overrides `tone`. */
  color?: string
  tone?: Tone
  /** Leading glyph, drawn in the pill's colour. */
  icon?: ReactNode | IconName
  size?: 'sm' | 'md'
  style?: StyleProp<ViewStyle>
}) {
  const c = color
    ? { fg: color, bg: alpha(color, 0.1), edge: alpha(color, 0.36) }
    : tone === 'neutral'
      ? { fg: t.text2, bg: t.surface2, edge: t.border }
      : TONES[tone]
  const glyph = typeof icon === 'string'
    ? <Icon name={icon as IconName} size={size === 'md' ? 13 : 12} color={c.fg} strokeWidth={2} />
    : icon
  return (
    <View
      style={[
        s.pill,
        { backgroundColor: c.bg, borderColor: c.edge, paddingHorizontal: size === 'md' ? 10 : 8, paddingVertical: size === 'md' ? 4 : 3 },
        style,
      ]}
    >
      {glyph}
      <Text
        numberOfLines={1}
        style={[type.label, { color: c.fg, fontSize: size === 'md' ? font.size.caption : font.size.micro + 0.5, lineHeight: 13 }]}
      >
        {children}
      </Text>
    </View>
  )
}

/** The name a category goes by: the design's label ("Vapes", "Pre-rolls")
 *  when it is one we know, else the catalogue's own word, capitalised. */
export function categoryName(name: string): string {
  const c = categoryStyle(name)
  return c === categories.other && name.toLowerCase() !== 'other' ? name.charAt(0).toUpperCase() + name.slice(1) : c.label
}

/** A category as a pill: its hue, its glyph, its name. */
export function CategoryTag({ category, size = 'sm', style }: {
  category: string
  size?: 'sm' | 'md'
  style?: StyleProp<ViewStyle>
}) {
  const c = categoryStyle(category)
  return (
    <Pill
      color={c.color}
      size={size}
      style={style}
      icon={<CategoryIcon category={category} size={size === 'md' ? 13 : 12} strokeWidth={2} />}
    >
      {c.label}
    </Pill>
  )
}

/* ── Bullet — the subway-style disc ────────────────────────────────────────── */

export function Bullet({ letter, color, size = 28, ink = t.text1, style }: {
  letter: string
  color: string
  size?: number
  /** Letter colour; dark ink on light discs. */
  ink?: string
  style?: StyleProp<ViewStyle>
}) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: color, alignItems: 'center', justifyContent: 'center' }, style]}
    >
      <Text
        allowFontScaling={false}
        style={{ fontFamily: fonts.sansBold, fontSize: Math.round(size * 0.5), lineHeight: Math.round(size * 0.62), color: ink }}
      >
        {letter}
      </Text>
    </View>
  )
}

/** A store's avatar: its initial on its borough's MTA line colour, as on the map. */
export function StoreBullet({ name, address, size = 28, style }: {
  name: string
  address?: string | null
  size?: number
  style?: StyleProp<ViewStyle>
}) {
  const c = boroughColor(address)
  const letter = (name.replace(/^the\s+/i, '').match(/[A-Za-z0-9]/)?.[0] ?? '·').toUpperCase()
  // N/Q/R/W yellow carries a dark letter on the real signs too.
  return <Bullet letter={letter} color={c} size={size} ink={c === NYC_COLOR ? t.bg : t.text1} style={style} />
}

/** Indica / sativa / hybrid as a lettered bullet, not another coloured pill. */
export function ClassificationTag({ classification }: { classification: string }) {
  const st = strains[classification.toLowerCase()]
  if (!st) return <Pill>{classification}</Pill>
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <Bullet letter={st.letter} color={st.color} size={17} ink={t.accentInk} />
      <Text style={[type.meta, { color: t.text2, fontFamily: fonts.sansMedium }]}>{st.label}</Text>
    </View>
  )
}

/** Lab percentages to at most two decimals ("0.45%", "1.2%"). */
export function formatPercent(p: number): string {
  return `${Number(p.toFixed(2))}%`
}

/* ── TerpeneProfile — the chart the product is named after ─────────────────── */
/* One labelled row per terpene, strongest first, with a bar whose length is
   its share of the strongest. Name and number carry identity; the colour
   (what the terpene smells like) is the second cue, never the only one. */

export function TerpeneProfile({ terpenes }: { terpenes: { name: string; percent?: number | null }[] }) {
  const rows = [...terpenes].sort((a, b) => (b.percent ?? -1) - (a.percent ?? -1))
  const max = Math.max(0, ...rows.map(r => r.percent ?? 0))

  if (max <= 0) {
    return (
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
        {rows.map((tp, i) => {
          const st = terpeneStyle(tp.name)
          return (
            <View key={`${tp.name}-${i}`} style={s.terpeneChip}>
              <View style={[s.dot, { backgroundColor: st.color }]} />
              <Text style={[type.meta, { color: t.text1 }]}>{st.name}</Text>
            </View>
          )
        })}
      </View>
    )
  }

  return (
    <View style={{ gap: space[3] }} accessibilityRole="list">
      {rows.map((tp, i) => {
        const st = terpeneStyle(tp.name)
        const share = tp.percent != null ? tp.percent / max : 0
        return (
          <View
            key={`${tp.name}-${i}`}
            accessible
            accessibilityLabel={tp.percent != null ? `${st.name}, ${formatPercent(tp.percent)}` : st.name}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[2] }}>
              <View style={[s.dot, { backgroundColor: st.color }]} />
              <Text style={type.bodyStrong}>{st.name}</Text>
              {st.aroma ? (
                <Text numberOfLines={1} style={[type.meta, { flexShrink: 1 }]}>{st.aroma}</Text>
              ) : null}
              <Text style={[type.mono, { marginLeft: 'auto' }]}>{tp.percent != null ? formatPercent(tp.percent) : '—'}</Text>
            </View>
            <View style={s.track}>
              <View style={{ width: `${Math.max(2, share * 100)}%`, height: '100%', borderRadius: 4, backgroundColor: st.color }} />
            </View>
          </View>
        )
      })}
    </View>
  )
}

/* ── Shared styles ─────────────────────────────────────────────────────────── */

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10, padding: space[7], backgroundColor: t.bg },
  muted: { ...type.body, color: t.text3, textAlign: 'center' },
  /** A raised surface is separated by its edge, not a shadow. */
  card: { backgroundColor: t.surface1, borderRadius: radius.lg, borderWidth: 1, borderColor: t.border },
  name: type.bodyStrong,
  meta: type.meta,
  input: {
    ...type.input,
    backgroundColor: t.surface2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: t.border,
    paddingHorizontal: space[4],
    minHeight: 52,
  },
})

const s = StyleSheet.create({
  disc: {
    width: 48, height: 48, borderRadius: 24, borderWidth: 1, marginBottom: 4,
    alignItems: 'center', justifyContent: 'center',
  },
  feedMessage: { ...type.bodyStrong, fontSize: font.size.callout, lineHeight: 21, textAlign: 'center' },
  feedHint: { ...type.meta, fontSize: font.size.small + 1, lineHeight: 19, textAlign: 'center', maxWidth: 300 },
  button: {
    minHeight: 48,
    borderRadius: BUTTON_RADIUS,
    paddingHorizontal: space[5],
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonInner: { flexDirection: 'row', alignItems: 'center', gap: space[2] },
  plate: { backgroundColor: t.tile, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  sectionHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space[3],
    paddingHorizontal: space[4], marginTop: space[6], marginBottom: space[3],
  },
  sectionAction: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  pill: {
    flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 5,
    borderWidth: 1, borderRadius: radius.pill,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  terpeneChip: {
    flexDirection: 'row', alignItems: 'center', gap: 7,
    backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border, borderRadius: radius.pill,
    paddingVertical: 6, paddingLeft: 10, paddingRight: 12,
  },
  track: { marginTop: 6, height: 4, borderRadius: 4, backgroundColor: t.surface2, overflow: 'hidden' },
})
