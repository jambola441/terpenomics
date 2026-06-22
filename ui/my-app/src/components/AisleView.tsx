import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { CartItem, DispensaryListing } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { Pressable, FeedState, Skeleton, Label } from './ui'

const CATEGORY_EMOJI: Record<string, string> = {
  flower: '🌸', vaporizers: '💨', cart: '💨', edible: '🍬', concentrate: '💎',
  preroll: '🌿', tinctures: '🧪', topical: '🧴', merch: '🛍️', other: '📦',
}

const CATEGORIES = ['flower', 'preroll', 'vaporizers', 'edible', 'concentrate', 'tinctures', 'topical', 'merch', 'other']

type SortKey = 'featured' | 'price-asc' | 'price-desc' | 'name'
const SORTS: { key: SortKey; label: string }[] = [
  { key: 'featured', label: 'Featured' },
  { key: 'price-asc', label: 'Price: Low → High' },
  { key: 'price-desc', label: 'Price: High → Low' },
  { key: 'name', label: 'Name A–Z' },
]

function formatPrice(cents: number | null) {
  if (cents == null) return null
  return `$${(cents / 100).toFixed(2)}`
}

function titleCase(s: string) {
  return s.replace(/(^|\s|-)\w/g, c => c.toUpperCase())
}

// Parse a variant like "3.5g" / "100mg" / "1 oz" into grams for natural ordering
function variantWeight(v: string): number {
  const m = v.match(/([\d.]+)\s*(g|mg|oz)?/i)
  if (!m) return Number.MAX_SAFE_INTEGER
  let n = parseFloat(m[1])
  const unit = (m[2] || 'g').toLowerCase()
  if (unit === 'mg') n /= 1000
  if (unit === 'oz') n *= 28.3495
  return n
}

interface Filters {
  search: string
  brand: Set<string>
  subtype: Set<string>
  variant: Set<string>
}

function listingMatches(l: DispensaryListing, f: Filters): boolean {
  if (f.search) {
    const q = f.search.toLowerCase()
    const hay = [l.scraped_name, l.scraped_brand, l.strain, l.subtype].filter(Boolean).join(' ').toLowerCase()
    if (!hay.includes(q)) return false
  }
  if (f.brand.size && !(l.scraped_brand && f.brand.has(l.scraped_brand))) return false
  if (f.subtype.size && !(l.subtype && f.subtype.has(l.subtype))) return false
  if (f.variant.size && !(l.variant && f.variant.has(l.variant))) return false
  return true
}

interface Props {
  dispensaryId: string
  dispensaryName: string
  dispensarySlug?: string
  category: string
  acceptsPickup?: boolean
  onAddToCart?: (item: CartItem) => void
  cart?: CartItem[]
}

export default function AisleView({
  dispensaryId, dispensaryName, dispensarySlug = '', category,
  acceptsPickup = false, onAddToCart, cart = [],
}: Props) {
  const navigate = useNavigate()
  const [all, setAll] = useState<DispensaryListing[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [searchFocus, setSearchFocus] = useState(false)
  const [brand, setBrand] = useState<Set<string>>(new Set())
  const [subtype, setSubtype] = useState<Set<string>>(new Set())
  const [variant, setVariant] = useState<Set<string>>(new Set())
  const [sort, setSort] = useState<SortKey>('featured')
  const [sheet, setSheet] = useState(false)

  const c = categoryColor(category)

  // Load the whole category once (paginated; API caps limit at 100), then
  // filter/sort/facet entirely on the client for instant UX.
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setAll([])
    setBrand(new Set()); setSubtype(new Set()); setVariant(new Set()); setSearch(''); setSort('featured')

    ;(async () => {
      const PAGE = 100
      const MAX = 1000 // safety cap
      const acc: DispensaryListing[] = []
      try {
        for (let offset = 0; offset < MAX; offset += PAGE) {
          const page = await api.portal.getDispensaryListings(dispensaryId, { category, limit: PAGE, offset })
          if (cancelled) return
          acc.push(...page)
          if (page.length < PAGE) break
        }
        if (!cancelled) setAll(acc)
      } catch {
        if (!cancelled) setError('Failed to load')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [dispensaryId, category])

  const filters: Filters = { search, brand, subtype, variant }

  // Facet options with counts. Counts respect the OTHER active facets (true faceted search).
  function facetFor(field: 'scraped_brand' | 'subtype' | 'variant', exclude: keyof Filters) {
    const base: Filters = { ...filters, [exclude]: new Set<string>() }
    const counts = new Map<string, number>()
    for (const l of all) {
      if (!listingMatches(l, base)) continue
      const v = (l[field] as string | null) ?? ''
      if (!v) continue
      counts.set(v, (counts.get(v) ?? 0) + 1)
    }
    return [...counts.entries()].map(([value, count]) => ({ value, count }))
  }

  const brandFacet = useMemo(() => facetFor('scraped_brand', 'brand').sort((a, b) => b.count - a.count), [all, search, subtype, variant])
  const subtypeFacet = useMemo(() => facetFor('subtype', 'subtype').sort((a, b) => b.count - a.count), [all, search, brand, variant])
  const variantFacet = useMemo(() => facetFor('variant', 'variant').sort((a, b) => variantWeight(a.value) - variantWeight(b.value)), [all, search, brand, subtype])

  const filtered = useMemo(() => all.filter(l => listingMatches(l, filters)), [all, search, brand, subtype, variant])

  const sorted = useMemo(() => {
    const arr = [...filtered]
    if (sort === 'price-asc' || sort === 'price-desc') {
      const dir = sort === 'price-asc' ? 1 : -1
      arr.sort((a, b) => {
        if (a.price_cents == null) return 1
        if (b.price_cents == null) return -1
        return (a.price_cents - b.price_cents) * dir
      })
    } else if (sort === 'name') {
      arr.sort((a, b) => (a.scraped_name ?? '').localeCompare(b.scraped_name ?? ''))
    }
    return arr
  }, [filtered, sort])

  const activeCount = brand.size + subtype.size + variant.size
  const sortLabel = SORTS.find(s => s.key === sort)!.label

  function toggle(setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) {
    setter(prev => {
      const next = new Set(prev)
      next.has(value) ? next.delete(value) : next.add(value)
      return next
    })
  }

  function clearAll() {
    setBrand(new Set()); setSubtype(new Set()); setVariant(new Set())
  }

  function renderCard(l: DispensaryListing) {
    const price = formatPrice(l.price_cents)
    const cartQty = cart.filter(i => i.listingId === l.id).reduce((s, i) => s + i.quantity, 0)

    return (
      <Pressable
        key={l.id}
        onClick={() => navigate(`/portal/map/${dispensaryId}/listings/${l.id}`)}
        style={{
          background: t.surface1, borderRadius: radius.lg, border: `1px solid ${t.border}`,
          overflow: 'hidden', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ position: 'relative', aspectRatio: '1 / 1', background: t.tile, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.06)' }}>
          {l.image_url ? (
            <img src={l.image_url} alt={l.scraped_name ?? ''} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 12, boxSizing: 'border-box' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            <span style={{ fontSize: 34, opacity: 0.5 }}>{CATEGORY_EMOJI[category] ?? '📦'}</span>
          )}
          {l.variant && (
            <span style={{
              position: 'absolute', top: 8, left: 8,
              background: alpha('#000', 0.62), color: '#fff', backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
              fontSize: font.size.micro, fontWeight: font.weight.bold, padding: '3px 8px', borderRadius: radius.pill,
            }}>{l.variant}</span>
          )}
          {acceptsPickup && onAddToCart && (
            <button
              aria-label="Add to cart"
              onClick={e => {
                e.stopPropagation()
                onAddToCart({
                  listingId: l.id, dispensaryId, dispensarySlug, dispensaryName,
                  name: l.scraped_name ?? '—', brand: l.scraped_brand ?? null,
                  variant: l.variant ?? null, price_cents: l.price_cents ?? null,
                  url: l.url ?? null, image_url: l.image_url ?? null, quantity: 1,
                })
              }}
              style={{
                position: 'absolute', bottom: 8, right: 8,
                width: 32, height: 32, borderRadius: '50%',
                background: cartQty > 0 ? t.accent : '#fff',
                border: 'none', cursor: 'pointer', padding: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 13, fontWeight: 700, color: '#0a0a0a',
                boxShadow: '0 2px 10px rgba(0,0,0,0.45)',
                transition: `background var(--t-fast)`,
              }}
            >
              {cartQty > 0 ? cartQty : (
                <span style={{ position: 'relative', width: 10, height: 10, display: 'block' }}>
                  <span style={{ position: 'absolute', top: '50%', left: 0, right: 0, height: 2, marginTop: -1, background: '#0a0a0a', borderRadius: 1 }} />
                  <span style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 2, marginLeft: -1, background: '#0a0a0a', borderRadius: 1 }} />
                </span>
              )}
            </button>
          )}
        </div>
        <div style={{ padding: '10px 11px 12px', flex: 1, display: 'flex', flexDirection: 'column' }}>
          {price && <div style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: font.size.callout, marginBottom: 4 }}>{price}</div>}
          <div style={{
            color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small + 1, lineHeight: 1.3,
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          } as React.CSSProperties}>
            {l.scraped_name ?? l.strain ?? '—'}
          </div>
          {l.scraped_brand && (
            <div style={{ color: t.text3, fontSize: font.size.caption, marginTop: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {l.scraped_brand}
            </div>
          )}
          {l.subtype && l.subtype.toLowerCase() !== category.toLowerCase() && (
            <div style={{ marginTop: 8 }}>
              <span style={{
                background: alpha(c, 0.13), color: c, border: `1px solid ${alpha(c, 0.3)}`,
                fontSize: font.size.micro, fontWeight: font.weight.bold, padding: '2px 8px', borderRadius: radius.pill,
                textTransform: 'capitalize', letterSpacing: '0.03em',
              }}>{l.subtype}</span>
            </div>
          )}
        </div>
      </Pressable>
    )
  }

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>

      {/* ── Title + search (scroll away) ── */}
      <div>

        {/* Row 1: back + title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 'calc(env(safe-area-inset-top, 0px) + 20px) 16px 10px' }}>
          <button
            onClick={() => navigate(`/portal/map/${dispensaryId}`)}
            aria-label="Back"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.text2, fontSize: 26, padding: '0 2px', lineHeight: 1, flexShrink: 0, alignSelf: 'flex-start', marginTop: 2 }}
          >←</button>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero, letterSpacing: '-0.02em', textTransform: 'capitalize', lineHeight: 1.1 }}>
              <span style={{ fontSize: 24 }}>{CATEGORY_EMOJI[category] ?? '📦'}</span>
              {category}
            </div>
            {dispensaryName && (
              <div style={{ color: t.text3, fontSize: font.size.small + 1, marginTop: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {dispensaryName}
              </div>
            )}
          </div>
        </div>

        {/* Row 2: search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 14px 8px' }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            onFocus={() => setSearchFocus(true)}
            onBlur={() => setSearchFocus(false)}
            placeholder={`Search ${category}…`}
            style={{
              flex: 1, background: t.surface2,
              border: `1px solid ${searchFocus ? t.accent : t.border}`,
              boxShadow: searchFocus ? 'var(--ring)' : 'none',
              borderRadius: radius.md, color: t.text1, fontSize: font.size.body, padding: '10px 13px', outline: 'none',
              transition: `border-color var(--t-fast), box-shadow var(--t-fast)`,
            }}
          />
          {search && (
            <button onClick={() => setSearch('')} aria-label="Clear search"
              style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.md, color: t.text3, fontSize: 13, padding: '0 12px', height: 40, cursor: 'pointer', flexShrink: 0 }}>✕</button>
          )}
        </div>
      </div>

      {/* ── Sticky controls: category switcher + filter bar ── */}
      <div style={{ position: 'sticky', top: 0, zIndex: 10, background: 'rgba(11,11,13,0.92)', backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)', borderBottom: `1px solid ${t.border}` }}>

        {/* Category switcher */}
        <div className="no-scrollbar" style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '10px 14px 10px' }}>
          {CATEGORIES.map(cat => {
            const active = category === cat
            const cc = categoryColor(cat)
            return (
              <button
                key={cat}
                onClick={() => navigate(`/portal/map/${dispensaryId}/aisle/${encodeURIComponent(cat)}`)}
                style={{
                  flexShrink: 0, cursor: 'pointer', whiteSpace: 'nowrap', textTransform: 'capitalize',
                  fontSize: font.size.small + 1, fontWeight: active ? font.weight.bold : font.weight.medium,
                  padding: '7px 14px', borderRadius: radius.pill,
                  background: active ? alpha(cc, 0.16) : t.surface2,
                  border: `1px solid ${active ? alpha(cc, 0.55) : t.border}`,
                  color: active ? cc : t.text3,
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  transition: `all var(--t-fast)`,
                }}
              >
                <span style={{ fontSize: 13 }}>{CATEGORY_EMOJI[cat] ?? '📦'}</span>{cat}
              </button>
            )
          })}
        </div>

        {/* Row 3: filter / sort bar */}
        <div className="no-scrollbar" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 14px 10px', overflowX: 'auto' }}>
          <button
            onClick={() => setSheet(true)}
            style={{
              flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 7, cursor: 'pointer',
              padding: '8px 14px', borderRadius: radius.pill,
              background: activeCount ? 'var(--accent-tint)' : t.surface2,
              border: `1px solid ${activeCount ? t.accent : t.border}`,
              color: activeCount ? t.accent : t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.semibold,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
              <path d="M3 5h18v2l-7 7v5l-4 2v-7L3 7z" />
            </svg>
            Filters{activeCount ? ` · ${activeCount}` : ''}
          </button>

          <button
            onClick={() => setSheet(true)}
            style={{
              flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer',
              padding: '8px 14px', borderRadius: radius.pill, background: t.surface2, border: `1px solid ${t.border}`,
              color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium,
            }}
          >
            {sortLabel} <span style={{ color: t.text3 }}>▾</span>
          </button>

          {/* Active filter chips */}
          {[...subtype].map(v => <ActiveChip key={'s' + v} label={titleCase(v)} onRemove={() => toggle(setSubtype, v)} />)}
          {[...brand].map(v => <ActiveChip key={'b' + v} label={v} onRemove={() => toggle(setBrand, v)} />)}
          {[...variant].map(v => <ActiveChip key={'v' + v} label={v} onRemove={() => toggle(setVariant, v)} />)}
          {activeCount > 0 && (
            <button onClick={clearAll} style={{ flexShrink: 0, background: 'none', border: 'none', color: t.text3, fontSize: font.size.small, cursor: 'pointer', whiteSpace: 'nowrap', textDecoration: 'underline' }}>
              Clear
            </button>
          )}
        </div>
      </div>

      {/* ── Body ── */}
      {loading ? (
        <GridSkeleton />
      ) : error ? (
        <FeedState kind="error" message={error} />
      ) : all.length === 0 ? (
        <FeedState kind="empty" message={`No ${category} in stock`} hint="Check back soon — menus update regularly." icon={CATEGORY_EMOJI[category] ?? '🌿'} />
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '14px 16px 6px' }}>
            <span style={{ color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium }}>
              {sorted.length} {sorted.length === 1 ? 'product' : 'products'}
            </span>
          </div>
          {sorted.length === 0 ? (
            <FeedState
              kind="empty"
              message="No matches"
              hint={search ? `Nothing matches “${search}” with these filters.` : 'Try removing a filter.'}
              icon="🔍"
              style={{ minHeight: 240 }}
            />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '4px 12px 96px' }}>
              {sorted.map(renderCard)}
            </div>
          )}
        </>
      )}

      {/* ── Filter & sort sheet ── */}
      <FilterSheet
        open={sheet}
        onClose={() => setSheet(false)}
        resultCount={sorted.length}
        categoryColor={c}
        sort={sort}
        onSort={setSort}
        subtypeFacet={subtypeFacet}
        brandFacet={brandFacet}
        variantFacet={variantFacet}
        subtypeSel={subtype}
        brandSel={brand}
        variantSel={variant}
        onToggleSubtype={v => toggle(setSubtype, v)}
        onToggleBrand={v => toggle(setBrand, v)}
        onToggleVariant={v => toggle(setVariant, v)}
        onClear={clearAll}
        activeCount={activeCount}
      />
    </div>
  )
}

/* ── Active filter chip (removable) ───────────────────────────────────────── */
function ActiveChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span style={{
      flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 5,
      background: 'var(--accent-tint)', border: `1px solid ${alpha('#a8e063', 0.4)}`, color: t.accent,
      fontSize: font.size.small, fontWeight: font.weight.semibold, padding: '5px 6px 5px 11px', borderRadius: radius.pill,
      whiteSpace: 'nowrap', maxWidth: 160,
    }}>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      <button onClick={onRemove} aria-label={`Remove ${label}`}
        style={{ background: 'none', border: 'none', color: t.accent, cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: '0 2px', flexShrink: 0 }}>✕</button>
    </span>
  )
}

/* ── Facet chip (toggle, with count) ──────────────────────────────────────── */
function FacetChip({ label, count, active, color, onClick }: {
  label: string; count?: number; active: boolean; color: string; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        cursor: 'pointer', whiteSpace: 'nowrap', textTransform: 'capitalize',
        fontSize: font.size.small + 1, fontWeight: active ? font.weight.bold : font.weight.medium,
        padding: '8px 13px', borderRadius: radius.pill,
        background: active ? alpha(color, 0.16) : t.surface2,
        border: `1px solid ${active ? color : t.border}`,
        color: active ? color : t.text2,
        display: 'inline-flex', alignItems: 'center', gap: 6,
        transition: `all var(--t-fast)`,
      }}
    >
      {label}
      {count != null && (
        <span style={{ color: active ? color : t.text4, fontWeight: font.weight.semibold, fontSize: font.size.caption }}>{count}</span>
      )}
    </button>
  )
}

/* ── Bottom sheet: Filter & sort ──────────────────────────────────────────── */
function FilterSheet({
  open, onClose, resultCount, categoryColor: cc, sort, onSort,
  subtypeFacet, brandFacet, variantFacet, subtypeSel, brandSel, variantSel,
  onToggleSubtype, onToggleBrand, onToggleVariant, onClear, activeCount,
}: {
  open: boolean
  onClose: () => void
  resultCount: number
  categoryColor: string
  sort: SortKey
  onSort: (s: SortKey) => void
  subtypeFacet: { value: string; count: number }[]
  brandFacet: { value: string; count: number }[]
  variantFacet: { value: string; count: number }[]
  subtypeSel: Set<string>
  brandSel: Set<string>
  variantSel: Set<string>
  onToggleSubtype: (v: string) => void
  onToggleBrand: (v: string) => void
  onToggleVariant: (v: string) => void
  onClear: () => void
  activeCount: number
}) {
  return (
    <>
      {/* Backdrop */}
      {open && (
        <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: alpha('#000', 0.6), zIndex: 2200, backdropFilter: 'blur(2px)' }} />
      )}

      {/* Panel */}
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 2300,
        background: t.surface1, borderTop: `1px solid ${t.border}`,
        borderRadius: `${radius['2xl']} ${radius['2xl']} 0 0`, boxShadow: 'var(--e-3)',
        transform: open ? 'translateY(0)' : 'translateY(100%)',
        transition: `transform 0.34s ${'cubic-bezier(0.32,0.72,0,1)'}`,
        maxHeight: '86dvh', display: 'flex', flexDirection: 'column',
      }}>
        {/* Handle + header */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: t.surface3 }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px 4px' }}>
          <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, letterSpacing: '-0.01em' }}>Filter &amp; sort</div>
          {activeCount > 0 && (
            <button onClick={onClear} style={{ background: 'none', border: 'none', color: t.text3, fontSize: font.size.small + 1, cursor: 'pointer' }}>Clear all</button>
          )}
        </div>

        {/* Scrollable groups */}
        <div style={{ overflowY: 'auto', padding: '12px 20px 8px', display: 'flex', flexDirection: 'column', gap: 22 }}>
          {/* Sort */}
          <div>
            <Label style={{ marginBottom: 10 }}>Sort</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {SORTS.map(s => (
                <FacetChip key={s.key} label={s.label} active={sort === s.key} color="var(--accent)" onClick={() => onSort(s.key)} />
              ))}
            </div>
          </div>

          {subtypeFacet.length > 1 && (
            <FacetGroup title="Subcategory" facet={subtypeFacet} sel={subtypeSel} color={cc} onToggle={onToggleSubtype} />
          )}
          {variantFacet.length > 1 && (
            <FacetGroup title="Weight / Size" facet={variantFacet} sel={variantSel} color={cc} onToggle={onToggleVariant} />
          )}
          {brandFacet.length > 1 && (
            <FacetGroup title="Brand" facet={brandFacet} sel={brandSel} color={cc} onToggle={onToggleBrand} />
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: '12px 20px', borderTop: `1px solid ${t.border}` }}>
          <button
            onClick={onClose}
            style={{
              width: '100%', background: t.accent, border: 'none', borderRadius: radius.lg,
              color: '#0a0a0a', fontWeight: font.weight.bold, fontSize: font.size.callout, padding: '14px', cursor: 'pointer',
              boxShadow: 'var(--e-1)',
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

function FacetGroup({ title, facet, sel, color, onToggle }: {
  title: string
  facet: { value: string; count: number }[]
  sel: Set<string>
  color: string
  onToggle: (v: string) => void
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
            onClick={() => onToggle(f.value)}
          />
        ))}
      </div>
    </div>
  )
}

function GridSkeleton() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '18px 12px 80px' }}>
      {[0, 1, 2, 3, 4, 5].map(i => (
        <div key={i} style={{ background: 'var(--surface-1)', borderRadius: radius.lg, border: `1px solid ${t.border}`, overflow: 'hidden' }}>
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
