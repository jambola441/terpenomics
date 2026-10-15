import { Alert } from 'react-native'
import { router } from 'expo-router'
import { api } from './api'

/**
 * Open a product, addressed as the web portal addresses it: by its product
 * key, plus its brand when it has one (an unbranded product has a key of its
 * own). Every product tap in the app goes through here.
 *
 * Until the app has the web's cross-store product page, this opens the
 * cheapest in-stock store's listing instead. When the product page lands, only
 * this function changes.
 */
export async function openProduct(key: string, brand: string | null) {
  try {
    const detail = await api.portal.getProductDetail(key, brand)
    const byPrice = (a: { price_cents: number | null }, b: { price_cents: number | null }) =>
      (a.price_cents ?? Infinity) - (b.price_cents ?? Infinity)
    const best = detail.offerings.filter(o => o.in_stock).sort(byPrice)[0] ?? detail.offerings[0]
    if (best) router.push(`/listing/${best.dispensary_id}/${best.listing_id}`)
    else Alert.alert('Not in stock', 'No store we track has this right now.')
  } catch (e: any) {
    Alert.alert('Could not open product', e?.message ?? String(e))
  }
}
