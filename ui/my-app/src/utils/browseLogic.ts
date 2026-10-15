/* ============================================================================
   browseLogic — the rules behind every "browse a set of products" screen,
   with no framework in them, so the web portal (components/BrowseScreen,
   browse, LineShelves, SearchView) and the app (mobile/src/components/browse,
   via `@web/utils/browseLogic`) filter, count, sort and shelve the same way.

   Nothing here touches the DOM, the router or React: data in, data out.
   ========================================================================== */

import type { PortalBrandDetail, PortalCategoryDetail, PortalProduct } from '../types'
import { formatDollarsShort, haversineMi } from './format'
import { LINE_MIN_PRODUCTS, NO_LINE } from './lines'

/* ── Sorts and radii ──────────────────────────────────────────────────────── */

export const SORT_KEYS = ['featured', 'nearest', 'price-asc', 'price-desc', 'name'] as const
export type SortKey = typeof SORT_KEYS[number]

export type SortOption = { key: SortKey; label: string; needsLocation?: boolean }

export const SORTS: SortOption[] = [
  { key: 'featured', label: 'Featured' },
  { key: 'nearest', label: 'Nearest', needsLocation: true },
  { key: 'price-asc', label: 'Price: Low → High' },
  { key: 'price-desc', label: 'Price: High → Low' },
  { key: 'name', label: 'Name A–Z' },
]

/** Sorts for screens with no per-offering coordinates (search). */
export const SORTS_NO_LOCATION: SortOption[] = SORTS.filter(s => !s.needsLocation)

export function sortLabelOf(sort: SortKey): string {
  return (SORTS.find(s => s.key === sort) ?? SORTS[0]).label
}

/** Radius options in miles. `null` = no distance limit. */
export const RADII: { value: number | null; label: string }[] = [
  { value: null, label: 'Any' },
  { value: 2, label: '2 mi' },
  { value: 5, label: '5 mi' },
  { value: 10, label: '10 mi' },
  { value: 25, label: '25 mi' },
]

export type Facet = { value: string; count: number }

/* ── Helpers ──────────────────────────────────────────────────────────────── */

/** Parse a variant like "3.5g" / "100mg" / "1 oz" into grams for natural ordering. */
export function variantWeight(v: string): number {
  const m = v.match(/([\d.]+)\s*(g|mg|oz)?/i)
  if (!m) return Number.MAX_SAFE_INTEGER
  let n = parseFloat(m[1])
  const unit = (m[2] || 'g').toLowerCase()
  if (unit === 'mg') n /= 1000
  if (unit === 'oz') n *= 28.3495
  return n
}

/**
 * The identity a listing groups under, matching the `products` view's GROUP BY
 * and the key built by `GET /customer/brands/{name}`. Keeping this in one place
 * is what lets a search result open the brand-product view.
 */
export function productKey(parts: {
  category?: string | null
  subtype?: string | null
  product_line?: string | null
  strain?: string | null
  variant?: string | null
}): string {
  return [parts.category, parts.subtype, parts.product_line, parts.strain, parts.variant]
    .map(p => (p == null ? '' : String(p)))
    .join('|')
}

/** Toggle one value in a set, returning a new set. */
export function toggled(set: Set<string>, value: string): Set<string> {
  const next = new Set(set)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}

/** The full span of starting prices — the bounds of the price range control.
 *  Null when fewer than two products are priced or they all cost the same. */
export function priceBoundsOf(prices: (number | null)[]): [number, number] | null {
  const known = prices.filter((p): p is number => p != null)
  if (known.length < 2) return null
  const lo = Math.min(...known)
  const hi = Math.max(...known)
  return hi > lo ? [lo, hi] : null
}

/** Price control step: whole dollars, scaled so it stays usable over a wide span. */
export function priceStep([min, max]: [number, number]): number {
  return Math.max(100, Math.round((max - min) / 100 / 100) * 100)
}

/** Clamp a chosen range to the bounds; the full span means "no price filter". */
export function clampPrice(next: [number, number], [min, max]: [number, number]): [number, number] | null {
  const clamped: [number, number] = [Math.max(min, next[0]), Math.min(max, next[1])]
  return clamped[0] <= min && clamped[1] >= max ? null : clamped
}

export function priceRangeLabel([lo, hi]: [number, number]): string {
  return `${formatDollarsShort(lo)}–${formatDollarsShort(hi)}`
}

/* ── The card ─────────────────────────────────────────────────────────────── */

/** The normalized shape every browse surface maps its rows into. */
export type BrowseCardItem = {
  name: string
  brand: string | null
  category: string | null
  subtype: string | null
  variant: string | null
  imageUrl: string | null
  /** Lowest known price, or null when nothing is priced. */
  priceCents: number | null
  /** True when offerings span a range, so the price reads "from $X". */
  multiPriced: boolean
  /** How many dispensaries carry it. 1 on single-store surfaces (an aisle). */
  dispensaryCount: number
  /** Miles to the nearest offering; null without a location fix. */
  distanceMi: number | null
  /** Shown when the product sits at exactly one dispensary. */
  storeName: string | null
  /** No store has it in stock right now. Search lists these too, so it says so. */
  outOfStock?: boolean
}

/** Whether the card shows its subtype: not when it just restates the page. */
export function showsSubtype(item: BrowseCardItem, suppressSubtype?: string | null): boolean {
  return !!item.subtype && item.subtype.toLowerCase() !== (suppressSubtype ?? '').toLowerCase()
}

/** The card's footer: how many stores carry it, else the one store, else nothing. */
export function availabilityOf(item: BrowseCardItem): string | null {
  return item.dispensaryCount > 1 ? `At ${item.dispensaryCount} dispensaries` : item.storeName
}

/* ── Category and brand pages (BrowseScreen) ──────────────────────────────── */

/** One store's copy of a product, flattened from whatever shape the endpoint
 *  used. The category endpoint indexes into a store table and the brand
 *  endpoint inlines the store; neither difference matters up here. */
export type BrowseOffering = {
  storeName: string
  lat: number | null
  lng: number | null
  priceCents: number | null
}

export type BrowseItem = {
  /** The product key, as the product page is addressed by. */
  key: string
  name: string
  brand: string | null
  category: string | null
  subtype: string | null
  strain: string | null
  variant: string | null
  /** The brand's product line, null when the product is in none. */
  line: string | null
  imageUrl: string | null
  minPriceCents: number | null
  maxPriceCents: number | null
  dispensaryCount: number
  offerings: BrowseOffering[]
}

/** The category endpoint sends its stores once and has offerings index into
 *  that table; the browse engine wants each offering to carry its own store. */
export function categoryItems(data: PortalCategoryDetail): BrowseItem[] {
  return data.products.map(product => ({
    key: product.key,
    name: product.name,
    brand: product.brand,
    category: product.category,
    subtype: product.subtype,
    strain: product.strain,
    variant: product.variant,
    line: product.product_line,
    imageUrl: product.image_url,
    minPriceCents: product.min_price_cents,
    maxPriceCents: product.max_price_cents,
    dispensaryCount: product.dispensary_count,
    offerings: product.offerings.flatMap(offering => {
      const store = data.dispensaries[offering.dispensary_index]
      if (!store) return []
      return [{ storeName: store.name, lat: store.lat, lng: store.lng, priceCents: offering.price_cents }]
    }),
  }))
}

/** The brand endpoint inlines each offering's store, and every product is this
 *  brand's — the page's own subject rather than a field on the row. */
export function brandItems(data: PortalBrandDetail): BrowseItem[] {
  return data.products.map(product => ({
    key: product.key,
    name: product.name,
    brand: data.name,
    category: product.category,
    subtype: product.subtype,
    strain: product.strain,
    variant: product.variant,
    line: product.product_line,
    imageUrl: product.image_url,
    minPriceCents: product.min_price_cents,
    // The brand endpoint aggregates to a single price, so a card here never
    // shows a "from" range the way a category card can.
    maxPriceCents: null,
    dispensaryCount: product.dispensary_count,
    offerings: product.offerings.map(offering => ({
      storeName: offering.dispensary_name,
      lat: offering.lat,
      lng: offering.lng,
      priceCents: offering.price_cents,
    })),
  }))
}

/** Whether any of the brand's lines is big enough to filter by. */
export function hasRealLine(data: PortalBrandDetail): boolean {
  const counts = new Map<string, number>()
  for (const product of data.products) {
    if (!product.product_line) continue
    const n = (counts.get(product.product_line) ?? 0) + 1
    if (n >= LINE_MIN_PRODUCTS) return true
    counts.set(product.product_line, n)
  }
  return false
}

/** A brand page's facets. Category leads, in place of the brand facet the
 *  category page has: it is the one thing that varies across a brand's whole
 *  range. The line comes second, never first, so it never takes over the
 *  quick rail. */
export function brandFacetKeys(showLines: boolean): FacetKey[] {
  return showLines ? ['category', 'line', 'subtype', 'variant'] : ['category', 'subtype', 'variant']
}

/** A category page's facets: no category facet, every product is already it. */
export const CATEGORY_FACETS: readonly FacetKey[] = ['subtype', 'brand', 'variant']

export type FacetKey = 'category' | 'subtype' | 'brand' | 'variant' | 'line'

export const FACET_KEYS: readonly FacetKey[] = ['category', 'subtype', 'brand', 'variant', 'line']

export const FACET_TITLES: Record<FacetKey, string> = {
  category: 'Category',
  subtype: 'Subtype',
  brand: 'Brand',
  variant: 'Weight / Size',
  line: 'Product line',
}

/** Brand casing ("UP", "Liquid Diamonds") is the name; sizes carry units. */
export const KEEPS_CASE: ReadonlySet<FacetKey> = new Set(['variant', 'line'])

export type FacetSelection = Record<FacetKey, Set<string>>

export function emptySelection(): FacetSelection {
  return { category: new Set(), subtype: new Set(), brand: new Set(), variant: new Set(), line: new Set() }
}

/** The value an item files under for a facet. Only the line facet has a bucket
 *  for "none"; elsewhere an item without the field simply has no value. */
export function facetValue(item: BrowseItem, key: FacetKey): string | null {
  if (key === 'line') return item.line ?? NO_LINE
  return item[key]
}

/** Sizes read naturally in size order; everything else reads best by how much
 *  of the set it covers. */
export const FACET_SORTS: Record<FacetKey, (a: Facet, b: Facet) => number> = {
  category: (a, b) => b.count - a.count,
  subtype: (a, b) => b.count - a.count,
  brand: (a, b) => b.count - a.count,
  variant: (a, b) => variantWeight(a.value) - variantWeight(b.value),
  line: (a, b) => Number(a.value === NO_LINE) - Number(b.value === NO_LINE) || b.count - a.count,
}

/** An item plus the facts derived from where the shopper is standing. */
export type Enriched = {
  item: BrowseItem
  closestDist: number | null
  closestStore: string | null
  cheapestStore: string | null
  /** Lowercased haystack for the search box. */
  haystack: string
}

export type Position = { lat: number; lng: number }

/** Resolve each item's closest and cheapest store, once per position change. */
export function enrichItems(items: BrowseItem[], userPos: Position | null): Enriched[] {
  return items.map(item => {
    let closestDist = Infinity
    let closestStore: string | null = null
    let cheapestStore: string | null = null
    let cheapestPrice = Infinity

    for (const offering of item.offerings) {
      if (offering.priceCents != null && offering.priceCents < cheapestPrice) {
        cheapestPrice = offering.priceCents
        cheapestStore = offering.storeName
      }
      if (userPos && offering.lat != null && offering.lng != null) {
        const d = haversineMi(userPos.lat, userPos.lng, offering.lat, offering.lng)
        if (d < closestDist) { closestDist = d; closestStore = offering.storeName }
      }
    }

    return {
      item,
      closestDist: closestStore ? closestDist : null,
      closestStore,
      cheapestStore,
      haystack: [item.name, item.brand, item.category, item.subtype, item.strain, item.variant, item.line]
        .filter(Boolean).join(' ').toLowerCase(),
    }
  })
}

export type BrowseFilters = {
  /** Trimmed and lowercased. */
  search: string
  /** The facets this screen offers. A selection on any other (one the URL
   *  carried in, say) filters nothing, since there is no chip to undo it. */
  keys: readonly FacetKey[]
  facets: FacetSelection
  radiusMi: number | null
  price: [number, number] | null
}

/** Does an item survive the filters? `except` skips one, for counting it. */
export function matchesFilters(e: Enriched, f: BrowseFilters, except?: FacetKey | 'price' | 'radius'): boolean {
  if (f.search && !e.haystack.includes(f.search)) return false

  for (const key of f.keys) {
    if (except === key) continue
    const selected = f.facets[key]
    if (!selected.size) continue
    const value = facetValue(e.item, key)
    if (!value || !selected.has(value)) return false
  }

  if (except !== 'radius' && f.radiusMi != null) {
    // Only meaningful with a fix on the shopper's position; closestDist is null
    // without one.
    if (e.closestDist == null || e.closestDist > f.radiusMi) return false
  }
  if (except !== 'price' && f.price) {
    const p = e.item.minPriceCents
    // Unpriced products can't satisfy a narrowed range — drop them rather
    // than guess.
    if (p == null || p < f.price[0] || p > f.price[1]) return false
  }
  return true
}

/** Facet options with counts that respect every *other* active filter. */
export function facetOptionsFor(enriched: Enriched[], f: BrowseFilters): Record<FacetKey, Facet[]> {
  const out = {} as Record<FacetKey, Facet[]>
  for (const key of f.keys) {
    const counts = new Map<string, number>()
    for (const e of enriched) {
      if (!matchesFilters(e, f, key)) continue
      const value = facetValue(e.item, key)
      if (!value) continue
      counts.set(value, (counts.get(value) ?? 0) + 1)
    }
    out[key] = [...counts.entries()]
      .map(([value, count]) => ({ value, count }))
      .sort(FACET_SORTS[key])
  }
  return out
}

/** How many filters are on, for the Filters button's badge. */
export function activeFilterCount(f: Pick<BrowseFilters, 'keys' | 'facets' | 'radiusMi' | 'price'>): number {
  return f.keys.reduce((n, key) => n + f.facets[key].size, 0)
    + (f.radiusMi != null ? 1 : 0)
    + (f.price ? 1 : 0)
}

/** Sort a filtered list; returns a new array. */
export function sortEnriched(list: Enriched[], sort: SortKey): Enriched[] {
  const arr = [...list]
  if (sort === 'price-asc' || sort === 'price-desc') {
    const dir = sort === 'price-asc' ? 1 : -1
    arr.sort((a, b) => {
      const pa = a.item.minPriceCents
      const pb = b.item.minPriceCents
      if (pa == null) return 1
      if (pb == null) return -1
      return (pa - pb) * dir
    })
  } else if (sort === 'nearest') {
    arr.sort((a, b) => (a.closestDist ?? Infinity) - (b.closestDist ?? Infinity))
  } else if (sort === 'name') {
    arr.sort((a, b) => a.item.name.localeCompare(b.item.name))
  } else {
    // Featured: things that make a good card first — a photo, then breadth of
    // availability, then the server's ordering as the tiebreak.
    arr.sort((a, b) => {
      const img = Number(!!b.item.imageUrl) - Number(!!a.item.imageUrl)
      if (img) return img
      return b.item.dispensaryCount - a.item.dispensaryCount
    })
  }
  return arr
}

/** The page's best few, whatever line they are in, pinned above the shelves. */
export function bestPicks(filtered: Enriched[], hasLocation: boolean): { entries: Enriched[]; label: string } {
  const priced = (e: Enriched) => e.item.minPriceCents ?? Infinity
  const ranked = hasLocation
    ? [...filtered].sort((a, b) => (a.closestDist ?? Infinity) - (b.closestDist ?? Infinity) || priced(a) - priced(b))
    : [...filtered].sort((a, b) => priced(a) - priced(b))
  return {
    entries: ranked.slice(0, 4),
    label: hasLocation ? 'Nearest to you · any line' : 'Lowest price · any line',
  }
}

/** Why shelves are folded into one list right now, or null when they aren't.
 *  A search, a price or distance sort, or a narrower filter than category asks
 *  for one list in that order, and shelves would hide the answer: in 63 of 87
 *  brands with several lines, the cheapest product had no line. */
export function flattenReason(o: {
  canGroup: boolean
  grid: boolean
  search: string
  sort: SortKey
  facets: FacetSelection
}): 'search' | 'sort' | 'filter' | null {
  if (!o.canGroup || o.grid) return null
  if (o.search) return 'search'
  if (o.sort !== 'featured') return 'sort'
  if (o.facets.line.size || o.facets.subtype.size || o.facets.variant.size) return 'filter'
  return null
}

export function flattenNote(reason: 'search' | 'sort' | 'filter', sortLabel: string): string {
  return reason === 'search' ? 'One list while you search'
    : reason === 'sort' ? `One list while sorted by ${sortLabel.toLowerCase()}`
    : 'One list while filtered'
}

/** The card a browse item becomes. `name` is passed in: inside a line's shelf
 *  or filter the line is dropped from it (utils/lines nameWithinLine). */
export function browseCardOf(e: Enriched, name: string): BrowseCardItem {
  return {
    name,
    brand: e.item.brand,
    category: e.item.category,
    subtype: e.item.subtype,
    variant: e.item.variant,
    imageUrl: e.item.imageUrl,
    priceCents: e.item.minPriceCents,
    multiPriced: e.item.minPriceCents != null
      && e.item.maxPriceCents != null
      && e.item.maxPriceCents > e.item.minPriceCents,
    dispensaryCount: e.item.dispensaryCount,
    distanceMi: e.closestDist,
    storeName: e.closestStore ?? e.cheapestStore,
  }
}

/* ── Shelves by product line (LineShelves) ────────────────────────────────── */

/** A category is laid out by line only when all of these hold. The shelves have
 *  to carry a fair share of it, not every product: whatever no shelf holds goes
 *  on the "More" shelf, which is never hidden. On 2026-10-10 this gave 37
 *  brands shelves (24 under the first, stricter rule, which also capped the
 *  products in no line or in tiny lines); requiring two real lines is what
 *  keeps it from going further, and is what keeps shelves meaningful. */
const GROUP_MIN_PRODUCTS = 6      // enough products for shelves to mean anything
const GROUP_MIN_SHELVES = 2       // at least two real lines
const GROUP_MIN_ON_SHELVES = 0.4  // the shelves hold at least 40% of the category

/** Fewer products than this after the shopper's filters, and shelves of one or
 *  two cards read worse than the grid. */
export const GROUP_MIN_RESULTS = 8

/** Cards on one shelf before "See all" takes over. */
export const SHELF_CAP = 10
/** Cards shown for a category that is not laid out by line. */
export const SECTION_CAP = 6

export type Shelf<E> = { line: string; entries: E[] }

export type CategorySection<E> = {
  category: string | null
  entries: E[]
  /** Shelves, biggest first, when the category passes the rule; else empty. */
  shelves: Shelf<E>[]
  /** What no shelf holds: products in no line, or in a line too small for one. */
  rest: E[]
  /** The lines too small for a shelf, so "See all" on `rest` can select them. */
  thinLines: string[]
}

/** The page's entries by category (biggest first), each split into shelves when
 *  it passes the rule. Order within a shelf is the order `entries` came in. */
export function groupByLine<E>(entries: E[], itemOf: (e: E) => BrowseItem): CategorySection<E>[] {
  const byCategory = new Map<string | null, E[]>()
  for (const e of entries) {
    const key = itemOf(e).category
    byCategory.set(key, [...(byCategory.get(key) ?? []), e])
  }

  const sections: CategorySection<E>[] = []
  for (const [category, inCategory] of byCategory) {
    const byLine = new Map<string, E[]>()
    for (const e of inCategory) {
      const line = itemOf(e).line
      if (line) byLine.set(line, [...(byLine.get(line) ?? []), e])
    }
    const real = [...byLine].filter(([, es]) => es.length >= LINE_MIN_PRODUCTS)
    const thin = [...byLine].filter(([, es]) => es.length < LINE_MIN_PRODUCTS)
    const onShelves = real.reduce((n, [, es]) => n + es.length, 0)
    const n = inCategory.length

    const passes = n >= GROUP_MIN_PRODUCTS
      && real.length >= GROUP_MIN_SHELVES
      && onShelves / n >= GROUP_MIN_ON_SHELVES

    if (!passes) {
      sections.push({ category, entries: inCategory, shelves: [], rest: inCategory, thinLines: [] })
      continue
    }
    const shelfLines = new Set(real.map(([line]) => line))
    sections.push({
      category,
      entries: inCategory,
      shelves: real
        .sort(([a, ea], [b, eb]) => eb.length - ea.length || a.localeCompare(b))
        .map(([line, es]) => ({ line, entries: es })),
      rest: inCategory.filter(e => !shelfLines.has(itemOf(e).line ?? '')),
      thinLines: thin.map(([line]) => line),
    })
  }
  return sections.sort((a, b) => b.entries.length - a.entries.length)
}

/** Whether any category on the page passes: the page is groupable at all. */
export function hasShelves<E>(sections: CategorySection<E>[]): boolean {
  return sections.some(s => s.shelves.length > 0)
}

export function countLabel(n: number): string {
  return `${n} ${n === 1 ? 'product' : 'products'}`
}

/** "$35–48 · 16 stores": the span of starting prices and the stores carrying any of it. */
export function shelfMeta(items: BrowseItem[]): string {
  const prices = items.map(i => i.minPriceCents).filter((p): p is number => p != null)
  const stores = new Set(items.flatMap(i => i.offerings.map(o => o.storeName)))
  const parts: string[] = []
  if (prices.length) {
    const lo = Math.min(...prices)
    const hi = Math.max(...prices)
    parts.push(lo === hi ? formatDollarsShort(lo) : `${formatDollarsShort(lo)}–${formatDollarsShort(hi)}`)
  }
  if (stores.size) parts.push(`${stores.size} ${stores.size === 1 ? 'store' : 'stores'}`)
  return parts.join(' · ')
}

/* ── Search (SearchView) ──────────────────────────────────────────────────── */

/** How many rows search pulls per request, and before it stops and asks the
 *  shopper to narrow down. */
export const SEARCH_PAGE = 200
export const SEARCH_MAX_ROWS = 1000

export type SearchFacetKey = 'category' | 'subtype' | 'brand' | 'variant'

export type SearchFilters = {
  category: Set<string>
  subtype: Set<string>
  brand: Set<string>
  variant: Set<string>
  price: [number, number] | null
}

/** Does a row survive the filter set? `except` skips one facet, for counting. */
export function searchMatches(p: PortalProduct, f: SearchFilters, except?: SearchFacetKey | 'price'): boolean {
  if (except !== 'category' && f.category.size && !(p.category && f.category.has(p.category))) return false
  if (except !== 'subtype' && f.subtype.size && !(p.subtype && f.subtype.has(p.subtype))) return false
  if (except !== 'brand' && f.brand.size && !(p.brand && f.brand.has(p.brand))) return false
  if (except !== 'variant' && f.variant.size && !(p.variant && f.variant.has(p.variant))) return false
  if (except !== 'price' && f.price) {
    const v = p.min_price_cents
    // Unpriced products can't satisfy a narrowed range — drop them rather than guess.
    if (v == null || v < f.price[0] || v > f.price[1]) return false
  }
  return true
}

/** Facet options with counts that respect every *other* active filter, sorted
 *  as the sheet shows them (sizes by size, everything else by count). */
export function searchFacet(rows: PortalProduct[], f: SearchFilters, key: SearchFacetKey): Facet[] {
  const counts = new Map<string, number>()
  for (const p of rows) {
    if (!searchMatches(p, f, key)) continue
    const v = p[key]
    if (!v) continue
    counts.set(v, (counts.get(v) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort(key === 'variant'
      ? (a, b) => variantWeight(a.value) - variantWeight(b.value)
      : (a, b) => b.count - a.count)
}

export function searchSort(list: PortalProduct[], sort: SortKey): PortalProduct[] {
  const arr = [...list]
  if (sort === 'price-asc' || sort === 'price-desc') {
    const dir = sort === 'price-asc' ? 1 : -1
    arr.sort((a, b) => {
      const pa = a.min_price_cents
      const pb = b.min_price_cents
      if (pa == null) return 1
      if (pb == null) return -1
      return (pa - pb) * dir
    })
  } else if (sort === 'name') {
    arr.sort((a, b) => a.display_name.localeCompare(b.display_name))
  } else {
    // Featured: in stock first, then the products carried in the most places.
    arr.sort((a, b) => {
      const stock = Number(b.any_in_stock) - Number(a.any_in_stock)
      if (stock) return stock
      return b.dispensary_count - a.dispensary_count
    })
  }
  return arr
}

/** A search row as a card. Named server-side like every other listing surface,
 *  so search results and the pages they open agree on what it is called. */
export function searchCard(p: PortalProduct): BrowseCardItem {
  return {
    name: p.display_name,
    brand: p.brand,
    category: p.category,
    subtype: p.subtype,
    variant: p.variant,
    // The `products` view aggregates listings and carries no image; the card
    // falls back to the category plate, same as every other browse surface.
    imageUrl: null,
    priceCents: p.min_price_cents,
    multiPriced: p.min_price_cents != null && p.max_price_cents != null && p.max_price_cents > p.min_price_cents,
    dispensaryCount: p.dispensary_count,
    // The aggregate rows carry no coordinates, so search can't show distance.
    distanceMi: null,
    storeName: null,
    outOfStock: !p.any_in_stock,
  }
}

/** A search row's list key: its product key plus its brand. */
export function searchRowKey(p: PortalProduct): string {
  return productKey(p) + '|' + (p.brand ?? '')
}
