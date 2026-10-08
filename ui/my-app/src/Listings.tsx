import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { SearchBar } from './components/SearchBar'
import { AdminTable, badge, categoryColor, navBtnStyle, selectStyle, Dash, type Column } from './components/AdminTable'
import api from './api/client'
import type { Listing } from './types'
import { t, font } from './theme'
import { Icon } from './components/Icon'

const CATEGORIES = [
  'flower', 'vaporizers', 'preroll', 'concentrate', 'edible',
  'tinctures', 'topical', 'merch', 'other',
]
const LIMIT = 50

type FilterOptions = {
  dispensaries: { id: string; name: string }[]
  brands: string[]
  classifications: string[]
  subtypes: string[]
}

export default function Listings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  // Committed filter values live in the URL
  const q                 = searchParams.get('q') ?? ''
  const filterDispensary  = searchParams.get('dispensary_id') ?? ''
  const filterCategory    = searchParams.get('category') ?? ''
  const filterBrand       = searchParams.get('brand') ?? ''
  const filterSubtype     = searchParams.get('subtype') ?? ''
  const filterClass       = searchParams.get('classification') ?? ''
  const filterInStock     = searchParams.get('in_stock') ?? ''
  const sort              = searchParams.get('sort') ?? ''
  const order             = searchParams.get('order') ?? 'desc'

  // Controlled input state (unconfirmed search text)
  const [searchInput, setSearchInput] = useState(q)

  // Data state
  const [listings, setListings] = useState<Listing[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filterOpts, setFilterOpts] = useState<FilterOptions>({ dispensaries: [], brands: [], classifications: [], subtypes: [] })
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(true)

  // Keep searchInput in sync if the URL q param changes externally (e.g. back button)
  const prevQ = useRef(q)
  useEffect(() => {
    if (q !== prevQ.current) {
      setSearchInput(q)
      prevQ.current = q
    }
  }, [q])

  useEffect(() => {
    api.listings.filterOptions()
      .then(setFilterOpts)
      .catch(() => {})
  }, [])

  // Reset and fetch whenever URL filters change
  const filterKey = searchParams.toString()
  useEffect(() => {
    setOffset(0)
    setHasMore(true)
    fetchListings(0)
  }, [filterKey])

  async function fetchListings(currentOffset: number) {
    setLoading(true)
    setError(null)
    try {
      const inStockParam = filterInStock === 'true' ? true : filterInStock === 'false' ? false : undefined
      const data = await api.listings.list({
        q: q || undefined,
        dispensary_id: filterDispensary || undefined,
        category: filterCategory || undefined,
        brand: filterBrand || undefined,
        subtype: filterSubtype || undefined,
        classification: filterClass || undefined,
        in_stock: inStockParam,
        sort: sort || undefined,
        order: order || undefined,
        limit: LIMIT,
        offset: currentOffset,
      })
      setListings(prev => currentOffset === 0 ? data : [...prev, ...data])
      setHasMore(data.length === LIMIT)
      if (currentOffset > 0) setOffset(currentOffset)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function setFilter(key: string, value: string) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      if (value) next.set(key, value)
      else next.delete(key)
      return next
    })
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setFilter('q', searchInput.trim())
  }

  function clearSearch() {
    setSearchInput('')
    setFilter('q', '')
  }

  function clearFilters() {
    setSearchInput('')
    setSearchParams(new URLSearchParams())
  }

  function handleSort(col: string) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      if (sort === col) {
        next.set('order', order === 'asc' ? 'desc' : 'asc')
      } else {
        next.set('sort', col)
        next.set('order', 'asc')
      }
      return next
    })
  }

  const hasFilters = q || filterDispensary || filterCategory || filterBrand || filterSubtype || filterClass || filterInStock

  const columns: Column<Listing>[] = [
    { key: 'name', header: 'Scraped Name', sortable: true, td: { color: t.text1, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
      render: l => l.scraped_name ?? <Dash /> },
    { key: 'brand', header: 'Brand', sortable: true,
      render: l => l.scraped_brand ?? <Dash /> },
    { key: 'category', header: 'Category', sortable: true,
      render: l => l.scraped_category ? <span style={{ ...badge, ...categoryColor(l.scraped_category) }}>{l.scraped_category}</span> : <Dash /> },
    { key: 'subtype', header: 'Subtype', sortable: true,
      render: l => l.subtype ?? <Dash /> },
    { key: 'product_line', header: 'Product Line', sortable: true, td: { color: t.text2 },
      render: l => l.product_line ?? <Dash /> },
    { key: 'strain', header: 'Strain', sortable: true, td: { color: t.text1 },
      render: l => l.strain ?? <Dash /> },
    { key: 'classification', header: 'Class', td: { color: t.text2 },
      render: l => l.classification ?? <Dash /> },
    { key: 'variant', header: 'Variant',
      render: l => l.variant ?? <Dash /> },
    { key: 'dispensary', header: 'Dispensary', sortable: true, td: { color: t.text2 },
      render: l => l.dispensary_name },
    { key: 'price', header: 'Price', sortable: true,
      render: l => l.price_cents != null ? `$${(l.price_cents / 100).toFixed(2)}` : <Dash /> },
    { key: 'in_stock', header: 'In Stock',
      render: l => l.in_stock ? <Icon name="check" size={15} color={t.success} label="In stock" /> : <Icon name="close" size={15} color={t.text4} label="Out of stock" /> },
    { key: 'link', header: '', align: 'right', stopPropagation: true,
      render: l => l.url ? <a href={l.url} target="_blank" rel="noopener noreferrer" style={{ color: t.accent, textDecoration: 'none', display: 'inline-flex' }} title={l.url}><Icon name="arrow-up-right" size={15} label="Open on store site" /></a> : null },
  ]

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 1300, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Listings</h1>
        </div>

        {/* Search + filters */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
          <SearchBar
            value={searchInput}
            onChange={setSearchInput}
            onSearch={handleSearch}
            onClear={clearSearch}
            placeholder="Search by name or brand…"
            disabled={loading}
            showClearButton={!!q}
          />

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <select aria-label="Dispensary"
              value={filterDispensary}
              onChange={e => setFilter('dispensary_id', e.target.value)}
              style={selectStyle}
            >
              <option value="">All dispensaries</option>
              {filterOpts.dispensaries.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>

            <select aria-label="Category"
              value={filterCategory}
              onChange={e => setFilter('category', e.target.value)}
              style={selectStyle}
            >
              <option value="">All categories</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            <select aria-label="Brand"
              value={filterBrand}
              onChange={e => setFilter('brand', e.target.value)}
              style={selectStyle}
            >
              <option value="">All brands</option>
              {filterOpts.brands.map(b => <option key={b} value={b}>{b}</option>)}
            </select>

            <select aria-label="Subtype"
              value={filterSubtype}
              onChange={e => setFilter('subtype', e.target.value)}
              style={selectStyle}
            >
              <option value="">All subtypes</option>
              {filterOpts.subtypes.map(s => <option key={s} value={s}>{s}</option>)}
            </select>

            <select aria-label="Strain type"
              value={filterClass}
              onChange={e => setFilter('classification', e.target.value)}
              style={selectStyle}
            >
              <option value="">All classifications</option>
              {filterOpts.classifications.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            <select aria-label="Stock"
              value={filterInStock}
              onChange={e => setFilter('in_stock', e.target.value)}
              style={selectStyle}
            >
              <option value="">All stock</option>
              <option value="true">In stock</option>
              <option value="false">Out of stock</option>
            </select>

            {hasFilters && (
              <button onClick={clearFilters} style={{ fontSize: 12, padding: '4px 10px', cursor: 'pointer', background: 'transparent', border: `1px solid ${t.borderStrong}`, borderRadius: 4, color: t.text2 }}>
                Clear all
              </button>
            )}
          </div>
        </div>

        {error && <div style={{ color: t.danger, marginBottom: 16 }}>{error}</div>}

        <p style={{ fontSize: 13, color: t.text3, marginBottom: 12 }}>
          {q ? <>Searching: <strong style={{ color: t.text2 }}>{q}</strong> — </> : null}
          Showing {listings.length} listing(s)
        </p>

        {loading && listings.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>Loading…</div>
        ) : listings.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>No listings found.</div>
        ) : (
          <AdminTable
            columns={columns}
            rows={listings}
            rowKey={l => l.id}
            onRowClick={l => navigate(`/admin/listings/${l.id}`)}
            sorting={{ sort, order, onSort: handleSort }}
          />
        )}

        {loading && listings.length > 0 && (
          <div style={{ padding: 16, color: t.text3, textAlign: 'center' }}>Loading more…</div>
        )}

        {!loading && hasMore && listings.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button
              onClick={() => fetchListings(offset + LIMIT)}
              style={{ padding: '8px 20px', background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 6, color: t.text2, cursor: 'pointer' }}
            >
              Load more
            </button>
          </div>
        )}

      </div>
    </div>
  )
}

