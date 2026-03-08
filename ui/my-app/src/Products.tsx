// src/Products.tsx
import { useEffect, useState } from 'react'
import { usePagination } from './hooks/usePagination'
import { useSearch } from './hooks/useSearch'
import { SearchBar } from './components/SearchBar'
import api from './api/client'
import type { Product } from './types'

export default function Products() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const { hasMore, limit, offset, loadMore, reset: resetPagination, updateHasMore } = usePagination(50)
  const { search, searchInput, setSearchInput, handleSearch, clearSearch } = useSearch()

  useEffect(() => {
    fetchProducts(true)
  }, [search])

  async function fetchProducts(reset: boolean = false) {
    setLoading(true)
    setError(null)

    try {
      const currentOffset = reset ? 0 : offset
      const data = await api.products.list({
        q: search || undefined,
        limit,
        offset: currentOffset,
      })

      setProducts(prev => reset ? data : [...prev, ...data])
      updateHasMore(data.length)
      
      if (reset) {
        resetPagination()
      } else {
        loadMore()
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadMoreProducts() {
    await fetchProducts(false)
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Products</h1>
        <SearchBar
          value={searchInput}
          onChange={setSearchInput}
          onSearch={handleSearch}
          onClear={clearSearch}
          placeholder="Search by name, brand, or category..."
          disabled={loading}
          showClearButton={!!search}
        />
      </div>

      {error && (
        <div style={{ color: 'crimson', marginBottom: 12 }}>Error: {error}</div>
      )}

      {search && (
        <p style={{ marginBottom: 12, opacity: 0.8 }}>
          Searching for: <strong>{search}</strong> — Showing {products.length} result(s)
        </p>
      )}
      {!search && (
        <p style={{ marginBottom: 12, opacity: 0.8 }}>
          Showing {products.length} product(s)
        </p>
      )}

      {loading && products.length === 0 ? (
        <div>Loading…</div>
      ) : products.length === 0 ? (
        <div>No products found.</div>
      ) : (
        <table border={1} cellPadding={8} style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Brand</th>
              <th>Category</th>
              <th>Active</th>
              <th>Terpenes</th>
              <th>Cannabinoids</th>
            </tr>
          </thead>
          <tbody>
            {products.map(p => (
              <tr key={p.id}>
                <td><a href={`/products/${p.id}`}>{p.name}</a></td>
                <td>{p.brand ?? '—'}</td>
                <td>{p.category}</td>
                <td>{p.is_active ? 'Yes' : 'No'}</td>
                <td>
                  {p.terpenes && p.terpenes.length > 0 ? (
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                      {p.terpenes.map((t, i) => (
                        <li key={i}>
                          {t.name}
                          {t.percent != null ? ` (${t.percent}%)` : ''}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    '—'
                  )}
                </td>
                <td>
                  {p.cannabinoids && p.cannabinoids.length > 0 ? (
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                      {p.cannabinoids.map((c, i) => (
                        <li key={i}>
                          {c.name} ({c.family.toUpperCase()})
                          {c.percent != null ? ` — ${c.percent}%` : ''}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {hasMore && products.length > 0 && !loading && (
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <button type="button" onClick={loadMoreProducts}>
            Load More Products
          </button>
        </div>
      )}

      {loading && products.length > 0 && (
        <div style={{ marginTop: 16, textAlign: 'center', opacity: 0.7 }}>
          Loading more...
        </div>
      )}
    </div>
  )
}
