/** Formatting shared across the portal: money, dates, distance.
 *
 * These lived in `components/browse.tsx` next to the browse UI kit and were
 * duplicated again inside the portal shell. Neither is a home for a currency
 * helper, so both now read from here.
 */

export function formatDollars(cents: number) {
  return `$${(cents / 100).toFixed(2)}`
}

/** Whole dollars, for the price slider readout where cents are noise. */
export function formatDollarsShort(cents: number) {
  return `$${Math.round(cents / 100)}`
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function haversineMi(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 3958.8
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

export function formatDist(mi: number) {
  return mi < 0.1 ? '< 0.1 mi' : `${mi.toFixed(1)} mi`
}
