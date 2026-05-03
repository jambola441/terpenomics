import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePagination } from './hooks/usePagination'
import { useSearch } from './hooks/useSearch'
import { SearchBar } from './components/SearchBar'
import api from './api/client'
import type { Product } from './types'

const CATEGORIES = [
  'flower', 'vaporizers', 'cart', 'edible', 'concentrate',
  'preroll', 'tinctures', 'topical', 'merch', 'other',
]

export default function Products() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [brands, setBrands] = useState<string[]>([])
  const [filterBrand, setFilterBrand] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterVariant, setFilterVariant] = useState('')
  const navigate = useNavigate()

  const { hasMore, limit, offset, loadMore, reset: resetPagination, updateHasMore } = usePagination(50)
  const { search, searchInput, setSearchInput, handleSearch, clearSearch } = useSearch()

  useEffect(() => {
    api.products.listAllBrands().then(setBrands).catch(() => {})
  }, [])

  useEffect(() => {
    fetchProducts(true)
  }, [search, filterBrand, filterCategory, filterVariant])

  async function fetchProducts(reset: boolean = false) {
    setLoading(true)
    setError(null)
    try {
      const currentOffset = reset ? 0 : offset
      const data = await api.products.list({
        q: search || undefined,
        brand: filterBrand || undefined,
        category: filterCategory || undefined,
        variant: filterVariant || undefined,
        limit,
        offset: currentOffset,
      })
      setProducts(prev => reset ? data : [...prev, ...data])
      updateHasMore(data.length)
      if (reset) resetPagination()
      else loadMore()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const activeFilters = [filterBrand, filterCategory, filterVariant].filter(Boolean).length

  function clearFilters() {
    setFilterBrand('')
    setFilterCategory('')
    setFilterVariant('')
  }

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Products</h2>
          <div style={{ marginLeft: 'auto' }}>
            <SearchBar
              value={searchInput}
              onChange={setSearchInput}
              onSearch={handleSearch}
              onClear={clearSearch}
              placeholder="Search by name, brand, or category…"
              disabled={loading}
              showClearButton={!!search}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={filterBrand} onChange={e => setFilterBrand(e.target.value)} style={selectStyle}>
            <option value="">All brands</option>
            {brands.map(b => <option key={b} value={b}>{b}</option>)}
          </select>

          <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)} style={selectStyle}>
            <option value="">All categories</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>

          <input
            value={filterVariant}
            onChange={e => setFilterVariant(e.target.value)}
            placeholder="Variant…"
            style={{ ...selectStyle, width: 120 }}
          />

          {(activeFilters > 0 || search) && (
            <button onClick={() => { clearFilters(); clearSearch() }} style={{ fontSize: 12, padding: '4px 10px', cursor: 'pointer', background: 'transparent', border: '1px solid #374151', borderRadius: 4, color: '#94a3b8' }}>
              Clear all
            </button>
          )}
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>Error: {error}</div>}

        <p style={{ fontSize: 13, color: '#475569', marginBottom: 12 }}>
          {search ? <>Searching: <strong style={{ color: '#94a3b8' }}>{search}</strong> — </> : null}
          Showing {products.length} product(s)
        </p>

        {loading && products.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : products.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>No products found.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Brand</th>
                <th style={thStyle}>Variant</th>
                <th style={thStyle}>Category</th>
                <th style={thStyle}>Active</th>
                <th style={thStyle}>Terpenes</th>
              </tr>
            </thead>
            <tbody>
              {products.map(p => (
                <tr
                  key={p.id}
                  style={{ borderBottom: '1px solid #0f172a', cursor: 'pointer' }}
                  onClick={() => navigate(`/admin/products/${p.id}`)}
                  onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = '#0f172a'}
                  onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'}
                >
                  <td style={{ ...tdStyle, color: '#f1f5f9', fontWeight: 500 }}>{p.name}</td>
                  <td style={tdStyle}>{p.brand ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{p.variant ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{p.category}</td>
                  <td style={tdStyle}>{p.is_active ? <span style={{ color: '#86efac' }}>Yes</span> : <span style={{ color: '#475569' }}>No</span>}</td>
                  <td style={tdStyle}>
                    {p.terpenes?.length > 0
                      ? <span style={{ color: '#94a3b8' }}>{p.terpenes.map(t => t.name).join(', ')}</span>
                      : <span style={{ color: '#475569' }}>—</span>}
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
            <button onClick={() => fetchProducts(false)} style={navBtnStyle}>
              Load more
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
const selectStyle: React.CSSProperties = { fontSize: 13, padding: '5px 8px', borderRadius: 4, background: '#0f172a', border: '1px solid #1e293b', color: '#94a3b8' }
