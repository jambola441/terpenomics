/**
 * Where a partner's stores are, relative to the shopper: the nearest one, the
 * order to list partners in, and a link that opens directions. Shared with the app.
 */
import { haversineMi } from './format'
import type { PortalPartner, PortalPartnerLocation } from '../types'

export type Position = { lat: number; lng: number }

/** The partner's store nearest to `pos`, among those on the map. */
export function nearestStore(partner: PortalPartner, pos: Position | null): { location: PortalPartnerLocation; miles: number } | null {
  if (!pos) return null
  let best: { location: PortalPartnerLocation; miles: number } | null = null
  for (const location of partner.locations) {
    if (location.lat == null || location.lng == null) continue
    const miles = haversineMi(pos.lat, pos.lng, location.lat, location.lng)
    if (!best || miles < best.miles) best = { location, miles }
  }
  return best
}

/** Nearest first when the shopper's position is known (partners with no store on
 *  the map last), A–Z otherwise. */
export function sortPartners(partners: PortalPartner[], pos: Position | null): PortalPartner[] {
  if (!pos) return partners
  const miles = new Map(partners.map(p => [p.id, nearestStore(p, pos)?.miles ?? Infinity]))
  return [...partners].sort((a, b) => miles.get(a.id)! - miles.get(b.id)! || a.name.localeCompare(b.name))
}

/** A maps link with directions to the store: its coordinates when placed, else its
 *  address. Apple Maps on Apple devices, Google Maps elsewhere. */
export function directionsUrl(location: PortalPartnerLocation, apple = false): string | null {
  const to = location.lat != null && location.lng != null
    ? `${location.lat},${location.lng}`
    : location.address
  if (!to) return null
  return apple
    ? `https://maps.apple.com/?daddr=${encodeURIComponent(to)}`
    : `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(to)}`
}

/** "(845) 555-0100" stays as typed; the link dials the digits. */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}
