import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { SearchBar } from './components/SearchBar'
import api from './api/client'
import type { Listing } from './types'

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

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1300, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Listings</h2>
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
            <select
              value={filterDispensary}
              onChange={e => setFilter('dispensary_id', e.target.value)}
              style={selectStyle}
            >
              <option value="">All dispensaries</option>
              {filterOpts.dispensaries.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>

            <select
              value={filterCategory}
              onChange={e => setFilter('category', e.target.value)}
              style={selectStyle}
            >
              <option value="">All categories</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            <select
              value={filterBrand}
              onChange={e => setFilter('brand', e.target.value)}
              style={selectStyle}
            >
              <option value="">All brands</option>
              {filterOpts.brands.map(b => <option key={b} value={b}>{b}</option>)}
            </select>

            <select
              value={filterSubtype}
              onChange={e => setFilter('subtype', e.target.value)}
              style={selectStyle}
            >
              <option value="">All subtypes</option>
              {filterOpts.subtypes.map(s => <option key={s} value={s}>{s}</option>)}
            </select>

            <select
              value={filterClass}
              onChange={e => setFilter('classification', e.target.value)}
              style={selectStyle}
            >
              <option value="">All classifications</option>
              {filterOpts.classifications.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            <select
              value={filterInStock}
              onChange={e => setFilter('in_stock', e.target.value)}
              style={selectStyle}
            >
              <option value="">All stock</option>
              <option value="true">In stock</option>
              <option value="false">Out of stock</option>
            </select>

            {hasFilters && (
              <button onClick={clearFilters} style={{ fontSize: 12, padding: '4px 10px', cursor: 'pointer', background: 'transparent', border: '1px solid #374151', borderRadius: 4, color: '#94a3b8' }}>
                Clear all
              </button>
            )}
          </div>
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>{error}</div>}

        <p style={{ fontSize: 13, color: '#475569', marginBottom: 12 }}>
          {q ? <>Searching: <strong style={{ color: '#94a3b8' }}>{q}</strong> — </> : null}
          Showing {listings.length} listing(s)
        </p>

        {loading && listings.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : listings.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>No listings found.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                <SortTh col="name"       label="Scraped Name" sort={sort} order={order} onSort={handleSort} />
                <SortTh col="brand"      label="Brand"        sort={sort} order={order} onSort={handleSort} />
                <SortTh col="category"   label="Category"     sort={sort} order={order} onSort={handleSort} />
                <SortTh col="subtype"      label="Subtype"       sort={sort} order={order} onSort={handleSort} />
                <SortTh col="product_line" label="Product Line"  sort={sort} order={order} onSort={handleSort} />
                <SortTh col="strain"       label="Strain"        sort={sort} order={order} onSort={handleSort} />
                <th style={thStyle}>Class</th>
                <th style={thStyle}>Variant</th>
                <SortTh col="dispensary" label="Dispensary"   sort={sort} order={order} onSort={handleSort} />
                <SortTh col="price"      label="Price"        sort={sort} order={order} onSort={handleSort} />
                <th style={thStyle}>In Stock</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {listings.map(l => (
                <tr key={l.id} style={{ borderBottom: '1px solid #0f172a', cursor: 'pointer' }}
                  onClick={() => navigate(`/admin/listings/${l.id}`)}
                  onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = '#0f172a'}
                  onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'}
                >
                  <td style={{ ...tdStyle, color: '#f1f5f9', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.scraped_name ?? <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={tdStyle}>{l.scraped_brand ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>
                    {l.scraped_category
                      ? <span style={{ ...badge, ...categoryColor(l.scraped_category) }}>{l.scraped_category}</span>
                      : <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={tdStyle}>{l.subtype ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={{ ...tdStyle, color: '#94a3b8' }}>{l.product_line ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={{ ...tdStyle, color: '#a5b4fc' }}>{l.strain ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={{ ...tdStyle, color: '#94a3b8' }}>{l.classification ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{l.variant ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={{ ...tdStyle, color: '#94a3b8' }}>{l.dispensary_name}</td>
                  <td style={tdStyle}>{l.price_cents != null ? `$${(l.price_cents / 100).toFixed(2)}` : <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{l.in_stock ? <span style={{ color: '#86efac' }}>✓</span> : <span style={{ color: '#475569' }}>✗</span>}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }} onClick={e => e.stopPropagation()}>
                    {l.url
                      ? <a href={l.url} target="_blank" rel="noopener noreferrer" style={{ color: '#6366f1', textDecoration: 'none', fontSize: 14 }} title={l.url}>↗</a>
                      : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {loading && listings.length > 0 && (
          <div style={{ padding: 16, color: '#475569', textAlign: 'center' }}>Loading more…</div>
        )}

        {!loading && hasMore && listings.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button
              onClick={() => fetchListings(offset + LIMIT)}
              style={{ padding: '8px 20px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer' }}
            >
              Load more
            </button>
          </div>
        )}

      </div>
    </div>
  )
}

const CATEGORY_COLORS: Record<string, { background: string; color: string }> = {
  flower:      { background: '#14532d', color: '#86efac' },
  preroll:     { background: '#1a2e05', color: '#a3e635' },
  vaporizers:  { background: '#1e1b4b', color: '#a5b4fc' },
  concentrate: { background: '#431407', color: '#fdba74' },
  edible:      { background: '#4a1942', color: '#f0abfc' },
  tinctures:   { background: '#0c4a6e', color: '#7dd3fc' },
  topical:     { background: '#3b3a2a', color: '#fde68a' },
  merch:       { background: '#1c1917', color: '#a8a29e' },
}
function categoryColor(cat: string) {
  return CATEGORY_COLORS[cat] ?? { background: '#1e293b', color: '#94a3b8' }
}

function SortTh({ col, label, sort, order, onSort }: { col: string; label: string; sort: string; order: string; onSort: (c: string) => void }) {
  const active = sort === col
  return (
    <th style={{ ...thStyle, cursor: 'pointer', userSelect: 'none' }} onClick={() => onSort(col)}>
      {label}
      {active && <span style={{ marginLeft: 4, color: '#6366f1' }}>{order === 'asc' ? '↑' : '↓'}</span>}
    </th>
  )
}

const badge: React.CSSProperties = { padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 500 }
const thStyle: React.CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
const selectStyle: React.CSSProperties = { fontSize: 13, padding: '5px 8px', borderRadius: 4, background: '#0f172a', border: '1px solid #1e293b', color: '#94a3b8' }
