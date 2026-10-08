/* ============================================================================
   Terpee design tokens — the single source of truth for colour, type,
   space, radius and motion, shared by the web portal and the mobile app.

   The web reads these through CSS custom properties (design/css.ts writes them
   onto :root at startup; theme.ts hands out `var(--token)` strings). The app
   imports this file directly as `@web/design/tokens`. Neither keeps a copy, so
   a change here is a change everywhere.

   Two layers, after the Uniform design system:
     palette — the named inks. Build with these only when defining a role.
     color   — the roles screens use (bg, surface, text, accent…). Screens never
               hard-code hex; if a role is missing, add it here.

   The idea, in one line: a field guide to what is on the city's shelves.
     Loam   — the near-black ground, tinted toward leaf green, not grey.
     Paper  — warm specimen-label white for text and for the photo plate.
     Resin  — the one brand colour: the amber of ripe trichomes (and of the cab
              that gets you there). Used for the primary action and very little
              else, so it keeps meaning "this is the thing to press".
     Terpene hues — every category, strain type and terpene gets a colour from
              one OKLCH ring at the same lightness, so no hue shouts over another
              and each stays legible (≥ 8:1) on the dark ground.

   Every foreground/background pair below was checked for WCAG contrast;
   the ratios are noted where they matter.
   ========================================================================== */

/* ── Palette (primitives) ─────────────────────────────────────────────────── */

export const palette = {
  // Loam — OKLCH L .165 → .335 at hue 155, chroma ~.01
  loam950: '#0c0f0d', // app ground
  loam900: '#131714', // cards, sheets
  loam850: '#1a201c', // raised: inputs, chips, hover
  loam800: '#242925', // pressed / active
  loam750: '#222723', // hairline
  loam700: '#323934', // emphasised hairline
  loam1000: '#040705', // scrim base

  // Paper — warm whites and the greys between paper and loam
  paper: '#f2f0e9', //  16.9:1 on loam950
  stone300: '#bebeb6', // 10.3:1
  stone500: '#93958d', //  6.4:1 — the lowest step allowed for readable text
  stone700: '#676a64', //  3.5:1 — placeholders, disabled, decoration only
  plate: '#f3f1ea', // the light plate product photos sit on
  plateLine: '#dad7cf',
  plateInk: '#595549',

  // Resin — the brand
  resin: '#f0b550', // 10.5:1 on loam950
  resinBright: '#f6ca70',
  resinDeep: '#ca9246',
  resinInk: '#221505', // text on resin, 9.7:1
  resinShadow: '#3f2903',

  // Signals
  leaf: '#83d494', // positive — 10.8:1
  leafShadow: '#1a3520',
  ember: '#f1735c', // danger — 6.7:1
  emberShadow: '#4b1e18',
  saffron: '#f9aa60', // caution — 10.0:1
  saffronShadow: '#45290a',
  sky: '#80c1e6', // information — 9.8:1
  skyShadow: '#103243',
} as const

/* ── Roles ────────────────────────────────────────────────────────────────── */

export const color = {
  // Surfaces, dark → light
  bg: palette.loam950,
  surface1: palette.loam900,
  surface2: palette.loam850,
  surface3: palette.loam800,
  tile: palette.plate,
  tileLine: palette.plateLine,
  tileInk: palette.plateInk,
  scrim: 'rgba(4, 7, 5, 0.72)',

  // Hairlines
  border: palette.loam750,
  borderStrong: palette.loam700,

  // Text ramp
  text1: palette.paper, // names, headings, values
  text2: palette.stone300, // readable secondary: brand, address, body copy
  text3: palette.stone500, // labels, captions, meta
  text4: palette.stone700, // placeholders, disabled, dividers-as-text

  // Accent (Resin)
  accent: palette.resin,
  accentStrong: palette.resinBright,
  accentDim: palette.resinDeep,
  accentInk: palette.resinInk,
  accentTint: 'rgba(240, 181, 80, 0.12)',

  // Signals — keep the words meaningful without the colour
  success: palette.leaf,
  successTint: 'rgba(131, 212, 148, 0.12)',
  successEdge: 'rgba(131, 212, 148, 0.38)',
  danger: palette.ember,
  dangerTint: 'rgba(241, 115, 92, 0.12)',
  dangerEdge: 'rgba(241, 115, 92, 0.42)',
  warning: palette.saffron,
  warningTint: 'rgba(249, 170, 96, 0.12)',
  warningEdge: 'rgba(249, 170, 96, 0.40)',
  info: palette.sky,
  infoTint: 'rgba(128, 193, 230, 0.12)',
  infoEdge: 'rgba(128, 193, 230, 0.38)',
} as const

export type ColorRole = keyof typeof color

/* ── Categories ───────────────────────────────────────────────────────────── */
/* One ring of hues at OKLCH L .78, chroma ≤ .10. Each category also has a
   glyph from design/icons.ts drawn for its form factor, so the colour is never
   the only thing telling two categories apart. */

export type CategoryStyle = { label: string; color: string; icon: string }

export const categories: Record<string, CategoryStyle> = {
  flower: { label: 'Flower', color: '#8bc993', icon: 'bud' },
  preroll: { label: 'Pre-rolls', color: '#ccb391', icon: 'preroll' },
  vaporizers: { label: 'Vapes', color: '#82c1e2', icon: 'cart' },
  edible: { label: 'Edibles', color: '#ef9cab', icon: 'gummy' },
  concentrate: { label: 'Concentrates', color: '#d2a3e1', icon: 'crystal' },
  tincture: { label: 'Tinctures', color: '#77c8c4', icon: 'dropper' },
  topical: { label: 'Topicals', color: '#eda382', icon: 'tube' },
  merch: { label: 'Merch', color: '#bbb7a9', icon: 'tote' },
  other: { label: 'Other', color: '#b2bab3', icon: 'package' },
}

/** Older spellings the catalogue still carries. */
const CATEGORY_ALIASES: Record<string, string> = {
  cart: 'vaporizers',
  carts: 'vaporizers',
  vape: 'vaporizers',
  vapes: 'vaporizers',
  tinctures: 'tincture',
  edibles: 'edible',
  prerolls: 'preroll',
  'pre-roll': 'preroll',
  concentrates: 'concentrate',
  topicals: 'topical',
}

export function categoryStyle(category: string | null | undefined): CategoryStyle {
  if (!category) return categories.other
  const key = category.toLowerCase()
  return categories[key] ?? categories[CATEGORY_ALIASES[key]] ?? categories.other
}

/* ── Strain type ──────────────────────────────────────────────────────────── */
/* Shown as a lettered bullet — the same disc the map uses for stores — rather
   than another coloured pill, so a "Flower · Hybrid" card never shows two
   green pills side by side. */

export const strains: Record<string, { label: string; letter: string; color: string }> = {
  indica: { label: 'Indica', letter: 'I', color: '#b4adf4' },
  sativa: { label: 'Sativa', letter: 'S', color: '#f69f72' },
  hybrid: { label: 'Hybrid', letter: 'H', color: '#a9cb7d' },
}

/* ── Terpenes ─────────────────────────────────────────────────────────────── */
/* Each terpene takes the colour of what it smells like. These drive the
   terpene profile — the one chart the whole product is named after. */

export type TerpeneStyle = { name: string; aroma: string; color: string }

const TERPENES: (TerpeneStyle & { match: RegExp })[] = [
  { name: 'Myrcene', aroma: 'mango, earth', color: '#f5ac69', match: /myrcene/ },
  { name: 'Limonene', aroma: 'citrus peel', color: '#d1bf53', match: /limonene/ },
  { name: 'Caryophyllene', aroma: 'black pepper, clove', color: '#fda296', match: /caryophyllene/ },
  { name: 'Linalool', aroma: 'lavender', color: '#c7aff5', match: /linalool/ },
  { name: 'Pinene', aroma: 'pine, rosemary', color: '#86d29b', match: /pinene/ },
  { name: 'Humulene', aroma: 'hops, wood', color: '#b8c683', match: /humulene/ },
  { name: 'Terpinolene', aroma: 'apple, lilac', color: '#77d1c2', match: /terpinolene/ },
  { name: 'Ocimene', aroma: 'sweet basil', color: '#78d3b1', match: /ocimene/ },
  { name: 'Bisabolol', aroma: 'chamomile, honey', color: '#d6bb79', match: /bisabolol/ },
  { name: 'Eucalyptol', aroma: 'eucalyptus', color: '#84c9e5', match: /eucalyptol|cineole/ },
  { name: 'Nerolidol', aroma: 'wood, rose', color: '#eba6c6', match: /nerolidol/ },
  { name: 'Valencene', aroma: 'orange', color: '#f3ae58', match: /valencene/ },
  { name: 'Geraniol', aroma: 'rose, geranium', color: '#f5a3b5', match: /geraniol/ },
  { name: 'Terpineol', aroma: 'lilac, pine', color: '#d8abe2', match: /terpineol/ },
  { name: 'Camphene', aroma: 'fir, damp wood', color: '#86cccf', match: /camphene/ },
  { name: 'Guaiol', aroma: 'pine, rose', color: '#a9cb7d', match: /guaiol/ },
]

const TERPENE_FALLBACK = '#b2bab3'

/** Colour and aroma for a terpene name as labs write it ("β-Myrcene",
 *  "alpha-Pinene", "trans-Caryophyllene"). Unknown names get a neutral. */
export function terpeneStyle(name: string): TerpeneStyle {
  const key = name.toLowerCase()
  const hit = TERPENES.find(tp => tp.match.test(key))
  return hit ? { name: hit.name, aroma: hit.aroma, color: hit.color } : { name, aroma: '', color: TERPENE_FALLBACK }
}

/* ── Type ─────────────────────────────────────────────────────────────────── */
/* Fraunces (display) — a soft old-style serif for page titles and store
     names: the specimen-label warmth.
   Public Sans (text) — a civic grotesk for everything you read and tap.
   IBM Plex Mono (data) — eyebrows, sizes, potency and lab numbers.
   All three are SIL Open Font License and self-hosted. */

export const typeface = {
  display: 'Fraunces',
  sans: 'Public Sans',
  mono: 'IBM Plex Mono',
} as const

export const fontSize = {
  micro: 10,
  caption: 11,
  small: 12,
  body: 14,
  callout: 15,
  title: 17,
  heading: 20,
  display: 24,
  hero: 30,
} as const

export const fontWeight = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  heavy: 800,
} as const

/** Letter-spacing in em. Display type tightens as it grows; mono labels open. */
export const tracking = {
  display: -0.015,
  title: -0.01,
  body: 0,
  label: 0.06,
} as const

/* ── Space, radius, motion ────────────────────────────────────────────────── */

export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 7: 32, 8: 40 } as const

/** Tighter than before: cards read as considered objects, not bubbles. */
export const radii = { xs: 4, sm: 6, md: 8, lg: 12, xl: 16, '2xl': 20, pill: 999 } as const

export const duration = { fast: 120, base: 180, slow: 280 } as const

/** Translate `#rrggbb` + alpha (0..1) into rgba() for tints. */
export function alpha(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}
