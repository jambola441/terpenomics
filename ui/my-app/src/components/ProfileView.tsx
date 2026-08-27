/* ============================================================================
   ProfileView — everything the portal knows about the shopper.

   Three things that all answer "what about me?" and were previously scattered:
   the pickup orders they have open, the taste feedback they have left on past
   purchases (which is what the recommender reads), and the account details
   themselves. They live behind one tab bar rather than three nav entries,
   because a shopper visits this section rarely and with a specific errand.
   ========================================================================== */

import { useEffect, useState } from 'react'
import api from '../api/client'
import type {
  CustomerProfile, Feedback, Order, PortalPurchase, PortalDispensary,
} from '../types'
import type { Session } from '@supabase/supabase-js'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { FeedState, ProductImage, Label } from './ui'
import OrderCard from './OrderCard'
import { formatDate, formatDollars } from '../utils/format'

type Pane = 'orders' | 'feedback' | 'profile'

const PANES: { key: Pane; label: string }[] = [
  { key: 'orders', label: 'Orders' },
  { key: 'feedback', label: 'Feedback' },
  { key: 'profile', label: 'Profile' },
]

interface Props {
  session: Session
  customerId: string
  orders: Order[]
  ordersLoading: boolean
  ordersError: string | null
  onCancelOrder: (orderId: string) => void
  cancellingIds: Set<string>
  onSignOut: () => void
}

export default function ProfileView({
  session, customerId, orders, ordersLoading, ordersError,
  onCancelOrder, cancellingIds, onSignOut,
}: Props) {
  const [pane, setPane] = useState<Pane>('orders')
  const [profile, setProfile] = useState<CustomerProfile | null>(null)

  useEffect(() => {
    api.me.getProfile().then(setProfile).catch(() => setProfile(null))
  }, [])

  const openOrders = orders.filter(o => o.status === 'submitted' || o.status === 'ready').length

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>
      {/* Identity */}
      <div style={{ padding: '28px 20px 0', display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{
          width: 56, height: 56, borderRadius: '50%', flexShrink: 0,
          background: t.surface2, border: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: t.accent, fontWeight: font.weight.heavy, fontSize: 22,
        }}>
          {(profile?.name ?? session.user.email ?? session.user.phone ?? '?').charAt(0).toUpperCase()}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{
            color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title,
            letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {profile?.name || 'Your account'}
          </div>
          <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
            {profile?.phone ?? session.user.phone ?? profile?.email ?? session.user.email}
          </div>
        </div>
      </div>

      {/* Pane switcher */}
      <div style={{ display: 'flex', gap: 6, padding: '20px 16px 0' }}>
        {PANES.map(p => (
          <button
            key={p.key}
            onClick={() => setPane(p.key)}
            style={{
              flex: 1, cursor: 'pointer',
              background: pane === p.key ? alpha(t.accent, 0.14) : t.surface2,
              border: `1px solid ${pane === p.key ? t.accent : t.border}`,
              borderRadius: radius.pill, padding: '9px 0',
              color: pane === p.key ? t.accent : t.text3,
              fontSize: font.size.small, fontWeight: pane === p.key ? font.weight.bold : font.weight.medium,
              transition: 'all var(--t-fast)',
            }}
          >
            {p.label}
            {p.key === 'orders' && openOrders > 0 ? ` · ${openOrders}` : ''}
          </button>
        ))}
      </div>

      <div style={{ padding: '18px 16px 28px', maxWidth: 560, margin: '0 auto' }}>
        {pane === 'orders' && (
          <OrdersPane
            orders={orders}
            loading={ordersLoading}
            error={ordersError}
            onCancelOrder={onCancelOrder}
            cancellingIds={cancellingIds}
          />
        )}
        {pane === 'feedback' && <FeedbackPane customerId={customerId} />}
        {pane === 'profile' && (
          <ProfilePane
            profile={profile}
            session={session}
            onSaved={setProfile}
            onSignOut={onSignOut}
          />
        )}
      </div>
    </div>
  )
}

/* ── Orders ────────────────────────────────────────────────────────────────── */

function OrdersPane({ orders, loading, error, onCancelOrder, cancellingIds }: {
  orders: Order[]
  loading: boolean
  error: string | null
  onCancelOrder: (orderId: string) => void
  cancellingIds: Set<string>
}) {
  if (loading) return <FeedState kind="loading" message="Loading your orders…" />
  if (error) return <FeedState kind="error" message={error} />
  if (orders.length === 0) {
    return (
      <FeedState
        kind="empty"
        message="No orders yet"
        hint="Orders you place for pickup show up here with their pickup code."
        icon="🛍️"
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {orders.map(order => (
        <OrderCard
          key={order.id}
          order={order}
          onCancel={onCancelOrder}
          cancelling={cancellingIds.has(order.id)}
        />
      ))}
    </div>
  )
}

/* ── Feedback ──────────────────────────────────────────────────────────────── */

/** Rating a past purchase is the only signal the recommender has, so this pane
 *  exists to make the un-rated items easy to find and one tap to clear. */
function FeedbackPane({ customerId }: { customerId: string }) {
  const [purchases, setPurchases] = useState<PortalPurchase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<Record<string, Feedback>>({})
  const [saving, setSaving] = useState<Set<string>>(new Set())

  useEffect(() => {
    api.portal.getPurchases(customerId)
      .then(data => {
        setPurchases(data)
        const initial: Record<string, Feedback> = {}
        data.forEach(p => p.items.forEach(item => {
          if (item.feedback !== undefined) initial[item.id] = item.feedback ?? null
        }))
        setFeedback(initial)
      })
      .catch(() => setError('Could not load your purchases.'))
  }, [customerId])

  async function rate(itemId: string, value: Feedback) {
    const previous = feedback[itemId] ?? null
    setFeedback(prev => ({ ...prev, [itemId]: value }))
    setSaving(prev => new Set(prev).add(itemId))
    try {
      await api.portal.setFeedback(customerId, itemId, value)
    } catch {
      setFeedback(prev => ({ ...prev, [itemId]: previous }))
    } finally {
      setSaving(prev => {
        const next = new Set(prev)
        next.delete(itemId)
        return next
      })
    }
  }

  if (error) return <FeedState kind="error" message={error} />
  if (purchases === null) return <FeedState kind="loading" message="Loading your purchases…" />
  if (purchases.length === 0) {
    return (
      <FeedState
        kind="empty"
        message="Nothing to rate yet"
        hint="Once you've bought something, rate it here and your recommendations start to fit."
        icon="👍"
      />
    )
  }

  const items = purchases.flatMap(p => p.items)
  const rated = items.filter(item => (feedback[item.id] ?? null) !== null).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ color: t.text3, fontSize: font.size.small, lineHeight: 1.5 }}>
        {rated} of {items.length} rated. Ratings feed your recommendations — a 👎 is as
        useful as a 👍.
      </div>

      {purchases.map(purchase => (
        <div key={purchase.id}>
          <div style={{
            display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
            gap: 12, marginBottom: 10,
          }}>
            <Label>{formatDate(purchase.purchased_at)}</Label>
            <span style={{ color: t.text3, fontSize: font.size.small }}>
              {purchase.total_amount_cents ? formatDollars(purchase.total_amount_cents) : '—'}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {purchase.items.map(item => {
              const current = feedback[item.id] ?? item.feedback ?? null
              const isSaving = saving.has(item.id)
              const color = categoryColor(item.product_category)

              return (
                <div
                  key={item.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: 12,
                    background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg,
                  }}
                >
                  <ProductImage
                    category={item.product_category}
                    height={48}
                    style={{ width: 48, flexShrink: 0, borderRadius: radius.sm }}
                    pad={6}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small + 1,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>
                      {item.product_name}
                    </div>
                    <div style={{
                      color, fontSize: font.size.caption, fontWeight: font.weight.semibold,
                      textTransform: 'capitalize', marginTop: 2,
                    }}>
                      {item.product_category}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 5, flexShrink: 0 }}>
                    {RATINGS.map(({ value, glyph, color: ratingColor }) => {
                      const active = current === value
                      return (
                        <button
                          key={value}
                          disabled={isSaving}
                          onClick={() => rate(item.id, active ? null : value)}
                          aria-label={value}
                          style={{
                            cursor: isSaving ? 'default' : 'pointer',
                            opacity: isSaving ? 0.5 : 1,
                            background: active ? alpha(ratingColor, 0.18) : t.surface2,
                            border: `1px solid ${active ? ratingColor : t.border}`,
                            borderRadius: radius.md, padding: '6px 9px', fontSize: 14,
                            transition: 'all var(--t-fast)',
                          }}
                        >
                          {glyph}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

const RATINGS: { value: Exclude<Feedback, null>; glyph: string; color: string }[] = [
  { value: 'like', glyph: '👍', color: 'var(--accent)' },
  { value: 'neutral', glyph: '😑', color: 'var(--text-3)' },
  { value: 'dislike', glyph: '👎', color: 'var(--danger)' },
]

/* ── Profile ───────────────────────────────────────────────────────────────── */

function ProfilePane({ profile, session, onSaved, onSignOut }: {
  profile: CustomerProfile | null
  session: Session
  onSaved: (profile: CustomerProfile) => void
  onSignOut: () => void
}) {
  const [name, setName] = useState('')
  const [optIn, setOptIn] = useState(false)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [stores, setStores] = useState<PortalDispensary[] | null>(null)

  useEffect(() => {
    if (!profile) return
    setName(profile.name ?? '')
    setOptIn(profile.marketing_opt_in)
  }, [profile])

  useEffect(() => {
    api.me.listPreferredDispensaries().then(setStores).catch(() => setStores([]))
  }, [])

  const dirty = profile != null
    && (name.trim() !== (profile.name ?? '') || optIn !== profile.marketing_opt_in)

  async function save() {
    setSaving(true)
    setStatus(null)
    try {
      const updated = await api.me.updateProfile({ name: name.trim(), marketing_opt_in: optIn })
      onSaved(updated)
      setStatus('Saved')
    } catch {
      setStatus('Could not save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  if (!profile) return <FeedState kind="loading" message="Loading your profile…" />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <div>
        <Label>Name</Label>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="What should we call you?"
          style={{
            width: '100%', boxSizing: 'border-box', marginTop: 8,
            background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.lg,
            color: t.text1, fontSize: font.size.body, padding: '12px 14px', outline: 'none',
          }}
        />
      </div>

      {/* Identity, shown but not editable: these are how sign-in and in-store
          purchase matching find this account. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <ReadOnlyRow label="Phone" value={profile.phone ?? session.user.phone ?? '—'} />
        <ReadOnlyRow label="Email" value={profile.email ?? session.user.email ?? '—'} />
        <div style={{ color: t.text4, fontSize: font.size.caption, lineHeight: 1.5 }}>
          Phone and email identify your account at sign-in and at the counter. Ask a staff
          member to change either.
        </div>
      </div>

      <label style={{
        display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer',
        background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: 14,
      }}>
        <input
          type="checkbox"
          checked={optIn}
          onChange={e => setOptIn(e.target.checked)}
          style={{ width: 18, height: 18, marginTop: 1, accentColor: 'var(--accent)', flexShrink: 0 }}
        />
        <span>
          <span style={{ color: t.text1, fontSize: font.size.body, fontWeight: font.weight.semibold }}>
            Deal alerts
          </span>
          <span style={{ display: 'block', color: t.text3, fontSize: font.size.small, marginTop: 3, lineHeight: 1.5 }}>
            Occasional texts about drops and discounts at the stores you follow.
          </span>
        </span>
      </label>

      <div>
        <Label>Stores you follow</Label>
        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 8, lineHeight: 1.5 }}>
          {stores === null
            ? 'Loading…'
            : stores.length === 0
              ? 'None yet — pick some on the home tab to build your feed.'
              : stores.map(s => s.name).join(' · ')}
        </div>
      </div>

      <div>
        <button
          onClick={save}
          disabled={!dirty || saving}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: dirty && !saving ? t.accent : t.surface2,
            border: 'none', borderRadius: radius.lg,
            color: dirty && !saving ? t.accentInk : t.text3,
            fontWeight: font.weight.bold, fontSize: font.size.callout,
            padding: 13, cursor: dirty && !saving ? 'pointer' : 'default',
          }}
        >
          {saving ? 'Saving…' : 'Save changes'}
        </button>
        {status && (
          <div style={{ color: t.text3, fontSize: font.size.small, textAlign: 'center', marginTop: 10 }}>
            {status}
          </div>
        )}
      </div>

      <button
        onClick={onSignOut}
        style={{
          margin: '0 auto', background: 'transparent', border: `1px solid ${t.border}`,
          borderRadius: radius.lg, color: t.danger,
          fontSize: font.size.callout, fontWeight: font.weight.semibold,
          padding: '12px 32px', cursor: 'pointer',
        }}
      >
        Sign out
      </button>
    </div>
  )
}

function ReadOnlyRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
      background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg,
      padding: '12px 14px',
    }}>
      <span style={{ color: t.text3, fontSize: font.size.small }}>{label}</span>
      <span style={{
        color: t.text2, fontSize: font.size.small, minWidth: 0,
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {value}
      </span>
    </div>
  )
}
