// src/Purchases.tsx
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import supabase  from './utils/supabase'

type PurchaseRow = {
  id: string
  purchased_at: string
  total_amount_cents: number
  source: string
  external_id?: string | null
  notes?: string | null
  customer_id: string
  customer_name?: string | null
  customer_phone?: string | null
  item_count?: number | null
}

const API_BASE = 'https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev'

function dollars(cents: number | null | undefined) {
  if (cents == null) return '—'
  return `$${(cents / 100).toFixed(2)}`
}

export default function Purchases() {
  const [rows, setRows] = useState<PurchaseRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // filters
  const [q, setQ] = useState('')
  const [source, setSource] = useState<string>('')
  const [limit, setLimit] = useState<number>(50)

  const queryString = useMemo(() => {
    const params = new URLSearchParams()
    if (q.trim()) params.set('q', q.trim())
    if (source) params.set('source', source)
    params.set('limit', String(limit))
    return params.toString()
  }, [q, source, limit])

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryString])

  async function authHeader() {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (!token) throw new Error('Not authenticated')
    return { Authorization: `Bearer ${token}` }
  }

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const headers = await authHeader()
      const res = await fetch(`${API_BASE}/admin/purchases?${queryString}`, { headers })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setRows(data)
    } catch (e: any) {
      setError(e?.message ?? String(e))
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <h1>Purchases</h1>
        <button type="button" onClick={() => load()} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <input
          placeholder="Search customer name/phone/email or external id"
          value={q}
          onChange={e => setQ(e.target.value)}
          style={{ minWidth: 320, flex: 1 }}
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

      {loading ? (
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
    </div>
  )
}
