// src/Customers.tsx
import { useEffect, useState } from 'react'
import { usePagination } from './hooks/usePagination'
import { useSearch } from './hooks/useSearch'
import { SearchBar } from './components/SearchBar'
import api from './api/client'
import type { Customer } from './types'

export default function Customers() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const { hasMore, limit, offset, loadMore, reset: resetPagination, updateHasMore } = usePagination(50)
  const { search, searchInput, setSearchInput, handleSearch, clearSearch } = useSearch()

  useEffect(() => {
    fetchCustomers(true)
  }, [search])

  async function fetchCustomers(reset: boolean = false) {
    setLoading(true)
    setError(null)

    try {
      const currentOffset = reset ? 0 : offset
      const data = await api.customers.list({
        q: search || undefined,
        limit,
        offset: currentOffset,
      })

      setCustomers(prev => reset ? data : [...prev, ...data])
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

  async function loadMoreCustomers() {
    await fetchCustomers(false)
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Customers</h1>
        <SearchBar
          value={searchInput}
          onChange={setSearchInput}
          onSearch={handleSearch}
          onClear={clearSearch}
          placeholder="Search by name, email, or phone..."
          disabled={loading}
          showClearButton={!!search}
        />
      </div>

      {error && (
        <div style={{ color: 'crimson', marginBottom: 12 }}>Error: {error}</div>
      )}

      {search && (
        <p style={{ marginBottom: 12, opacity: 0.8 }}>
          Searching for: <strong>{search}</strong> — Showing {customers.length} result(s)
        </p>
      )}
      {!search && (
        <p style={{ marginBottom: 12, opacity: 0.8 }}>
          Showing {customers.length} customer(s)
        </p>
      )}

      {loading && customers.length === 0 ? (
        <div>Loading…</div>
      ) : customers.length === 0 ? (
        <div>No customers found.</div>
      ) : (
        <table border={1} cellPadding={8} style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Marketing</th>
              <th>Last Visit</th>
            </tr>
          </thead>
          <tbody>
            {customers.map(c => (
              <tr key={c.id}>
                <td><a href={`/customers/${c.id}`}>{c.name ?? '—'}</a></td>
                <td>{c.email ?? '—'}</td>
                <td>{c.phone ?? '—'}</td>
                <td>{c.marketing_opt_in ? 'Yes' : 'No'}</td>
                <td>{c.last_visit_at ? new Date(c.last_visit_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {hasMore && customers.length > 0 && !loading && (
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <button type="button" onClick={loadMoreCustomers}>
            Load More Customers
          </button>
        </div>
      )}

      {loading && customers.length > 0 && (
        <div style={{ marginTop: 16, textAlign: 'center', opacity: 0.7 }}>
          Loading more...
        </div>
      )}
    </div>
  )
}
