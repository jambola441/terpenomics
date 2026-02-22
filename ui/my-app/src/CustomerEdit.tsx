// src/CustomerEdit.tsx
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import supabase  from './utils/supabase'
import api from './api/client'
import { ProductSearch } from './components/ProductSearch'
import type { Product, RecommendedProduct } from './types'

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

type ProductTerpenesMap = Record<string, ItemTerpene[]>

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
  const [productTerpenes, setProductTerpenes] = useState<ProductTerpenesMap>({})
  const [hasMorePurchases, setHasMorePurchases] = useState(true)
  const [purchasesLimit] = useState(20)

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

  // order creation state
  const [isOrderFormOpen, setIsOrderFormOpen] = useState(false)
  const [orderItems, setOrderItems] = useState<Array<{
    product: Product
    quantity: number
    price_cents: number
  }>>([])
  const [orderSubmitting, setOrderSubmitting] = useState(false)
  const [orderError, setOrderError] = useState<string | null>(null)

  // recommendations state
  const [recommendations, setRecommendations] = useState<RecommendedProduct[]>([])
  const [recsLoading, setRecsLoading] = useState(false)
  const [recsError, setRecsError] = useState<string | null>(null)

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
      
      // 1. Load basic customer info
      const custRes = await fetch(`${API_BASE}/admin/customers/${cid}`, { headers })
      if (!custRes.ok) throw new Error(await custRes.text())
      const customerData: Customer = await custRes.json()

      setCustomer(customerData)
      setName(customerData.name ?? '')
      setPhone(customerData.phone ?? '')
      setEmail(customerData.email ?? '')
      setMarketing(Boolean(customerData.marketing_opt_in))

      // 2. Load purchases (paginated)
      await loadPurchases(headers, 0, true)

    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setLoading(false)
    }
  }

  async function loadPurchases(headers: Record<string, string>, offset: number, reset: boolean = false) {
    try {
      const purchasesRes = await fetch(
        `${API_BASE}/admin/customers/${cid}/purchases?limit=${purchasesLimit}&offset=${offset}`,
        { headers }
      )
      if (!purchasesRes.ok) throw new Error(await purchasesRes.text())
      const purchasesData: Purchase[] = await purchasesRes.json()

      // Update purchases state
      setPurchases(prev => reset ? purchasesData : [...prev, ...purchasesData])
      setHasMorePurchases(purchasesData.length === purchasesLimit)

      // 3. Load product terpenes for all products in these purchases
      const productIds = new Set<string>()
      for (const p of purchasesData) {
        for (const it of p.items ?? []) {
          productIds.add(it.product_id)
        }
      }

      if (productIds.size > 0) {
        const terpenesRes = await fetch(
          `${API_BASE}/admin/products/terpenes?product_ids=${Array.from(productIds).join(',')}`,
          { headers }
        )
        if (!terpenesRes.ok) throw new Error(await terpenesRes.text())
        const terpenesData: ProductTerpenesMap = await terpenesRes.json()
        
        setProductTerpenes(prev => ({ ...prev, ...terpenesData }))
      }

      // 4. Initialize feedback state
      const fb: Record<string, Feedback> = {}
      for (const p of purchasesData) {
        for (const it of p.items ?? []) {
          fb[it.id] = (it.feedback ?? null) as Feedback
        }
      }
      
      if (reset) {
        setRowFeedback(fb)
        setRowError({})
        setRowSaving({})
      } else {
        setRowFeedback(prev => ({ ...prev, ...fb }))
      }

    } catch (e: any) {
      setError(e?.message ?? String(e))
    }
  }

  async function loadMorePurchases() {
    setLoading(true)
    try {
      const headers = await authHeader()
      await loadPurchases(headers, purchases.length, false)
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

  // Load recommendations
  async function loadRecommendations() {
    if (!cid) return
    setRecsLoading(true)
    setRecsError(null)
    try {
      const data = await api.customers.getRecommendedProducts(cid, { 
        limit: 10, 
        window_days: windowDays 
      })
      setRecommendations(data)
    } catch (e: any) {
      setRecsError(e?.message ?? String(e))
    } finally {
      setRecsLoading(false)
    }
  }

  // Load recommendations when terpene window changes
  useEffect(() => {
    if (!cid) return
    void loadRecommendations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cid, windowDays])

  // Order creation functions
  function addOrderItem(product: Product) {
    setOrderItems(prev => [...prev, {
      product,
      quantity: 1,
      price_cents: 0,
    }])
  }

  function removeOrderItem(index: number) {
    setOrderItems(prev => prev.filter((_, i) => i !== index))
  }

  function updateOrderItem(index: number, field: 'quantity' | 'price_cents', value: number) {
    setOrderItems(prev => prev.map((item, i) =>
      i === index ? { ...item, [field]: value } : item
    ))
  }

  const orderTotal = useMemo(() => {
    return orderItems.reduce((sum, item) => sum + (item.quantity * item.price_cents), 0)
  }, [orderItems])

  async function submitOrder() {
    if (!cid || orderItems.length === 0) return
    
    setOrderSubmitting(true)
    setOrderError(null)
    
    try {
      // Step 1: Create purchase
      const purchase = await api.purchases.create({
        customer_id: cid,
        source: 'manual',
      })

      // Step 2: Add items (batch)
      const items = orderItems.map(item => ({
        product_id: item.product.id,
        quantity: item.quantity,
        line_amount_cents: item.price_cents,
      }))

      await api.purchaseItems.createBatch(purchase.id, items)

      // Step 3: Finalize purchase
      await api.purchases.finalize(purchase.id)

      // Success - clear form and refresh purchases
      setOrderItems([])
      setIsOrderFormOpen(false)
      setMsg('Order created successfully!')
      
      // Refresh purchases list
      const headers = await authHeader()
      await loadPurchases(headers, 0, true)
    } catch (e: any) {
      setOrderError(e?.message ?? String(e))
    } finally {
      setOrderSubmitting(false)
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

      {/* Order Creation Section */}
      <div style={{ border: '1px solid #ddd', padding: 12, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Create New Order</h2>
          <button
            type="button"
            onClick={() => setIsOrderFormOpen(!isOrderFormOpen)}
          >
            {isOrderFormOpen ? 'Hide' : 'Show'}
          </button>
        </div>

        {isOrderFormOpen && (
          <div style={{ display: 'grid', gap: 12 }}>
            <ProductSearch
              onSelect={addOrderItem}
              disabled={orderSubmitting}
              placeholder="Search products to add..."
            />

            {orderError && (
              <div style={{ color: 'crimson' }}>{orderError}</div>
            )}

            {orderItems.length > 0 ? (
              <>
                <table border={1} cellPadding={8} style={{ borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th align="left">Product</th>
                      <th align="center">Quantity</th>
                      <th align="right">Price (cents)</th>
                      <th align="right">Line Total</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {orderItems.map((item, index) => (
                      <tr key={index}>
                        <td>
                          <div><strong>{item.product.name}</strong></div>
                          {item.product.brand && (
                            <div style={{ fontSize: 12, opacity: 0.7 }}>{item.product.brand}</div>
                          )}
                        </td>
                        <td align="center">
                          <input
                            type="number"
                            min={1}
                            value={item.quantity}
                            onChange={(e) => updateOrderItem(index, 'quantity', Number(e.target.value))}
                            style={{ width: 60 }}
                            disabled={orderSubmitting}
                          />
                        </td>
                        <td align="right">
                          <input
                            type="number"
                            min={0}
                            value={item.price_cents}
                            onChange={(e) => updateOrderItem(index, 'price_cents', Number(e.target.value))}
                            style={{ width: 100 }}
                            disabled={orderSubmitting}
                          />
                        </td>
                        <td align="right">
                          {dollars(item.quantity * item.price_cents)}
                        </td>
                        <td>
                          <button
                            type="button"
                            onClick={() => removeOrderItem(index)}
                            disabled={orderSubmitting}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={3} align="right"><strong>Total:</strong></td>
                      <td align="right"><strong>{dollars(orderTotal)}</strong></td>
                      <td></td>
                    </tr>
                  </tfoot>
                </table>

                <div>
                  <button
                    type="button"
                    onClick={submitOrder}
                    disabled={orderSubmitting || orderItems.length === 0}
                  >
                    {orderSubmitting ? 'Creating Order...' : 'Create Order'}
                  </button>
                </div>
              </>
            ) : (
              <p style={{ margin: 0, opacity: 0.7 }}>
                Search for products above to add them to the order.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Recommendations Section */}
      <div style={{ border: '1px solid #ddd', padding: 12, marginBottom: 24 }}>
        <h2 style={{ margin: '0 0 12px 0' }}>Recommended Products (Based on Terpene Preferences)</h2>
        
        {recsLoading && <div>Loading recommendations...</div>}
        {recsError && <div style={{ color: 'crimson' }}>Error: {recsError}</div>}
        
        {!recsLoading && recommendations.length === 0 && (
          <p style={{ margin: 0, opacity: 0.7 }}>
            No recommendations available. Customer needs purchase history with feedback to generate recommendations.
          </p>
        )}

        {!recsLoading && recommendations.length > 0 && (
          <div style={{ display: 'grid', gap: 12 }}>
            {recommendations.map((rec) => (
              <div key={rec.id} style={{ border: '1px solid #eee', padding: 12, borderRadius: 4 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <strong>{rec.name}</strong>
                      {rec.purchased_count > 0 && (
                        <span style={{ 
                          fontSize: 11, 
                          backgroundColor: '#e3f2fd', 
                          color: '#1976d2',
                          padding: '2px 6px',
                          borderRadius: 3,
                        }}>
                          Purchased {rec.purchased_count}x
                        </span>
                      )}
                    </div>
                    {rec.brand && (
                      <div style={{ fontSize: 12, opacity: 0.7 }}>{rec.brand} · {rec.category}</div>
                    )}
                    <div style={{ fontSize: 12, marginTop: 4 }}>
                      <strong>Top Terpenes:</strong> {fmtTerpenes(rec.terpenes.slice(0, 5))}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 14, fontWeight: 'bold', color: '#2e7d32' }}>
                      {rec.score.toFixed(2)} match score
                    </div>
                    {isOrderFormOpen && (
                      <button
                        type="button"
                        onClick={() => addOrderItem({
                          id: rec.id,
                          name: rec.name,
                          brand: rec.brand,
                          category: rec.category,
                          is_active: true,
                          terpenes: rec.terpenes,
                        })}
                        style={{ marginTop: 4, fontSize: 12 }}
                      >
                        Add to Order
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

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
                      const terpenes = productTerpenes[it.product_id] ?? []

                      return (
                        <tr key={it.id}>
                          <td>{it.product_name}</td>
                          <td style={{ maxWidth: 420 }}>{fmtTerpenes(terpenes)}</td>
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

      {hasMorePurchases && purchases.length > 0 && (
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <button type="button" onClick={loadMorePurchases} disabled={loading}>
            {loading ? 'Loading…' : 'Load More Purchases'}
          </button>
        </div>
      )}
    </div>
  )
}
