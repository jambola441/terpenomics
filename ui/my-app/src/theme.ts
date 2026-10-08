/* ============================================================================
   theme.ts — typed accessors for the design tokens.

   The values live in design/tokens.ts and reach the page as CSS custom
   properties (design/css.ts). Everything here is a `var(--token)` string, so it
   drops straight into an inline `style={{...}}` prop and follows the tokens.
   ========================================================================== */

import {
  color as palette,
  categoryStyle,
  fontSize,
  fontWeight,
  alpha as tint,
} from './design/tokens'

export const t = {
  // Surfaces
  bg: 'var(--bg)',
  surface1: 'var(--surface-1)',
  surface2: 'var(--surface-2)',
  surface3: 'var(--surface-3)',
  tile: 'var(--tile)',
  tileLine: 'var(--tile-line)',
  tileInk: 'var(--tile-ink)',
  scrim: 'var(--scrim)',

  // Borders
  border: 'var(--border)',
  borderStrong: 'var(--border-strong)',

  // Text ramp
  text1: 'var(--text-1)',
  text2: 'var(--text-2)',
  text3: 'var(--text-3)',
  text4: 'var(--text-4)',

  // Accent (Resin)
  accent: 'var(--accent)',
  accentStrong: 'var(--accent-strong)',
  accentDim: 'var(--accent-dim)',
  accentInk: 'var(--accent-ink)',
  accentTint: 'var(--accent-tint)',

  // Signals
  danger: 'var(--danger)',
  dangerTint: 'var(--danger-tint)',
  dangerEdge: 'var(--danger-edge)',
  success: 'var(--success)',
  successTint: 'var(--success-tint)',
  successEdge: 'var(--success-edge)',
  warning: 'var(--warning)',
  warningTint: 'var(--warning-tint)',
  warningEdge: 'var(--warning-edge)',
  info: 'var(--info)',
  infoTint: 'var(--info-tint)',
  infoEdge: 'var(--info-edge)',
} as const

/** Status tones for badges and callouts: foreground, wash, edge. */
export type Tone = 'neutral' | 'accent' | 'success' | 'danger' | 'warning' | 'info'

export const tone: Record<Tone, { fg: string; bg: string; edge: string }> = {
  neutral: { fg: t.text2, bg: t.surface2, edge: t.border },
  accent: { fg: t.accent, bg: t.accentTint, edge: 'color-mix(in srgb, var(--accent) 40%, transparent)' },
  success: { fg: t.success, bg: t.successTint, edge: t.successEdge },
  danger: { fg: t.danger, bg: t.dangerTint, edge: t.dangerEdge },
  warning: { fg: t.warning, bg: t.warningTint, edge: t.warningEdge },
  info: { fg: t.info, bg: t.infoTint, edge: t.infoEdge },
}

/** Border-radius scale */
export const radius = {
  xs: 'var(--r-xs)',
  sm: 'var(--r-sm)',
  md: 'var(--r-md)',
  lg: 'var(--r-lg)',
  xl: 'var(--r-xl)',
  '2xl': 'var(--r-2xl)',
  pill: 'var(--r-pill)',
} as const

/** Spacing scale (4pt). Use the raw numbers when CSS needs computed math. */
export const space = {
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  7: 32,
  8: 40,
} as const

/** Elevation */
export const shadow = {
  e1: 'var(--e-1)',
  e2: 'var(--e-2)',
  e3: 'var(--e-3)',
  ring: 'var(--ring)',
} as const

/** Motion */
export const motion = {
  fast: 'var(--t-fast)',
  base: 'var(--t-base)',
  slow: 'var(--t-slow)',
  spring: 'var(--ease-spring)',
} as const

/** Type — families, semantic sizes (px) and weights. */
export const font = {
  family: {
    display: 'var(--font-display)',
    sans: 'var(--font-sans)',
    mono: 'var(--font-mono)',
  },
  size: fontSize,
  weight: fontWeight,
} as const

/* ── Category system ───────────────────────────────────────────────────────── */

/** Real hex (not a var) so callers can derive tints with alpha(). */
export function categoryColor(category: string | null | undefined): string {
  return categoryStyle(category).color
}

export function categoryLabel(category: string | null | undefined): string {
  return category ? categoryStyle(category).label : 'Other'
}

export { categoryStyle }

/** Translate `#rrggbb` + alpha (0..1) into an rgba() string for tints. */
export const alpha = tint

/** The raw role values, for the few places that need a real colour (canvas,
 *  map markers, meta tags) rather than a CSS variable. */
export const raw = palette
