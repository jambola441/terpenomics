import * as Location from 'expo-location'

/**
 * Where placing an order is allowed. App Store guideline 1.4.3 expects a
 * cannabis app to be geo-restricted to where sale is legal, and every store we
 * list is in New York. Add a state here when a store outside it is onboarded.
 * The geocoder may return either the abbreviation or the full name.
 */
const LEGAL_REGIONS = new Set(['NY', 'New York'])

export type RegionCheck =
  | { ok: true }
  | { ok: false; reason: 'permission' | 'outside' | 'unavailable'; message: string }

/** Checked when an order is placed, not on launch: browsing menus is fine
 *  from anywhere, and reserving is the part that facilitates a sale. */
export async function checkLegalRegion(): Promise<RegionCheck> {
  const { status } = await Location.requestForegroundPermissionsAsync()
  if (status !== 'granted') {
    return {
      ok: false,
      reason: 'permission',
      message: 'Orders can only be placed from New York, so we need your location to confirm where you are. You can allow it in Settings.',
    }
  }

  try {
    // Last known position is quick and is plenty to tell which state you're in.
    const pos =
      (await Location.getLastKnownPositionAsync({ maxAge: 10 * 60 * 1000 })) ??
      (await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low }))
    const [place] = await Location.reverseGeocodeAsync(pos.coords)
    if (place?.isoCountryCode === 'US' && place.region && LEGAL_REGIONS.has(place.region)) return { ok: true }
    return {
      ok: false,
      reason: 'outside',
      message: 'Pickup orders can only be placed from New York. You can still browse menus from anywhere.',
    }
  } catch {
    return { ok: false, reason: 'unavailable', message: "We couldn't confirm your location. Check your connection and try again." }
  }
}
