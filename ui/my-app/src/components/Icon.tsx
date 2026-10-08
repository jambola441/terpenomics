/* ============================================================================
   Icon.tsx — renders a glyph from design/icons.ts as inline SVG.

   Icons inherit the text colour around them unless given one, and are hidden
   from assistive tech unless given a `label` — most sit next to words that
   already say what they mean.
   ========================================================================== */

import { createElement, type CSSProperties } from 'react'
import { icons, type IconName } from '../design/icons'
import { categoryStyle } from '../design/tokens'

export type { IconName }

export function Icon({
  name,
  size = 20,
  color,
  strokeWidth = 1.75,
  label,
  style,
}: {
  name: IconName
  size?: number
  color?: string
  strokeWidth?: number
  /** Accessible name; omit when adjacent text already names the action. */
  label?: string
  style?: CSSProperties
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      style={{ display: 'inline-block', flexShrink: 0, verticalAlign: 'middle', color, ...style }}
    >
      {icons[name].map(([tag, attrs], i) => createElement(tag, { key: i, ...attrs }))}
    </svg>
  )
}

/** The glyph for a product category (bud, cone, cartridge…). */
export function CategoryIcon({
  category,
  size = 20,
  color,
  strokeWidth,
  style,
}: {
  category: string | null | undefined
  size?: number
  /** Defaults to the category's own colour. */
  color?: string
  strokeWidth?: number
  style?: CSSProperties
}) {
  const c = categoryStyle(category)
  return (
    <Icon
      name={c.icon as IconName}
      size={size}
      color={color ?? c.color}
      strokeWidth={strokeWidth}
      style={style}
    />
  )
}

/** The Terpenomics mark — terpene ring and resin bead — with an optional
 *  wordmark beside it. */
export function Logo({
  size = 28,
  wordmark = true,
  color = 'var(--accent)',
  textColor = 'var(--text-1)',
  style,
}: {
  size?: number
  wordmark?: boolean
  color?: string
  textColor?: string
  style?: CSSProperties
}) {
  return (
    <span
      role="img"
      aria-label="Terpenomics"
      style={{ display: 'inline-flex', alignItems: 'center', gap: Math.round(size * 0.32), ...style }}
    >
      <Icon name="mark" size={size} color={color} strokeWidth={1.9} />
      {wordmark && (
        <span
          aria-hidden
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            fontSize: Math.round(size * 0.82),
            letterSpacing: '-0.02em',
            lineHeight: 1,
            color: textColor,
          }}
        >
          terpenomics
        </span>
      )}
    </span>
  )
}
