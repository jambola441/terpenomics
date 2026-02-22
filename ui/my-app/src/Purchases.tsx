// src/Purchases.tsx
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from './api/client'
import type { PurchaseRow } from './types'
import { SearchBar } from './components/SearchBar'
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

  // filters
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryString])

  async function load(reset: boolean = true) {
    setLoading(true)
    setError(null)
    try {
      const offset = reset ? 0 : rows.length
      const data = await api.purchases.list({
        q: search.trim() || undefined,
        source: source || undefined,
        limit,
        offset,
      })

      setRows(prev => reset ? data : [...prev, ...data])
      setHasMorePurchases(data.length === limit)
    } catch (e: any) {
      setError(e?.message ?? String(e))
      if (reset) setRows([])
    } finally {
      setLoading(false)
    }
  }

  async function loadMorePurchases() {
    await load(false)
  }

  function onSearchSubmit(e: React.FormEvent) {
    handleSearch(e)
    void load(true)
  }

  function onSearchClear() {
    clearSearch()
    void load(true)
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <h1>Purchases</h1>
        <button type="button" onClick={() => load(true)} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <SearchBar
          value={searchInput}
          onChange={setSearchInput}
          onSearch={onSearchSubmit}
          onClear={onSearchClear}
          placeholder="Search by customer name, email, phone, or external ID..."
          disabled={loading}
          showClearButton={!!search}
        />

        <select value={source} onChange={e => setSource(e.target.value)}>
          <option value="">All sources</option>
          <option value="manual">manual</option>
          <option value="pos_import">pos_import</option>
        </select>

        <select value={String(limit)} onChange={e => setLimit(Number(e.target.value))}>
          <option value="25">25</option>
          <option value="50">50</option>
          <option value="100">100</option>
          <option value="200">200</option>
        </select>
      </div>

      {error ? <div style={{ color: 'crimson', marginBottom: 12 }}>Error: {error}</div> : null}

      {!loading && rows.length > 0 && (
        <p style={{ marginBottom: 12, opacity: 0.8 }}>
          Showing {rows.length} purchase(s)
        </p>
      )}

      {loading && rows.length === 0 ? (
        <div>Loading…</div>
      ) : rows.length === 0 ? (
        <div>No purchases found.</div>
      ) : (
        <table border={1} cellPadding={8} style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th align="left">Date</th>
              <th align="right">Total</th>
              <th align="left">Source</th>
              <th align="left">Customer</th>
              <th align="left">Phone</th>
              <th align="right">Items</th>
              <th align="left">External</th>
              <th align="left">Open</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id}>
                <td>{new Date(r.purchased_at).toLocaleString()}</td>
                <td align="right">{dollars(r.total_amount_cents)}</td>
                <td>{r.source}</td>
                <td>{r.customer_name ?? r.customer_id}</td>
                <td>{r.customer_phone ?? '—'}</td>
                <td align="right">{r.item_count ?? '—'}</td>
                <td>{r.external_id ?? '—'}</td>
                <td>
                  <Link to={`/customers/${r.customer_id}`}>Customer</Link>
                  {' · '}
                  <a href={`#purchase-${r.id}`} onClick={e => e.preventDefault()}>
                    Purchase
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {hasMorePurchases && rows.length > 0 && !loading && (
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <button type="button" onClick={loadMorePurchases}>
            Load More Purchases
          </button>
        </div>
      )}

      {loading && rows.length > 0 && (
        <div style={{ marginTop: 16, textAlign: 'center', opacity: 0.7 }}>
          Loading more...
        </div>
      )}
    </div>
  )
}