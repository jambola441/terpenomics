import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePagination } from './hooks/usePagination'
import { useSearch } from './hooks/useSearch'
import { SearchBar } from './components/SearchBar'
import { AdminTable, navBtnStyle, Dash, type Column } from './components/AdminTable'
import api from './api/client'
import type { Customer } from './types'

export default function Customers() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

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
      const data = await api.customers.list({ q: search || undefined, limit, offset: currentOffset })
      setCustomers(prev => reset ? data : [...prev, ...data])
      updateHasMore(data.length)
      if (reset) resetPagination()
      else loadMore()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const columns: Column<Customer>[] = [
    { key: 'name', header: 'Name', td: { color: '#f1f5f9', fontWeight: 500 },
      render: c => c.name ?? <Dash /> },
    { key: 'email', header: 'Email', render: c => c.email ?? <Dash /> },
    { key: 'phone', header: 'Phone', render: c => c.phone ?? <Dash /> },
    { key: 'marketing', header: 'Marketing',
      render: c => c.marketing_opt_in ? <span style={{ color: '#86efac' }}>Yes</span> : <span style={{ color: '#475569' }}>No</span> },
    { key: 'last_visit', header: 'Last Visit',
      render: c => c.last_visit_at ? new Date(c.last_visit_at).toLocaleString() : <Dash /> },
  ]

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Customers</h2>
          <button
            onClick={() => navigate('/admin/customers/new')}
            style={{ ...navBtnStyle, color: '#a5b4fc', borderColor: '#3730a3' }}
          >
            + Register
          </button>
          <div style={{ marginLeft: 'auto' }}>
            <SearchBar
              value={searchInput}
              onChange={setSearchInput}
              onSearch={handleSearch}
              onClear={clearSearch}
              placeholder="Search by name, email, or phone…"
              disabled={loading}
              showClearButton={!!search}
            />
          </div>
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>Error: {error}</div>}

        <p style={{ fontSize: 13, color: '#475569', marginBottom: 12 }}>
          {search ? <>Searching: <strong style={{ color: '#94a3b8' }}>{search}</strong> — </> : null}
          Showing {customers.length} customer(s)
        </p>

        {loading && customers.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : customers.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>No customers found.</div>
        ) : (
          <AdminTable
            columns={columns}
            rows={customers}
            rowKey={c => c.id}
            onRowClick={c => navigate(`/admin/customers/${c.id}`)}
          />
        )}

        {loading && customers.length > 0 && (
          <div style={{ padding: 16, color: '#475569', textAlign: 'center' }}>Loading more…</div>
        )}

        {!loading && hasMore && customers.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button onClick={() => fetchCustomers(false)} style={navBtnStyle}>Load more</button>
          </div>
        )}
      </div>
    </div>
  )
}
