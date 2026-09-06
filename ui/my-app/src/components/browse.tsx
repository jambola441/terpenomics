/* ============================================================================
   browse.tsx — the shared shopping-surface vocabulary.

   Every "browse a set of products" screen (category, search) is built from
   these pieces so the pages stay visually and behaviourally identical: same
   hero stats, same sticky toolbar, same chips, same filter sheet, same card.
   Only the data source and which facets apply differ per screen.
   ========================================================================== */

import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { t, radius, font, alpha } from '../theme'
import type { ListingPriceContext } from '../types'
import { useRenderWindow } from '../utils/browseState'
import { Pressable, Skeleton, Label, ProductImage } from './ui'
import { formatDist, formatDollars, formatDollarsShort, haversineMi } from '../utils/format'

// Re-exported so the browse surfaces can keep pulling their whole toolkit from
// one place; `utils/format` is where these are defined.
export { formatDist, formatDollars, formatDollarsShort, haversineMi }

/* ── Constants ────────────────────────────────────────────────────────────── */

export const CATEGORY_EMOJI: Record<string, string> = {
  flower: '🌸', vaporizers: '💨', cart: '💨', edible: '🍬', concentrate: '💎',
  preroll: '🌿', tincture: '🧪', tinctures: '🧪', topical: '🧴', merch: '🛍️', other: '📦',
}

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

/* ── Hero stats ───────────────────────────────────────────────────────────── */

export function Stat({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <span style={{ color: t.text2, fontSize: font.size.small + 1 }}>
      <span style={{ color, fontWeight: font.weight.bold }}>{value.toLocaleString()}</span> {label}
    </span>
  )
}

export function Dot() {
  return <span aria-hidden style={{ color: t.text4, fontSize: font.size.small }}>·</span>
}

/* ── Search field ─────────────────────────────────────────────────────────── */

export function SearchField({ value, onChange, placeholder, focused, onFocus, onBlur, autoFocus }: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  focused: boolean
  onFocus: () => void
  onBlur: () => void
  autoFocus?: boolean
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ position: 'relative', flex: 1 }}>
        <svg
          width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden
          style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', color: t.text3 }}
        >
          <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" />
        </svg>
        <input
          value={value}
          autoFocus={autoFocus}
          onChange={e => onChange(e.target.value)}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder={placeholder}
          style={{
            width: '100%', background: alpha('#000', 0.32),
            border: `1px solid ${focused ? t.accent : 'rgba(255,255,255,0.10)'}`,
            boxShadow: focused ? 'var(--ring)' : 'none',
            borderRadius: radius.pill, color: t.text1, fontSize: font.size.body,
            padding: '11px 14px 11px 34px', outline: 'none',
            transition: 'border-color var(--t-fast), box-shadow var(--t-fast)',
          }}
        />
      </div>
      {value && (
        <button
          onClick={() => onChange('')}
          aria-label="Clear search"
          style={{
            background: alpha('#000', 0.32), border: '1px solid rgba(255,255,255,0.10)',
            borderRadius: '50%', color: t.text2, fontSize: 13,
            width: 38, height: 38, flexShrink: 0,
          }}
        >
          ✕
        </button>
      )}
    </div>
  )
}

/* ── Sticky toolbar ───────────────────────────────────────────────────────── */

/**
 * The bar that sticks under the hero: an optional quick-filter rail, then the
 * Filters / sort buttons and the removable active-filter chips.
 */
export function BrowseToolbar({ quickRail, activeCount, sortLabel, onOpenSheet, activeChips, onClear }: {
  quickRail?: ReactNode
  activeCount: number
  sortLabel: string
  onOpenSheet: () => void
  activeChips?: ReactNode
  onClear: () => void
}) {
  return (
    <div style={{
      position: 'sticky', top: 0, zIndex: 10,
      background: 'rgba(11,11,13,0.92)',
      backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
      borderBottom: `1px solid ${t.border}`,
    }}>
      {quickRail}

      <div
        className="no-scrollbar"
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 14px 10px', overflowX: 'auto' }}
      >
        <button
          onClick={onOpenSheet}
          style={{
            flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '8px 14px', borderRadius: radius.pill,
            background: activeCount ? 'var(--accent-tint)' : t.surface2,
            border: `1px solid ${activeCount ? t.accent : t.border}`,
            color: activeCount ? t.accent : t.text2,
            fontSize: font.size.small + 1, fontWeight: font.weight.semibold,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
            <path d="M3 5h18v2l-7 7v5l-4 2v-7L3 7z" />
          </svg>
          Filters{activeCount ? ` · ${activeCount}` : ''}
        </button>

        <button
          onClick={onOpenSheet}
          style={{
            flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '8px 14px', borderRadius: radius.pill,
            background: t.surface2, border: `1px solid ${t.border}`,
            color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium,
          }}
        >
          {sortLabel} <span style={{ color: t.text3 }}>▾</span>
        </button>

        {activeChips}

        {activeCount > 0 && (
          <button
            onClick={onClear}
            style={{
              flexShrink: 0, background: 'none', border: 'none', color: t.text3,
              fontSize: font.size.small, whiteSpace: 'nowrap', textDecoration: 'underline',
            }}
          >
            Clear
          </button>
        )}
      </div>
    </div>
  )
}

/* ── Product card ─────────────────────────────────────────────────────────── */

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
}

/**
 * How this store's price stands against the others carrying the same product.
 *
 * The one thing a dispensary's own menu cannot tell a shopper, so it earns a
 * line on every card of that menu. Three states, and the losing one gets the
 * colour, because a cheaper price down the road is the version worth reading.
 *
 * Both the store page and its "See all" aisle draw it from here: a card and the
 * card it turns into after a tap should not describe the market differently.
 */
export function MarketNote({ market, priceCents, style }: {
  market?: ListingPriceContext | null
  priceCents: number | null
  style?: CSSProperties
}) {
  const m = market ?? NO_COMPARISON
  const others = `${m.other_store_count} other ${m.other_store_count === 1 ? 'store' : 'stores'}`
  const min = m.min_cents

  const [text, color] =
    m.other_store_count === 0 ? ['Only at this store', t.text4]
    : min != null && priceCents != null && min < priceCents ? [`${formatDollars(min)} at ${others}`, t.warning]
    : m.is_cheapest ? [`Best price of ${m.other_store_count + 1}`, t.accent]
    : [`Also at ${others}`, t.text4]

  return (
    <div style={{
      fontSize: font.size.micro, fontWeight: font.weight.medium, color,
      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      ...style,
    }}>
      {text}
    </div>
  )
}

/** What a row looks like when nothing came back to compare it against. A
 *  response without the comparison degrades to "nobody else has it" rather
 *  than blanking the card. */
const NO_COMPARISON: ListingPriceContext = {
  other_store_count: 0, min_cents: null, avg_cents: null, max_cents: null, is_cheapest: false,
}

export function BrowseCard({ item, color, suppressSubtype, action, footer, onOpen }: {
  item: BrowseCardItem
  color: string
  /** Hide the subtype tag when it just restates the page (e.g. "flower" on /flower). */
  suppressSubtype?: string | null
  /** Overlaid bottom-right on the image — e.g. an add-to-cart button. */
  action?: ReactNode
  /** Replaces the availability line. A single-store surface has nothing to say
   *  about where else to buy, but plenty to say about the price. */
  footer?: ReactNode
  onOpen: () => void
}) {
  const showSubtype = !!item.subtype
    && item.subtype.toLowerCase() !== (suppressSubtype ?? '').toLowerCase()
  // Single-store surfaces have nothing useful to say here; stay quiet instead
  // of printing a placeholder.
  const availability = item.dispensaryCount > 1
    ? `📍 At ${item.dispensaryCount} dispensaries`
    : item.storeName

  return (
    <Pressable
      onClick={onOpen}
      lift
      style={{
        background: t.surface1, borderRadius: radius.lg, border: `1px solid ${t.border}`,
        overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}
    >
      <div style={{ position: 'relative' }}>
        <ProductImage src={item.imageUrl} alt={item.name} category={item.category} radius="0" pad={12} />

        {item.variant && (
          <span style={{
            position: 'absolute', top: 8, left: 8,
            background: alpha('#000', 0.62), color: '#fff',
            backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
            fontSize: font.size.micro, fontWeight: font.weight.bold,
            padding: '3px 8px', borderRadius: radius.pill,
          }}>
            {item.variant}
          </span>
        )}

        {item.distanceMi != null && (
          <span style={{
            position: 'absolute', top: 8, right: 8,
            background: alpha('#000', 0.62), color: t.accent,
            backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
            fontSize: font.size.micro, fontWeight: font.weight.bold,
            padding: '3px 8px', borderRadius: radius.pill,
          }}>
            {formatDist(item.distanceMi)}
          </span>
        )}

        {action && (
          <div style={{ position: 'absolute', bottom: 8, right: 8 }}>{action}</div>
        )}
      </div>

      <div style={{ padding: '10px 11px 12px', flex: 1, display: 'flex', flexDirection: 'column' }}>
        {item.priceCents != null ? (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 4 }}>
            {item.multiPriced && (
              <span style={{ color: t.text4, fontSize: font.size.micro, fontWeight: font.weight.semibold }}>from</span>
            )}
            <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: font.size.callout }}>
              {formatDollars(item.priceCents)}
            </span>
          </div>
        ) : (
          <div style={{ color: t.text4, fontSize: font.size.caption, marginBottom: 4 }}>Price not listed</div>
        )}

        <div style={{
          color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small + 1, lineHeight: 1.3,
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        } as React.CSSProperties}>
          {item.name}
        </div>

        {item.brand && (
          <div style={{
            color: t.text3, fontSize: font.size.caption, marginTop: 3,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {item.brand}
          </div>
        )}

        {showSubtype && (
          <div style={{ marginTop: 8 }}>
            <span style={{
              background: alpha(color, 0.13), color, border: `1px solid ${alpha(color, 0.3)}`,
              fontSize: font.size.micro, fontWeight: font.weight.bold,
              padding: '2px 8px', borderRadius: radius.pill,
              textTransform: 'capitalize', letterSpacing: '0.03em',
            }}>
              {item.subtype}
            </span>
          </div>
        )}

        {/* Availability footer, pinned to the bottom so cards align in the grid */}
        {footer ? (
          <div style={{ marginTop: 'auto', paddingTop: 8 }}>{footer}</div>
        ) : availability && (
          <div style={{
            marginTop: 'auto', paddingTop: 8, color: t.text3, fontSize: font.size.micro,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {availability}
          </div>
        )}
      </div>
    </Pressable>
  )
}

/* ── Product grid ─────────────────────────────────────────────────────────── */

/** Cards mounted per window. Two columns, so this is twenty rows — several
 *  screens of runway ahead of the shopper at any moment. */
export const GRID_PAGE = 40

/**
 * The two-column product grid, rendered a window at a time.
 *
 * `items` is the whole filtered list and stays whole: the toolbar count, the
 * facet counts and the filter sheet all describe every match, not the part
 * currently on screen. What is windowed is the *mounting*. A category runs to a
 * few thousand products, and each card is a couple of dozen nodes and an image,
 * so handing the browser all of them up front cost seconds of layout and
 * thousands of image requests before the first card was legible — on the phones
 * this is built for, it read as a hang.
 *
 * The window grows by a page whenever the sentinel below the grid comes within
 * a screen or so of the viewport, which keeps the next cards mounted before the
 * shopper reaches them.
 */
export function BrowseGrid<T>({ items, page = GRID_PAGE, resetKey, children }: {
  items: T[]
  page?: number
  /** Change this when the list becomes a different list rather than a narrowed
   *  one — a new search — and the window starts over at one page. Filters do
   *  not qualify: they leave the shopper where they were on the page, and
   *  collapsing the grid under them would jump the view. */
  resetKey?: string
  /** Renders one card. Must set a `key` — this is a list. */
  children: (item: T) => ReactNode
}) {
  const { count, grow } = useRenderWindow(page, resetKey)
  const hasMore = count < items.length
  const shown = hasMore ? items.slice(0, count) : items

  // Re-armed on every growth rather than built once: observing an element
  // delivers an immediate callback with its current state, so a page that lands
  // with the sentinel still in view grows again instead of stalling until the
  // shopper scrolls. Growth is synchronous, so this settles in a frame or two —
  // once the sentinel is pushed below the margin, or once the list runs out and
  // the sentinel stops rendering at all.
  const sentinel = useRef<HTMLDivElement>(null)
  const growRef = useRef(grow)
  growRef.current = grow
  useEffect(() => {
    const node = sentinel.current
    if (!node) return
    const observer = new IntersectionObserver(entries => {
      if (entries[0]?.isIntersecting) growRef.current()
    }, { rootMargin: '600px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [count, items.length])

  return (
    <>
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10,
        padding: hasMore ? '10px 12px 0' : '10px 12px 96px',
      }}>
        {shown.map(children)}
      </div>
      {hasMore && (
        <div ref={sentinel} style={{ height: 96 }} aria-hidden />
      )}
    </>
  )
}

/* ── Chips ────────────────────────────────────────────────────────────────── */

export function ActiveChip({ label, onRemove, capitalize = true }: {
  label: string
  onRemove: () => void
  /** Off for labels that carry their own casing — "Within 10 mi", "$20–$60". */
  capitalize?: boolean
}) {
  return (
    <span style={{
      flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 5,
      background: 'var(--accent-tint)', border: `1px solid ${alpha('#a8e063', 0.4)}`, color: t.accent,
      fontSize: font.size.small, fontWeight: font.weight.semibold,
      padding: '5px 6px 5px 11px', borderRadius: radius.pill,
      whiteSpace: 'nowrap', maxWidth: 170, textTransform: capitalize ? 'capitalize' : 'none',
    }}>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      <button
        onClick={onRemove}
        aria-label={`Remove ${label}`}
        style={{ background: 'none', border: 'none', color: t.accent, fontSize: 14, lineHeight: 1, padding: '0 2px', flexShrink: 0 }}
      >
        ✕
      </button>
    </span>
  )
}

export function FacetChip({ label, count, active, color, onClick, disabled = false, capitalize = true }: {
  label: string
  count?: number
  active: boolean
  color: string
  onClick: () => void
  disabled?: boolean
  /** Off for labels that carry their own casing — units, sizes, sort phrases. */
  capitalize?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        flexShrink: 0, whiteSpace: 'nowrap', textTransform: capitalize ? 'capitalize' : 'none',
        fontSize: font.size.small + 1, fontWeight: active ? font.weight.bold : font.weight.medium,
        padding: '8px 13px', borderRadius: radius.pill,
        background: active ? alpha(color, 0.16) : t.surface2,
        border: `1px solid ${active ? color : t.border}`,
        color: disabled ? t.text4 : active ? color : t.text2,
        opacity: disabled ? 0.5 : 1,
        display: 'inline-flex', alignItems: 'center', gap: 6,
        transition: 'all var(--t-fast)',
      }}
    >
      {label}
      {count != null && (
        <span style={{ color: active ? color : t.text4, fontWeight: font.weight.semibold, fontSize: font.size.caption }}>
          {count}
        </span>
      )}
    </button>
  )
}

export function FacetGroup({ title, facet, sel, color, onToggle, capitalize = true }: {
  title: string
  facet: Facet[]
  sel: Set<string>
  color: string
  onToggle: (v: string) => void
  capitalize?: boolean
}) {
  return (
    <div>
      <Label style={{ marginBottom: 10 }}>{title}</Label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {facet.map(f => (
          <FacetChip
            key={f.value}
            label={f.value}
            count={f.count}
            active={sel.has(f.value)}
            color={color}
            capitalize={capitalize}
            onClick={() => onToggle(f.value)}
          />
        ))}
      </div>
    </div>
  )
}

/* ── Price range slider ───────────────────────────────────────────────────── */

export function PriceRange({ bounds, value, onChange, color }: {
  bounds: [number, number]
  value: [number, number] | null
  onChange: (v: [number, number] | null) => void
  color: string
}) {
  const [min, max] = bounds
  // Step in whole dollars, scaled so the slider stays usable over a wide span.
  const step = Math.max(100, Math.round((max - min) / 100 / 100) * 100)
  const [lo, hi] = value ?? bounds
  const pct = (v: number) => ((v - min) / (max - min)) * 100

  function set(next: [number, number]) {
    const clamped: [number, number] = [Math.max(min, next[0]), Math.min(max, next[1])]
    if (clamped[0] <= min && clamped[1] >= max) onChange(null)
    else onChange(clamped)
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
        <Label>Price</Label>
        <span style={{ color: value ? color : t.text3, fontSize: font.size.small + 1, fontWeight: font.weight.semibold }}>
          {formatDollarsShort(lo)} – {formatDollarsShort(hi)}{hi >= max ? '+' : ''}
        </span>
      </div>

      <div className="range-dual" style={{ margin: '0 12px' }}>
        {/* Track */}
        <div style={{
          position: 'absolute', left: 0, right: 0, top: '50%', height: 4, marginTop: -2,
          background: t.surface3, borderRadius: 2,
        }} />
        {/* Selected span */}
        <div style={{
          position: 'absolute', top: '50%', height: 4, marginTop: -2,
          left: `${pct(lo)}%`, right: `${100 - pct(hi)}%`,
          background: color, borderRadius: 2,
        }} />
        <input
          type="range"
          aria-label="Minimum price"
          min={min} max={max} step={step} value={lo}
          onChange={e => set([Math.min(Number(e.target.value), hi - step), hi])}
        />
        <input
          type="range"
          aria-label="Maximum price"
          min={min} max={max} step={step} value={hi}
          onChange={e => set([lo, Math.max(Number(e.target.value), lo + step)])}
        />
      </div>
    </div>
  )
}

/* ── Filter & sort sheet ──────────────────────────────────────────────────── */

/** One toggleable facet section in the sheet. */
export type SheetGroup = {
  key: string
  title: string
  facet: Facet[]
  sel: Set<string>
  onToggle: (v: string) => void
  capitalize?: boolean
}

/** Distance section config; omit entirely on screens without coordinates. */
export type SheetDistance = {
  hasLocation: boolean
  radiusMi: number | null
  onRadius: (r: number | null) => void
}

export function FilterSheet({
  open, onClose, resultCount, color, sort, onSort, sorts = SORTS,
  distance, priceBounds, price, onPrice, groups, onClear, activeCount,
}: {
  open: boolean
  onClose: () => void
  resultCount: number
  color: string
  sort: SortKey
  onSort: (s: SortKey) => void
  sorts?: SortOption[]
  distance?: SheetDistance
  priceBounds: [number, number] | null
  price: [number, number] | null
  onPrice: (p: [number, number] | null) => void
  groups: SheetGroup[]
  onClear: () => void
  activeCount: number
}) {
  // Close on Escape while the sheet is up.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      {open && (
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, background: alpha('#000', 0.6), zIndex: 2200, backdropFilter: 'blur(2px)' }}
        />
      )}

      <div
        role="dialog"
        aria-label="Filter and sort"
        aria-hidden={!open}
        style={{
          position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 2300,
          background: t.surface1, borderTop: `1px solid ${t.border}`,
          borderRadius: `${radius['2xl']} ${radius['2xl']} 0 0`, boxShadow: 'var(--e-3)',
          transform: open ? 'translateY(0)' : 'translateY(100%)',
          visibility: open ? 'visible' : 'hidden',
          transition: 'transform 0.34s cubic-bezier(0.32,0.72,0,1), visibility 0.34s',
          maxHeight: '86dvh', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: t.surface3 }} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px 4px' }}>
          <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, letterSpacing: '-0.01em' }}>
            Filter &amp; sort
          </div>
          {activeCount > 0 && (
            <button onClick={onClear} style={{ background: 'none', border: 'none', color: t.text3, fontSize: font.size.small + 1 }}>
              Clear all
            </button>
          )}
        </div>

        <div style={{ overflowY: 'auto', padding: '14px 20px 8px', display: 'flex', flexDirection: 'column', gap: 22 }}>
          {/* Sort */}
          <div>
            <Label style={{ marginBottom: 10 }}>Sort</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {sorts.map(s => (
                <FacetChip
                  key={s.key}
                  label={s.label}
                  active={sort === s.key}
                  color="var(--accent)"
                  disabled={!!s.needsLocation && !distance?.hasLocation}
                  onClick={() => onSort(s.key)}
                />
              ))}
            </div>
          </div>

          {/* Distance — only where offerings carry coordinates */}
          {distance && (
            <div>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
                <Label>Distance</Label>
                {!distance.hasLocation && (
                  <span style={{ color: t.text4, fontSize: font.size.caption }}>Location off</span>
                )}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {RADII.map(r => (
                  <FacetChip
                    key={r.label}
                    label={r.label}
                    active={distance.radiusMi === r.value}
                    color="var(--accent)"
                    disabled={!distance.hasLocation}
                    capitalize={false}
                    onClick={() => distance.onRadius(r.value)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Price */}
          {priceBounds && (
            <PriceRange bounds={priceBounds} value={price} onChange={onPrice} color="var(--accent)" />
          )}

          {groups.filter(g => g.facet.length > 1).map(g => (
            <FacetGroup
              key={g.key}
              title={g.title}
              facet={g.facet}
              sel={g.sel}
              color={color}
              onToggle={g.onToggle}
              capitalize={g.capitalize}
            />
          ))}
        </div>

        <div style={{ padding: '12px 20px', borderTop: `1px solid ${t.border}` }}>
          <button
            onClick={onClose}
            style={{
              width: '100%', background: t.accent, border: 'none', borderRadius: radius.lg,
              color: 'var(--accent-ink)', fontWeight: font.weight.bold, fontSize: font.size.callout,
              padding: 14, boxShadow: 'var(--e-1)',
            }}
          >
            Show {resultCount} {resultCount === 1 ? 'product' : 'products'}
          </button>
        </div>
        <div style={{ height: 'env(safe-area-inset-bottom, 0px)' }} />
      </div>
    </>
  )
}

/* ── Skeleton ─────────────────────────────────────────────────────────────── */

export function GridSkeleton() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '18px 12px 80px' }}>
      {[0, 1, 2, 3, 4, 5].map(i => (
        <div key={i} style={{ background: t.surface1, borderRadius: radius.lg, border: `1px solid ${t.border}`, overflow: 'hidden' }}>
          <Skeleton height={0} radius="0" style={{ aspectRatio: '1 / 1', height: 'auto' }} />
          <div style={{ padding: '10px 11px 12px' }}>
            <Skeleton width="45%" height={14} style={{ marginBottom: 8 }} />
            <Skeleton width="90%" height={12} style={{ marginBottom: 6 }} />
            <Skeleton width="55%" height={11} />
          </div>
        </div>
      ))}
    </div>
  )
}
