/* ============================================================================
   BrowseScreen — the machinery every "browse a set of products" page shares.

   A category page and a brand page ask the same question of different slices of
   the catalogue, so they should offer the same tools: search, facets with live
   counts, a distance radius, a price range, and a sort. They did not — the
   category page had all of it and the brand page had a row of category chips —
   because each screen carried its own copy of the filter engine and only one
   copy ever got the work.

   Now the engine lives here and the pages supply three things: their items,
   their hero, and which facets apply to them. A brand page has no use for a
   brand facet; a category page has no use for a category facet. Everything else
   is identical, which is the point.

   `browse.tsx` holds the individual controls this assembles; this file holds
   the behaviour that connects them.
   ========================================================================== */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { t, font, radius } from '../theme'
import {
  readEnum, readNumber, readRange, readSet, useFilterParams, useScrollMemory,
  writeOne, writeRange, writeSet,
} from '../utils/browseState'
import { FeedState } from './ui'
import { Icon, type IconName } from './Icon'
import {
  ActiveChip, BrowseCard, BrowseGrid, BrowseToolbar, FacetChip, FilterSheet, GridSkeleton,
  SearchField, type SheetGroup,
} from './browse'
import { NO_LINE, nameWithinLine } from '../utils/lines'
import {
  FACET_TITLES, GROUP_MIN_RESULTS, KEEPS_CASE, SORTS, SORTS_NO_LOCATION, SORT_KEYS,
  activeFilterCount, bestPicks, browseCardOf, emptySelection, enrichItems, facetOptionsFor,
  flattenNote, flattenReason, groupByLine, hasShelves, matchesFilters, priceBoundsOf, priceRangeLabel,
  sortEnriched, sortLabelOf,
  type BrowseFilters, type BrowseItem, type Enriched, type FacetKey, type SortKey,
} from '../utils/browseLogic'
import LineShelves from './LineShelves'

/* ── What a page hands over ───────────────────────────────────────────────
   The item shape, the facets and the filter rules live in utils/browseLogic
   (framework-free, shared with the app); re-exported for the pages. */

export type { BrowseItem, BrowseOffering, FacetKey } from '../utils/browseLogic'

interface Props {
  items: BrowseItem[]
  loading: boolean
  error: string | null
  /** Shown as Try again on the error state. */
  onRetry?: () => void

  /** Accent for chips, stats and cards. */
  color: string
  /** Which facets this slice of the catalogue can be narrowed by. The first
   *  doubles as the quick rail above the results. */
  facets: readonly FacetKey[]

  /** Rendered above the search field, inside the hero block. */
  hero: ReactNode
  heroBackground: string
  /** Sits behind the hero — the oversized glyph or logo. */
  heroDecoration?: ReactNode

  searchPlaceholder: string
  /** Changing this clears the controls: a different brand or category has
   *  different facets, so carrying a selection over would filter to nothing. */
  resetKey: string

  /** How many the page holds before filtering, for "12 of 340". */
  totalCount: number
  truncated?: boolean
  /** A subtype equal to this is the page's own subject and reads as noise on
   *  the card — "flower" on every card of the flower category. */
  suppressSubtype?: string

  emptyMessage: string
  emptyHint?: string
  /** A glyph name from design/icons.ts, or a node (e.g. a category glyph). */
  emptyIcon?: IconName | ReactNode

  onOpen: (item: BrowseItem) => void

  /** Offer shelves by product line (flag `lines_grouped`), for the categories
   *  that pass LineShelves' rule. Needs the line facet among `facets`. */
  groupable?: boolean
}

type View = 'shelves' | 'grid'
const VIEWS: readonly View[] = ['shelves', 'grid']

export default function BrowseScreen({
  items, loading, error, onRetry, color, facets, hero, heroBackground, heroDecoration,
  searchPlaceholder, resetKey, totalCount, truncated, suppressSubtype,
  emptyMessage, emptyHint, emptyIcon, onOpen, groupable = false,
}: Props) {
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [locationDenied, setLocationDenied] = useState(false)

  // Seeded from the URL so that coming back from a product restores the screen
  // the shopper left, rather than an empty one.
  const [initialParams] = useSearchParams()
  const [search, setSearch] = useState(() => initialParams.get('q') ?? '')
  const [searchFocus, setSearchFocus] = useState(false)
  const [selected, setSelected] = useState<Record<FacetKey, Set<string>>>(() => ({
    category: readSet(initialParams, 'category'),
    subtype: readSet(initialParams, 'subtype'),
    brand: readSet(initialParams, 'brand'),
    variant: readSet(initialParams, 'variant'),
    line: readSet(initialParams, 'line'),
  }))
  const [radiusMi, setRadiusMi] = useState<number | null>(() => readNumber(initialParams, 'radius'))
  const [price, setPrice] = useState<[number, number] | null>(() => readRange(initialParams, 'price'))
  const [sort, setSort] = useState<SortKey>(() => readEnum(initialParams, 'sort', SORT_KEYS, 'featured'))
  const [view, setView] = useState<View>(() => readEnum(initialParams, 'view', VIEWS, 'shelves'))
  const [sheet, setSheet] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)

  useFilterParams({
    q: writeOne(search),
    // Only the facets this screen offers: a stale key from another screen would
    // otherwise sit in the URL filtering nothing.
    category: facets.includes('category') ? writeSet(selected.category) : [],
    subtype: facets.includes('subtype') ? writeSet(selected.subtype) : [],
    brand: facets.includes('brand') ? writeSet(selected.brand) : [],
    variant: facets.includes('variant') ? writeSet(selected.variant) : [],
    line: facets.includes('line') ? writeSet(selected.line) : [],
    radius: writeOne(radiusMi),
    price: writeRange(price),
    sort: sort === 'featured' ? [] : [sort],
    // Shelves are the default where they exist, so only the grid is written.
    view: groupable && view === 'grid' ? ['grid'] : [],
  })
  useScrollMemory(scrollRef, !loading && items.length > 0)

  // Skipped on mount, where the controls came from the URL.
  const previousKey = useRef(resetKey)
  useEffect(() => {
    if (previousKey.current === resetKey) return
    previousKey.current = resetKey
    setSearch('')
    setSelected(emptySelection())
    setRadiusMi(null); setPrice(null); setSort('featured'); setView('shelves')
    scrollRef.current?.scrollTo({ top: 0 })
  }, [resetKey])

  useEffect(() => {
    if (!navigator.geolocation) { setLocationDenied(true); return }
    navigator.geolocation.getCurrentPosition(
      pos => setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setLocationDenied(true),
    )
  }, [])

  const hasLocation = userPos != null

  // Resolve each item's closest and cheapest store once per position change.
  const enriched = useMemo<Enriched[]>(() => enrichItems(items, userPos), [items, userPos])

  // Full price span across the page — the bounds of the range slider.
  const priceBounds = useMemo(() => priceBoundsOf(enriched.map(e => e.item.minPriceCents)), [enriched])

  const filters: BrowseFilters = {
    search: search.trim().toLowerCase(),
    keys: facets,
    facets: selected,
    radiusMi,
    price,
  }

  // Every derived list depends on the same inputs; one signature keeps the
  // memos honest without listing six dependencies four times.
  const filterSignature = JSON.stringify([
    filters.search,
    facets,
    (Object.keys(selected) as FacetKey[]).map(k => [...selected[k]]),
    radiusMi,
    price,
  ])

  /** Facet options with counts that respect every *other* active filter. */
  const facetOptions = useMemo(
    () => facetOptionsFor(enriched, filters),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enriched, facets, filterSignature],
  )

  const filtered = useMemo(
    () => enriched.filter(e => matchesFilters(e, filters)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enriched, filterSignature],
  )

  const sorted = useMemo(() => sortEnriched(filtered, sort), [filtered, sort])

  // Drop a nearest sort / radius filter that location permission can't support.
  useEffect(() => {
    if (hasLocation) return
    if (sort === 'nearest') setSort('featured')
    if (radiusMi != null) setRadiusMi(null)
  }, [hasLocation, sort, radiusMi])

  // Shelves by line. Whether the page can have them is decided on everything
  // it holds, so the switch does not come and go as filters change; whether
  // they show right now also depends on what the shopper is doing. A search, a
  // price or distance sort, or a narrower filter than category asks for one
  // list in that order, and shelves would hide the answer: in 63 of 87
  // brands with several lines, the cheapest product had no line.
  const canGroup = useMemo(
    () => groupable && hasShelves(groupByLine(enriched, e => e.item)),
    [groupable, enriched],
  )
  const sections = useMemo(
    () => canGroup ? groupByLine(sorted, e => e.item) : [],
    [canGroup, sorted],
  )
  const flattenedBy = flattenReason({
    canGroup, grid: view === 'grid', search: filters.search, sort, facets: selected,
  })
  const showShelves = canGroup && view === 'shelves' && !flattenedBy
    && sorted.length >= GROUP_MIN_RESULTS && hasShelves(sections)

  // The page's best few, whatever line they are in, pinned above the shelves.
  const best = useMemo(
    () => showShelves ? bestPicks(filtered, hasLocation) : { entries: [] as Enriched[], label: '' },
    [showShelves, filtered, hasLocation],
  )

  /** Narrow to what a shelf's "See all" names; the grid takes over from there. */
  function seeOnly(category: string | null, lines: string[]) {
    setSelected(prev => ({
      ...prev,
      category: category ? new Set([category]) : prev.category,
      line: new Set(lines),
    }))
    scrollRef.current?.scrollTo({ top: 0 })
  }

  function toggle(key: FacetKey, value: string) {
    setSelected(prev => {
      const next = new Set(prev[key])
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return { ...prev, [key]: next }
    })
  }

  function clearAll() {
    setSelected(emptySelection())
    setRadiusMi(null)
    setPrice(null)
  }

  const activeCount = activeFilterCount(filters)

  const sorts = hasLocation ? SORTS : SORTS_NO_LOCATION
  const sortLabel = sortLabelOf(sort)

  const [quickKey] = facets
  const quickFacet = facetOptions[quickKey] ?? []

  // With one line picked, every card is in it, and the name compose() gave it
  // ("Palms Blue Dream") repeats what the filter already says.
  const [onlyLine] = facets.includes('line') && selected.line.size === 1 ? [...selected.line] : []
  function nameInLine(item: BrowseItem): string {
    if (!onlyLine || onlyLine === NO_LINE || item.line !== onlyLine) return item.name
    return nameWithinLine(item.name, item.line)
  }

  function renderCard(e: Enriched, inLine: boolean) {
    return (
      <BrowseCard
        key={e.item.key}
        item={browseCardOf(e, inLine ? nameWithinLine(e.item.name, e.item.line) : nameInLine(e.item))}
        color={color}
        suppressSubtype={suppressSubtype}
        onOpen={() => onOpen(e.item)}
      />
    )
  }

  const groups: SheetGroup[] = facets.map(key => ({
    key,
    title: FACET_TITLES[key],
    facet: facetOptions[key] ?? [],
    sel: selected[key],
    onToggle: (value: string) => toggle(key, value),
    capitalize: !KEEPS_CASE.has(key),
  }))

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{
        position: 'relative',
        background: heroBackground,
        padding: 'calc(env(safe-area-inset-top, 0px) + 16px) 16px 18px',
        overflow: 'hidden',
      }}>
        {heroDecoration}
        {hero}
        <div style={{ position: 'relative', marginTop: 16 }}>
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder={searchPlaceholder}
            focused={searchFocus}
            onFocus={() => setSearchFocus(true)}
            onBlur={() => setSearchFocus(false)}
          />
        </div>
      </div>

      {/* ── Sticky controls ──────────────────────────────────────────────── */}
      <BrowseToolbar
        activeCount={activeCount}
        sortLabel={sortLabel}
        onOpenSheet={() => setSheet(true)}
        onClear={clearAll}
        quickRail={quickFacet.length > 1 && (
          <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '10px 14px 10px' }}>
            <FacetChip
              label="All"
              active={selected[quickKey].size === 0}
              color={color}
              onClick={() => setSelected(prev => ({ ...prev, [quickKey]: new Set() }))}
            />
            {quickFacet.map(f => (
              <FacetChip
                key={f.value}
                label={f.value}
                count={f.count}
                active={selected[quickKey].has(f.value)}
                color={color}
                capitalize={!KEEPS_CASE.has(quickKey)}
                onClick={() => toggle(quickKey, f.value)}
              />
            ))}
          </div>
        )}
        activeChips={<>
          {radiusMi != null && (
            <ActiveChip label={`Within ${radiusMi} mi`} capitalize={false} onRemove={() => setRadiusMi(null)} />
          )}
          {price && (
            <ActiveChip
              label={priceRangeLabel(price)}
              capitalize={false}
              onRemove={() => setPrice(null)}
            />
          )}
          {facets.flatMap(key => [...selected[key]].map(value => (
            <ActiveChip
              key={key + value}
              label={value}
              capitalize={!KEEPS_CASE.has(key)}
              onRemove={() => toggle(key, value)}
            />
          )))}
        </>}
      />

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      {loading ? (
        <GridSkeleton />
      ) : error ? (
        <FeedState kind="error" message={error} onRetry={onRetry} />
      ) : items.length === 0 ? (
        <FeedState kind="empty" message={emptyMessage} hint={emptyHint} icon={emptyIcon} />
      ) : (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, padding: '14px 16px 4px',
          }}>
            <span className="num" style={{ color: t.text2, fontFamily: font.family.mono, fontSize: font.size.caption, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {sorted.length} {sorted.length === 1 ? 'product' : 'products'}
              {sorted.length !== totalCount && <span style={{ color: t.text3 }}> of {totalCount}</span>}
            </span>
            {truncated && (
              <span style={{ color: t.text3, fontSize: font.size.caption }}>showing top matches</span>
            )}
            {canGroup && <ViewSwitch view={view} onChange={setView} />}
          </div>
          {flattenedBy && (
            <div style={{ color: t.text3, fontSize: font.size.caption, padding: '2px 16px 0' }}>
              {flattenNote(flattenedBy, sortLabel)}
            </div>
          )}

          {!hasLocation && (
            <div style={{ color: t.text3, fontSize: font.size.caption, padding: '2px 16px 0', display: 'flex', alignItems: 'center', gap: 5 }}>
              <Icon name="locate" size={13} />
              {locationDenied
                ? 'Turn on location to filter and sort by distance'
                : 'Finding your location to show distances…'}
            </div>
          )}

          {sorted.length === 0 ? (
            <FeedState
              kind="empty"
              message="No matches"
              hint={search
                ? `Nothing matches “${search}” with these filters.`
                : 'Try widening the distance or price range.'}
              icon="search"
              style={{ minHeight: 260 }}
            />
          ) : showShelves ? (
            <LineShelves
              sections={sections}
              itemOf={e => e.item}
              renderCard={renderCard}
              best={best}
              onSeeLine={(category, line) => seeOnly(category, [line])}
              onSeeRest={(category, thinLines) => seeOnly(category, [NO_LINE, ...thinLines])}
              onSeeCategory={category => setSelected(prev => ({
                ...prev, category: category ? new Set([category]) : prev.category,
              }))}
            />
          ) : (
            <BrowseGrid items={sorted}>
              {e => renderCard(e, false)}
            </BrowseGrid>
          )}
        </>
      )}

      <FilterSheet
        open={sheet}
        onClose={() => setSheet(false)}
        resultCount={sorted.length}
        color={color}
        sort={sort}
        onSort={setSort}
        sorts={sorts}
        distance={{ hasLocation, radiusMi, onRadius: setRadiusMi }}
        priceBounds={priceBounds}
        price={price}
        onPrice={setPrice}
        groups={groups}
        onClear={clearAll}
        activeCount={activeCount}
      />
    </div>
  )
}

/** Shelves by line, or the plain grid. Shown only where shelves exist. */
function ViewSwitch({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  const options: { key: View; label: string; icon: IconName }[] = [
    { key: 'shelves', label: 'Shelves', icon: 'list' },
    { key: 'grid', label: 'Grid', icon: 'grid' },
  ]
  return (
    <div role="group" aria-label="Layout" style={{
      display: 'flex', gap: 2, padding: 2, borderRadius: radius.md,
      background: t.surface1, border: `1px solid ${t.border}`, flexShrink: 0,
    }}>
      {options.map(o => {
        const active = view === o.key
        return (
          <button
            key={o.key}
            aria-pressed={active}
            onClick={() => onChange(o.key)}
            style={{
              border: 'none', cursor: 'pointer', borderRadius: radius.sm, padding: '5px 9px',
              display: 'inline-flex', alignItems: 'center', gap: 5,
              background: active ? t.surface3 : 'transparent',
              color: active ? t.text1 : t.text3,
              fontSize: font.size.caption, fontWeight: active ? font.weight.semibold : font.weight.medium,
            }}
          >
            <Icon name={o.icon} size={13} />
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
