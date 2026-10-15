import { Platform } from 'react-native'
import { router } from 'expo-router'

/*
 * Where product, listing, brand and store taps go — the app's twin of the web
 * portal's openProduct / openListing / openBrand / storePath. Screens call
 * these rather than building paths, so a route only changes here.
 */

/** The cross-store product page, addressed as the web addresses it: by its
 *  product key, plus its brand when it has one. */
export function openProduct(key: string, brand: string | null) {
  router.push({ pathname: '/product', params: brand ? { key, brand } : { key } })
}

/** One store's listing. */
export function openListing(dispensaryId: string, listingId: string) {
  router.push(`/listing/${dispensaryId}/${listingId}`)
}

/** A brand's page, optionally already narrowed to a category or a line. */
export function openBrand(brand: string, filter: { category?: string; line?: string } = {}) {
  const params: Record<string, string> = { name: brand }
  if (filter.category) params.category = filter.category
  if (filter.line) params.line = filter.line
  router.push({ pathname: '/shop/brand/[name]', params })
}

/** A store's menu, optionally opened at one aisle. */
export function openStore(dispensaryId: string, aisle?: string) {
  router.push({ pathname: '/store/[dispensaryId]', params: aisle ? { dispensaryId, aisle } : { dispensaryId } })
}

/** Directions in the phone's own maps app. */
export function directionsUrl(store: { lat: number | null; lng: number | null; address: string | null }): string | null {
  const dest = store.lat != null && store.lng != null
    ? `${store.lat},${store.lng}`
    : store.address ? encodeURIComponent(store.address) : null
  if (!dest) return null
  return Platform.OS === 'ios'
    ? `http://maps.apple.com/?daddr=${dest}`
    : `https://www.google.com/maps/dir/?api=1&destination=${dest}`
}
