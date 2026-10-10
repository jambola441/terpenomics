/* ============================================================================
   LineShelves — a brand page laid out by product line (flag `lines_grouped`).

   A brand page is a flat grid of everything the brand makes. For brands that
   name their lines well, that hides the shape shoppers remember them by ("their
   Palms all-in-ones"), so here each line gets a shelf: a header that says what
   the line is, and a row of its products.

   Most brands do not qualify, and the rule for who does is deliberately strict
   (`groupByLine`): on 2026-10-10, 81% of brands had no line at all, the median
   line held one product, and many "lines" were flavours or effects. A category
   that fails the rule is shown as it always was; a page with no category that
   passes is never grouped at all. Whatever has no line, or sits in a line too
   small for a shelf, goes on a last "More …" shelf and is never hidden.
   ========================================================================== */

import type { CSSProperties, ReactNode } from 'react'
import { t, font, categoryColor, categoryLabel } from '../theme'
import { Icon, CategoryIcon } from './Icon'
import { formatDollarsShort } from './browse'
import type { BrowseItem } from './BrowseScreen'
import { LINE_MIN_PRODUCTS } from '../utils/lines'

/* ── The rule ─────────────────────────────────────────────────────────────── */

/** A category is laid out by line only when all of these hold. Thresholds from
 *  the skeptic's pass over production data (2026-10-10): looser ones admitted
 *  brands whose biggest "shelf" was the products with no line. */
const GROUP_MIN_PRODUCTS = 6      // enough products for shelves to mean anything
const GROUP_MIN_SHELVES = 2       // at least two real lines
const GROUP_MIN_COVERAGE = 0.7    // the unlined shelf is at most 30% of the category
const GROUP_MAX_THIN = 0.15       // products in one- and two-product lines

/** Fewer products than this after the shopper's filters, and shelves of one or
 *  two cards read worse than the grid. */
export const GROUP_MIN_RESULTS = 8

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
    const lined = [...byLine.values()].reduce((n, es) => n + es.length, 0)
    const inThin = thin.reduce((n, [, es]) => n + es.length, 0)
    const n = inCategory.length

    const passes = n >= GROUP_MIN_PRODUCTS
      && real.length >= GROUP_MIN_SHELVES
      && lined / n >= GROUP_MIN_COVERAGE
      && inThin / n <= GROUP_MAX_THIN

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

/* ── The mark ─────────────────────────────────────────────────────────────── */

/**
 * A product line's mark: a diamond, after the subway's express bullet, in its
 * category's hue. Round lettered bullets already mean a store (borough colour)
 * or a strain type (I/S/H), so a line never borrows their shape. Always set
 * next to the line's name: the hue repeats across a category's lines and is
 * never the only cue. Hollow marks what is in no line.
 */
export function LineMark({ color, size = 12, hollow = false }: { color: string; size?: number; hollow?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden style={{ flexShrink: 0 }}>
      <rect
        x="2.5" y="2.5" width="7" height="7" transform="rotate(45 6 6)"
        fill={hollow ? 'none' : color}
        stroke={hollow ? t.text3 : 'none'}
        strokeWidth={hollow ? 1.2 : 0}
        strokeDasharray={hollow ? '2 1.6' : undefined}
      />
    </svg>
  )
}

/* ── The layout ───────────────────────────────────────────────────────────── */

/** Cards on one shelf before "See all" takes over; keeps a long line from
 *  becoming a wall of cards nobody scrolls sideways through. */
const SHELF_CAP = 10
/** Cards shown for a category that is not laid out by line. */
const SECTION_CAP = 6
const CARD_WIDTH = 156

interface Props<E> {
  sections: CategorySection<E>[]
  itemOf: (e: E) => BrowseItem
  /** Renders one card; must set a `key`. `inLine` is true on a line's own
   *  shelf, where the header already says the line. */
  renderCard: (e: E, inLine: boolean) => ReactNode
  /** Best picks across the whole page, lines or not, and what they are best at. */
  best: { entries: E[]; label: string }
  onSeeLine: (category: string | null, line: string) => void
  onSeeRest: (category: string | null, thinLines: string[]) => void
  onSeeCategory: (category: string | null) => void
}

export default function LineShelves<E>({
  sections, itemOf, renderCard, best, onSeeLine, onSeeRest, onSeeCategory,
}: Props<E>) {
  return (
    <div style={{ paddingBottom: 96 }}>
      {best.entries.length > 0 && (
        <div style={{ padding: '12px 0 4px' }}>
          <Eyebrow style={{ padding: '0 16px 8px' }}>{best.label}</Eyebrow>
          <Rail>{best.entries.map(e => <RailSlot key={itemOf(e).key}>{renderCard(e, false)}</RailSlot>)}</Rail>
        </div>
      )}

      {sections.map(section => {
        const label = categoryLabel(section.category)
        const color = categoryColor(section.category)
        return (
          <div key={section.category ?? '—'} style={{ paddingTop: 18 }}>
            {/* Category rule: glyph, name, hairline, count */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px 6px' }}>
              <CategoryIcon category={section.category} size={16} />
              <Eyebrow>{label}</Eyebrow>
              <div style={{ flex: 1, height: 1, background: t.border }} />
              <Eyebrow className="num">{section.entries.length}</Eyebrow>
            </div>

            {section.shelves.map(shelf => (
              <ShelfBlock
                key={shelf.line}
                eyebrow={`Line · ${label} · ${countLabel(shelf.entries.length)}`}
                title={shelf.line}
                mark={<LineMark color={color} size={16} />}
                meta={shelfMeta(shelf.entries.map(itemOf))}
                total={shelf.entries.length}
                onSeeAll={() => onSeeLine(section.category, shelf.line)}
              >
                <Rail>
                  {shelf.entries.slice(0, SHELF_CAP).map(e => <RailSlot key={itemOf(e).key}>{renderCard(e, true)}</RailSlot>)}
                </Rail>
              </ShelfBlock>
            ))}

            {section.rest.length > 0 && (section.shelves.length > 0 ? (
              <ShelfBlock
                eyebrow={`Not in a line · ${countLabel(section.rest.length)}`}
                title={`More ${label.toLowerCase()}`}
                mark={<LineMark color={color} size={16} hollow />}
                meta={shelfMeta(section.rest.map(itemOf))}
                total={section.rest.length}
                onSeeAll={() => onSeeRest(section.category, section.thinLines)}
              >
                <Rail>
                  {section.rest.slice(0, SHELF_CAP).map(e => <RailSlot key={itemOf(e).key}>{renderCard(e, false)}</RailSlot>)}
                </Rail>
              </ShelfBlock>
            ) : (
              // A category that is not laid out by line looks as it did: a grid.
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '4px 12px 0' }}>
                  {section.rest.slice(0, SECTION_CAP).map(e => renderCard(e, false))}
                </div>
                {section.rest.length > SECTION_CAP && (
                  <SeeAll total={section.rest.length} onClick={() => onSeeCategory(section.category)} style={{ padding: '10px 16px 0' }} />
                )}
              </>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function ShelfBlock({ eyebrow, title, mark, meta, total, onSeeAll, children }: {
  eyebrow: string
  title: string
  mark: ReactNode
  meta: string
  total: number
  onSeeAll: () => void
  children: ReactNode
}) {
  return (
    <section style={{ margin: '10px 0 0', paddingTop: 12, borderTop: `1px solid ${t.borderStrong}` }}>
      <div style={{ padding: '0 16px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <Eyebrow>{eyebrow}</Eyebrow>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          {mark}
          <h2 style={{
            margin: 0, flex: 1, minWidth: 0, color: t.text1, fontFamily: font.family.display,
            fontSize: font.size.heading, fontWeight: font.weight.semibold, letterSpacing: '-0.01em',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {title}
          </h2>
          {total > 1 && <SeeAll total={total} onClick={onSeeAll} />}
        </div>
        {meta && (
          <div className="num" style={{ color: t.text2, fontFamily: font.family.mono, fontSize: font.size.caption }}>{meta}</div>
        )}
      </div>
      {children}
    </section>
  )
}

function SeeAll({ total, onClick, style }: { total: number; onClick: () => void; style?: CSSProperties }) {
  return (
    <button
      onClick={onClick}
      style={{
        border: 'none', background: 'none', cursor: 'pointer', padding: '6px 0', flexShrink: 0,
        color: t.text2, fontSize: font.size.small, display: 'inline-flex', alignItems: 'center', gap: 2,
        ...style,
      }}
    >
      See all {total} <Icon name="chevron-right" size={14} />
    </button>
  )
}

function Rail({ children }: { children: ReactNode }) {
  return (
    // scroll-padding matches the side padding: without it, snapping a card's
    // start to the edge scrolls the padding away and the first card sits flush.
    <div className="no-scrollbar" style={{
      display: 'flex', gap: 10, overflowX: 'auto', padding: '0 12px 2px',
      scrollSnapType: 'x proximity', scrollPaddingInline: 12,
    }}>
      {children}
    </div>
  )
}

function RailSlot({ children }: { children: ReactNode }) {
  // Grid, not flex: a grid cell stretches the card to the slot's width.
  return <div style={{ width: CARD_WIDTH, flexShrink: 0, display: 'grid', scrollSnapAlign: 'start' }}>{children}</div>
}

function Eyebrow({ children, style, className }: { children: ReactNode; style?: CSSProperties; className?: string }) {
  return (
    <div className={className} style={{
      color: t.text3, fontFamily: font.family.mono, fontSize: font.size.micro + 0.5,
      textTransform: 'uppercase', letterSpacing: '0.06em', ...style,
    }}>
      {children}
    </div>
  )
}

function countLabel(n: number): string {
  return `${n} ${n === 1 ? 'product' : 'products'}`
}

/** "$35–48 · 16 stores": the span of starting prices and the stores carrying any of it. */
function shelfMeta(items: BrowseItem[]): string {
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
