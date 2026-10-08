// src/CustomerEdit.tsx
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import supabase  from './utils/supabase'
import api, { API_BASE } from './api/client'
import { ListingSearch } from './components/ListingSearch'
import type { Listing, PointsSummary } from './types'
import type { CSSProperties } from 'react'
import { t, font, radius } from './theme'
import { Icon } from './components/Icon'
import { navBtnStyle, pageWrap, primaryBtnStyle, selectStyle, tdStyle, thStyle } from './components/AdminTable'

type Feedback = 'like' | 'dislike' | 'neutral' | null

type ItemTerpene = {
  name: string
  percent?: number | null
}

type PurchaseItem = {
  id: string
  listing_id: string | null
  product_name: string | null
  /** The listing's lab profile, strongest first; empty when it has none. */
  terpenes: ItemTerpene[]
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

function dollars(cents: number | null | undefined) {
  if (cents == null) return '—'
  return `$${(cents / 100).toFixed(2)}`
}

function fmtFeedback(fb: Feedback) {
  if (!fb) return '—'
  const icon = fb === 'like' ? 'thumbs-up' : fb === 'dislike' ? 'thumbs-down' : 'face-neutral'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <Icon name={icon} size={14} />{fb}
    </span>
  )
}

function fmtTerpenes(terps: ItemTerpene[] | undefined) {
  if (!terps || terps.length === 0) return '—'
  const sorted = [...terps].sort((a, b) => (b.percent ?? -1) - (a.percent ?? -1))
  return sorted.map(tp => `${tp.name}${tp.percent != null ? ` (${tp.percent}%)` : ''}`).join(', ')
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
    listing: Listing
    quantity: number
    price_cents: number
  }>>([])
  const [orderSubmitting, setOrderSubmitting] = useState(false)
  const [orderError, setOrderError] = useState<string | null>(null)

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

      // 3. Initialize feedback state
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

  // Order creation functions. Purchases record what was bought at a specific
  // store, so items are listings, priced from the shelf by default.
  function addOrderItem(listing: Listing) {
    setOrderItems(prev => [...prev, {
      listing,
      quantity: 1,
      price_cents: listing.price_cents ?? 0,
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
        listing_id: item.listing.id,
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

  if (loading) return <div style={{ ...pageWrap, color: t.text3 }}>Loading…</div>
  if (error) return <div style={{ ...pageWrap, color: t.danger }}>Error: {error}</div>
  if (!customer) return <div style={{ ...pageWrap, color: t.text3 }}>Not found</div>

  return (
    <div style={pageWrap}>
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <button type="button" onClick={() => navigate(-1)} style={navBtnStyle}><Icon name="arrow-left" size={14} />Back</button>
        <h1 style={titleStyle}>Customer</h1>
      </div>

      <form onSubmit={saveCustomer} style={{ ...cardStyle, marginBottom: 24 }}>
        <div style={{ display: 'grid', gap: 14 }}>
          <div>
            <label style={labelStyle}>Name</label>
            <input value={name} onChange={e => setName(e.target.value)} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>Email</label>
            <input value={email} onChange={e => setEmail(e.target.value)} style={inputStyle} />
          </div>

          <div>
            <label style={labelStyle}>Phone</label>
            <input value={phone} onChange={e => setPhone(e.target.value)} style={inputStyle} />
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: t.text2 }}>
            <input type="checkbox" checked={marketing} onChange={e => setMarketing(e.target.checked)} /> Marketing opt-in
          </label>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button type="submit" disabled={saving} style={saving ? disabledBtnStyle : primaryBtnStyle}>{saving ? 'Saving…' : 'Save'}</button>
            {msg && <span style={{ fontSize: 13, color: t.text2 }}>{msg}</span>}
          </div>
        </div>
      </form>

      {/* Order Creation Section */}
      <div style={{ ...cardStyle, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: isOrderFormOpen ? 12 : 0 }}>
          <h2 style={sectionTitleStyle}>Create New Order</h2>
          <button
            type="button"
            onClick={() => setIsOrderFormOpen(!isOrderFormOpen)}
            style={navBtnStyle}
          >
            {isOrderFormOpen ? 'Hide' : 'Show'}
          </button>
        </div>

        {isOrderFormOpen && (
          <div style={{ display: 'grid', gap: 12 }}>
            <ListingSearch
              onSelect={addOrderItem}
              disabled={orderSubmitting}
              placeholder="Search listings to add..."
            />

            {orderError && (
              <div style={{ color: t.danger, fontSize: 13 }}>{orderError}</div>
            )}

            {orderItems.length > 0 ? (
              <>
                <table style={tableStyle}>
                  <thead>
                    <tr style={headRowStyle}>
                      <th align="left" style={thStyle}>Listing</th>
                      <th align="center" style={thStyle}>Quantity</th>
                      <th align="right" style={thStyle}>Price (cents)</th>
                      <th align="right" style={thStyle}>Line Total</th>
                      <th style={thStyle}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {orderItems.map((item, index) => (
                      <tr key={index} style={rowStyle}>
                        <td style={tdStyle}>
                          <div style={{ color: t.text1, fontWeight: 600 }}>{item.listing.scraped_name ?? '(unnamed listing)'}</div>
                          <div style={{ fontSize: 12, color: t.text3 }}>
                            {[item.listing.scraped_brand, item.listing.dispensary_name, item.listing.variant].filter(Boolean).join(' · ')}
                          </div>
                        </td>
                        <td align="center" style={tdStyle}>
                          <input
                            type="number"
                            min={1}
                            value={item.quantity}
                            onChange={(e) => updateOrderItem(index, 'quantity', Number(e.target.value))}
                            style={{ ...inputStyle, width: 64 }}
                            disabled={orderSubmitting}
                          />
                        </td>
                        <td align="right" style={tdStyle}>
                          <input
                            type="number"
                            min={0}
                            value={item.price_cents}
                            onChange={(e) => updateOrderItem(index, 'price_cents', Number(e.target.value))}
                            style={{ ...inputStyle, width: 100 }}
                            disabled={orderSubmitting}
                          />
                        </td>
                        <td align="right" style={tdStyle}>
                          {dollars(item.quantity * item.price_cents)}
                        </td>
                        <td style={tdStyle}>
                          <button
                            type="button"
                            onClick={() => removeOrderItem(index)}
                            disabled={orderSubmitting}
                            style={navBtnStyle}
                          >
                            <Icon name="close" size={14} />Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={3} align="right" style={{ ...tdStyle, color: t.text1, fontWeight: 600 }}>Total:</td>
                      <td align="right" style={{ ...tdStyle, color: t.text1, fontWeight: 600 }}>{dollars(orderTotal)}</td>
                      <td style={tdStyle}></td>
                    </tr>
                  </tfoot>
                </table>

                <div>
                  <button
                    type="button"
                    onClick={submitOrder}
                    disabled={orderSubmitting || orderItems.length === 0}
                    style={orderSubmitting || orderItems.length === 0 ? disabledBtnStyle : primaryBtnStyle}
                  >
                    {orderSubmitting ? 'Creating Order...' : 'Create Order'}
                  </button>
                </div>
              </>
            ) : (
              <p style={{ margin: 0, fontSize: 13, color: t.text3 }}>
                Search for listings above to add them to the order.
              </p>
            )}
          </div>
        )}
      </div>

      {cid && <TerpeePoints customerId={cid} />}

      <div style={{ ...cardStyle, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <h2 style={sectionTitleStyle}>Top Terpenes</h2>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label style={{ ...labelStyle, marginBottom: 0 }}>Window (days)</label>
            <input
              type="number"
              min={1}
              max={3650}
              value={windowDays}
              onChange={e => setWindowDays(Number(e.target.value))}
              style={{ ...inputStyle, width: 100 }}
            />
            <button type="button" onClick={() => loadScores()} disabled={scoresLoading} style={navBtnStyle}>
              {scoresLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {scoresError ? <div style={{ color: t.danger, fontSize: 13, marginTop: 10 }}>Error: {scoresError}</div> : null}

        {scoresLoading ? (
          <div style={mutedStyle}>Loading terpene scores…</div>
        ) : terpeneScores.length === 0 ? (
          <div style={mutedStyle}>No scored terpenes yet (needs likes/dislikes).</div>
        ) : (
          <table style={{ ...tableStyle, marginTop: 10 }}>
            <thead>
              <tr style={headRowStyle}>
                <th align="left" style={thStyle}>Terpene</th>
                <th align="right" style={thStyle}>Score</th>
                <th align="right" style={thStyle}>Likes</th>
                <th align="right" style={thStyle}>Dislikes</th>
              </tr>
            </thead>
            <tbody>
              {terpeneScores.slice(0, 15).map(row => (
                <tr key={row.terpene} style={rowStyle}>
                  <td style={{ ...tdStyle, color: t.text1 }}>{row.terpene}</td>
                  <td align="right" style={numStyle}>{row.score.toFixed(2)}</td>
                  <td align="right" style={numStyle}>{row.likes}</td>
                  <td align="right" style={numStyle}>{row.dislikes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2 style={{ ...sectionTitleStyle, marginBottom: 12 }}>Orders</h2>

      {purchases.length === 0 ? (
        <p style={mutedStyle}>No purchases.</p>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {purchases.map(p => (
            <div key={p.id} style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ color: t.text1, fontWeight: 600 }}>{new Date(p.purchased_at).toLocaleString()}</div>
                  <div style={metaStyle}>Order ID: <span style={{ fontFamily: font.family.mono }}>{p.id}</span></div>
                  <div style={metaStyle}>Source: {p.source}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ color: t.text1, fontWeight: 600 }}>{dollars(p.total_amount_cents)}</div>
                  <div style={metaStyle}>{p.items.length} item(s)</div>
                </div>
              </div>

              {p.items.length > 0 && (
                <table style={{ ...tableStyle, marginTop: 10 }}>
                  <thead>
                    <tr style={headRowStyle}>
                      <th align="left" style={thStyle}>Listing</th>
                      <th align="left" style={thStyle}>Terpenes</th>
                      <th align="right" style={thStyle}>Qty</th>
                      <th align="right" style={thStyle}>Line</th>
                      <th align="left" style={thStyle}>Feedback</th>
                      <th align="left" style={thStyle}>Feedback At</th>
                      <th align="left" style={thStyle}>Edit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.items.map(it => {
                      const current = rowFeedback[it.id] ?? (it.feedback ?? null)
                      const savingRow = Boolean(rowSaving[it.id])
                      const errRow = rowError[it.id]

                      return (
                        <tr key={it.id} style={rowStyle}>
                          <td style={{ ...tdStyle, color: t.text1 }}>{it.product_name}</td>
                          <td style={{ ...tdStyle, maxWidth: 420, fontSize: 12 }}>{fmtTerpenes(it.terpenes)}</td>
                          <td align="right" style={numStyle}>{it.quantity}</td>
                          <td align="right" style={numStyle}>{dollars(it.line_amount_cents)}</td>
                          <td style={tdStyle}>{fmtFeedback(it.feedback ?? null)}</td>
                          <td style={{ ...tdStyle, color: t.text3, fontSize: 12 }}>{it.feedback_at ? new Date(it.feedback_at).toLocaleString() : '—'}</td>
                          <td style={tdStyle}>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                              <select
                                style={selectStyle}
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
                                style={navBtnStyle}
                              >
                                {savingRow ? 'Saving…' : 'Save'}
                              </button>
                            </div>
                            {errRow ? <div style={{ color: t.danger, fontSize: 12 }}>{errRow}</div> : null}
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
          <button type="button" onClick={loadMorePurchases} disabled={loading} style={navBtnStyle}>
            {loading ? 'Loading…' : 'Load More Purchases'}
          </button>
        </div>
      )}
    </div>
    </div>
  )
}

/** Points earned at partner stores (connectors/points.py), newest first. */
function TerpeePoints({ customerId }: { customerId: string }) {
  const [data, setData] = useState<PointsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.partners.customerPoints(customerId).then(setData).catch(err => setError(err.message))
  }, [customerId])

  return (
    <div style={{ ...cardStyle, marginBottom: 24 }}>
      <h2 style={{ ...sectionTitleStyle, marginBottom: 8 }}>Terpee Points</h2>
      {error ? (
        <p style={{ color: t.danger, margin: 0, fontSize: 13 }}>{error}</p>
      ) : !data ? (
        <p style={mutedStyle}>Loading…</p>
      ) : (
        <>
          <p style={{ margin: '0 0 8px', fontSize: 14, color: t.text2 }}>
            <b style={{ color: t.text1 }}>{data.available.toLocaleString()}</b> available · <b style={{ color: t.text1 }}>{data.pending.toLocaleString()}</b> pending
          </p>
          {data.entries.length === 0 ? (
            <p style={mutedStyle}>No points yet. Points come from partner-store purchases matched to this customer.</p>
          ) : (
            <table style={tableStyle}>
              <thead>
                <tr style={{ ...headRowStyle, textAlign: 'left' }}>
                  <th style={thStyle}>When</th><th style={thStyle}>Partner</th><th style={thStyle}>Kind</th><th align="right" style={thStyle}>Eligible</th><th align="right" style={thStyle}>Points</th><th style={thStyle}>Available</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map(e => (
                  <tr key={e.id} style={rowStyle}>
                    <td style={tdStyle}>{new Date(e.created_at).toLocaleString()}</td>
                    <td style={tdStyle}>{e.partner_name ?? '—'}</td>
                    <td style={tdStyle}>{e.kind}</td>
                    <td align="right" style={numStyle}>{e.points > 0 ? `$${(e.eligible_cents / 100).toFixed(2)}` : '—'}</td>
                    <td align="right" style={{ ...numStyle, color: e.points < 0 ? t.danger : t.text1 }}>{e.points > 0 ? '+' : ''}{e.points}</td>
                    <td style={tdStyle}>{e.pending ? `pending until ${new Date(e.available_at).toLocaleDateString()}` : 'yes'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

const titleStyle: CSSProperties = { margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em', color: t.text1 }
const sectionTitleStyle: CSSProperties = { margin: 0, fontFamily: font.family.display, fontSize: font.size.title, fontWeight: 600, color: t.text1 }
const cardStyle: CSSProperties = { background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: 16 }
const labelStyle: CSSProperties = { display: 'block', fontSize: 13, color: t.text2, fontWeight: 500, marginBottom: 6 }
const inputStyle: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '8px 10px', fontSize: 14, borderRadius: 8,
  background: t.surface2, border: `1px solid ${t.border}`, color: t.text1, outline: 'none',
}
const disabledBtnStyle: CSSProperties = { ...primaryBtnStyle, background: t.surface2, border: `1px solid ${t.border}`, color: t.text4, cursor: 'default' }
const tableStyle: CSSProperties = { width: '100%', borderCollapse: 'collapse', fontSize: 13 }
const headRowStyle: CSSProperties = { borderBottom: `1px solid ${t.borderStrong}` }
const rowStyle: CSSProperties = { borderBottom: `1px solid ${t.border}` }
const numStyle: CSSProperties = { ...tdStyle, fontVariantNumeric: 'tabular-nums' }
const mutedStyle: CSSProperties = { margin: 0, fontSize: 13, color: t.text3 }
const metaStyle: CSSProperties = { fontSize: 12, color: t.text3 }
