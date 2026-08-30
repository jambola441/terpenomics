/* ============================================================================
   mapTiles.ts — which basemap the portal map draws, and how it's toned.

   CARTO's basemaps are no longer key-free: fetched anonymously they come back
   stamped "API KEY REQUIRED" across every tile, which is what the portal map
   had been showing. Pick a provider, put its key in VITE_MAP_TILE_KEY, and set
   VITE_MAP_PROVIDER to one of the presets below.

     thunderforest  transport-dark      — dark base with transit lines picked
                                          out in colour; the most subway-ish
     maptiler       streets-v2-dark     — clean dark streets, strong labels
     stadia         alidade_smooth_dark — minimal, low-clutter dark
     carto          voyager + dark labels — warm colour under light labels

   VITE_MAP_STYLE overrides a preset's style slug. With no key configured the
   map falls back to OpenStreetMap's own tiles, inverted into a night palette,
   so a missing key degrades instead of rendering a stamped or blank map.
   ========================================================================== */

export type TileConfig = {
  /** Tile template for the colour basemap. */
  baseUrl: string
  /** Optional label tiles drawn above the (filtered) basemap. */
  labelsUrl: string | null
  attribution: string
  /** CSS filter applied to the basemap pane so every provider reads as dusk. */
  filter: string
  /** Whether the provider serves `@2x` tiles — worth it on the phones this
   *  portal is built for, and what `{r}` in the templates expands to. */
  retina: boolean
}

/** Styles that are already dark only need their colour nudged up. */
const DARK_NATIVE_FILTER = 'saturate(1.22) contrast(1.03) brightness(1.02)'

/** Thunderforest's transport-dark draws the whole road network in bright red
 *  over yellow trunk routes — at city zoom that's a mesh loud enough to bury
 *  the store bullets. Pull its colour and brightness back so the map reads as
 *  ember-toned context and the bullets stay the brightest thing on screen.
 *  Another Thunderforest style will want its own VITE_MAP_TILE_FILTER. */
const TRANSPORT_DARK_FILTER = 'grayscale(0.55) saturate(0.95) brightness(0.7) contrast(1.06)'

/** CARTO's Voyager is a daylight style — tone it down to sit in a dark shell. */
const CARTO_FILTER = 'saturate(1.45) contrast(0.94) brightness(0.6) hue-rotate(-8deg)'

/** OSM ships a daylight map with no dark variant; invert it into a night one. */
const OSM_FILTER = 'invert(0.93) hue-rotate(180deg) saturate(1.15) brightness(0.86) contrast(0.9)'

type Preset = {
  defaultStyle: string
  attribution: string
  filter: string
  base: (style: string, key: string) => string
  labels?: (style: string, key: string) => string
}

const PRESETS: Record<string, Preset> = {
  thunderforest: {
    defaultStyle: 'transport-dark',
    attribution: '© Thunderforest © OpenStreetMap contributors',
    filter: TRANSPORT_DARK_FILTER,
    base: (style, key) =>
      `https://{s}.tile.thunderforest.com/${style}/{z}/{x}/{y}{r}.png?apikey=${key}`,
  },
  maptiler: {
    defaultStyle: 'streets-v2-dark',
    attribution: '© MapTiler © OpenStreetMap contributors',
    filter: DARK_NATIVE_FILTER,
    base: (style, key) => `https://api.maptiler.com/maps/${style}/{z}/{x}/{y}{r}.png?key=${key}`,
  },
  stadia: {
    defaultStyle: 'alidade_smooth_dark',
    attribution: '© Stadia Maps © OpenMapTiles © OpenStreetMap contributors',
    filter: DARK_NATIVE_FILTER,
    base: (style, key) =>
      `https://tiles.stadiamaps.com/tiles/${style}/{z}/{x}/{y}{r}.png?api_key=${key}`,
  },
  carto: {
    defaultStyle: 'rastertiles/voyager_nolabels',
    attribution: '© OpenStreetMap © CARTO',
    filter: CARTO_FILTER,
    base: (style, key) => `https://{s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}{r}.png?api_key=${key}`,
    labels: (_style, key) =>
      `https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png?api_key=${key}`,
  },
}

const OSM_FALLBACK: TileConfig = {
  baseUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  labelsUrl: null,
  attribution: '© OpenStreetMap contributors',
  filter: OSM_FILTER,
  retina: false,  // OSM serves no @2x tiles
}

const env = import.meta.env

export function tileConfig(): TileConfig {
  // A full URL wins over everything — for a provider we don't have a preset for.
  const customUrl = env.VITE_MAP_TILE_URL as string | undefined
  if (customUrl) {
    return {
      baseUrl: customUrl,
      labelsUrl: (env.VITE_MAP_LABEL_TILE_URL as string | undefined) ?? null,
      attribution: (env.VITE_MAP_TILE_ATTRIBUTION as string | undefined) ?? '',
      filter: (env.VITE_MAP_TILE_FILTER as string | undefined) ?? 'none',
      retina: env.VITE_MAP_TILE_RETINA === 'true',
    }
  }

  const key = env.VITE_MAP_TILE_KEY as string | undefined
  if (!key) return OSM_FALLBACK

  const name = (env.VITE_MAP_PROVIDER as string | undefined) ?? 'thunderforest'
  const preset = PRESETS[name]
  if (!preset) {
    console.warn(`[map] unknown VITE_MAP_PROVIDER "${name}" — falling back to OpenStreetMap`)
    return OSM_FALLBACK
  }

  const style = (env.VITE_MAP_STYLE as string | undefined) ?? preset.defaultStyle
  const encoded = encodeURIComponent(key)

  return {
    baseUrl: preset.base(style, encoded),
    labelsUrl: preset.labels ? preset.labels(style, encoded) : null,
    attribution: preset.attribution,
    filter: (env.VITE_MAP_TILE_FILTER as string | undefined) ?? preset.filter,
    retina: true,  // every preset provider serves @2x
  }
}
