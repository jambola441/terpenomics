/* ============================================================================
   theme.ts — typed accessors for the design tokens declared in index.css.
   Values are `var(--token)` strings so the CSS file stays the single source of
   truth; these can be dropped straight into inline `style={{...}}` props.
   ========================================================================== */

export const t = {
  // Surfaces
  bg: 'var(--bg)',
  surface1: 'var(--surface-1)',
  surface2: 'var(--surface-2)',
  surface3: 'var(--surface-3)',
  tile: 'var(--tile)',

  // Borders
  border: 'var(--border)',
  borderStrong: 'var(--border-strong)',

  // Text ramp
  text1: 'var(--text-1)',
  text2: 'var(--text-2)',
  text3: 'var(--text-3)',
  text4: 'var(--text-4)',

  // Accent
  accent: 'var(--accent)',
  accentStrong: 'var(--accent-strong)',
  accentDim: 'var(--accent-dim)',
  accentInk: 'var(--accent-ink)',
  accentTint: 'var(--accent-tint)',

  // Semantic
  danger: 'var(--danger)',
  success: 'var(--success)',
  warning: 'var(--warning)',
} as const

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

/** Type scale — semantic sizes (px) + weights. */
export const font = {
  size: {
    micro: 10,
    caption: 11,
    small: 12,
    body: 14,
    callout: 15,
    title: 17,
    heading: 20,
    display: 24,
    hero: 28,
  },
  weight: {
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
    heavy: 800,
  },
} as const

/* ── Category system ───────────────────────────────────────────────────────── */

export const CATEGORY_COLORS: Record<string, string> = {
  flower: '#5bb85f',
  cart: '#3b9bf0',
  vaporizers: '#3b9bf0',
  edible: '#ff9f43',
  concentrate: '#a958d8',
  preroll: '#22c3d6',
  tincture: '#8bc34a',
  topical: '#f0655a',
  merch: '#7a8a99',
  other: '#9aa0a6',
}

export const CATEGORY_IMAGES: Record<string, string> = {
  flower: '/flower.png',
  cart: '/cart.png',
  vaporizers: '/cart.png',
  preroll: '/preroll.png',
  tincture: '/tincture.png',
  edible: '/edible.png',
  concentrate: '/concentrate.png',
}

export function categoryColor(category: string | null | undefined): string {
  if (!category) return CATEGORY_COLORS.other
  return CATEGORY_COLORS[category] ?? CATEGORY_COLORS.other
}

export function categoryImage(category: string | null | undefined): string | undefined {
  if (!category) return undefined
  return CATEGORY_IMAGES[category]
}

/** Translate `#rrggbb` + alpha (0..1) into an rgba() string for tints. */
export function alpha(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}
