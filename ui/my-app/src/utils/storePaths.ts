/* Where a store's pages live. On the Map tab a store sits under the map
   (/portal/map/:id); opened from anywhere else it sits in that section
   (/portal/home/stores/:id), so Home's "See all" or a listing's "Menu" keeps
   the shopper in the tab they were in instead of moving them to Map. */

export function storePath(section: string, dispensaryId: string): string {
  return section === 'map' ? `/portal/map/${dispensaryId}` : `/portal/${section}/stores/${dispensaryId}`
}

export function aislePath(section: string, dispensaryId: string, category: string): string {
  return `${storePath(section, dispensaryId)}/aisle/${encodeURIComponent(category)}`
}

export function listingPath(section: string, dispensaryId: string, listingId: string): string {
  return `/portal/${section}/listings/${dispensaryId}/${listingId}`
}
