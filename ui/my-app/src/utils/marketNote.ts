/** What a card says about its price against the other stores carrying the
 *  same product. Shared by the portal's MarketNote and the app's, so both
 *  phrase a price the same way; each maps `tone` onto its own colours. */
import type { ListingPriceContext } from '../types'
import { formatDollars } from './format'

export type MarketTone = 'muted' | 'warning' | 'success'

/** A response without the comparison degrades to "nobody else has it" rather
 *  than blanking the card. */
const NO_COMPARISON: ListingPriceContext = {
  other_store_count: 0, min_cents: null, avg_cents: null, max_cents: null, is_cheapest: false,
}

export function marketNote(
  market: ListingPriceContext | null | undefined,
  priceCents: number | null,
): { text: string; tone: MarketTone } {
  const m = market ?? NO_COMPARISON
  const others = `${m.other_store_count} other ${m.other_store_count === 1 ? 'store' : 'stores'}`
  const min = m.min_cents
  if (m.other_store_count === 0) return { text: 'Only at this store', tone: 'muted' }
  if (min != null && priceCents != null && min < priceCents) return { text: `${formatDollars(min)} at ${others}`, tone: 'warning' }
  if (m.is_cheapest) return { text: `Best price of ${m.other_store_count + 1}`, tone: 'success' }
  return { text: `Also at ${others}`, tone: 'muted' }
}
