import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useMatch, useSearchParams } from 'react-router-dom'
import api from './api/client'
import supabase from './utils/supabase'
import DispensaryMap from './components/DispensaryMap'
import HomeFeed from './components/HomeFeed'
import CategoryView from './components/CategoryView'
import SearchView from './components/SearchView'
import ListingDetailView from './components/ListingDetail'
import type { PortalPurchase, RecommendedProduct, Feedback, CartItem, PortalBrandDetail, PortalBrandProduct, PortalBrandOffering, ListingDetail } from './types'
import type { Session } from '@supabase/supabase-js'
import { t, radius, font, alpha } from './theme'
import { Pressable, CategoryTag, FeedState, ClassificationTag, DetailBlock, CollapsibleBlock, SpecRow } from './components/ui'
import 'leaflet/dist/leaflet.css'

type Tab = 'home' | 'map' | 'search' | 'account'

const CATEGORY_IMAGES: Record<string, string> = {
  flower: '/flower.png',
  cart: '/cart.png',
  preroll: '/preroll.png',
  tincture: '/tincture.png',
  edible: '/edible.png',
  concentrate: '/concentrate.png',
}

const CATEGORY_COLORS: Record<string, string> = {
  flower: '#5bb85f',
  cart: '#3b9bf0',
  edible: '#ff9f43',
  concentrate: '#a958d8',
  preroll: '#22c3d6',
  tincture: '#8bc34a',
  topical: '#f0655a',
  merch: '#7a8a99',
  other: '#9aa0a6',
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

function haversineMi(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 3958.8
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function formatDist(mi: number) {
  return mi < 0.1 ? '< 0.1 mi' : `${mi.toFixed(1)} mi`
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
    height: '100dvh',
    overflowY: 'scroll',
    scrollSnapType: 'y mandatory',
    WebkitOverflowScrolling: 'touch' as any,
  }

  if (loading) {
    return <div style={feedStyle}><FeedState kind="loading" message="Loading orders…" style={{ height: '100%' }} /></div>
  }

  if (error) {
    return <div style={feedStyle}><FeedState kind="error" message="Failed to load orders" style={{ height: '100%' }} /></div>
  }

  if (purchases.length === 0) {
    return <div style={feedStyle}><FeedState kind="empty" message="No orders yet" hint="Your past purchases will show up here." icon="🧾" style={{ height: '100%' }} /></div>
  }

  return (
    <div style={feedStyle}>
      {purchases.map((purchase) => (
        <div key={purchase.id} style={{ scrollSnapAlign: 'start', padding: '16px 16px 0' }}>
          <div style={{
            background: t.surface1,
            borderRadius: radius.xl,
            padding: 20,
            minHeight: 280,
            marginBottom: 16,
            border: `1px solid ${t.border}`,
          }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <div style={{ color: t.text1, fontSize: font.size.title, fontWeight: font.weight.bold, letterSpacing: '-0.01em' }}>
                  {formatDate(purchase.purchased_at)}
                </div>
                <div style={{ color: t.text3, fontSize: font.size.small + 1, marginTop: 2 }}>
                  {purchase.items.length} {purchase.items.length === 1 ? 'item' : 'items'}
                </div>
              </div>
              <div style={{
                background: 'var(--accent-tint)',
                border: `1px solid ${alpha('#a8e063', 0.3)}`,
                borderRadius: radius.md,
                padding: '6px 12px',
                color: t.accent,
                fontWeight: font.weight.bold,
                fontSize: font.size.title,
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
      {/* Bottom padding so last card clears floating nav */}
      <div style={{ height: 92 }} />
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
    height: '100dvh',
    overflowY: 'scroll',
    scrollSnapType: 'y mandatory',
    WebkitOverflowScrolling: 'touch' as any,
  }

  if (loading) {
    return <div style={feedStyle}><FeedState kind="loading" message="Finding your picks…" style={{ height: '100%' }} /></div>
  }

  if (error) {
    return <div style={feedStyle}><FeedState kind="error" message="Failed to load recommendations" style={{ height: '100%' }} /></div>
  }

  if (recommendations.length === 0) {
    return (
      <div style={feedStyle}>
        <FeedState
          kind="empty"
          message="Rate your past orders"
          hint="Tap 👍 or 👎 on your order items to unlock personalized picks."
          icon="✨"
          style={{ height: '100%' }}
        />
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
          <Pressable
            key={rec.id}
            onClick={() => onProductClick(rec.id)}
            style={{ scrollSnapAlign: 'start', padding: '16px 16px 0' }}
          >
            <div style={{
              background: t.surface1,
              borderRadius: radius.xl,
              minHeight: 280,
              marginBottom: 16,
              position: 'relative',
              border: `1px solid ${t.border}`,
              overflow: 'hidden',
            }}>
              {/* Hero image — unified light plate */}
              {imgSrc ? (
                <div style={{ position: 'relative', height: 200, background: t.tile }}>
                  <img src={imgSrc} style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', padding: 18, boxSizing: 'border-box' }} />
                  {matchPct !== null && (
                    <div style={{
                      position: 'absolute',
                      top: 12,
                      right: 12,
                      background: t.accent,
                      color: '#0a0a0a',
                      fontSize: font.size.caption,
                      fontWeight: font.weight.heavy,
                      padding: '4px 10px',
                      borderRadius: radius.pill,
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                      boxShadow: 'var(--e-1)',
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
                    background: t.accent,
                    color: '#0a0a0a',
                    fontSize: font.size.caption,
                    fontWeight: font.weight.heavy,
                    padding: '4px 10px',
                    borderRadius: radius.pill,
                    letterSpacing: '0.05em',
                    textTransform: 'uppercase',
                  }}>
                    {matchPct}% match
                  </div>
                )
              )}

              {/* Content */}
              <div style={{ padding: imgSrc ? '14px 20px 20px' : 20 }}>
              {/* Category tag */}
              <div style={{ marginBottom: 12 }}>
                <CategoryTag category={rec.category} />
              </div>

              {/* Product name */}
              <div style={{
                color: t.text1,
                fontSize: font.size.display,
                fontWeight: font.weight.heavy,
                lineHeight: 1.2,
                marginBottom: 6,
                letterSpacing: '-0.01em',
                paddingRight: !imgSrc && matchPct !== null ? 80 : 0,
              }}>
                {rec.name}
              </div>

              {/* Brand */}
              {rec.brand && (
                <div style={{ color: t.text2, fontSize: font.size.small + 1, marginBottom: 16 }}>
                  {rec.brand}
                </div>
              )}

              {/* Terpenes */}
              {shownTerpenes.length > 0 && (
                <div style={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: 6, marginTop: 'auto' }}>
                  {shownTerpenes.map((tp) => (
                    <span key={tp.name} style={{
                      background: t.surface2,
                      color: t.text2,
                      border: `1px solid ${t.border}`,
                      fontSize: font.size.caption,
                      padding: '4px 10px',
                      borderRadius: radius.pill,
                    }}>
                      {tp.name}{tp.percent ? ` ${tp.percent.toFixed(1)}%` : ''}
                    </span>
                  ))}
                </div>
              )}

              {/* Purchased before */}
              {rec.purchased_count > 0 && (
                <div style={{ color: t.text3, fontSize: font.size.caption, marginTop: 12 }}>
                  Purchased {rec.purchased_count}× before
                </div>
              )}
              </div>
            </div>
          </Pressable>
        )
      })}
      <div style={{ height: 92 }} />
    </div>
  )
}

// ─── Products Feed ────────────────────────────────────────────────────────────

function LoginScreen() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const inputStyle: React.CSSProperties = {
    width: '100%',
    maxWidth: 320,
    background: t.surface2,
    border: `1px solid ${t.border}`,
    borderRadius: radius.md,
    color: t.text1,
    fontSize: 16,
    padding: '14px 16px',
    outline: 'none',
    marginBottom: 12,
    boxSizing: 'border-box',
  }

  async function handleSend() {
    if (!email.trim()) return
    setLoading(true)
    setError(null)
    try {
      const { error: err } = await supabase.auth.signInWithOtp({ email: email.trim() })
      if (err) throw err
      setSent(true)
      setCode('')
    } catch (e: any) {
      setError(e.message ?? 'Failed to send code')
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify() {
    const token = code.trim()
    if (!token) return
    setVerifying(true)
    setError(null)
    try {
      const { error: err } = await supabase.auth.verifyOtp({ email: email.trim(), token, type: 'email' })
      if (err) throw err
    } catch (e: any) {
      setError(e.message ?? 'Invalid code')
    } finally {
      setVerifying(false)
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
      background: t.bg,
    }}>
      <div style={{ fontSize: 40, marginBottom: 18 }}>🌿</div>
      <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.display, marginBottom: 8, textAlign: 'center', letterSpacing: '-0.01em' }}>
        Sign in
      </div>

      {!sent ? (
        <>
          <div style={{ color: t.text3, fontSize: font.size.body, marginBottom: 32, textAlign: 'center' }}>
            We'll send a code to your email.
          </div>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSend() }}
            placeholder="your@email.com"
            style={inputStyle}
          />
          <button
            onClick={handleSend}
            disabled={loading || !email.trim()}
            style={{
              width: '100%',
              maxWidth: 320,
              background: loading ? t.surface3 : t.accent,
              border: 'none',
              borderRadius: radius.md,
              color: loading ? t.text3 : '#0a0a0a',
              fontSize: font.size.callout,
              fontWeight: font.weight.bold,
              padding: '14px',
              cursor: loading ? 'default' : 'pointer',
              boxShadow: loading ? 'none' : 'var(--e-1)',
              transition: `background var(--t-base)`,
            }}
          >
            {loading ? 'Sending…' : 'Send code'}
          </button>
        </>
      ) : (
        <>
          <div style={{ color: t.text3, fontSize: font.size.body, marginBottom: 32, textAlign: 'center' }}>
            Enter the code sent to <span style={{ color: t.text2, fontWeight: font.weight.medium }}>{email}</span>
          </div>
          <input
            type="text"
            inputMode="numeric"
            value={code}
            onChange={e => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 8)
              setCode(v)
            }}
            onKeyDown={e => { if (e.key === 'Enter') handleVerify() }}
            placeholder="8-digit code"
            autoFocus
            style={{ ...inputStyle, fontSize: 24, letterSpacing: '0.3em', textAlign: 'center' }}
          />
          <button
            onClick={handleVerify}
            disabled={verifying || code.trim().length < 8}
            style={{
              width: '100%',
              maxWidth: 320,
              background: verifying || code.trim().length < 8 ? t.surface3 : t.accent,
              border: 'none',
              borderRadius: radius.md,
              color: verifying || code.trim().length < 8 ? t.text3 : '#0a0a0a',
              fontSize: font.size.callout,
              fontWeight: font.weight.bold,
              padding: '14px',
              cursor: verifying || code.trim().length < 8 ? 'default' : 'pointer',
              marginBottom: 12,
              boxShadow: verifying || code.trim().length < 8 ? 'none' : 'var(--e-1)',
              transition: `background var(--t-base)`,
            }}
          >
            {verifying ? 'Verifying…' : 'Verify'}
          </button>
          <button
            onClick={() => { setSent(false); setCode(''); setError(null) }}
            style={{
              background: 'none',
              border: 'none',
              color: t.text3,
              fontSize: font.size.small + 1,
              cursor: 'pointer',
              padding: '4px 0',
            }}
          >
            Use a different email
          </button>
        </>
      )}

      {error && (
        <div style={{ color: t.danger, fontSize: font.size.small + 1, marginTop: 12, textAlign: 'center' }}>{error}</div>
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
      background: t.bg,
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 40, marginBottom: 18 }}>🔗</div>
      <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.heading, marginBottom: 12, letterSpacing: '-0.01em' }}>
        Account not linked
      </div>
      <div style={{ color: t.text3, fontSize: font.size.body, lineHeight: 1.6, maxWidth: 300 }}>
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
        background: t.surface1,
        borderTop: `1px solid ${t.border}`,
        borderRadius: `${radius['2xl']} ${radius['2xl']} 0 0`,
        zIndex: 2300,
        transform: open ? 'translateY(0)' : 'translateY(100%)',
        transition: 'transform 0.32s cubic-bezier(0.32, 0.72, 0, 1)',
        maxHeight: '80dvh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: 'var(--e-3)',
      }}>
        {/* Handle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: t.surface3 }} />
        </div>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px 0' }}>
          <div>
            <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, letterSpacing: '-0.01em' }}>Your cart</div>
            {dispensaryName && (
              <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>{dispensaryName}</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {items.length > 0 && (
              <button
                onClick={onClear}
                style={{
                  background: 'transparent', border: `1px solid ${t.border}`,
                  borderRadius: radius.sm, color: t.text3, fontSize: font.size.small,
                  padding: '6px 11px', cursor: 'pointer',
                }}
              >
                Clear
              </button>
            )}
            <button
              onClick={onClose}
              aria-label="Close cart"
              style={{
                background: t.surface2, border: `1px solid ${t.border}`,
                borderRadius: radius.sm, color: t.text2, fontSize: 18,
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
            <div style={{ color: t.text3, fontSize: font.size.body, textAlign: 'center', padding: '40px 0' }}>
              <div style={{ fontSize: 30, marginBottom: 10 }}>🛒</div>
              Your cart is empty
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {items.map(item => (
                <div key={item.listingId} style={{
                  display: 'flex', gap: 12, alignItems: 'center',
                  background: t.surface2, borderRadius: radius.lg, padding: 12, border: `1px solid ${t.border}`,
                }}>
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt=""
                      style={{ width: 48, height: 48, borderRadius: radius.sm, objectFit: 'contain', background: t.tile, padding: 4, boxSizing: 'border-box', flexShrink: 0 }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  ) : (
                    <div style={{ width: 48, height: 48, borderRadius: radius.sm, background: t.surface3, flexShrink: 0 }} />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.body, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.name}
                    </div>
                    {item.variant && (
                      <div style={{ color: t.text3, fontSize: font.size.small }}>{item.variant}</div>
                    )}
                    {item.price_cents != null && (
                      <div style={{ color: t.accent, fontWeight: font.weight.bold, fontSize: font.size.small + 1, marginTop: 2 }}>
                        ${(item.price_cents / 100).toFixed(2)}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => onRemove(item.listingId)}
                    aria-label="Remove item"
                    style={{
                      background: 'transparent', border: 'none',
                      color: t.text3, fontSize: 18, cursor: 'pointer',
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
          <div style={{ padding: 20, borderTop: `1px solid ${t.border}`, marginTop: 16 }}>
            {total > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <span style={{ color: t.text2, fontSize: font.size.body }}>Estimated total</span>
                <span style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title }}>
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
                background: t.accent, borderRadius: radius.lg,
                color: '#0a0a0a', fontWeight: font.weight.bold, fontSize: font.size.callout,
                padding: '14px', textAlign: 'center', textDecoration: 'none',
                boxShadow: 'var(--e-1)',
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

// ─── Account View ─────────────────────────────────────────────────────────────

interface AccountViewProps {
  session: import('@supabase/supabase-js').Session
  onSignOut: () => void
}

function AccountView({ session, onSignOut }: AccountViewProps) {
  return (
    <div style={{
      height: '100dvh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '0 32px 92px',
      background: t.bg,
    }}>
      <div style={{
        width: 72,
        height: 72,
        borderRadius: '50%',
        background: t.surface2,
        border: `1px solid ${t.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 20,
      }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="var(--text-3)">
          <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
        </svg>
      </div>
      <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title, marginBottom: 6 }}>Your account</div>
      <div style={{ color: t.text3, fontSize: font.size.body, marginBottom: 40 }}>{session.user.email}</div>
      <button
        onClick={onSignOut}
        style={{
          background: 'transparent',
          border: `1px solid ${t.border}`,
          borderRadius: radius.lg,
          color: t.danger,
          fontSize: font.size.callout,
          fontWeight: font.weight.semibold,
          padding: '12px 32px',
          cursor: 'pointer',
        }}
      >
        Sign out
      </button>
    </div>
  )
}

// ─── Brand View ───────────────────────────────────────────────────────────────

function FilterChip({ label, active, onClick, color }: {
  label: string
  active: boolean
  onClick: () => void
  color?: string
}) {
  const accent = color ?? '#a8e063'
  return (
    <button
      onClick={onClick}
      style={{
        flexShrink: 0,
        cursor: 'pointer',
        whiteSpace: 'nowrap',
        textTransform: 'capitalize',
        fontSize: font.size.small,
        fontWeight: active ? font.weight.bold : font.weight.medium,
        padding: '6px 12px',
        borderRadius: radius.pill,
        background: active ? alpha(accent, 0.14) : t.surface2,
        border: `1px solid ${active ? accent : t.border}`,
        color: active ? accent : t.text3,
        transition: `all var(--t-fast)`,
      }}
    >
      {label}
    </button>
  )
}

interface BrandViewProps {
  brandName: string
  onBack: () => void
  onOpenProduct: (productKey: string) => void
}

type BrandSort = 'featured' | 'nearest' | 'price-asc' | 'price-desc'

type EnrichedProduct = {
  product: PortalBrandProduct
  closest: PortalBrandOffering | null
  closestDist: number | null
  cheapest: PortalBrandOffering | null
  cheapestDist: number | null
}

function BrandView({ brandName, onBack, onOpenProduct }: BrandViewProps) {
  const [brand, setBrand] = useState<PortalBrandDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [category, setCategory] = useState<string | null>(null)
  const [sort, setSort] = useState<BrandSort>('featured')
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setCategory(null)
    setSort('featured')
    api.portal.getBrand(brandName)
      .then(setBrand)
      .catch(() => setError('Failed to load brand'))
      .finally(() => setLoading(false))
  }, [brandName])

  useEffect(() => {
    navigator.geolocation?.getCurrentPosition(pos => {
      setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude })
    })
  }, [])

  // Category facets with product counts, ordered by frequency
  const categoryFacets = useMemo(() => {
    if (!brand) return [] as { name: string; count: number }[]
    const counts = new Map<string, number>()
    for (const p of brand.products) {
      if (p.category) counts.set(p.category, (counts.get(p.category) ?? 0) + 1)
    }
    return [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
  }, [brand])

  // For each product, resolve the closest in-stock offering and the cheapest one
  const enriched = useMemo<EnrichedProduct[]>(() => {
    if (!brand) return []
    return brand.products.map(product => {
      let closest: PortalBrandOffering | null = null
      let closestDist = Infinity
      let cheapest: PortalBrandOffering | null = null
      for (const o of product.offerings) {
        if (o.price_cents != null && (cheapest == null || o.price_cents < cheapest.price_cents!)) {
          cheapest = o
        }
        if (userPos && o.lat != null && o.lng != null) {
          const d = haversineMi(userPos.lat, userPos.lng, o.lat, o.lng)
          if (d < closestDist) { closestDist = d; closest = o }
        }
      }
      const cheapestDist = (userPos && cheapest?.lat != null && cheapest?.lng != null)
        ? haversineMi(userPos.lat, userPos.lng, cheapest.lat, cheapest.lng)
        : null
      return {
        product,
        closest,
        closestDist: closest ? closestDist : null,
        cheapest,
        cheapestDist,
      }
    })
  }, [brand, userPos])

  const visibleProducts = useMemo(() => {
    const filtered = category
      ? enriched.filter(e => e.product.category === category)
      : enriched
    const sorted = [...filtered]
    if (sort === 'price-asc' || sort === 'price-desc') {
      const dir = sort === 'price-asc' ? 1 : -1
      sorted.sort((a, b) => {
        const pa = a.product.min_price_cents
        const pb = b.product.min_price_cents
        if (pa == null) return 1
        if (pb == null) return -1
        return (pa - pb) * dir
      })
    } else if (sort === 'nearest') {
      sorted.sort((a, b) => (a.closestDist ?? Infinity) - (b.closestDist ?? Infinity))
    }
    return sorted
  }, [enriched, category, sort])

  return (
    <div style={{ height: '100dvh', overflowY: 'auto', background: t.bg }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '20px 16px 12px' }}>
        <button
          onClick={onBack}
          aria-label="Back"
          style={{ background: 'none', border: 'none', color: t.accent, fontSize: 26, cursor: 'pointer', padding: 0, lineHeight: 1 }}
        >
          ‹
        </button>
        <div style={{
          width: 56, height: 56, borderRadius: '50%', background: t.surface2, border: `1px solid ${t.border}`,
          overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          {brand?.image_url ? (
            <img src={brand.image_url} alt={brandName} style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: 22 }}>
              {brandName.charAt(0).toUpperCase()}
            </span>
          )}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.heading, letterSpacing: '-0.01em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {brandName}
          </div>
          {brand && (
            <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
              {brand.product_count} product{brand.product_count !== 1 ? 's' : ''} · {brand.dispensary_count} dispensar{brand.dispensary_count !== 1 ? 'ies' : 'y'}
            </div>
          )}
        </div>
      </div>

      {/* Filter / sort toolbar */}
      {brand && brand.products.length > 0 && (
        <div style={{ position: 'sticky', top: 0, zIndex: 5, background: 'rgba(11,11,13,0.86)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', paddingBottom: 4 }}>
          {/* Category chips */}
          {categoryFacets.length > 1 && (
            <div style={{ display: 'flex', overflowX: 'auto', gap: 8, padding: '4px 16px 8px', scrollbarWidth: 'none' } as React.CSSProperties}>
              <FilterChip label="All" active={category === null} onClick={() => setCategory(null)} />
              {categoryFacets.map(f => (
                <FilterChip
                  key={f.name}
                  label={`${f.name} ${f.count}`}
                  color={CATEGORY_COLORS[f.name] ?? '#888'}
                  active={category === f.name}
                  onClick={() => setCategory(category === f.name ? null : f.name)}
                />
              ))}
            </div>
          )}
          {/* Sort row */}
          <div style={{ display: 'flex', gap: 8, padding: '0 16px 6px', overflowX: 'auto', scrollbarWidth: 'none' } as React.CSSProperties}>
            <FilterChip label="Featured" active={sort === 'featured'} onClick={() => setSort('featured')} />
            {userPos && <FilterChip label="Nearest" active={sort === 'nearest'} onClick={() => setSort('nearest')} />}
            <FilterChip label="Price ↑" active={sort === 'price-asc'} onClick={() => setSort('price-asc')} />
            <FilterChip label="Price ↓" active={sort === 'price-desc'} onClick={() => setSort('price-desc')} />
          </div>
        </div>
      )}

      {loading ? (
        <FeedState kind="loading" message="Loading…" />
      ) : error ? (
        <FeedState kind="error" message={error} />
      ) : !brand || brand.products.length === 0 ? (
        <FeedState kind="empty" message="No products in stock" icon="🌿" />
      ) : visibleProducts.length === 0 ? (
        <FeedState kind="empty" message="No products in this category" icon="🔍" style={{ minHeight: 160 }} />
      ) : (
        <div style={{ padding: '4px 16px 92px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {!userPos && (
            <div style={{ color: t.text3, fontSize: font.size.caption, padding: '0 2px 2px' }}>
              📍 Turn on location to see distances and nearest stores
            </div>
          )}
          {visibleProducts.map((e) => (
            <BrandProductCard key={e.product.key} item={e} hasLocation={!!userPos} onOpen={() => onOpenProduct(e.product.key)} />
          ))}
        </div>
      )}
    </div>
  )
}

// One product row: closest in-stock store + price, plus the lowest price elsewhere
function BrandProductCard({ item, hasLocation, onOpen }: {
  item: EnrichedProduct
  hasLocation: boolean
  onOpen: () => void
}) {
  const { product, closest, closestDist, cheapest, cheapestDist } = item

  // The store we surface first: prefer the closest, else the cheapest
  const primary = closest ?? cheapest
  const otherCount = product.dispensary_count - 1
  // Show the "lowest price" line only when it's a genuinely cheaper, different store
  const showLowest =
    cheapest != null &&
    cheapest.price_cents != null &&
    primary != null &&
    cheapest.listing_id !== primary.listing_id &&
    (primary.price_cents == null || cheapest.price_cents < primary.price_cents)

  return (
    <Pressable
      onClick={onOpen}
      style={{
        background: t.surface1, borderRadius: radius.lg, padding: 14, display: 'flex', gap: 14,
        alignItems: 'center', border: `1px solid ${t.border}`,
      }}
    >
      {/* Thumbnail */}
      <div style={{
        width: 54, height: 54, borderRadius: radius.md, overflow: 'hidden', flexShrink: 0,
        background: t.tile, display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.06)',
      }}>
        {product.image_url
          ? <img src={product.image_url} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 6, boxSizing: 'border-box' }}
              onError={ev => { (ev.target as HTMLImageElement).style.display = 'none' }} />
          : <span style={{ fontSize: 20, opacity: 0.6 }}>🌿</span>}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {product.name}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 5, flexWrap: 'wrap' }}>
          {product.category && <CategoryTag category={product.category} />}
          {product.variant && (
            <span style={{ color: t.text3, fontSize: font.size.caption }}>{product.variant}</span>
          )}
        </div>

        {/* Closest store line */}
        {closest ? (
          <div style={{ color: t.text2, fontSize: font.size.small, marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            <span style={{ color: t.accent }}>📍 {closestDist != null ? formatDist(closestDist) : ''}</span>
            {' · '}{closest.dispensary_name}
          </div>
        ) : primary ? (
          <div style={{ color: t.text2, fontSize: font.size.small, marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {primary.dispensary_name}
          </div>
        ) : null}

        {/* Availability across dispensaries */}
        <div style={{
          color: otherCount > 0 ? t.accent : t.text3,
          fontSize: font.size.caption, marginTop: 3,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {otherCount > 0
            ? `Also at ${otherCount} other dispensar${otherCount === 1 ? 'y' : 'ies'}`
            : 'Only at this dispensary'}
        </div>
      </div>

      {/* Price column */}
      <div style={{ textAlign: 'right', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
        {primary?.price_cents != null && (
          <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.callout }}>{formatDollars(primary.price_cents)}</div>
        )}
        {showLowest && (
          <div style={{ color: t.accent, fontSize: font.size.micro, fontWeight: font.weight.semibold, whiteSpace: 'nowrap' }}>
            Low {formatDollars(cheapest!.price_cents!)}
            {hasLocation && cheapestDist != null ? ` · ${formatDist(cheapestDist)}` : ''}
          </div>
        )}
        {!showLowest && cheapest?.price_cents != null && product.dispensary_count > 1 && (
          <div style={{ color: t.text3, fontSize: font.size.micro }}>best price</div>
        )}
      </div>
    </Pressable>
  )
}

// ─── Brand Product View ─────────────────────────────────────────────────────

interface ProductViewProps {
  brandName: string
  productKey: string
  onBack: () => void
  onListingClick: (dispensaryId: string, listingId: string) => void
}

function ProductView({ brandName, productKey, onBack, onListingClick }: ProductViewProps) {
  const [brand, setBrand] = useState<PortalBrandDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [detail, setDetail] = useState<ListingDetail | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.portal.getBrand(brandName)
      .then(setBrand)
      .catch(() => setError('Failed to load product'))
      .finally(() => setLoading(false))
  }, [brandName])

  useEffect(() => {
    navigator.geolocation?.getCurrentPosition(pos => {
      setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude })
    })
  }, [])

  const product = useMemo(
    () => brand?.products.find(p => p.key === productKey) ?? null,
    [brand, productKey],
  )

  // Pull richer attributes (description, classification, terpenes, cannabinoids)
  // from a representative listing — the cheapest offering carrying this product.
  useEffect(() => {
    setDetail(null)
    if (!product || product.offerings.length === 0) return
    const rep = [...product.offerings]
      .filter(o => o.price_cents != null)
      .sort((a, b) => (a.price_cents! - b.price_cents!))[0] ?? product.offerings[0]
    let cancelled = false
    api.portal.getListing(rep.dispensary_id, rep.listing_id)
      .then(d => { if (!cancelled) setDetail(d) })
      .catch(() => { /* detail is best-effort */ })
    return () => { cancelled = true }
  }, [product])

  // All dispensaries carrying this product, with distance, sorted by distance (or price)
  const offerings = useMemo(() => {
    if (!product) return []
    const withDist = product.offerings.map(o => ({
      offering: o,
      dist: (userPos && o.lat != null && o.lng != null)
        ? haversineMi(userPos.lat, userPos.lng, o.lat, o.lng)
        : null,
    }))
    withDist.sort((a, b) => {
      if (a.dist != null && b.dist != null) return a.dist - b.dist
      if (a.dist != null) return -1
      if (b.dist != null) return 1
      // no location: cheapest first
      const pa = a.offering.price_cents
      const pb = b.offering.price_cents
      if (pa == null) return 1
      if (pb == null) return -1
      return pa - pb
    })
    return withDist
  }, [product, userPos])

  const prices = (product?.offerings ?? []).map(o => o.price_cents).filter((p): p is number => p != null)
  const minPrice = prices.length ? Math.min(...prices) : null
  const maxPrice = prices.length ? Math.max(...prices) : null
  const avgPrice = prices.length ? Math.round(prices.reduce((s, p) => s + p, 0) / prices.length) : null
  const savings = (minPrice != null && maxPrice != null) ? maxPrice - minPrice : 0

  const classification = detail?.classification ?? null
  const strain = product?.strain ?? detail?.strain ?? null
  const subtype = product?.subtype ?? detail?.subtype ?? null
  const productLine = product?.product_line ?? detail?.product_line ?? null
  const description = detail?.description ?? null
  const cannabinoids = detail?.cannabinoids ?? []
  const terpenes = detail?.terpenes ?? []
  const hasSpecs = !!(strain || subtype || productLine || product?.variant || classification)

  return (
    <div style={{ height: '100dvh', overflowY: 'auto', background: t.bg }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '20px 16px 8px' }}>
        <button
          onClick={onBack}
          style={{ background: 'none', border: 'none', color: t.accent, fontSize: 24, cursor: 'pointer', padding: 0, lineHeight: 1 }}
        >
          ‹
        </button>
        <div style={{ color: t.text3, fontSize: font.size.small, fontWeight: font.weight.semibold }}>{brandName}</div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: t.text3, fontSize: 14 }}>Loading…</span>
        </div>
      ) : error ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: t.danger, fontSize: 14 }}>{error}</span>
        </div>
      ) : !product ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span style={{ color: t.text3, fontSize: 14 }}>Product not found</span>
        </div>
      ) : (
        <>
          {/* Product hero */}
          <div style={{ display: 'flex', gap: 16, padding: '8px 16px 16px', alignItems: 'center' }}>
            <div style={{
              width: 88, height: 88, borderRadius: radius.lg, overflow: 'hidden', flexShrink: 0,
              background: t.tile, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {product.image_url
                ? <img src={product.image_url} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 8, boxSizing: 'border-box' }}
                    onError={ev => { (ev.target as HTMLImageElement).style.display = 'none' }} />
                : <span style={{ fontSize: 32, opacity: 0.6 }}>🌿</span>}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.heading, lineHeight: 1.15 }}>
                {product.name}
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 7, flexWrap: 'wrap' }}>
                {product.category && <CategoryTag category={product.category} />}
                {classification && <ClassificationTag classification={classification} />}
                {product.variant && <span style={{ color: t.text3, fontSize: font.size.caption }}>{product.variant}</span>}
              </div>
              {minPrice != null && (
                <div style={{ color: t.text2, fontSize: font.size.small, marginTop: 8 }}>
                  {minPrice === maxPrice
                    ? formatDollars(minPrice)
                    : `${formatDollars(minPrice)} – ${formatDollars(maxPrice!)}`}
                </div>
              )}
            </div>
          </div>

          {/* Price insights */}
          {minPrice != null && (
            <div style={{ padding: '0 16px 18px' }}>
              <div style={{
                display: 'flex', background: t.surface1, border: `1px solid ${t.border}`,
                borderRadius: radius.lg, overflow: 'hidden',
              }}>
                {[
                  { label: 'Lowest', value: formatDollars(minPrice), accent: true },
                  { label: 'Average', value: avgPrice != null ? formatDollars(avgPrice) : '—', accent: false },
                  { label: 'Highest', value: maxPrice != null ? formatDollars(maxPrice) : '—', accent: false },
                ].map((cell, i) => (
                  <div key={cell.label} style={{
                    flex: 1, padding: '12px 8px', textAlign: 'center',
                    borderLeft: i > 0 ? `1px solid ${t.border}` : 'none',
                  }}>
                    <div style={{ color: cell.accent ? t.accent : t.text1, fontWeight: font.weight.heavy, fontSize: font.size.callout }}>{cell.value}</div>
                    <div style={{ color: t.text3, fontSize: font.size.micro, marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{cell.label}</div>
                  </div>
                ))}
              </div>
              {savings > 0 && (
                <div style={{ color: t.accent, fontSize: font.size.caption, fontWeight: font.weight.semibold, marginTop: 8, textAlign: 'center' }}>
                  Save up to {formatDollars(savings)} by choosing the lowest-priced store
                </div>
              )}
            </div>
          )}

          {/* Cannabinoids */}
          {cannabinoids.length > 0 && (
            <DetailBlock title="Cannabinoids" style={{ padding: '0 16px 18px' }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {cannabinoids.map((c, i) => (
                  <div key={`${c.name}-${i}`} style={{
                    background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.md,
                    padding: '8px 12px', minWidth: 64,
                  }}>
                    <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.body }}>
                      {c.percent != null ? `${c.percent}%` : '—'}
                    </div>
                    <div style={{ color: t.text3, fontSize: font.size.micro, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{c.name}</div>
                  </div>
                ))}
              </div>
            </DetailBlock>
          )}

          {/* Terpenes */}
          {terpenes.length > 0 && (
            <DetailBlock title="Terpenes" style={{ padding: '0 16px 18px' }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {terpenes.map((tp, i) => (
                  <span key={`${tp.name}-${i}`} style={{
                    background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.pill,
                    padding: '6px 12px', color: t.text2, fontSize: font.size.small,
                  }}>
                    {tp.name}{tp.percent != null ? ` · ${tp.percent}%` : ''}
                  </span>
                ))}
              </div>
            </DetailBlock>
          )}

          {/* Specs */}
          {hasSpecs && (
            <DetailBlock title="Details" style={{ padding: '0 16px 18px' }}>
              <div>
                {strain && <SpecRow label="Strain" value={strain} />}
                {classification && <SpecRow label="Type" value={classification} />}
                {subtype && <SpecRow label="Form" value={subtype} />}
                {productLine && <SpecRow label="Product line" value={productLine} />}
                {product.variant && <SpecRow label="Size" value={product.variant} />}
              </div>
            </DetailBlock>
          )}

          {/* Description */}
          {description && (
            <CollapsibleBlock title="Product Description" style={{ padding: '0 16px 18px' }}>
              <p style={{ color: t.text2, fontSize: font.size.small, lineHeight: 1.6, margin: 0, whiteSpace: 'pre-wrap' }}>
                {description}
              </p>
            </CollapsibleBlock>
          )}

          {/* Availability heading */}
          <div style={{ color: t.text2, fontWeight: font.weight.bold, fontSize: font.size.callout, padding: '8px 16px 4px' }}>
            {product.dispensary_count === 1
              ? 'Available at 1 dispensary'
              : `Available at ${product.dispensary_count} dispensaries`}
          </div>
          {!userPos && (
            <div style={{ color: t.text3, fontSize: font.size.caption, padding: '0 16px 6px' }}>
              📍 Turn on location to sort by distance
            </div>
          )}

          {/* Dispensary list */}
          <div style={{ padding: '4px 16px 92px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {offerings.map(({ offering: o, dist }) => {
              const isCheapest = o.price_cents != null && o.price_cents === minPrice && minPrice !== maxPrice
              return (
                <Pressable
                  key={o.listing_id}
                  onClick={() => onListingClick(o.dispensary_id, o.listing_id)}
                  style={{
                    background: t.surface1, borderRadius: radius.lg, padding: 14, display: 'flex', gap: 12,
                    alignItems: 'center', border: `1px solid ${t.border}`,
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {o.dispensary_name}
                    </div>
                    <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 3 }}>
                      {dist != null ? `📍 ${formatDist(dist)}` : (o.in_stock ? 'In stock' : 'Out of stock')}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
                    {o.price_cents != null && (
                      <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.callout }}>{formatDollars(o.price_cents)}</div>
                    )}
                    {isCheapest && (
                      <div style={{ color: t.accent, fontSize: font.size.micro, fontWeight: font.weight.semibold }}>lowest</div>
                    )}
                  </div>
                  <span style={{ color: t.text4, fontSize: 18, marginLeft: 2 }}>›</span>
                </Pressable>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Root Component ───────────────────────────────────────────────────────────

export default function CustomerPortal() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const matchBrandProduct = useMatch('/portal/brands/:brandName/products/:productKey')
  const matchBrand = useMatch('/portal/brands/:brandName')
  const matchCategory = useMatch('/portal/categories/:category')
  const matchListing = useMatch('/portal/map/:dispensaryId/listings/:listingId')
  const matchAisle = useMatch('/portal/map/:dispensaryId/aisle/:category')
  const matchDispensary = useMatch('/portal/map/:dispensaryId')
  const matchTab = useMatch('/portal/:tab')

  const brandProductBrand = matchBrandProduct?.params.brandName ? decodeURIComponent(matchBrandProduct.params.brandName) : null
  const brandProductKey = matchBrandProduct?.params.productKey ? decodeURIComponent(matchBrandProduct.params.productKey) : null
  const selectedBrandName = matchBrand?.params.brandName ? decodeURIComponent(matchBrand.params.brandName) : null
  const selectedCategory = matchCategory?.params.category ? decodeURIComponent(matchCategory.params.category) : null
  const selectedListingId = matchListing?.params.listingId ?? null
  const selectedListingDispensaryId = matchListing?.params.dispensaryId ?? null
  const selectedDispensaryId = matchDispensary?.params.dispensaryId ?? null
  const activeTab: Tab = (matchListing || matchDispensary || matchAisle)
    ? 'map'
    : (matchBrand || matchBrandProduct || matchCategory)
      ? 'home'
      : ((matchTab?.params.tab as Tab | undefined) ?? 'home')

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

  function handleTabChange(tab: Tab) {
    navigate('/portal/' + tab)
  }

  async function handleSignOut() {
    await supabase.auth.signOut()
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
    return <div style={{ height: '100dvh', background: t.bg }}><FeedState kind="loading" message="Loading…" style={{ height: '100%' }} /></div>
  }
  if (!session) return <LoginScreen />
  if (profileError) return <NotLinkedScreen />
  if (!customerId) {
    return <div style={{ height: '100dvh', background: t.bg }}><FeedState kind="loading" message="Loading…" style={{ height: '100%' }} /></div>
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: t.bg,
      overflow: 'hidden',
    }}>
      {/* Feed area */}
      {activeTab === 'home' && brandProductBrand && brandProductKey && (
        <ProductView
          brandName={brandProductBrand}
          productKey={brandProductKey}
          onBack={() => navigate(-1)}
          onListingClick={(dispensaryId, listingId) => navigate(`/portal/map/${dispensaryId}/listings/${listingId}`)}
        />
      )}
      {activeTab === 'home' && !brandProductBrand && selectedBrandName && (
        <BrandView
          brandName={selectedBrandName}
          onBack={() => navigate(-1)}
          onOpenProduct={(productKey) => navigate(`/portal/brands/${encodeURIComponent(selectedBrandName)}/products/${encodeURIComponent(productKey)}`)}
        />
      )}
      {activeTab === 'home' && !brandProductBrand && !selectedBrandName && selectedCategory && (
        <CategoryView
          categoryName={selectedCategory}
          onBack={() => navigate(-1)}
          onOpenBrandProduct={(brand, productKey) =>
            navigate(`/portal/brands/${encodeURIComponent(brand)}/products/${encodeURIComponent(productKey)}`)}
          onOpenListing={(dispensaryId, listingId) =>
            navigate(`/portal/map/${dispensaryId}/listings/${listingId}`)}
        />
      )}
      {activeTab === 'home' && !brandProductBrand && !selectedBrandName && !selectedCategory && <HomeFeed />}
      {activeTab === 'search' && (
        <SearchView
          initialCategory={searchParams.get('category')}
          onOpenBrandProduct={(brandName, key) =>
            navigate(`/portal/brands/${encodeURIComponent(brandName)}/products/${encodeURIComponent(key)}`)}
          onOpenCategory={(categoryName) =>
            navigate('/portal/categories/' + encodeURIComponent(categoryName))}
        />
      )}
      {activeTab === 'map' && selectedListingId && selectedListingDispensaryId ? (
        <ListingDetailView
          dispensaryId={selectedListingDispensaryId}
          listingId={selectedListingId}
          onAddToCart={handleAddToCart}
          cartQuantity={cart.filter(i => i.listingId === selectedListingId).reduce((s, i) => s + i.quantity, 0)}
        />
      ) : activeTab === 'map' && (
        <DispensaryMap
          activeDispensaryId={selectedDispensaryId}
          onAddToCart={handleAddToCart}
          cart={cart}
        />
      )}
      {activeTab === 'account' && session && (
        <AccountView session={session} onSignOut={handleSignOut} />
      )}

      {/* Cart drawer */}
      <CartDrawer
        items={cart}
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        onRemove={handleRemoveFromCart}
        onClear={() => setCart([])}
      />

      {/* Floating bottom nav */}
      <div style={{
        position: 'fixed',
        bottom: 16,
        left: 12,
        right: 12,
        height: 60,
        background: 'rgba(14, 14, 14, 0.92)',
        backdropFilter: 'blur(24px)',
        WebkitBackdropFilter: 'blur(24px)',
        borderRadius: 20,
        border: '1px solid rgba(255,255,255,0.07)',
        boxShadow: '0 4px 32px rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        zIndex: 2100,
        padding: '0 6px',
        gap: 2,
      }}>
        {/* Home */}
        <button
          onClick={() => handleTabChange('home')}
          style={{
            flex: 1,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 3,
            color: activeTab === 'home' ? '#a8e063' : '#555',
            padding: '0 4px',
            height: '100%',
            transition: 'color 0.15s',
            borderRadius: 16,
          }}
        >
          <svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor">
            <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>
          </svg>
          <span style={{ fontSize: 10, fontWeight: activeTab === 'home' ? 700 : 400, letterSpacing: '0.02em' }}>Home</span>
        </button>

        {/* Map */}
        <button
          onClick={() => handleTabChange('map')}
          style={{
            flex: 1,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 3,
            color: activeTab === 'map' ? '#a8e063' : '#555',
            padding: '0 4px',
            height: '100%',
            transition: 'color 0.15s',
            borderRadius: 16,
          }}
        >
          <svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
          </svg>
          <span style={{ fontSize: 10, fontWeight: activeTab === 'map' ? 700 : 400, letterSpacing: '0.02em' }}>Map</span>
        </button>

        {/* Search — wide pill */}
        <button
          onClick={() => handleTabChange('search')}
          style={{
            flex: 2,
            background: activeTab === 'search' ? 'rgba(168,224,99,0.1)' : 'rgba(255,255,255,0.05)',
            border: activeTab === 'search' ? '1px solid rgba(168,224,99,0.25)' : '1px solid rgba(255,255,255,0.07)',
            borderRadius: 14,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            padding: '0 12px',
            height: 40,
            color: activeTab === 'search' ? '#a8e063' : '#555',
            transition: 'all 0.15s',
          }}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
            <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
          </svg>
          <span style={{ fontSize: 13, fontWeight: 500, flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            Search products
          </span>
        </button>

        {/* Cart with badge */}
        {(() => {
          const totalQty = cart.reduce((s, i) => s + i.quantity, 0)
          return (
            <button
              onClick={() => setCartOpen(true)}
              style={{
                flex: 1,
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 3,
                color: totalQty > 0 ? '#a8e063' : '#555',
                padding: '0 4px',
                height: '100%',
                transition: 'color 0.15s',
                borderRadius: 16,
                position: 'relative',
              }}
            >
              <div style={{ position: 'relative' }}>
                <svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96C5 16.1 6.9 18 9 18h12v-2H9.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63H19c.75 0 1.41-.41 1.75-1.03l3.58-6.49c.08-.14.12-.31.12-.48 0-.55-.45-1-1-1H5.21l-.94-2H1z"/>
                </svg>
                {totalQty > 0 && (
                  <div style={{
                    position: 'absolute',
                    top: -5,
                    right: -7,
                    background: '#a8e063',
                    color: '#0a0a0a',
                    fontSize: 9,
                    fontWeight: 800,
                    width: 15,
                    height: 15,
                    borderRadius: 8,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    {totalQty}
                  </div>
                )}
              </div>
              <span style={{ fontSize: 10, fontWeight: 400, letterSpacing: '0.02em' }}>Cart</span>
            </button>
          )
        })()}

        {/* Account */}
        <button
          onClick={() => handleTabChange('account')}
          style={{
            flex: 1,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 3,
            color: activeTab === 'account' ? '#a8e063' : '#555',
            padding: '0 4px',
            height: '100%',
            transition: 'color 0.15s',
            borderRadius: 16,
          }}
        >
          <svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
          </svg>
          <span style={{ fontSize: 10, fontWeight: activeTab === 'account' ? 700 : 400, letterSpacing: '0.02em' }}>Account</span>
        </button>
      </div>
    </div>
  )
}
