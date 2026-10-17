import { useEffect, useState } from 'react'
import * as Location from 'expo-location'
import type { Position } from '@web/utils/partnerPlaces'

/*
 * Where the shopper is, for distances and "nearest first", the way the web
 * gets it from the browser. One position for the whole app: the first screen
 * that shows a distance asks iOS (once; iOS remembers the answer), and every
 * screen after shares what came back. Denied or unavailable reads as null, and
 * screens fall back to price or A–Z.
 */

let current: Position | null = null
/** Whether an attempt has finished, so null can be told apart from "not yet". */
let settled = false
let pending: Promise<Position | null> | null = null
const listeners = new Set<(p: Position | null) => void>()

async function locate(): Promise<Position | null> {
  try {
    let { status, canAskAgain } = await Location.getForegroundPermissionsAsync()
    if (status !== 'granted' && canAskAgain) ({ status } = await Location.requestForegroundPermissionsAsync())
    if (status !== 'granted') return null
    // A recent fix is instant and close enough for "0.5 mi"; else ask for one.
    const fix =
      (await Location.getLastKnownPositionAsync({ maxAge: 30 * 60 * 1000 })) ??
      (await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }))
    return { lat: fix.coords.latitude, lng: fix.coords.longitude }
  } catch {
    return null
  }
}

/** The shopper's position, asking for it the first time any screen needs it. */
export function usePosition(): Position | null {
  const [pos, setPos] = useState<Position | null>(current)
  useEffect(() => {
    listeners.add(setPos)
    if (!current && !pending) {
      pending = locate().then(p => {
        current = p
        settled = true
        // A null answer may be a slow GPS or a "not now"; the next screen
        // that mounts tries again, without asking twice (canAskAgain).
        pending = null
        listeners.forEach(l => l(p))
        return p
      })
    }
    return () => { listeners.delete(setPos) }
  }, [])
  return pos
}

/** "off" once asking came back empty (denied, or no fix), so a screen can say
 *  "Turn on location"; "pending" until then. Starts the ask like usePosition. */
export function useLocationStatus(): 'pending' | 'on' | 'off' {
  const pos = usePosition()
  if (pos) return 'on'
  return settled ? 'off' : 'pending'
}
