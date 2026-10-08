/* ============================================================================
   ui.tsx — small presentational primitives shared across the customer portal.
   Encodes the design language (tokens from theme.ts, glyphs from Icon.tsx) so
   screens stay consistent: image plates, skeletons, feed states, tags, store
   bullets, the terpene profile, tactile press.
   ========================================================================== */

import { useState } from 'react'
import type { CSSProperties, ReactNode, PointerEvent } from 'react'
import { t, radius, font, categoryColor, categoryLabel, alpha } from '../theme'
import { strains, terpeneStyle } from '../design/tokens'
import { icons } from '../design/icons'
import { Icon, CategoryIcon, type IconName } from './Icon'
import { boroughColor, NYC_COLOR } from '../utils/boroughs'

/* ── Spinner ───────────────────────────────────────────────────────────────── */

export function Spinner({ size = 18, color = t.text3 }: { size?: number; color?: string }) {
  return (
    <span
      aria-hidden
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        border: `2px solid ${alpha('#f2f0e9', 0.12)}`,
        borderTopColor: color,
        borderRadius: '50%',
        animation: 'ds-spin 0.7s linear infinite',
      }}
    />
  )
}

/* ── Skeleton (shimmer placeholder) ────────────────────────────────────────── */

export function Skeleton({
  width = '100%',
  height = 14,
  radius: r = radius.sm,
  style,
}: {
  width?: number | string
  height?: number | string
  radius?: string
  style?: CSSProperties
}) {
  return (
    <div
      style={{
        width,
        height,
        borderRadius: r,
        background:
          'linear-gradient(90deg, var(--surface-1) 25%, var(--surface-2) 37%, var(--surface-1) 63%)',
        backgroundSize: '400% 100%',
        animation: 'ds-shimmer 1.4s ease infinite',
        ...style,
      }}
    />
  )
}

/* ── FeedState — centered loading / error / empty ──────────────────────────── */

export function FeedState({
  kind,
  message,
  hint,
  icon,
  style,
  onRetry,
}: {
  kind: 'loading' | 'error' | 'empty'
  message: string
  hint?: string
  /** A glyph name from design/icons.ts, or any node. */
  icon?: IconName | ReactNode
  style?: CSSProperties
  /** Offers "Try again". An error with nothing to press is a dead end. */
  onRetry?: () => void
}) {
  const glyph = typeof icon === 'string' && icon in icons
    ? <Icon name={icon as IconName} size={22} />
    : icon ?? <Icon name={kind === 'error' ? 'alert' : 'leaf'} size={22} />
  return (
    <div
      // Announced, so a screen reader hears that loading finished or failed.
      role={kind === 'error' ? 'alert' : 'status'}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        minHeight: 200,
        padding: '0 32px',
        textAlign: 'center',
        ...style,
      }}
    >
      {kind === 'loading' ? (
        <Spinner size={22} />
      ) : (
        <div
          style={{
            width: 48, height: 48, borderRadius: '50%', marginBottom: 4,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: kind === 'error' ? t.dangerTint : t.surface2,
            border: `1px solid ${kind === 'error' ? t.dangerEdge : t.border}`,
            color: kind === 'error' ? t.danger : t.text3,
          }}
        >
          {glyph}
        </div>
      )}
      <div
        style={{
          color: kind === 'error' ? t.danger : t.text1,
          fontSize: font.size.callout,
          fontWeight: font.weight.semibold,
        }}
      >
        {message}
      </div>
      {hint && (
        <div style={{ color: t.text3, fontSize: font.size.small + 1, lineHeight: 1.5, maxWidth: 300 }}>
          {hint}
        </div>
      )}
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            marginTop: 6, minHeight: 44, padding: '0 20px', borderRadius: radius.md,
            background: t.surface2, border: `1px solid ${t.borderStrong}`, color: t.text1,
            fontSize: font.size.body, fontWeight: font.weight.semibold, cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: 8,
          }}
        >
          <Icon name="refresh" size={16} />
          Try again
        </button>
      )}
    </div>
  )
}

/* ── Pill / badge ──────────────────────────────────────────────────────────── */

export function Pill({
  children,
  color,
  tone = 'neutral',
  size = 'sm',
  style,
}: {
  children: ReactNode
  /** explicit color (e.g. a category color); overrides tone */
  color?: string
  tone?: 'neutral' | 'accent' | 'category'
  size?: 'sm' | 'md'
  style?: CSSProperties
}) {
  const c = color ?? (tone === 'accent' ? 'var(--accent)' : null)
  const colored = tone === 'category' || tone === 'accent' || !!color
  const pad = size === 'md' ? '4px 10px' : '3px 8px'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        background: colored && c ? alphaVar(c, 0.1) : 'var(--surface-2)',
        border: `1px solid ${colored && c ? alphaVar(c, 0.36) : 'var(--border)'}`,
        color: colored && c ? c : t.text2,
        fontFamily: font.family.mono,
        fontSize: size === 'md' ? font.size.caption : font.size.micro + 0.5,
        fontWeight: font.weight.medium,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        padding: pad,
        borderRadius: radius.pill,
        lineHeight: 1.2,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </span>
  )
}

/* category colors are real hex; CSS-var accent needs color-mix for alpha */
function alphaVar(color: string, a: number): string {
  if (color.startsWith('#')) return alpha(color, a)
  // CSS variable or named color → use color-mix (widely supported)
  return `color-mix(in srgb, ${color} ${Math.round(a * 100)}%, transparent)`
}

/* ── CategoryTag — convenience pill bound to the category palette ──────────── */

export function CategoryTag({ category, size = 'sm', style }: { category: string; size?: 'sm' | 'md'; style?: CSSProperties }) {
  return (
    <Pill color={categoryColor(category)} tone="category" size={size} style={style}>
      <CategoryIcon category={category} size={size === 'md' ? 13 : 12} strokeWidth={2} />
      {categoryLabel(category)}
    </Pill>
  )
}

/* ── Pressable — tactile wrapper (scale + dim on press, hover lift) ─────────── */

export function Pressable({
  children,
  onClick,
  style,
  lift = false,
  disabled = false,
}: {
  children: ReactNode
  onClick?: () => void
  style?: CSSProperties
  /** raise elevation slightly on hover (pointer devices) */
  lift?: boolean
  disabled?: boolean
}) {
  const [pressed, setPressed] = useState(false)
  const [hover, setHover] = useState(false)

  const down = (e: PointerEvent) => {
    if (disabled) return
    if (e.pointerType === 'mouse' && e.button !== 0) return
    setPressed(true)
  }
  const up = () => setPressed(false)

  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick && !disabled ? 0 : undefined}
      onClick={disabled ? undefined : onClick}
      onKeyDown={
        onClick && !disabled
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onClick()
              }
            }
          : undefined
      }
      onPointerDown={down}
      onPointerUp={up}
      onPointerLeave={() => {
        up()
        setHover(false)
      }}
      onPointerCancel={up}
      onPointerEnter={(e) => e.pointerType === 'mouse' && setHover(true)}
      style={{
        cursor: disabled ? 'default' : onClick ? 'pointer' : undefined,
        transform: pressed ? 'scale(0.975)' : 'none',
        filter: pressed ? 'brightness(1.08)' : 'none',
        boxShadow: lift && hover && !pressed ? 'var(--e-2)' : undefined,
        transition: `transform var(--t-fast), filter var(--t-fast), box-shadow var(--t-base)`,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/* ── ProductImage — the unified light "plate" that tames glaring photos ─────── */

export function ProductImage({
  src,
  alt = '',
  category,
  height,
  radius: r = radius.lg,
  pad = 10,
  style,
}: {
  src?: string | null
  alt?: string
  category?: string | null
  height?: number | string
  radius?: string
  pad?: number
  style?: CSSProperties
}) {
  const [errored, setErrored] = useState(false)
  const showSrc = src && !errored ? src : undefined

  return (
    <div
      style={{
        position: 'relative',
        height,
        aspectRatio: height ? undefined : '1 / 1',
        background: 'var(--tile)',
        borderRadius: r,
        overflow: 'hidden',
        boxShadow: 'inset 0 0 0 1px rgba(34, 21, 5, 0.06)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        ...style,
      }}
    >
      {showSrc ? (
        <img
          src={showSrc}
          alt={alt}
          onError={() => setErrored(true)}
          // A grid of these can run to hundreds of cards. The frame above already
          // reserves the space, so deferring the ones below the fold costs no
          // layout shift and saves the request, the decode and the memory until
          // the shopper actually scrolls that far.
          loading="lazy"
          decoding="async"
          style={{ width: '100%', height: '100%', objectFit: 'contain', padding: pad, boxSizing: 'border-box' }}
        />
      ) : (
        // No photo: the category's glyph, drawn like a specimen sketch on the
        // plate, rather than a stock photo of some other product.
        <CategoryIcon
          category={category}
          color={t.tileInk}
          strokeWidth={1.25}
          size={typeof height === 'number' ? Math.max(24, Math.min(56, Math.round(height * 0.32))) : 44}
          style={{ opacity: 0.55 }}
        />
      )}
    </div>
  )
}

/* ── SectionHeader — consistent "Title  ·  action →" rhythm ─────────────────── */

export function SectionHeader({
  title,
  action,
  onAction,
  icon,
  style,
}: {
  title: ReactNode
  action?: string
  onAction?: () => void
  icon?: ReactNode
  style?: CSSProperties
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        {icon}
        <span
          style={{
            color: t.text1,
            fontFamily: font.family.display,
            fontSize: font.size.heading,
            fontWeight: font.weight.semibold,
            letterSpacing: '-0.015em',
            lineHeight: 1.2,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {title}
        </span>
      </div>
      {action && (
        <button
          onClick={onAction}
          style={{
            background: 'none',
            border: 'none',
            color: t.text2,
            fontSize: font.size.small + 1,
            fontWeight: font.weight.semibold,
            cursor: 'pointer',
            padding: '4px 0',
            whiteSpace: 'nowrap',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 2,
            transition: `color var(--t-fast)`,
          }}
        >
          {action} <Icon name="chevron-right" size={15} />
        </button>
      )}
    </div>
  )
}

/* ── Label — the mono eyebrow, like the field on a specimen label ──────────── */

export function Label({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        color: t.text3,
        fontFamily: font.family.mono,
        fontSize: font.size.caption,
        fontWeight: font.weight.medium,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/* ── ClassificationTag — indica / sativa / hybrid as a lettered bullet ─────── */

export const CLASSIFICATION_COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(strains).map(([k, v]) => [k, v.color]),
)

export function ClassificationTag({ classification }: { classification: string }) {
  const s = strains[classification.toLowerCase()]
  if (!s) return <Pill>{classification}</Pill>
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        color: t.text2, fontSize: font.size.small, fontWeight: font.weight.medium, lineHeight: 1,
      }}
    >
      <Bullet letter={s.letter} color={s.color} size={17} ink={t.accentInk} />
      {s.label}
    </span>
  )
}

/* ── Bullet — the subway-style disc. Stores wear their borough's MTA colour
      (as on the map); strain types wear theirs. ───────────────────────────── */

export function Bullet({
  letter,
  color,
  size = 28,
  ink = '#ffffff',
  style,
}: {
  letter: string
  color: string
  size?: number
  /** letter colour; dark ink on light discs */
  ink?: string
  style?: CSSProperties
}) {
  return (
    <span
      aria-hidden
      style={{
        width: size, height: size, borderRadius: '50%', flexShrink: 0,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: color, color: ink,
        fontFamily: font.family.sans, fontWeight: font.weight.bold,
        fontSize: Math.round(size * 0.5), lineHeight: 1,
        ...style,
      }}
    >
      {letter}
    </span>
  )
}

/** The letter a store's bullet carries — its first letter or digit, skipping a
 *  leading "The" so The Spot and Spot Cannabis don't both read "T". */
export function storeInitial(name: string): string {
  return (name.replace(/^the\s+/i, '').match(/[A-Za-z0-9]/)?.[0] ?? '·').toUpperCase()
}

/** A store's bullet: its initial on its borough's line colour. */
export function StoreBullet({ name, address, size = 28, style }: {
  name: string
  address?: string | null
  size?: number
  style?: CSSProperties
}) {
  const c = boroughColor(address)
  const letter = storeInitial(name)
  // N/Q/R/W yellow carries a black letter on the real signs too.
  return <Bullet letter={letter} color={c} size={size} ink={c === NYC_COLOR ? '#1a1a1a' : '#ffffff'} style={style} />
}

/* ── DetailBlock — uppercase-titled content section ─────────────────────────── */

export function DetailBlock({ title, children, style }: { title: string; children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={style}>
      <Label style={{ marginBottom: 10 }}>{title}</Label>
      {children}
    </div>
  )
}

/* ── CollapsibleBlock — titled section, collapsed by default ────────────────── */

export function CollapsibleBlock({ title, defaultOpen = false, children, style }: { title: string; defaultOpen?: boolean; children: ReactNode; style?: CSSProperties }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={style}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
          background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          color: t.text3, fontFamily: font.family.mono, fontWeight: font.weight.medium, fontSize: font.size.caption,
          textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: open ? 10 : 0,
        }}
      >
        {title}
        <Icon name="chevron-down" size={16} color={t.text3} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: `transform var(--t-fast)` }} />
      </button>
      {open && children}
    </div>
  )
}

/* ── SpecRow — label/value row with divider ────────────────────────────────── */

export function SpecRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '8px 0', borderBottom: `1px solid ${t.border}` }}>
      <span style={{ color: t.text3, fontSize: font.size.small }}>{label}</span>
      <span className="num" style={{ color: t.text1, fontSize: font.size.small, fontWeight: font.weight.semibold, textAlign: 'right', textTransform: 'capitalize' }}>{value}</span>
    </div>
  )
}

/* ── TerpeneProfile — the chart the product is named after ─────────────────── */
/* One labelled row per terpene, strongest first, with a bar whose length is
   its share of the strongest one. The name and number carry the identity; the
   colour (what the terpene smells like) is a second cue, never the only one. */

export function TerpeneProfile({ terpenes }: { terpenes: { name: string; percent?: number | null }[] }) {
  const rows = [...terpenes].sort((a, b) => (b.percent ?? -1) - (a.percent ?? -1))
  const max = Math.max(0, ...rows.map(r => r.percent ?? 0))
  const measured = max > 0

  if (!measured) {
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
        {rows.map((tp, i) => {
          const s = terpeneStyle(tp.name)
          return (
            <span key={`${tp.name}-${i}`} title={s.aroma || undefined} style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.pill,
              padding: '6px 12px 6px 10px', color: t.text1, fontSize: font.size.small,
            }}>
              <span aria-hidden style={{ width: 8, height: 8, borderRadius: '50%', background: s.color }} />
              {s.name}
            </span>
          )
        })}
      </div>
    )
  }

  return (
    <div role="list" style={{ display: 'grid', gap: 12 }}>
      {rows.map((tp, i) => {
        const s = terpeneStyle(tp.name)
        const share = tp.percent != null ? tp.percent / max : 0
        return (
          <div key={`${tp.name}-${i}`} role="listitem" title={tp.percent != null ? `${s.name} ${tp.percent}%` : s.name}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span aria-hidden style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, flexShrink: 0, alignSelf: 'center' }} />
              <span style={{ color: t.text1, fontSize: font.size.body, fontWeight: font.weight.semibold }}>{s.name}</span>
              {s.aroma && <span style={{ color: t.text3, fontSize: font.size.small, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.aroma}</span>}
              <span className="num" style={{ marginLeft: 'auto', color: t.text2, fontFamily: font.family.mono, fontSize: font.size.small }}>
                {tp.percent != null ? `${tp.percent}%` : '—'}
              </span>
            </div>
            <div aria-hidden style={{ marginTop: 6, height: 4, borderRadius: 4, background: t.surface2, overflow: 'hidden' }}>
              <div style={{ width: `${Math.max(2, share * 100)}%`, height: '100%', borderRadius: 4, background: s.color }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ── Page chrome ──────────────────────────────────────────────────────────── */

/** The round back control every drill-down screen opens with. `glass` for
 *  when it floats over a coloured hero or a photo. */
export function BackButton({ onClick, label = 'Back', glass = false, style }: {
  onClick: () => void
  label?: string
  glass?: boolean
  style?: CSSProperties
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 38, height: 38, borderRadius: '50%', padding: 0, flexShrink: 0,
        background: glass ? 'rgba(12, 15, 13, 0.55)' : t.surface2,
        border: `1px solid ${glass ? 'rgba(242, 240, 233, 0.12)' : t.border}`,
        color: t.text1, cursor: 'pointer',
        backdropFilter: glass ? 'blur(10px)' : undefined,
        WebkitBackdropFilter: glass ? 'blur(10px)' : undefined,
        ...style,
      }}
    >
      <Icon name="arrow-left" size={18} />
    </button>
  )
}

/** A screen's title: Fraunces at hero size, with an optional quiet line under. */
export function PageTitle({ children, sub, size = font.size.hero, style }: {
  children: ReactNode
  sub?: ReactNode
  size?: number
  style?: CSSProperties
}) {
  return (
    <div style={style}>
      <h1 style={{
        color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold,
        fontSize: size, letterSpacing: '-0.02em', lineHeight: 1.08, margin: 0,
      }}>
        {children}
      </h1>
      {sub && (
        <div style={{ color: t.text3, fontSize: font.size.small + 1, marginTop: 6 }}>{sub}</div>
      )}
    </div>
  )
}

/** A brand's avatar: its photo on the same light plate products sit on, or
 *  its initial set in the display face when there is no photo. */
export function BrandMark({ name, imageUrl, size = 62, style }: {
  name: string
  imageUrl?: string | null
  size?: number
  style?: CSSProperties
}) {
  const [errored, setErrored] = useState(false)
  const photo = imageUrl && !errored
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.24), overflow: 'hidden', flexShrink: 0,
      background: photo ? t.tile : t.surface2,
      border: `1px solid ${photo ? 'transparent' : t.border}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      ...style,
    }}>
      {photo ? (
        <img
          src={imageUrl!}
          alt=""
          loading="lazy"
          onError={() => setErrored(true)}
          style={{ width: '100%', height: '100%', objectFit: 'contain', padding: Math.round(size * 0.08), boxSizing: 'border-box' }}
        />
      ) : (
        <span aria-hidden style={{
          color: t.text2, fontFamily: font.family.display, fontWeight: font.weight.semibold,
          fontSize: Math.round(size * 0.42), lineHeight: 1,
        }}>
          {name.charAt(0).toUpperCase()}
        </span>
      )}
    </div>
  )
}
