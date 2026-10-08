import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { SearchBar } from './components/SearchBar'
import { AdminTable, badge, categoryColor, navBtnStyle, selectStyle, Dash, type Column } from './components/AdminTable'
import api from './api/client'
import type { Product } from './types'
import { t, font } from './theme'
import { Icon } from './components/Icon'

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

  const columns: Column<Product>[] = [
    { key: 'brand', header: 'Brand', sortable: true, td: { color: t.text1, fontWeight: 500 },
      render: p => p.brand ?? <Dash /> },
    { key: 'category', header: 'Category', sortable: true,
      render: p => p.category ? <span style={{ ...badge, ...categoryColor(p.category) }}>{p.category}</span> : <Dash /> },
    { key: 'subtype', header: 'Subtype', sortable: true, td: { color: t.text2 },
      render: p => p.subtype ?? <Dash /> },
    { key: 'product_line', header: 'Product Line', sortable: true, td: { color: t.text2 },
      render: p => p.product_line ?? <Dash /> },
    { key: 'strain', header: 'Strain / Flavor', sortable: true, td: { color: t.text1 },
      render: p => p.strain ?? <Dash /> },
    { key: 'variant', header: 'Variant',
      render: p => p.variant ?? <Dash /> },
    { key: 'price', header: 'Price', sortable: true,
      render: p => priceRange(p) ?? <Dash /> },
    { key: 'stores', header: 'Stores', sortable: true, align: 'center',
      render: p => <span style={{ color: p.dispensary_count > 1 ? t.success : t.text2 }}>{p.dispensary_count}</span> },
    { key: 'listings', header: 'Listings', sortable: true, align: 'center', td: { color: t.text2 },
      render: p => p.listing_count },
    { key: 'stock', header: 'Stock',
      render: p => p.any_in_stock ? <Icon name="check" size={15} color={t.success} label="In stock" /> : <Icon name="close" size={15} color={t.text4} label="Out of stock" /> },
  ]

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 1300, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Products</h1>
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
            <select aria-label="Brand" value={filterBrand} onChange={e => setFilter('brand', e.target.value)} style={selectStyle}>
              <option value="">All brands</option>
              {brands.map(b => <option key={b} value={b}>{b}</option>)}
            </select>

            <select aria-label="Category" value={filterCategory} onChange={e => setFilter('category', e.target.value)} style={selectStyle}>
              <option value="">All categories</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            <select aria-label="Stock" value={filterInStock} onChange={e => setFilter('in_stock', e.target.value)} style={selectStyle}>
              <option value="">All availability</option>
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

        {error && <div style={{ color: t.danger, marginBottom: 16 }}>Error: {error}</div>}

        <p style={{ fontSize: 13, color: t.text3, marginBottom: 12 }}>
          {q ? <>Searching: <strong style={{ color: t.text2 }}>{q}</strong> — </> : null}
          Showing {products.length} product tuple(s)
        </p>

        {loading && products.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>Loading…</div>
        ) : products.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>No products found.</div>
        ) : (
          <AdminTable
            columns={columns}
            rows={products}
            rowKey={(_p, i) => i}
            onRowClick={p => navigate(`/admin/products/detail?${tupleParams(p)}`)}
            sorting={{ sort, order, onSort: handleSort }}
          />
        )}

        {loading && products.length > 0 && (
          <div style={{ padding: 16, color: t.text3, textAlign: 'center' }}>Loading more…</div>
        )}

        {!loading && hasMore && products.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button
              onClick={() => fetchProducts(offset + LIMIT)}
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

