import { useState, useEffect } from 'react'
import { useNavigate, useMatch } from 'react-router-dom'
import api from './api/client'
import supabase from './utils/supabase'
import DispensaryMap from './components/DispensaryMap'
import ListingDetailView from './components/ListingDetail'
import type { PortalPurchase, RecommendedProduct, Feedback, PortalProduct, CartItem } from './types'
import type { Session } from '@supabase/supabase-js'
import 'leaflet/dist/leaflet.css'

type Tab = 'orders' | 'foryou' | 'products' | 'map'

const CATEGORY_IMAGES: Record<string, string> = {
  flower: '/flower.png',
  cart: '/cart.png',
  preroll: '/preroll.png',
  tincture: '/tincture.png',
  edible: '/edible.png',
  concentrate: '/concentrate.png',
}

const CATEGORY_COLORS: Record<string, string> = {
  flower: '#4caf50',
  cart: '#2196f3',
  edible: '#ff9800',
  concentrate: '#9c27b0',
  preroll: '#00bcd4',
  tincture: '#8bc34a',
  topical: '#f44336',
  merch: '#607d8b',
  other: '#9e9e9e',
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatDollars(cents: number) {
  return `$${(cents / 100).toFixed(2)}`
}

// ─── Orders Feed ──────────────────────────────────────────────────────────────

interface OrdersFeedProps {
  purchases: PortalPurchase[]
  loading: boolean
  error: string | null
  feedback: Record<string, Feedback>
  savingItems: Set<string>
  onFeedback: (itemId: string, value: Feedback) => void
  onProductClick: (productId: string) => void
}

function OrdersFeed({ purchases, loading, error, feedback, savingItems, onFeedback, onProductClick }: OrdersFeedProps) {
  const feedStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    overflowY: 'scroll',
    scrollSnapType: 'y mandatory',
    WebkitOverflowScrolling: 'touch' as any,
  }

  if (loading) {
    return (
      <div style={{ ...feedStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#555', fontSize: 14 }}>Loading orders...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ ...feedStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#f44336', fontSize: 14 }}>Failed to load orders</span>
      </div>
    )
  }

  if (purchases.length === 0) {
    return (
      <div style={{ ...feedStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#555', fontSize: 14 }}>No orders yet</span>
      </div>
    )
  }

  return (
    <div style={feedStyle}>
      {purchases.map((purchase) => (
        <div key={purchase.id} style={{ scrollSnapAlign: 'start', padding: '16px 16px 0' }}>
          <div style={{
            background: '#1a1a1a',
            borderRadius: 16,
            padding: 20,
            minHeight: 280,
            marginBottom: 16,
          }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <div style={{ color: '#fff', fontSize: 18, fontWeight: 700 }}>
                  {formatDate(purchase.purchased_at)}
                </div>
                <div style={{ color: '#666', fontSize: 13, marginTop: 2 }}>
                  {purchase.items.length} {purchase.items.length === 1 ? 'item' : 'items'}
                </div>
              </div>
              <div style={{
                background: '#2a2a2a',
                borderRadius: 10,
                padding: '6px 12px',
                color: '#a8e063',
                fontWeight: 700,
                fontSize: 16,
              }}>
                {purchase.total_amount_cents ? formatDollars(purchase.total_amount_cents) : '—'}
              </div>
            </div>

            {/* Items */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {purchase.items.map((item) => {
                const currentFeedback = feedback[item.id] ?? item.feedback ?? null
                const saving = savingItems.has(item.id)

                const imgSrc = CATEGORY_IMAGES[item.product_category]
                const catColor = CATEGORY_COLORS[item.product_category] ?? '#555'

                return (
                  <div
                    key={item.id}
                    style={{
                      position: 'relative',
                      aspectRatio: '1 / 1',
                      borderRadius: 12,
                      overflow: 'hidden',
                      cursor: 'pointer',
                    }}
                    onClick={() => onProductClick(item.product_id)}
                  >
                    {/* Background: image or color fill */}
                    {imgSrc ? (
                      <img src={imgSrc} style={{
                        position: 'absolute',
                        inset: 0,
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                      }} />
                    ) : (
                      <div style={{
                        position: 'absolute',
                        inset: 0,
                        background: `linear-gradient(135deg, ${catColor}44 0%, #111 100%)`,
                      }} />
                    )}

                    {/* Full-card frost */}
                    <div style={{
                      position: 'absolute',
                      inset: 0,
                      backdropFilter: 'blur(0px)',
                      WebkitBackdropFilter: 'blur(0px)',
                      background: 'rgba(0,0,0,0.32)',
                    }} />

                    {/* Content */}
                    <div style={{
                      position: 'absolute',
                      inset: 0,
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      padding: 14,
                    }}>
                      {/* Category pill — top right */}
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{
                          color: '#fff',
                          fontWeight: 700,
                          fontSize: 16,
                          textAlign: 'left',
                        }}>
                          {item.product_name}
                        </span>
                        <span style={{
                          background: 'rgba(0,0,0,0.4)',
                          border: `1px solid ${catColor}`,
                          color: catColor,
                          fontSize: 9,
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: 20,
                          textTransform: 'uppercase',
                          letterSpacing: '0.06em',
                          height: 'fit-content',
                          width: 'fit-content',
                        }}>
                          {item.product_category}
                        </span>
                      </div>

                      {/* Bottom: feedback */}
                      <div>
                        <div
                          style={{ display: 'flex', justifyContent: 'center', gap: 6, padding: 6, borderRadius: 8, width: '100%' }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {(['like', 'dislike', 'neutral'] as const).map((val) => {
                            const labels: Record<string, string> = { like: '👍', dislike: '👎', neutral: '😑' }
                            const activeColors: Record<string, string> = {
                              like: '#a8e063',
                              dislike: '#f44336',
                              neutral: '#aaa',
                            }
                            const isActive = currentFeedback === val
                            return (
                              <button
                                key={val}
                                disabled={saving}
                                onClick={() => onFeedback(item.id, isActive ? null : val)}
                                style={{
                                  background: isActive ? activeColors[val] + '33' : 'rgba(0,0,0,0.7)',
                                  border: `1px solid ${isActive ? activeColors[val] : 'rgba(255,255,255,0.2)'}`,
                                  borderRadius: 8,
                                  color: isActive ? activeColors[val] : 'rgba(255,255,255,1)',
                                  fontSize: val === 'neutral' ? 16 : 13,
                                  padding: '4px 11px',
                                  cursor: saving ? 'default' : 'pointer',
                                  opacity: saving ? 0.5 : 1,
                                  transition: 'all 0.15s',
                                }}
                              >
                                {labels[val]}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ))}
      {/* Bottom padding so last card clears nav */}
      <div style={{ height: 16 }} />
    </div>
  )
}

// ─── Recommendations Feed ─────────────────────────────────────────────────────

interface RecsFeedProps {
  recommendations: RecommendedProduct[]
  loading: boolean
  error: string | null
  onProductClick: (productId: string) => void
}

function RecsFeed({ recommendations, loading, error, onProductClick }: RecsFeedProps) {
  const feedStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    overflowY: 'scroll',
    scrollSnapType: 'y mandatory',
    WebkitOverflowScrolling: 'touch' as any,
  }

  if (loading) {
    return (
      <div style={{ ...feedStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#555', fontSize: 14 }}>Finding your picks...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ ...feedStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#f44336', fontSize: 14 }}>Failed to load recommendations</span>
      </div>
    )
  }

  if (recommendations.length === 0) {
    return (
      <div style={{ ...feedStyle, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 32px' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 36, marginBottom: 16 }}>✨</div>
          <div style={{ color: '#fff', fontWeight: 700, fontSize: 18, marginBottom: 8 }}>
            Rate your past orders
          </div>
          <div style={{ color: '#555', fontSize: 14, lineHeight: 1.5 }}>
            Tap 👍 or 👎 on your order items to unlock personalized picks.
          </div>
        </div>
      </div>
    )
  }

  const maxScore = recommendations[0].score

  return (
    <div style={feedStyle}>
      {recommendations.map((rec) => {
        const matchPct = maxScore > 0 ? Math.round((rec.score / maxScore) * 100) : null
        const catColor = CATEGORY_COLORS[rec.category] ?? '#555'
        const shownTerpenes = rec.terpenes.slice(0, 5)

        const imgSrc = CATEGORY_IMAGES[rec.category]

        return (
          <div
            key={rec.id}
            style={{ scrollSnapAlign: 'start', padding: '16px 16px 0', cursor: 'pointer' }}
            onClick={() => onProductClick(rec.id)}
          >
            <div style={{
              background: '#1a1a1a',
              borderRadius: 16,
              minHeight: 280,
              marginBottom: 16,
              position: 'relative',
              border: `1px solid #2a2a2a`,
              overflow: 'hidden',
            }}>
              {/* Hero image */}
              {imgSrc ? (
                <div style={{ position: 'relative', height: 200 }}>
                  <img src={imgSrc} style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
                  <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, transparent 40%, #1a1a1a 100%)' }} />
                  {matchPct !== null && (
                    <div style={{
                      position: 'absolute',
                      top: 12,
                      right: 12,
                      background: '#a8e063',
                      color: '#0a0a0a',
                      fontSize: 11,
                      fontWeight: 800,
                      padding: '4px 10px',
                      borderRadius: 20,
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                    }}>
                      {matchPct}% match
                    </div>
                  )}
                </div>
              ) : (
                matchPct !== null && (
                  <div style={{
                    position: 'absolute',
                    top: 16,
                    right: 16,
                    background: '#a8e063',
                    color: '#0a0a0a',
                    fontSize: 11,
                    fontWeight: 800,
                    padding: '4px 10px',
                    borderRadius: 20,
                    letterSpacing: '0.05em',
                    textTransform: 'uppercase',
                  }}>
                    {matchPct}% match
                  </div>
                )
              )}

              {/* Content */}
              <div style={{ padding: imgSrc ? '12px 20px 20px' : 20 }}>
              {/* Category tag */}
              <div style={{
                display: 'inline-block',
                background: catColor + '22',
                border: `1px solid ${catColor}`,
                color: catColor,
                fontSize: 10,
                fontWeight: 700,
                padding: '3px 10px',
                borderRadius: 20,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 12,
              }}>
                {rec.category}
              </div>

              {/* Product name */}
              <div style={{
                color: '#fff',
                fontSize: 24,
                fontWeight: 800,
                lineHeight: 1.2,
                marginBottom: 6,
                paddingRight: !imgSrc && matchPct !== null ? 80 : 0,
              }}>
                {rec.name}
              </div>

              {/* Brand */}
              {rec.brand && (
                <div style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>
                  {rec.brand}
                </div>
              )}

              {/* Terpenes */}
              {shownTerpenes.length > 0 && (
                <div style={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: 6, marginTop: 'auto' }}>
                  {shownTerpenes.map((t) => (
                    <span key={t.name} style={{
                      background: '#2a2a2a',
                      color: '#888',
                      fontSize: 11,
                      padding: '3px 10px',
                      borderRadius: 20,
                    }}>
                      {t.name}{t.percent ? ` ${t.percent.toFixed(1)}%` : ''}
                    </span>
                  ))}
                </div>
              )}

              {/* Purchased before */}
              {rec.purchased_count > 0 && (
                <div style={{ color: '#444', fontSize: 11, marginTop: 12 }}>
                  Purchased {rec.purchased_count}× before
                </div>
              )}
              </div>
            </div>
          </div>
        )
      })}
      <div style={{ height: 16 }} />
    </div>
  )
}

// ─── Products Feed ────────────────────────────────────────────────────────────

interface ProductsFeedProps {
  onProductClick: (productId: string) => void
}

function ProductsFeed({ onProductClick }: ProductsFeedProps) {
  const [products, setProducts] = useState<PortalProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetchProducts()
  }, [search])

  async function fetchProducts() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.portal.getProducts({ q: search || undefined, limit: 50 })
      setProducts(data)
    } catch {
      setError('Failed to load products')
    } finally {
      setLoading(false)
    }
  }

  const feedStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    overflowY: 'auto',
    WebkitOverflowScrolling: 'touch' as any,
  }

  return (
    <div style={feedStyle}>
      {/* Search bar */}
      <div style={{ padding: '16px 16px 8px', display: 'flex', gap: 8 }}>
        <input
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') setSearch(searchInput) }}
          placeholder="Search products..."
          style={{
            flex: 1,
            background: '#1a1a1a',
            border: '1px solid #2a2a2a',
            borderRadius: 10,
            color: '#fff',
            fontSize: 14,
            padding: '10px 14px',
            outline: 'none',
          }}
        />
        {search && (
          <button
            onClick={() => { setSearchInput(''); setSearch('') }}
            style={{
              background: '#2a2a2a',
              border: 'none',
              borderRadius: 10,
              color: '#888',
              fontSize: 14,
              padding: '0 14px',
              cursor: 'pointer',
            }}
          >
            ✕
          </button>
        )}
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: '#555', fontSize: 14 }}>Loading...</span>
        </div>
      ) : error ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: '#f44336', fontSize: 14 }}>{error}</span>
        </div>
      ) : products.length === 0 ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: '#555', fontSize: 14 }}>No products found</span>
        </div>
      ) : (
        <div style={{ padding: '0 16px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {products.map((p) => {
            const catColor = CATEGORY_COLORS[p.category] ?? '#555'
            const imgSrc = CATEGORY_IMAGES[p.category]
            return (
              <div
                key={p.id}
                onClick={() => onProductClick(p.id)}
                style={{
                  background: '#1a1a1a',
                  borderRadius: 12,
                  padding: 16,
                  display: 'flex',
                  gap: 14,
                  alignItems: 'center',
                  cursor: 'pointer',
                  border: '1px solid #222',
                }}
              >
                {/* Thumbnail */}
                <div style={{
                  width: 52,
                  height: 52,
                  borderRadius: 10,
                  overflow: 'hidden',
                  flexShrink: 0,
                  background: catColor + '22',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  {imgSrc
                    ? <img src={imgSrc} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    : <span style={{ fontSize: 20 }}>🌿</span>
                  }
                </div>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: '#fff', fontWeight: 700, fontSize: 15, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {p.name}
                  </div>
                  {p.brand && (
                    <div style={{ color: '#666', fontSize: 12, marginTop: 2 }}>{p.brand}</div>
                  )}
                  <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                    <span style={{
                      background: catColor + '22',
                      border: `1px solid ${catColor}`,
                      color: catColor,
                      fontSize: 9,
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 20,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                    }}>
                      {p.category}
                    </span>
                    {p.terpenes.length > 0 && (
                      <span style={{ background: '#2a2a2a', color: '#666', fontSize: 10, padding: '2px 8px', borderRadius: 20 }}>
                        {p.terpenes.length} terpene{p.terpenes.length !== 1 ? 's' : ''}
                      </span>
                    )}
                    {p.cannabinoids.length > 0 && (
                      <span style={{ background: '#2a2a2a', color: '#666', fontSize: 10, padding: '2px 8px', borderRadius: 20 }}>
                        {p.cannabinoids.length} cannabinoid{p.cannabinoids.length !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                </div>

                <span style={{ color: '#333', fontSize: 18 }}>›</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── Product Detail ───────────────────────────────────────────────────────────

interface ProductDetailProps {
  productId: string
  onBack: () => void
}

function ProductDetail({ productId, onBack }: ProductDetailProps) {
  const [product, setProduct] = useState<PortalProduct | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.portal.getProduct(productId)
      .then(setProduct)
      .catch(() => setError('Failed to load product'))
      .finally(() => setLoading(false))
  }, [productId])

  const feedStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    overflowY: 'auto',
    WebkitOverflowScrolling: 'touch' as any,
  }

  if (loading) {
    return (
      <div style={{ ...feedStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#555', fontSize: 14 }}>Loading...</span>
      </div>
    )
  }

  if (error || !product) {
    return (
      <div style={{ ...feedStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#f44336', fontSize: 14 }}>{error ?? 'Not found'}</span>
      </div>
    )
  }

  const catColor = CATEGORY_COLORS[product.category] ?? '#555'
  const imgSrc = CATEGORY_IMAGES[product.category]

  return (
    <div style={feedStyle}>
      {/* Back button */}
      <button
        onClick={onBack}
        style={{
          position: 'absolute',
          top: 16,
          left: 16,
          zIndex: 10,
          background: 'rgba(0,0,0,0.6)',
          border: '1px solid #333',
          borderRadius: 20,
          color: '#fff',
          fontSize: 13,
          padding: '6px 14px',
          cursor: 'pointer',
        }}
      >
        ← Back
      </button>

      {/* Hero */}
      {imgSrc ? (
        <div style={{ position: 'relative' }}>
          <img src={imgSrc} style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', background: '#111' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, transparent 40%, #0a0a0a 100%)' }} />
        </div>
      ) : (
        <div style={{ height: 120, background: `linear-gradient(135deg, ${catColor}33 0%, #111 100%)` }} />
      )}

      {/* Content */}
      <div style={{ padding: '20px 20px 32px' }}>
        {/* Category pill */}
        <div style={{
          display: 'inline-block',
          background: catColor + '22',
          border: `1px solid ${catColor}`,
          color: catColor,
          fontSize: 10,
          fontWeight: 700,
          padding: '3px 10px',
          borderRadius: 20,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginBottom: 12,
        }}>
          {product.category}
        </div>

        {/* Name */}
        <div style={{ color: '#fff', fontSize: 28, fontWeight: 800, lineHeight: 1.2, marginBottom: 6 }}>
          {product.name}
        </div>

        {/* Brand */}
        {product.brand && (
          <div style={{ color: '#666', fontSize: 14, marginBottom: 24 }}>{product.brand}</div>
        )}

        {/* Cannabinoids */}
        {product.cannabinoids.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <div style={{ color: '#555', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
              Cannabinoids
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 , justifyContent: 'center'}}>
              {product.cannabinoids.map((c) => (
                <div key={c.name} style={{
                  background: '#1a1a1a',
                  border: '1px solid #2a2a2a',
                  borderRadius: 10,
                  padding: '8px 14px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 2,
                  minWidth: 72,
                }}>
                  <span style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>{c.name}</span>
                  <span style={{
                    color: c.family === 'thc' ? '#a8e063' : '#2196f3',
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}>
                    {c.family.toUpperCase()}
                  </span>
                  {c.percent != null && (
                    <span style={{ color: '#555', fontSize: 11 }}>{c.percent}%</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Terpenes */}
        {product.terpenes.length > 0 && (
          <div>
            <div style={{ color: '#555', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
              Terpenes
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 , justifyContent: 'center'}}>
              {product.terpenes.map((t) => (
                <span key={t.name} style={{
                  background: '#2a2a2a',
                  color: '#888',
                  fontSize: 12,
                  padding: '5px 12px',
                  borderRadius: 20,
                }}>
                  {t.name}{t.percent != null ? ` ${t.percent}%` : ''}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Login Screen ─────────────────────────────────────────────────────────────

function LoginScreen() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSend() {
    if (!email.trim()) return
    setLoading(true)
    setError(null)
    try {
      const { error: err } = await supabase.auth.signInWithOtp({ email: email.trim() })
      if (err) throw err
      setSent(true)
    } catch (e: any) {
      setError(e.message ?? 'Failed to send link')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100dvh',
      padding: '0 32px',
      background: '#0a0a0a',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      <div style={{ fontSize: 36, marginBottom: 20 }}>🌿</div>
      <div style={{ color: '#fff', fontWeight: 800, fontSize: 24, marginBottom: 8, textAlign: 'center' }}>
        Sign in
      </div>
      <div style={{ color: '#555', fontSize: 14, marginBottom: 32, textAlign: 'center' }}>
        {sent ? 'Check your email for a magic link.' : "We'll send you a magic link."}
      </div>

      {!sent && (
        <>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSend() }}
            placeholder="your@email.com"
            style={{
              width: '100%',
              maxWidth: 320,
              background: '#1a1a1a',
              border: '1px solid #2a2a2a',
              borderRadius: 10,
              color: '#fff',
              fontSize: 16,
              padding: '14px 16px',
              outline: 'none',
              marginBottom: 12,
              boxSizing: 'border-box',
            }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !email.trim()}
            style={{
              width: '100%',
              maxWidth: 320,
              background: loading ? '#222' : '#a8e063',
              border: 'none',
              borderRadius: 10,
              color: loading ? '#555' : '#0a0a0a',
              fontSize: 15,
              fontWeight: 700,
              padding: '14px',
              cursor: loading ? 'default' : 'pointer',
            }}
          >
            {loading ? 'Sending…' : 'Send magic link'}
          </button>
          {error && (
            <div style={{ color: '#f44336', fontSize: 13, marginTop: 12 }}>{error}</div>
          )}
        </>
      )}
    </div>
  )
}

// ─── Not Linked Screen ────────────────────────────────────────────────────────

function NotLinkedScreen() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100dvh',
      padding: '0 32px',
      background: '#0a0a0a',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 36, marginBottom: 20 }}>🔗</div>
      <div style={{ color: '#fff', fontWeight: 800, fontSize: 22, marginBottom: 12 }}>
        Account not linked
      </div>
      <div style={{ color: '#555', fontSize: 14, lineHeight: 1.6 }}>
        Your email isn't connected to a customer account yet. Ask a staff member to link your account.
      </div>
    </div>
  )
}

// ─── Cart Drawer ──────────────────────────────────────────────────────────────

interface CartDrawerProps {
  items: CartItem[]
  open: boolean
  onClose: () => void
  onRemove: (listingId: string) => void
  onClear: () => void
}

function CartDrawer({ items, open, onClose, onRemove, onClear }: CartDrawerProps) {
  const total = items.reduce((sum, i) => sum + (i.price_cents ?? 0) * i.quantity, 0)
  const dispensaryName = items[0]?.dispensaryName ?? ''

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          onClick={onClose}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
            zIndex: 2200, backdropFilter: 'blur(2px)',
          }}
        />
      )}

      {/* Drawer */}
      <div style={{
        position: 'fixed',
        bottom: 0, left: 0, right: 0,
        background: '#141414',
        borderTop: '1px solid #2a2a2a',
        borderRadius: '20px 20px 0 0',
        zIndex: 2300,
        transform: open ? 'translateY(0)' : 'translateY(100%)',
        transition: 'transform 0.3s cubic-bezier(0.32, 0.72, 0, 1)',
        maxHeight: '80dvh',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* Handle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: '#333' }} />
        </div>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px 0' }}>
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 18 }}>Your cart</div>
            {dispensaryName && (
              <div style={{ color: '#555', fontSize: 12, marginTop: 2 }}>{dispensaryName}</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {items.length > 0 && (
              <button
                onClick={onClear}
                style={{
                  background: 'transparent', border: '1px solid #2a2a2a',
                  borderRadius: 8, color: '#555', fontSize: 12,
                  padding: '5px 10px', cursor: 'pointer',
                }}
              >
                Clear
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                background: '#2a2a2a', border: 'none',
                borderRadius: 8, color: '#888', fontSize: 18,
                width: 32, height: 32, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              ×
            </button>
          </div>
        </div>

        {/* Items */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '16px 20px 0' }}>
          {items.length === 0 ? (
            <div style={{ color: '#555', fontSize: 14, textAlign: 'center', padding: '32px 0' }}>
              Cart is empty
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {items.map(item => (
                <div key={item.listingId} style={{
                  display: 'flex', gap: 12, alignItems: 'center',
                  background: '#1a1a1a', borderRadius: 12, padding: 12,
                }}>
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt=""
                      style={{ width: 48, height: 48, borderRadius: 8, objectFit: 'contain', background: '#111', flexShrink: 0 }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  ) : (
                    <div style={{ width: 48, height: 48, borderRadius: 8, background: '#222', flexShrink: 0 }} />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: '#fff', fontWeight: 600, fontSize: 14, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.name}
                    </div>
                    {item.variant && (
                      <div style={{ color: '#555', fontSize: 12 }}>{item.variant}</div>
                    )}
                    {item.price_cents != null && (
                      <div style={{ color: '#a8e063', fontWeight: 700, fontSize: 13, marginTop: 2 }}>
                        ${(item.price_cents / 100).toFixed(2)}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => onRemove(item.listingId)}
                    style={{
                      background: 'transparent', border: 'none',
                      color: '#444', fontSize: 18, cursor: 'pointer',
                      padding: '4px 8px', flexShrink: 0,
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {items.length > 0 && (
          <div style={{ padding: 20, borderTop: '1px solid #1e1e1e', marginTop: 16 }}>
            {total > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <span style={{ color: '#666', fontSize: 14 }}>Estimated total</span>
                <span style={{ color: '#fff', fontWeight: 700, fontSize: 18 }}>
                  ${(total / 100).toFixed(2)}
                </span>
              </div>
            )}
            <a
              href={items[0]?.url ?? '#'}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'block', width: '100%', boxSizing: 'border-box',
                background: '#a8e063', borderRadius: 12,
                color: '#0a0a0a', fontWeight: 700, fontSize: 15,
                padding: '14px', textAlign: 'center', textDecoration: 'none',
              }}
            >
              Order at {dispensaryName} →
            </a>
          </div>
        )}
        <div style={{ height: 'env(safe-area-inset-bottom, 0px)' }} />
      </div>
    </>
  )
}

// ─── Root Component ───────────────────────────────────────────────────────────

export default function CustomerPortal() {
  const navigate = useNavigate()
  const matchProduct = useMatch('/portal/products/:productId')
  const matchListing = useMatch('/portal/map/:dispensaryId/listings/:listingId')
  const matchAisle = useMatch('/portal/map/:dispensaryId/aisle/:category')
  const matchDispensary = useMatch('/portal/map/:dispensaryId')
  const matchTab = useMatch('/portal/:tab')

  const selectedProductId = matchProduct?.params.productId ?? null
  const selectedListingId = matchListing?.params.listingId ?? null
  const selectedListingDispensaryId = matchListing?.params.dispensaryId ?? null
  const selectedDispensaryId = matchDispensary?.params.dispensaryId ?? null
  const activeTab: Tab = (matchListing || matchDispensary || matchAisle)
    ? 'map'
    : matchProduct
      ? 'products'
      : ((matchTab?.params.tab as Tab | undefined) ?? 'orders')

  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [customerId, setCustomerId] = useState<string | null>(null)
  const [profileError, setProfileError] = useState<string | null>(null)

  const [purchases, setPurchases] = useState<PortalPurchase[]>([])
  const [purchasesLoading, setPurchasesLoading] = useState(true)
  const [purchasesError, setPurchasesError] = useState<string | null>(null)

  const [feedback, setFeedback] = useState<Record<string, Feedback>>({})
  const [savingItems, setSavingItems] = useState<Set<string>>(new Set())

  const [recommendations, setRecommendations] = useState<RecommendedProduct[]>([])
  const [recsLoading, setRecsLoading] = useState(false)
  const [recsError, setRecsError] = useState<string | null>(null)
  const [recsFetched, setRecsFetched] = useState(false)

  const [cart, setCart] = useState<CartItem[]>([])
  const [cartOpen, setCartOpen] = useState(false)

  // Track Supabase session
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  // Resolve customer ID once session is available, auto-linking on first login
  useEffect(() => {
    if (!session) return
    api.me.getProfile()
      .then(profile => setCustomerId(profile.id))
      .catch(() =>
        api.me.linkCustomer()
          .then(() => api.me.getProfile())
          .then(profile => setCustomerId(profile.id))
          .catch(err => setProfileError(err.message ?? 'not_linked'))
      )
  }, [session])

  const id = customerId

  // Load orders once customer is resolved
  useEffect(() => {
    if (!id) return
    setPurchasesLoading(true)
    api.portal.getPurchases(id)
      .then((data) => {
        setPurchases(data)
        const initial: Record<string, Feedback> = {}
        data.forEach((p) => p.items.forEach((item) => {
          if (item.feedback !== undefined) initial[item.id] = item.feedback ?? null
        }))
        setFeedback(initial)
      })
      .catch(() => setPurchasesError('failed'))
      .finally(() => setPurchasesLoading(false))
  }, [id])

  function loadRecommendations() {
    if (!id) return
    setRecsLoading(true)
    api.portal.getRecommendations(id)
      .then(setRecommendations)
      .catch(() => setRecsError('failed'))
      .finally(() => setRecsLoading(false))
  }

  useEffect(() => {
    if (activeTab === 'foryou' && !recsFetched && id) {
      setRecsFetched(true)
      loadRecommendations()
    }
  }, [activeTab, id])

  function handleTabChange(tab: Tab) {
    navigate('/portal/' + tab)
  }

  function handleProductClick(productId: string) {
    navigate('/portal/products/' + productId)
  }

  function handleAddToCart(item: CartItem) {
    setCart(prev => {
      const existing = prev.findIndex(i => i.listingId === item.listingId)
      if (existing !== -1) {
        const next = [...prev]
        next[existing] = { ...next[existing], quantity: next[existing].quantity + 1 }
        return next
      }
      return [...prev, item]
    })
  }

  function handleRemoveFromCart(listingId: string) {
    setCart(prev => prev.filter(i => i.listingId !== listingId))
  }

  async function handleFeedback(itemId: string, value: Feedback) {
    if (!id) return
    const previous = feedback[itemId] ?? null
    setFeedback((prev) => ({ ...prev, [itemId]: value }))
    setSavingItems((prev) => new Set(prev).add(itemId))

    try {
      await api.portal.setFeedback(id, itemId, value)
    } catch {
      setFeedback((prev) => ({ ...prev, [itemId]: previous }))
    } finally {
      setSavingItems((prev) => {
        const next = new Set(prev)
        next.delete(itemId)
        return next
      })
    }
  }

  // Auth / loading gates
  if (session === undefined) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100dvh', background: '#0a0a0a' }}>
        <span style={{ color: '#333', fontSize: 14 }}>Loading…</span>
      </div>
    )
  }
  if (!session) return <LoginScreen />
  if (profileError) return <NotLinkedScreen />
  if (!customerId) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100dvh', background: '#0a0a0a' }}>
        <span style={{ color: '#333', fontSize: 14 }}>Loading…</span>
      </div>
    )
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: '#0a0a0a',
      overflow: 'hidden',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      {/* Feed area */}
      {activeTab === 'orders' && (
        <OrdersFeed
          purchases={purchases}
          loading={purchasesLoading}
          error={purchasesError}
          feedback={feedback}
          savingItems={savingItems}
          onFeedback={handleFeedback}
          onProductClick={handleProductClick}
        />
      )}
      {activeTab === 'foryou' && (
        <RecsFeed
          recommendations={recommendations}
          loading={recsLoading}
          error={recsError}
          onProductClick={handleProductClick}
        />
      )}
      {activeTab === 'products' && selectedProductId && (
        <ProductDetail
          productId={selectedProductId}
          onBack={() => navigate(-1)}
        />
      )}
      {activeTab === 'products' && !selectedProductId && (
        <ProductsFeed onProductClick={handleProductClick} />
      )}
      {activeTab === 'map' && selectedListingId && selectedListingDispensaryId ? (
        <ListingDetailView
          dispensaryId={selectedListingDispensaryId}
          listingId={selectedListingId}
          onProductClick={handleProductClick}
          onAddToCart={handleAddToCart}
          cartQuantity={cart.filter(i => i.listingId === selectedListingId).reduce((s, i) => s + i.quantity, 0)}
        />
      ) : activeTab === 'map' && (
        <DispensaryMap
          activeDispensaryId={selectedDispensaryId}
          onProductClick={handleProductClick}
          onAddToCart={handleAddToCart}
          cart={cart}
        />
      )}

      {/* Floating cart button */}
      {cart.length > 0 && (() => {
        const totalQty = cart.reduce((s, i) => s + i.quantity, 0)
        const totalCents = cart.reduce((s, i) => s + (i.price_cents ?? 0) * i.quantity, 0)
        return (
          <button
            onClick={() => setCartOpen(true)}
            style={{
              position: 'fixed',
              bottom: 72,
              left: 12,
              right: 12,
              zIndex: 2100,
              background: '#1c1c1e',
              border: '1px solid #2a2a2a',
              borderRadius: 16,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '14px 18px',
              boxShadow: '0 8px 32px rgba(0,0,0,0.7)',
            }}
          >
            <span style={{
              background: '#333', borderRadius: 8,
              color: '#fff', fontWeight: 700, fontSize: 13,
              padding: '4px 10px', minWidth: 28, textAlign: 'center',
            }}>
              {totalQty}
            </span>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 15 }}>View cart</span>
            {totalCents > 0
              ? <span style={{ color: '#a8e063', fontWeight: 700, fontSize: 15 }}>${(totalCents / 100).toFixed(2)}</span>
              : <span style={{ width: 40 }} />
            }
          </button>
        )
      })()}

      {/* Cart drawer */}
      <CartDrawer
        items={cart}
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        onRemove={handleRemoveFromCart}
        onClear={() => setCart([])}
      />

      {/* Bottom nav */}
      <div style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        height: 64,
        background: '#111',
        borderTop: '1px solid #222',
        display: 'flex',
      }}>
        {([
          { key: 'orders', label: 'Orders', icon: '🧾' },
          { key: 'foryou', label: 'For You', icon: '✨' },
          { key: 'products', label: 'Menu', icon: '🌿' },
          { key: 'map', label: 'Map', icon: '📍' },
        ] as const).map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => handleTabChange(key)}
            style={{
              flex: 1,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 4,
              color: activeTab === key ? '#a8e063' : '#555',
              transition: 'color 0.15s',
            }}
          >
            <span style={{ fontSize: 20 }}>{icon}</span>
            <span style={{
              fontSize: 11,
              fontWeight: activeTab === key ? 700 : 400,
              letterSpacing: '0.02em',
              textTransform: 'uppercase',
            }}>
              {label}
            </span>
            {activeTab === key && (
              <div style={{
                position: 'absolute',
                bottom: 0,
                width: 32,
                height: 2,
                background: '#a8e063',
                borderRadius: 2,
              }} />
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
