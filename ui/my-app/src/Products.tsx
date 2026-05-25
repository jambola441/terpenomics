import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { SearchBar } from './components/SearchBar'
import api from './api/client'
import type { Product } from './types'

const NULL_SENTINEL = '__null__'

function tupleParams(p: Product) {
  const enc = (v: string | null) => v ?? NULL_SENTINEL
  return new URLSearchParams({
    brand:        enc(p.brand),
    category:     p.category,
    subtype:      enc(p.subtype),
    product_line: enc(p.product_line),
    strain:       enc(p.strain),
    variant:      enc(p.variant),
  }).toString()
}

const CATEGORIES = [
  'flower', 'vaporizers', 'preroll', 'concentrate', 'edible',
  'tinctures', 'topical', 'merch', 'other',
]
const LIMIT = 50

function fmt(cents: number | null) {
  return cents != null ? `$${(cents / 100).toFixed(2)}` : null
}

function priceRange(p: Product) {
  const lo = fmt(p.min_price_cents)
  const hi = fmt(p.max_price_cents)
  if (!lo && !hi) return null
  if (lo === hi || !hi) return lo
  return `${lo} – ${hi}`
}

export default function Products() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  // Committed filter values live in the URL
  const q              = searchParams.get('q') ?? ''
  const filterBrand    = searchParams.get('brand') ?? ''
  const filterCategory = searchParams.get('category') ?? ''
  const filterInStock  = searchParams.get('in_stock') ?? ''
  const sort           = searchParams.get('sort') ?? ''
  const order          = searchParams.get('order') ?? 'asc'

  // Controlled input state (unconfirmed search text)
  const [searchInput, setSearchInput] = useState(q)

  // Data state
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [brands, setBrands] = useState<string[]>([])
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
    api.products.listAllBrands().then(setBrands).catch(() => {})
  }, [])

  // Reset and fetch whenever URL filters change
  const filterKey = searchParams.toString()
  useEffect(() => {
    setOffset(0)
    setHasMore(true)
    fetchProducts(0)
  }, [filterKey])

  async function fetchProducts(currentOffset: number) {
    setLoading(true)
    setError(null)
    try {
      const inStockParam = filterInStock === 'true' ? true : filterInStock === 'false' ? false : undefined
      const data = await api.products.list({
        q: q || undefined,
        brand: filterBrand || undefined,
        category: filterCategory || undefined,
        in_stock: inStockParam,
        sort: sort || undefined,
        order: order || undefined,
        limit: LIMIT,
        offset: currentOffset,
      })
      setProducts(prev => currentOffset === 0 ? data : [...prev, ...data])
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

  const hasFilters = q || filterBrand || filterCategory || filterInStock

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1300, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Products</h2>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
          <SearchBar
            value={searchInput}
            onChange={setSearchInput}
            onSearch={handleSearch}
            onClear={clearSearch}
            placeholder="Search brand, strain, category…"
            disabled={loading}
            showClearButton={!!q}
          />

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <select value={filterBrand} onChange={e => setFilter('brand', e.target.value)} style={selectStyle}>
              <option value="">All brands</option>
              {brands.map(b => <option key={b} value={b}>{b}</option>)}
            </select>

            <select value={filterCategory} onChange={e => setFilter('category', e.target.value)} style={selectStyle}>
              <option value="">All categories</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            <select value={filterInStock} onChange={e => setFilter('in_stock', e.target.value)} style={selectStyle}>
              <option value="">All availability</option>
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

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>Error: {error}</div>}

        <p style={{ fontSize: 13, color: '#475569', marginBottom: 12 }}>
          {q ? <>Searching: <strong style={{ color: '#94a3b8' }}>{q}</strong> — </> : null}
          Showing {products.length} product tuple(s)
        </p>

        {loading && products.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : products.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>No products found.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                <SortTh col="brand"    label="Brand"        sort={sort} order={order} onSort={handleSort} />
                <SortTh col="category" label="Category"     sort={sort} order={order} onSort={handleSort} />
                <SortTh col="subtype"      label="Subtype"         sort={sort} order={order} onSort={handleSort} />
                <SortTh col="product_line" label="Product Line"    sort={sort} order={order} onSort={handleSort} />
                <SortTh col="strain"       label="Strain / Flavor" sort={sort} order={order} onSort={handleSort} />
                <th style={thStyle}>Variant</th>
                <SortTh col="price"    label="Price"        sort={sort} order={order} onSort={handleSort} />
                <SortTh col="stores"   label="Stores"       sort={sort} order={order} onSort={handleSort} />
                <SortTh col="listings" label="Listings"     sort={sort} order={order} onSort={handleSort} />
                <th style={thStyle}>Stock</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p, i) => (
                <tr
                  key={i}
                  style={{ borderBottom: '1px solid #0f172a', cursor: 'pointer' }}
                  onClick={() => navigate(`/admin/products/detail?${tupleParams(p)}`)}
                  onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = '#0f172a'}
                  onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'}
                >
                  <td style={{ ...tdStyle, color: '#f1f5f9', fontWeight: 500 }}>
                    {p.brand ?? <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={tdStyle}>
                    {p.category
                      ? <span style={{ ...badge, ...categoryColor(p.category) }}>{p.category}</span>
                      : <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={{ ...tdStyle, color: '#94a3b8' }}>
                    {p.subtype ?? <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={{ ...tdStyle, color: '#94a3b8' }}>
                    {p.product_line ?? <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={{ ...tdStyle, color: '#a5b4fc' }}>
                    {p.strain ?? <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={tdStyle}>
                    {p.variant ?? <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={tdStyle}>
                    {priceRange(p) ?? <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center' }}>
                    <span style={{ color: p.dispensary_count > 1 ? '#86efac' : '#94a3b8' }}>
                      {p.dispensary_count}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center', color: '#94a3b8' }}>
                    {p.listing_count}
                  </td>
                  <td style={tdStyle}>
                    {p.any_in_stock
                      ? <span style={{ color: '#86efac' }}>✓</span>
                      : <span style={{ color: '#475569' }}>✗</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {loading && products.length > 0 && (
          <div style={{ padding: 16, color: '#475569', textAlign: 'center' }}>Loading more…</div>
        )}

        {!loading && hasMore && products.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button
              onClick={() => fetchProducts(offset + LIMIT)}
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
