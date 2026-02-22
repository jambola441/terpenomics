// src/CustomerEdit.tsx
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import supabase  from './utils/supabase'

type Feedback = 'like' | 'dislike' | 'neutral' | null

type ItemTerpene = {
  name: string
  percent?: number | null
}

type PurchaseItem = {
  id: string
  product_id: string
  product_name: string
  quantity: number
  line_amount_cents?: number | null
  feedback?: Feedback
  feedback_at?: string | null
  terpenes?: ItemTerpene[]
}

type Purchase = {
  id: string
  purchased_at: string
  total_amount_cents: number
  source: string
  notes?: string | null
  items: PurchaseItem[]
}

type Customer = {
  id: string
  name?: string | null
  phone?: string | null
  email?: string | null
  marketing_opt_in: boolean
  last_visit_at?: string | null
}

type CustomerDetail = {
  customer: Customer
  purchases: Purchase[]
}

type TerpeneScoreRow = {
  terpene: string
  score: number
  likes: number
  dislikes: number
  neutrals: number
}

type TerpeneScoresResponse = {
  customer_id: string
  window_days: number
  cutoff: string
  scores: TerpeneScoreRow[]
}

const API_BASE = 'https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev'

function dollars(cents: number | null | undefined) {
  if (cents == null) return '—'
  return `$${(cents / 100).toFixed(2)}`
}

function fmtFeedback(fb: Feedback) {
  if (!fb) return '—'
  if (fb === 'like') return '👍 like'
  if (fb === 'dislike') return '👎 dislike'
  return '😐 neutral'
}

function fmtTerpenes(terps: ItemTerpene[] | undefined) {
  if (!terps || terps.length === 0) return '—'
  const sorted = [...terps].sort((a, b) => (b.percent ?? -1) - (a.percent ?? -1))
  return sorted.map(t => `${t.name}${t.percent != null ? ` (${t.percent}%)` : ''}`).join(', ')
}

export default function CustomerEdit() {
  const { customerId } = useParams()
  const navigate = useNavigate()
  const cid = useMemo(() => (customerId ?? '').trim(), [customerId])

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const [customer, setCustomer] = useState<Customer | null>(null)
  const [purchases, setPurchases] = useState<Purchase[]>([])

  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [marketing, setMarketing] = useState(false)

  // terpene scores
  const [scoresLoading, setScoresLoading] = useState(false)
  const [scoresError, setScoresError] = useState<string | null>(null)
  const [windowDays, setWindowDays] = useState<number>(180)
  const [terpeneScores, setTerpeneScores] = useState<TerpeneScoreRow[]>([])

  // per-row feedback UI state
  const [rowFeedback, setRowFeedback] = useState<Record<string, Feedback>>({})
  const [rowSaving, setRowSaving] = useState<Record<string, boolean>>({})
  const [rowError, setRowError] = useState<Record<string, string | null>>({})

  useEffect(() => {
    if (!cid) return
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cid])

  useEffect(() => {
    if (!cid) return
    void loadScores()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cid, windowDays])

  async function authHeader() {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (!token) throw new Error('Not authenticated')
    return { Authorization: `Bearer ${token}` }
  }

  async function load() {
    setLoading(true)
    setError(null)
    setMsg(null)

    try {
      const headers = await authHeader()
      const res = await fetch(`${API_BASE}/admin/customers/${cid}`, { headers })
      if (!res.ok) throw new Error(await res.text())
      const data: CustomerDetail = await res.json()

      setCustomer(data.customer)
      setPurchases(data.purchases ?? [])

      setName(data.customer.name ?? '')
      setPhone(data.customer.phone ?? '')
      setEmail(data.customer.email ?? '')
      setMarketing(Boolean(data.customer.marketing_opt_in))

      const fb: Record<string, Feedback> = {}
      for (const p of data.purchases ?? []) {
        for (const it of p.items ?? []) {
          fb[it.id] = (it.feedback ?? null) as Feedback
        }
      }
      setRowFeedback(fb)
      setRowError({})
      setRowSaving({})
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setLoading(false)
    }
  }

  async function loadScores() {
    setScoresLoading(true)
    setScoresError(null)
    try {
      const headers = await authHeader()
      const res = await fetch(
        `${API_BASE}/admin/customers/${cid}/terpene-scores?window_days=${encodeURIComponent(String(windowDays))}`,
        { headers }
      )
      if (!res.ok) throw new Error(await res.text())
      const data: TerpeneScoresResponse = await res.json()
      setTerpeneScores(data.scores ?? [])
    } catch (e: any) {
      setScoresError(e?.message ?? String(e))
      setTerpeneScores([])
    } finally {
      setScoresLoading(false)
    }
  }

  async function saveCustomer(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setMsg(null)

    try {
      const headers = await authHeader()
      const payload = {
        name: name || null,
        phone: phone || null,
        email: email || null,
        marketing_opt_in: marketing,
      }

      const res = await fetch(`${API_BASE}/admin/customers/${cid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify(payload),
      })

      if (!res.ok) throw new Error(await res.text())
      setMsg('Saved')
      await load()
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setSaving(false)
    }
  }

  async function saveItemFeedback(itemId: string) {
    setRowSaving(prev => ({ ...prev, [itemId]: true }))
    setRowError(prev => ({ ...prev, [itemId]: null }))

    try {
      const headers = await authHeader()
      const payload = { feedback: rowFeedback[itemId] }

      const res = await fetch(`${API_BASE}/admin/purchase-items/${itemId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify(payload),
      })

      if (!res.ok) throw new Error(await res.text())
      const updated = await res.json()

      setPurchases(prev =>
        prev.map(p => ({
          ...p,
          items: p.items.map(it =>
            it.id === itemId
              ? { ...it, feedback: updated.feedback ?? null, feedback_at: updated.feedback_at ?? null }
              : it
          ),
        }))
      )

      // refresh terpene scores after feedback change
      await loadScores()
    } catch (e: any) {
      setRowError(prev => ({ ...prev, [itemId]: e?.message ?? String(e) }))
    } finally {
      setRowSaving(prev => ({ ...prev, [itemId]: false }))
    }
  }

  if (loading) return <div style={{ padding: 24 }}>Loading…</div>
  if (error) return <div style={{ padding: 24 }}>Error: {error}</div>
  if (!customer) return <div style={{ padding: 24 }}>Not found</div>

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Customer</h1>
        <button type="button" onClick={() => navigate(-1)}>Back</button>
      </div>

      <form onSubmit={saveCustomer} style={{ marginBottom: 24 }}>
        <div style={{ display: 'grid', gap: 10 }}>
          <div>
            <label>Name</label>
            <input value={name} onChange={e => setName(e.target.value)} style={{ width: '100%' }} />
          </div>

          <div>
            <label>Email</label>
            <input value={email} onChange={e => setEmail(e.target.value)} style={{ width: '100%' }} />
          </div>

          <div>
            <label>Phone</label>
            <input value={phone} onChange={e => setPhone(e.target.value)} style={{ width: '100%' }} />
          </div>

          <label>
            <input type="checkbox" checked={marketing} onChange={e => setMarketing(e.target.checked)} /> Marketing opt-in
          </label>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
            {msg && <span>{msg}</span>}
          </div>
        </div>
      </form>

      <div style={{ border: '1px solid #ddd', padding: 12, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0 }}>Top Terpenes</h2>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label style={{ fontSize: 12, opacity: 0.8 }}>Window (days)</label>
            <input
              type="number"
              min={1}
              max={3650}
              value={windowDays}
              onChange={e => setWindowDays(Number(e.target.value))}
              style={{ width: 100 }}
            />
            <button type="button" onClick={() => loadScores()} disabled={scoresLoading}>
              {scoresLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {scoresError ? <div style={{ color: 'crimson' }}>Error: {scoresError}</div> : null}

        {scoresLoading ? (
          <div>Loading terpene scores…</div>
        ) : terpeneScores.length === 0 ? (
          <div style={{ opacity: 0.8 }}>No scored terpenes yet (needs likes/dislikes).</div>
        ) : (
          <table border={1} cellPadding={8} style={{ borderCollapse: 'collapse', width: '100%', marginTop: 10 }}>
            <thead>
              <tr>
                <th align="left">Terpene</th>
                <th align="right">Score</th>
                <th align="right">Likes</th>
                <th align="right">Dislikes</th>
              </tr>
            </thead>
            <tbody>
              {terpeneScores.slice(0, 15).map(row => (
                <tr key={row.terpene}>
                  <td>{row.terpene}</td>
                  <td align="right">{row.score.toFixed(2)}</td>
                  <td align="right">{row.likes}</td>
                  <td align="right">{row.dislikes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>Orders</h2>

      {purchases.length === 0 ? (
        <p>No purchases.</p>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {purchases.map(p => (
            <div key={p.id} style={{ border: '1px solid #ddd', padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div><strong>{new Date(p.purchased_at).toLocaleString()}</strong></div>
                  <div style={{ fontSize: 12, opacity: 0.8 }}>Order ID: {p.id}</div>
                  <div style={{ fontSize: 12, opacity: 0.8 }}>Source: {p.source}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div><strong>{dollars(p.total_amount_cents)}</strong></div>
                  <div style={{ fontSize: 12, opacity: 0.8 }}>{p.items.length} item(s)</div>
                </div>
              </div>

              {p.items.length > 0 && (
                <table
                  border={1}
                  cellPadding={8}
                  style={{ borderCollapse: 'collapse', width: '100%', marginTop: 10 }}
                >
                  <thead>
                    <tr>
                      <th align="left">Product</th>
                      <th align="left">Terpenes</th>
                      <th align="right">Qty</th>
                      <th align="right">Line</th>
                      <th align="left">Feedback</th>
                      <th align="left">Feedback At</th>
                      <th align="left">Edit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.items.map(it => {
                      const current = rowFeedback[it.id] ?? (it.feedback ?? null)
                      const savingRow = Boolean(rowSaving[it.id])
                      const errRow = rowError[it.id]

                      return (
                        <tr key={it.id}>
                          <td>{it.product_name}</td>
                          <td style={{ maxWidth: 420 }}>{fmtTerpenes(it.terpenes)}</td>
                          <td align="right">{it.quantity}</td>
                          <td align="right">{dollars(it.line_amount_cents)}</td>
                          <td>{fmtFeedback(it.feedback ?? null)}</td>
                          <td>{it.feedback_at ? new Date(it.feedback_at).toLocaleString() : '—'}</td>
                          <td>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                              <select
                                value={current ?? ''}
                                onChange={e =>
                                  setRowFeedback(prev => ({
                                    ...prev,
                                    [it.id]: (e.target.value || null) as Feedback,
                                  }))
                                }
                                disabled={savingRow}
                              >
                                <option value="">—</option>
                                <option value="like">like</option>
                                <option value="neutral">neutral</option>
                                <option value="dislike">dislike</option>
                              </select>
                              <button
                                type="button"
                                onClick={() => saveItemFeedback(it.id)}
                                disabled={savingRow}
                              >
                                {savingRow ? 'Saving…' : 'Save'}
                              </button>
                            </div>
                            {errRow ? <div style={{ color: 'crimson', fontSize: 12 }}>{errRow}</div> : null}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
