// BrowseScreen — the machinery the category and brand pages share, the twin of
// the web's components/BrowseScreen.tsx. The pages supply their items, their
// hero and which facets apply; this holds search-within, facets with live
// counts, the distance radius, the price range, the sort and the Shelves/Grid
// switch. The rules themselves (matching, counting, sorting, shelving) come
// from @web/utils/browseLogic, so both platforms answer the same way.
//
// Differences from the web: the controls are not written to the URL (a pushed
// screen keeps its state while a product is open on top of it), and a page is
// remounted rather than reset when its subject changes (the caller keys it).

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { nameWithinLine, NO_LINE } from '@web/utils/lines'
import {
  FACET_TITLES, GROUP_MIN_RESULTS, KEEPS_CASE, SORTS, SORTS_NO_LOCATION,
  activeFilterCount, bestPicks, browseCardOf, emptySelection, enrichItems, facetOptionsFor,
  flattenNote, flattenReason, groupByLine, hasShelves, matchesFilters, priceBoundsOf, priceRangeLabel,
  sortEnriched, sortLabelOf, toggled,
  type BrowseFilters, type BrowseItem, type Enriched, type FacetKey, type FacetSelection, type SortKey,
} from '@web/utils/browseLogic'
import { useKnownPosition } from '@/components/partners'
import { FeedState } from '@/components/ui'
import { Icon, type IconName } from '@/components/Icon'
import BrowseCard from './BrowseCard'
import BrowseList, { type ScrollToTop } from './BrowseList'
import FilterSheet, { type SheetGroup } from './FilterSheet'
import LineShelves from './LineShelves'
import {
  ActiveChip, BrowseToolbar, FacetChip, GridSkeleton, SearchField, ViewSwitch, useGridCardWidth,
  type BrowseView,
} from './controls'
import { t, font, fonts } from '@/lib/theme'

export type { BrowseItem, FacetKey }

/** How long to wait for a known position before saying location is off. */
const LOCATION_GRACE_MS = 1500

export default function BrowseScreen({
  items, loading, error, onRetry, refreshing, onRefresh, color, facets, hero, decoration, wash,
  searchPlaceholder, totalCount, truncated, suppressSubtype,
  emptyMessage, emptyHint, emptyIcon, onOpen, groupable = false,
}: {
  items: BrowseItem[]
  loading: boolean
  error: string | null
  onRetry?: () => void
  refreshing?: boolean
  onRefresh?: () => void
  /** Accent for chips and cards. */
  color: string
  /** Which facets this slice can be narrowed by; the first is the quick rail. */
  facets: readonly FacetKey[]
  hero: ReactNode
  decoration?: ReactNode
  /** The hero wash's opacity at the top. */
  wash?: number
  searchPlaceholder: string
  /** How many the page holds before filtering, for "12 of 340". */
  totalCount: number
  truncated?: boolean
  /** A subtype equal to this is the page's own subject and reads as noise. */
  suppressSubtype?: string
  emptyMessage: string
  emptyHint?: string
  emptyIcon?: IconName
  onOpen: (item: BrowseItem) => void
  /** Offer shelves by product line (flag `lines_grouped`). Needs the line facet. */
  groupable?: boolean
}) {
  // Only a position the shopper already shared; this screen never asks.
  const userPos = useKnownPosition()
  const [locationSettled, setLocationSettled] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setLocationSettled(true), LOCATION_GRACE_MS)
    return () => clearTimeout(id)
  }, [])
  const hasLocation = userPos != null

  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<FacetSelection>(emptySelection)
  const [radiusChoice, setRadiusMi] = useState<number | null>(null)
  const [price, setPrice] = useState<[number, number] | null>(null)
  const [sortChoice, setSort] = useState<SortKey>('featured')
  const [view, setView] = useState<BrowseView>('shelves')
  const [sheet, setSheet] = useState(false)
  const listRef = useRef<ScrollToTop>(null)
  const cardWidth = useGridCardWidth()

  // A nearest sort or a radius only stands while there is a position to use;
  // without one they read as Featured and Any (the web drops them in an effect).
  const sort: SortKey = !hasLocation && sortChoice === 'nearest' ? 'featured' : sortChoice
  const radiusMi = hasLocation ? radiusChoice : null

  const enriched = useMemo(() => enrichItems(items, userPos), [items, userPos])
  const priceBounds = useMemo(() => priceBoundsOf(enriched.map(e => e.item.minPriceCents)), [enriched])

  const filters: BrowseFilters = useMemo(() => ({
    search: search.trim().toLowerCase(), keys: facets, facets: selected, radiusMi, price,
  }), [search, facets, selected, radiusMi, price])

  const facetOptions = useMemo(() => facetOptionsFor(enriched, filters), [enriched, filters])
  const filtered = useMemo(() => enriched.filter(e => matchesFilters(e, filters)), [enriched, filters])
  const sorted = useMemo(() => sortEnriched(filtered, sort), [filtered, sort])

  // Whether the page can have shelves is decided on everything it holds, so
  // the switch does not come and go as filters change.
  const canGroup = useMemo(
    () => groupable && hasShelves(groupByLine(enriched, e => e.item)),
    [groupable, enriched],
  )
  const sections = useMemo(() => (canGroup ? groupByLine(sorted, e => e.item) : []), [canGroup, sorted])
  const sortLabel = sortLabelOf(sort)
  const flattenedBy = flattenReason({ canGroup, grid: view === 'grid', search: filters.search, sort, facets: selected })
  const showShelves = canGroup && view === 'shelves' && !flattenedBy
    && sorted.length >= GROUP_MIN_RESULTS && hasShelves(sections)
  const best = useMemo(
    () => (showShelves ? bestPicks(filtered, hasLocation) : { entries: [] as Enriched[], label: '' }),
    [showShelves, filtered, hasLocation],
  )

  const toTop = () => listRef.current?.scrollToOffset({ offset: 0, animated: false })

  /** Narrow to what a shelf's "See all" names; the grid takes over from there. */
  function seeOnly(category: string | null, lines: string[]) {
    setSelected(prev => ({
      ...prev,
      category: category ? new Set([category]) : prev.category,
      line: new Set(lines),
    }))
    toTop()
  }

  function toggle(key: FacetKey, value: string) {
    setSelected(prev => ({ ...prev, [key]: toggled(prev[key], value) }))
  }

  function clearAll() {
    setSelected(emptySelection())
    setRadiusMi(null)
    setPrice(null)
  }

  const activeCount = activeFilterCount(filters)
  const sorts = hasLocation ? SORTS : SORTS_NO_LOCATION

  const [quickKey] = facets
  const quickFacet = facetOptions[quickKey] ?? []

  // With one line picked, every card is in it, and "Palms Blue Dream" repeats
  // what the filter already says.
  const [onlyLine] = facets.includes('line') && selected.line.size === 1 ? [...selected.line] : []
  function nameInLine(item: BrowseItem): string {
    if (!onlyLine || onlyLine === NO_LINE || item.line !== onlyLine) return item.name
    return nameWithinLine(item.name, item.line)
  }

  function renderCard(e: Enriched, inLine: boolean, width: number) {
    return (
      <BrowseCard
        item={browseCardOf(e, inLine ? nameWithinLine(e.item.name, e.item.line) : nameInLine(e.item))}
        color={color}
        suppressSubtype={suppressSubtype}
        width={width}
        onPress={() => onOpen(e.item)}
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

  const toolbar = (
    <BrowseToolbar
      activeCount={activeCount}
      sortLabel={sortLabel}
      onOpenSheet={() => setSheet(true)}
      onClear={clearAll}
      quickRail={quickFacet.length > 1 ? (
        <>
          <FacetChip
            label="All"
            active={selected[quickKey].size === 0}
            color={color}
            onPress={() => setSelected(prev => ({ ...prev, [quickKey]: new Set() }))}
          />
          {quickFacet.map(f => (
            <FacetChip
              key={f.value}
              label={f.value}
              count={f.count}
              active={selected[quickKey].has(f.value)}
              color={color}
              capitalize={!KEEPS_CASE.has(quickKey)}
              onPress={() => toggle(quickKey, f.value)}
            />
          ))}
        </>
      ) : null}
      activeChips={(
        <>
          {radiusMi != null ? (
            <ActiveChip label={`Within ${radiusMi} mi`} capitalize={false} onRemove={() => setRadiusMi(null)} />
          ) : null}
          {price ? <ActiveChip label={priceRangeLabel(price)} capitalize={false} onRemove={() => setPrice(null)} /> : null}
          {facets.flatMap(key => [...selected[key]].map(value => (
            <ActiveChip
              key={key + value}
              label={value}
              capitalize={!KEEPS_CASE.has(key)}
              onRemove={() => toggle(key, value)}
            />
          )))}
        </>
      )}
    />
  )

  const heroBlock = (
    <>
      {hero}
      <View style={{ marginTop: 16 }}>
        <SearchField value={search} onChange={setSearch} placeholder={searchPlaceholder} />
      </View>
    </>
  )

  const ready = !loading && !error && items.length > 0
  const status = ready ? (
    <View>
      <View style={s.countRow}>
        <Text style={s.count}>
          {sorted.length} {sorted.length === 1 ? 'product' : 'products'}
          {sorted.length !== totalCount ? <Text style={{ color: t.text3 }}> of {totalCount}</Text> : null}
        </Text>
        {truncated ? <Text style={s.note}>showing top matches</Text> : null}
        {canGroup ? <ViewSwitch view={view} onChange={setView} /> : null}
      </View>
      {flattenedBy ? <Text style={[s.note, s.line]}>{flattenNote(flattenedBy, sortLabel)}</Text> : null}
      {!hasLocation ? (
        <View style={[s.line, s.locate]}>
          <Icon name="locate" size={13} color={t.text3} />
          <Text style={s.note}>
            {locationSettled ? 'Turn on location to filter and sort by distance' : 'Finding your location to show distances…'}
          </Text>
        </View>
      ) : null}
    </View>
  ) : null

  let body: ReactNode = null
  if (loading) body = <GridSkeleton />
  else if (error) body = <FeedState error={error} onRetry={onRetry} style={s.state} />
  else if (items.length === 0) body = <FeedState empty={emptyMessage} hint={emptyHint} icon={emptyIcon} style={s.state} />
  else if (sorted.length === 0) {
    body = (
      <FeedState
        empty="No matches"
        hint={search ? `Nothing matches “${search}” with these filters.` : 'Try widening the distance or price range.'}
        icon="search"
        style={s.state}
      />
    )
  } else if (showShelves) {
    body = (
      <LineShelves
        sections={sections}
        itemOf={e => e.item}
        renderCard={renderCard}
        gridCardWidth={cardWidth}
        best={best}
        onSeeLine={(category, line) => seeOnly(category, [line])}
        onSeeRest={(category, thinLines) => seeOnly(category, [NO_LINE, ...thinLines])}
        onSeeCategory={category => setSelected(prev => ({
          ...prev, category: category ? new Set([category]) : prev.category,
        }))}
      />
    )
  }

  return (
    <>
      <BrowseList<Enriched>
        listRef={listRef}
        color={color}
        wash={wash}
        decoration={decoration}
        hero={heroBlock}
        toolbar={toolbar}
        status={status}
        items={sorted}
        keyOf={e => e.item.key}
        renderCard={(e, width) => renderCard(e, false, width)}
        body={body}
        refreshing={refreshing}
        onRefresh={onRefresh}
      />
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
    </>
  )
}

const s = StyleSheet.create({
  countRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12,
    paddingTop: 14, paddingHorizontal: 16, paddingBottom: 4,
  },
  count: {
    fontFamily: fonts.mono, fontSize: font.size.caption, color: t.text2,
    textTransform: 'uppercase', letterSpacing: 0.66, fontVariant: ['tabular-nums'],
  },
  note: { fontFamily: fonts.sans, fontSize: font.size.caption, color: t.text3 },
  line: { paddingTop: 2, paddingHorizontal: 16 },
  locate: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  state: { flex: 0, minHeight: 300, paddingVertical: 48 },
})
