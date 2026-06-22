/* ============================================================================
   ui.tsx — small presentational primitives shared across the customer portal.
   Encodes the refined design language (tokens from theme.ts) so screens stay
   consistent: image plates, skeletons, feed states, pills, tactile press.
   ========================================================================== */

import { useState } from 'react'
import type { CSSProperties, ReactNode, PointerEvent } from 'react'
import { t, radius, motion, font, categoryColor, categoryImage, alpha } from '../theme'

/* ── Spinner ───────────────────────────────────────────────────────────────── */

export function Spinner({ size = 18, color = t.text3 }: { size?: number; color?: string }) {
  return (
    <span
      aria-hidden
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        border: `2px solid ${alpha('#ffffff', 0.12)}`,
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
}: {
  kind: 'loading' | 'error' | 'empty'
  message: string
  hint?: string
  icon?: ReactNode
  style?: CSSProperties
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        minHeight: 200,
        padding: '0 32px',
        textAlign: 'center',
        ...style,
      }}
    >
      {kind === 'loading' ? (
        <Spinner size={22} />
      ) : (
        <div style={{ fontSize: 34, lineHeight: 1 }}>{icon ?? (kind === 'error' ? '⚠️' : '✨')}</div>
      )}
      <div
        style={{
          color: kind === 'error' ? t.danger : t.text2,
          fontSize: font.size.callout,
          fontWeight: font.weight.semibold,
        }}
      >
        {message}
      </div>
      {hint && (
        <div style={{ color: t.text4, fontSize: font.size.small, lineHeight: 1.5, maxWidth: 280 }}>
          {hint}
        </div>
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
  const pad = size === 'md' ? '4px 11px' : '3px 9px'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        background: colored && c ? alphaVar(c, 0.14) : 'var(--surface-2)',
        border: `1px solid ${colored && c ? alphaVar(c, 0.5) : 'var(--border)'}`,
        color: colored && c ? c : t.text3,
        fontSize: font.size.micro,
        fontWeight: font.weight.bold,
        letterSpacing: '0.05em',
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
      {category}
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
  const fallbackImg = categoryImage(category)
  const showSrc = src && !errored ? src : undefined
  const c = categoryColor(category)

  return (
    <div
      style={{
        position: 'relative',
        height,
        aspectRatio: height ? undefined : '1 / 1',
        background: 'var(--tile)',
        borderRadius: r,
        overflow: 'hidden',
        boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.06)',
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
          style={{ width: '100%', height: '100%', objectFit: 'contain', padding: pad, boxSizing: 'border-box' }}
        />
      ) : fallbackImg ? (
        <img
          src={fallbackImg}
          alt={alt}
          style={{ width: '100%', height: '100%', objectFit: 'contain', padding: pad, boxSizing: 'border-box', opacity: 0.92 }}
        />
      ) : (
        <span style={{ fontSize: 26, color: c, opacity: 0.85 }}>🌿</span>
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
            fontSize: font.size.title,
            fontWeight: font.weight.bold,
            letterSpacing: '-0.01em',
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
            color: t.accent,
            fontSize: font.size.small,
            fontWeight: font.weight.semibold,
            cursor: 'pointer',
            padding: '4px 0',
            whiteSpace: 'nowrap',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            transition: `color var(--t-fast)`,
          }}
        >
          {action} <span aria-hidden>→</span>
        </button>
      )}
    </div>
  )
}

/* ── Label — uppercase micro section label ─────────────────────────────────── */

export function Label({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        color: t.text3,
        fontSize: font.size.caption,
        fontWeight: font.weight.bold,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/* ── ClassificationTag — indica / sativa / hybrid pill ─────────────────────── */

export const CLASSIFICATION_COLORS: Record<string, string> = {
  indica: '#9c6ade',
  sativa: '#f0655a',
  hybrid: '#5bb85f',
}

export function ClassificationTag({ classification }: { classification: string }) {
  return (
    <Pill color={CLASSIFICATION_COLORS[classification] ?? '#7a8a99'} tone="category">
      {classification}
    </Pill>
  )
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
          color: t.text3, fontWeight: font.weight.bold, fontSize: font.size.caption,
          textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: open ? 10 : 0,
        }}
      >
        {title}
        <span style={{ color: t.text4, fontSize: 14, transform: open ? 'rotate(90deg)' : 'none', transition: `transform var(--t-fast)` }}>›</span>
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
      <span style={{ color: t.text1, fontSize: font.size.small, fontWeight: font.weight.semibold, textAlign: 'right', textTransform: 'capitalize' }}>{value}</span>
    </div>
  )
}
