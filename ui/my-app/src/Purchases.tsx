import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from './api/client'
import type { PurchaseRow } from './types'
import { SearchBar } from './components/SearchBar'
import { AdminTable, navBtnStyle, selectStyle, Dash, type Column } from './components/AdminTable'
import { useSearch } from './hooks/useSearch'

function dollars(cents: number | null | undefined) {
  if (cents == null) return '—'
  return `$${(cents / 100).toFixed(2)}`
}

export default function Purchases() {
  const [rows, setRows] = useState<PurchaseRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMorePurchases, setHasMorePurchases] = useState(true)
  const navigate = useNavigate()

  const { search, searchInput, setSearchInput, handleSearch, clearSearch } = useSearch()
  const [source, setSource] = useState<string>('')
  const [limit, setLimit] = useState<number>(50)

  const queryString = useMemo(() => {
    const params = new URLSearchParams()
    if (search.trim()) params.set('q', search.trim())
    if (source) params.set('source', source)
    params.set('limit', String(limit))
    return params.toString()
  }, [search, source, limit])

  useEffect(() => {
    void load(true)
  }, [queryString])

  async function load(reset: boolean = true) {
    setLoading(true)
    setError(null)
    try {
      const offset = reset ? 0 : rows.length
      const data = await api.purchases.list({ q: search.trim() || undefined, source: source || undefined, limit, offset })
      setRows(prev => reset ? data : [...prev, ...data])
      setHasMorePurchases(data.length === limit)
    } catch (e: any) {
      setError(e?.message ?? String(e))
      if (reset) setRows([])
    } finally {
      setLoading(false)
    }
  }

  function onSearchSubmit(e: React.FormEvent) { handleSearch(e); void load(true) }
  function onSearchClear() { clearSearch(); void load(true) }

  const columns: Column<PurchaseRow>[] = [
    { key: 'date', header: 'Date', render: r => new Date(r.purchased_at).toLocaleString() },
    { key: 'total', header: 'Total', align: 'right', th: { textAlign: 'right' }, td: { fontVariantNumeric: 'tabular-nums' },
      render: r => dollars(r.total_amount_cents) },
    { key: 'source', header: 'Source', render: r => r.source },
    { key: 'customer', header: 'Customer', td: { color: '#f1f5f9', fontWeight: 500 },
      render: r => r.customer_name ?? r.customer_id },
    { key: 'phone', header: 'Phone', render: r => r.customer_phone ?? <Dash /> },
    { key: 'items', header: 'Items', align: 'right', th: { textAlign: 'right' }, render: r => r.item_count ?? <Dash /> },
    { key: 'external', header: 'External', td: { color: '#475569', fontSize: 11 },
      render: r => r.external_id ?? '—' },
  ]

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Purchases</h2>
          <button onClick={() => load(true)} disabled={loading} style={{ ...navBtnStyle, marginLeft: 'auto' }}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
          <SearchBar
            value={searchInput}
            onChange={setSearchInput}
            onSearch={onSearchSubmit}
            onClear={onSearchClear}
            placeholder="Search by customer name, email, phone, or external ID…"
            disabled={loading}
            showClearButton={!!search}
          />
          <select value={source} onChange={e => setSource(e.target.value)} style={selectStyle}>
            <option value="">All sources</option>
            <option value="manual">manual</option>
            <option value="pos_import">pos_import</option>
          </select>
          <select value={String(limit)} onChange={e => setLimit(Number(e.target.value))} style={selectStyle}>
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="200">200</option>
          </select>
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>Error: {error}</div>}

        {rows.length > 0 && (
          <p style={{ fontSize: 13, color: '#475569', marginBottom: 12 }}>Showing {rows.length} purchase(s)</p>
        )}

        {loading && rows.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : rows.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>No purchases found.</div>
        ) : (
          <AdminTable
            columns={columns}
            rows={rows}
            rowKey={r => r.id}
            onRowClick={r => navigate(`/admin/customers/${r.customer_id}`)}
          />
        )}

        {loading && rows.length > 0 && (
          <div style={{ padding: 16, color: '#475569', textAlign: 'center' }}>Loading more…</div>
        )}

        {!loading && hasMorePurchases && rows.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button onClick={() => load(false)} style={navBtnStyle}>Load more</button>
          </div>
        )}
      </div>
    </div>
  )
}
