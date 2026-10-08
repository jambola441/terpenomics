/* ============================================================================
   ProfileView — everything the portal knows about the shopper.

   Three things that all answer "what about me?" and were previously scattered:
   the pickup orders they have open, the taste feedback they have left on past
   purchases (which is what the recommender reads), and the account details
   themselves. They live behind one tab bar rather than three nav entries,
   because a shopper visits this section rarely and with a specific errand.
   ========================================================================== */

import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import api from '../api/client'
import type {
  CustomerProfile, Feedback, Order, PointsSummary, PortalPurchase, PortalDispensary,
} from '../types'
import type { Session } from '@supabase/auth-js'
import { t, radius, font, categoryColor, categoryLabel } from '../theme'
import { FeedState, ProductImage, Label } from './ui'
import { Icon, type IconName } from './Icon'
import OrderCard from './OrderCard'
import ReceiptUpload from './ReceiptUpload'
import EmailEditor from './EmailEditor'
import { formatDate, formatDollars } from '../utils/format'

type Pane = 'orders' | 'points' | 'feedback' | 'profile'

const PANES: { key: Pane; label: string }[] = [
  { key: 'orders', label: 'Orders' },
  { key: 'points', label: 'Points' },
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
  /** A failed cancel, by order id. Shown on that order's card only. */
  cancelErrors: Record<string, string>
  onSignOut: () => void
}

export default function ProfileView({
  session, customerId, orders, ordersLoading, ordersError,
  onCancelOrder, cancellingIds, cancelErrors, onSignOut,
}: Props) {
  // The pane is in the URL (/portal/profile/points), so a link can open one.
  const navigate = useNavigate()
  const segment = useLocation().pathname.split('/')[3]
  const pane: Pane = PANES.some(p => p.key === segment) ? segment as Pane : 'orders'
  const setPane = (next: Pane) => navigate(`/portal/profile/${next}`, { replace: true })
  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [points, setPoints] = useState<PointsSummary | null>(null)
  const [pointsError, setPointsError] = useState<string | null>(null)

  function loadPoints() {
    api.me.getPoints().then(setPoints).catch(err => setPointsError(err.message))
  }

  useEffect(() => {
    api.me.getProfile().then(setProfile).catch(() => setProfile(null))
    loadPoints()
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
          color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold, fontSize: 24,
        }}>
          {(profile?.name ?? session.user.email ?? session.user.phone ?? '?').charAt(0).toUpperCase()}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{
            color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold, fontSize: font.size.display,
            letterSpacing: '-0.02em', lineHeight: 1.15, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {profile?.name || 'Your account'}
          </div>
          <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
            {profile?.phone ?? session.user.phone ?? profile?.email ?? session.user.email}
          </div>
        </div>
        {points && (
          <button
            onClick={() => setPane('points')}
            aria-label={`${points.available} Terpee points`}
            style={{
              flexShrink: 0, cursor: 'pointer', padding: '7px 12px 7px 10px', borderRadius: radius.pill,
              background: t.accentTint, border: `1px solid ${t.accentDim}`,
              color: t.accent, fontWeight: font.weight.bold, fontSize: font.size.callout,
              display: 'inline-flex', alignItems: 'center', gap: 5,
            }}
          >
            <Icon name="drop" size={15} strokeWidth={2} />
            <span className="num">{points.available.toLocaleString()}</span>
            <span style={{ fontFamily: font.family.mono, fontWeight: font.weight.medium, fontSize: font.size.caption }}>pts</span>
          </button>
        )}
      </div>

      {/* Pane switcher */}
      <div role="tablist" style={{
        display: 'flex', gap: 2, margin: '22px 16px 0', padding: 3,
        background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.md,
      }}>
        {PANES.map(p => (
          <button
            key={p.key}
            role="tab"
            aria-selected={pane === p.key}
            onClick={() => setPane(p.key)}
            style={{
              flex: 1, cursor: 'pointer',
              background: pane === p.key ? t.surface3 : 'transparent',
              border: 'none', boxShadow: pane === p.key ? 'var(--e-1)' : 'none',
              borderRadius: radius.sm, padding: '8px 0',
              color: pane === p.key ? t.text1 : t.text3,
              fontSize: font.size.small + 1, fontWeight: pane === p.key ? font.weight.semibold : font.weight.medium,
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
            cancelErrors={cancelErrors}
          />
        )}
        {pane === 'points' && <PointsPane data={points} error={pointsError} onUploaded={loadPoints} />}
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

function OrdersPane({ orders, loading, error, onCancelOrder, cancellingIds, cancelErrors }: {
  orders: Order[]
  loading: boolean
  /** Loading the list failed. A failed cancel is per card, not this. */
  error: string | null
  onCancelOrder: (orderId: string) => void
  cancellingIds: Set<string>
  cancelErrors: Record<string, string>
}) {
  if (loading) return <FeedState kind="loading" message="Loading your orders…" />
  if (error) return <FeedState kind="error" message={error} />
  if (orders.length === 0) {
    return (
      <FeedState
        kind="empty"
        message="No orders yet"
        hint="Orders you place for pickup show up here with their pickup code."
        icon="bag"
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
          cancelError={cancelErrors[order.id] ?? null}
        />
      ))}
    </div>
  )
}

/* ── Points ────────────────────────────────────────────────────────────────── */

const POINTS_KIND: Record<string, string> = { earn: 'Earned', receipt: 'Receipt', refund: 'Refunded', adjust: 'Adjusted' }

/** Terpee points from shopping at partner stores. Earned points sit as pending
 *  for a week (so a return can cancel them) and then become available. */
function PointsPane({ data, error, onUploaded }: {
  data: PointsSummary | null
  error: string | null
  onUploaded: () => void
}) {
  if (error) return <FeedState kind="error" message="Couldn't load your points" hint={error} />
  if (!data) return <FeedState kind="loading" message="Loading your points…" />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{
        background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg,
        padding: '18px 20px', display: 'flex', alignItems: 'flex-end', gap: 24,
      }}>
        <div>
          <Label>Available</Label>
          <div className="num" style={{ color: t.accent, fontSize: 36, fontWeight: font.weight.bold, lineHeight: 1.1, marginTop: 4, letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="drop" size={24} strokeWidth={1.75} />
            {data.available.toLocaleString()}
          </div>
        </div>
        <div style={{ paddingBottom: 4 }}>
          <Label>Pending</Label>
          <div className="num" style={{ color: t.text2, fontSize: font.size.title, fontWeight: font.weight.bold, marginTop: 4 }}>
            {data.pending.toLocaleString()}
          </div>
        </div>
      </div>
      <div style={{ color: t.text3, fontSize: font.size.small, lineHeight: 1.5 }}>
        Earn {data.points_per_dollar === 1 ? '1 point' : `${data.points_per_dollar} points`} per dollar
        (before tax and tip) when you shop at Terpee partner stores with your phone number on the
        receipt. Points become available {data.pending_days} days after your purchase.
      </div>

      <ReceiptUpload onUploaded={onUploaded} />

      {data.entries.length === 0 ? (
        <FeedState
          kind="empty"
          message="No points yet"
          hint="Shop at a Terpee partner store and give them your phone number at checkout."
          icon="drop"
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {data.entries.map(e => (
            <div key={e.id} style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '12px 2px',
              borderBottom: `1px solid ${t.border}`,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: t.text1, fontSize: font.size.callout, fontWeight: font.weight.semibold }}>
                  {e.partner_name ?? 'Terpee'}
                </div>
                <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
                  {POINTS_KIND[e.kind] ?? e.kind} · {formatDate(e.created_at)}
                  {e.pending && e.points > 0 ? ` · available ${formatDate(e.available_at)}` : ''}
                </div>
              </div>
              <div className="num" style={{
                fontFamily: font.family.mono, fontWeight: font.weight.medium, fontSize: font.size.callout,
                color: e.points < 0 ? t.danger : e.pending ? t.text3 : t.success,
              }}>
                {e.points > 0 ? '+' : ''}{e.points.toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      )}
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
        icon="thumbs-up"
      />
    )
  }

  const items = purchases.flatMap(p => p.items)
  const rated = items.filter(item => (feedback[item.id] ?? null) !== null).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ color: t.text3, fontSize: font.size.small, lineHeight: 1.5 }}>
        {rated} of {items.length} rated. Ratings feed your recommendations — a thumbs-down
        is as useful as a thumbs-up.
      </div>

      {purchases.map(purchase => (
        <div key={purchase.id}>
          <div style={{
            display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
            gap: 12, marginBottom: 10,
          }}>
            <Label>{formatDate(purchase.purchased_at)}</Label>
            <span className="num" style={{ color: t.text2, fontFamily: font.family.mono, fontSize: font.size.small }}>
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
                      color, fontFamily: font.family.mono, fontSize: font.size.caption,
                      textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 3,
                    }}>
                      {categoryLabel(item.product_category)}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 5, flexShrink: 0 }}>
                    {RATINGS.map(({ value, icon, color: ratingColor }) => {
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
                            background: active ? `color-mix(in srgb, ${ratingColor} 14%, transparent)` : t.surface2,
                            border: `1px solid ${active ? ratingColor : t.border}`,
                            color: active ? ratingColor : t.text3,
                            borderRadius: radius.md, width: 36, height: 34, padding: 0,
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            transition: 'all var(--t-fast)',
                          }}
                        >
                          <Icon name={icon} size={17} />
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

const RATINGS: { value: Exclude<Feedback, null>; icon: IconName; color: string }[] = [
  { value: 'like', icon: 'thumbs-up', color: 'var(--success)' },
  { value: 'neutral', icon: 'face-neutral', color: 'var(--text-2)' },
  { value: 'dislike', icon: 'thumbs-down', color: 'var(--danger)' },
]

/* ── Profile ───────────────────────────────────────────────────────────────── */

function ProfilePane({ profile, session, onSaved, onSignOut }: {
  profile: CustomerProfile | null
  session: Session
  onSaved: (profile: CustomerProfile) => void
  onSignOut: () => void
}) {
  const [first, setFirst] = useState('')
  const [last, setLast] = useState('')
  const [optIn, setOptIn] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [stores, setStores] = useState<PortalDispensary[] | null>(null)

  useEffect(() => {
    if (!profile) return
    setFirst(profile.first_name ?? '')
    setLast(profile.last_name ?? '')
    setOptIn(profile.marketing_opt_in)
  }, [profile])

  useEffect(() => {
    api.me.listPreferredDispensaries().then(setStores).catch(() => setStores([]))
  }, [])

  const namesChanged = profile != null
    && (first.trim() !== (profile.first_name ?? '') || last.trim() !== (profile.last_name ?? ''))
  const dirty = profile != null && (namesChanged || optIn !== profile.marketing_opt_in)

  async function deleteAccount() {
    const ok = confirm(
      'Delete your account?\n\nThis signs you out everywhere, cancels open pickup orders, and forfeits '
      + 'your points. Your name, phone number and receipt photos are erased. This cannot be undone.',
    )
    if (!ok) return
    setDeleting(true)
    try {
      await api.me.deleteAccount()
      onSignOut()
    } catch (err) {
      setStatus(err instanceof Error && err.message ? err.message : 'Could not delete your account. Try again.')
      setDeleting(false)
    }
  }

  async function save() {
    setSaving(true)
    setStatus(null)
    try {
      const updated = await api.me.updateProfile({
        ...(namesChanged ? { first_name: first.trim(), last_name: last.trim() } : {}),
        marketing_opt_in: optIn,
        // Opting in records consent to the disclosure shown beside the box.
        marketing_sms_version: profile!.onboarding.disclosures.marketing_sms.version,
        platform: 'web',
      })
      onSaved(updated)
      setStatus('Saved')
    } catch (err) {
      setStatus(err instanceof Error && err.message ? err.message : 'Could not save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  if (!profile) return <FeedState kind="loading" message="Loading your profile…" />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <div style={{ display: 'flex', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Label>First name</Label>
          <input
            value={first}
            onChange={e => setFirst(e.target.value)}
            autoComplete="given-name"
            maxLength={100}
            style={nameInputStyle}
          />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Label>Last name</Label>
          <input
            value={last}
            onChange={e => setLast(e.target.value)}
            autoComplete="family-name"
            maxLength={100}
            placeholder="Optional"
            style={nameInputStyle}
          />
        </div>
      </div>

      {/* Phone is shown but not editable: it is how sign-in and in-store
          purchase matching find this account. Email is contact only, and
          changes after a code sent to the new address. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <ReadOnlyRow label="Phone" value={profile.phone ?? session.user.phone ?? '—'} />
        <div style={{ color: t.text3, fontSize: font.size.caption, lineHeight: 1.5 }}>
          Your phone number is how you sign in and how stores match your purchases. Ask a
          staff member to change it.
        </div>
        <EmailEditor profile={profile} onSaved={onSaved} />
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
            Deal alerts by text
          </span>
          <span style={{ display: 'block', color: t.text3, fontSize: font.size.small, marginTop: 3, lineHeight: 1.5 }}>
            {profile.onboarding.disclosures.marketing_sms.text}
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
          disabled={!dirty || saving || (namesChanged && !first.trim())}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: dirty && !saving ? t.accent : t.surface2,
            border: 'none', borderRadius: radius.md,
            color: dirty && !saving ? t.accentInk : t.text4,
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
          margin: '0 auto', background: 'transparent', border: `1px solid ${t.borderStrong}`,
          borderRadius: radius.md, color: t.text1,
          fontSize: font.size.callout, fontWeight: font.weight.semibold,
          padding: '11px 24px', cursor: 'pointer',
          display: 'inline-flex', alignItems: 'center', gap: 8,
        }}
      >
        <Icon name="log-out" size={17} color={t.text3} />
        Sign out
      </button>

      <button
        onClick={deleteAccount}
        disabled={deleting}
        style={{
          margin: '0 auto', background: 'transparent', border: 'none',
          color: t.danger, fontSize: font.size.small, textDecoration: 'underline', textUnderlineOffset: 3,
          padding: 8, cursor: deleting ? 'default' : 'pointer',
        }}
      >
        {deleting ? 'Deleting…' : 'Delete account'}
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

const nameInputStyle = {
  width: '100%', boxSizing: 'border-box', marginTop: 8,
  background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.md,
  color: t.text1, fontSize: font.size.body, padding: '12px 14px', outline: 'none',
} as const
