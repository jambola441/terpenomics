import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePagination } from './hooks/usePagination'
import { useSearch } from './hooks/useSearch'
import { SearchBar } from './components/SearchBar'
import { AdminTable, navBtnStyle, Dash, type Column, primaryBtnStyle } from './components/AdminTable'
import api from './api/client'
import type { Customer } from './types'
import { t, font } from './theme'
import { Icon } from './components/Icon'

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
    { key: 'name', header: 'Name', td: { color: t.text1, fontWeight: 500 },
      render: c => c.name ?? <Dash /> },
    { key: 'email', header: 'Email', render: c => c.email ?? <Dash /> },
    { key: 'phone', header: 'Phone', render: c => c.phone ?? <Dash /> },
    { key: 'marketing', header: 'Marketing',
      render: c => c.marketing_opt_in ? <span style={{ color: t.success }}>Yes</span> : <span style={{ color: t.text3 }}>No</span> },
    { key: 'last_visit', header: 'Last Visit',
      render: c => c.last_visit_at ? new Date(c.last_visit_at).toLocaleString() : <Dash /> },
  ]

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Customers</h1>
          <button
            onClick={() => navigate('/admin/customers/new')}
            style={primaryBtnStyle}
          >
            <Icon name="plus" size={14} />Register
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

        {error && <div style={{ color: t.danger, marginBottom: 16 }}>Error: {error}</div>}

        <p style={{ fontSize: 13, color: t.text3, marginBottom: 12 }}>
          {search ? <>Searching: <strong style={{ color: t.text2 }}>{search}</strong> — </> : null}
          Showing {customers.length} customer(s)
        </p>

        {loading && customers.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>Loading…</div>
        ) : customers.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>No customers found.</div>
        ) : (
          <AdminTable
            columns={columns}
            rows={customers}
            rowKey={c => c.id}
            onRowClick={c => navigate(`/admin/customers/${c.id}`)}
          />
        )}

        {loading && customers.length > 0 && (
          <div style={{ padding: 16, color: t.text3, textAlign: 'center' }}>Loading more…</div>
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
