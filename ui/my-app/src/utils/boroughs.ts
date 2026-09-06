/* ============================================================================
   boroughs.ts — NYC borough detection + the MTA-derived colour each one wears
   on the portal map. Colours are the official line bullets that serve each
   borough, so the map reads as a subway map rather than a generic pin drop.
   ========================================================================== */

export type Borough =
  | 'Manhattan'
  | 'Brooklyn'
  | 'Queens'
  | 'The Bronx'
  | 'Staten Island'

/** MTA bullet colours: 1/2/3 red, B/D/F/M orange, 7 purple, 4/5/6 green,
 *  SIR blue — and N/Q/R/W yellow for anything we can't place. */
export const BOROUGH_COLORS: Record<Borough, string> = {
  Manhattan: '#ee352e',
  Brooklyn: '#ff6319',
  Queens: '#b933ad',
  'The Bronx': '#00933c',
  'Staten Island': '#0039a6',
}

/** Fallback for a store whose address doesn't name a borough. */
export const NYC_COLOR = '#fccc0a'

/** Address fragments that identify a borough, longest/most specific first. */
const PATTERNS: Array<[Borough, RegExp]> = [
  ['Staten Island', /staten\s*island|\bs\.?i\.?\b/i],
  ['The Bronx', /\bbronx\b/i],
  ['Brooklyn', /brooklyn|\bbklyn\b|williamsburg|bushwick|bed[- ]stuy|park slope|greenpoint|crown heights|flatbush|sunset park|gowanus|dumbo|bay ridge/i],
  ['Queens', /\bqueens\b|astoria|long island city|\blic\b|flushing|ridgewood|jackson heights|forest hills|jamaica, ?ny|sunnyside|woodside|rockaway/i],
  ['Manhattan', /manhattan|\bnew york,? ?ny\b|harlem|soho|tribeca|chelsea|midtown|upper east|upper west|east village|west village|lower east|\bnyc\b/i],
]

/** Best-effort borough for a store address. Returns null when the address is
 *  missing or names nothing we recognise — callers fall back to `NYC_COLOR`. */
export function boroughOf(address: string | null | undefined): Borough | null {
  if (!address) return null
  for (const [borough, pattern] of PATTERNS) {
    if (pattern.test(address)) return borough
  }
  return null
}

/** The colour a known borough wears — `NYC_COLOR` for the unplaceable ones. */
export function colorForBorough(borough: Borough | null): string {
  return borough ? BOROUGH_COLORS[borough] : NYC_COLOR
}

/** The colour a store's bullet wears on the map, resolved from its address. */
export function boroughColor(address: string | null | undefined): string {
  return colorForBorough(boroughOf(address))
}

/** Short label for a chip — "The Bronx" reads better unprefixed at chip size. */
export function boroughLabel(borough: Borough | null): string {
  if (!borough) return 'NYC'
  return borough === 'The Bronx' ? 'Bronx' : borough
}
