import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { navBtnStyle, selectStyle, type Column } from './components/AdminTable'
import api from './api/client'
import supabase from './utils/supabase'
import { rememberNext } from './utils/redirect'
import type { Partner, PartnerPortalDetail, PartnerPosOrder } from './types'
import { primaryBtn } from './utils/partners'
import { Banner, ConnectionCard, LocationsTable, OrdersTable, Section, muted, page, wrap } from './components/partnerUi'

/**
 * The partner's own dashboard: /partner and /partner/:partnerId.
 *
 * A partner signs in with Google. The API only lets them in if an admin added
 * that Google email under the partner's "Partner logins". Once in, they connect,
 * reconnect, pause or disconnect their Square account and see the orders it
 * sends. Orders say whether the shopper was a Terpee member, never who.
 *
 * Square's OAuth sends the browser back to /partner?pos=connected&partner_id=…
 * (or ?pos=error&reason=…), which this page turns into a banner.
 */
export default function PartnerPortal() {
  const [session, setSession] = useState<Session | null | undefined>(undefined)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  if (session === undefined) return <Shell><div style={muted}>Loading…</div></Shell>
  if (!session) return <SignIn />
  return <Portal />
}

/* ── Signed out ────────────────────────────────────────────────────────────── */

function SignIn() {
  const [params] = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function google() {
    setLoading(true)
    setError(null)
    // OAuth leaves the app; AuthCallback reads this to come back here.
    rememberNext(`/partner${params.toString() ? `?${params}` : ''}`)
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    })
    if (error) {
      setLoading(false)
      setError(error.message)
    }
  }

  return (
    <Shell>
      <div style={{ maxWidth: 420, margin: '12vh auto 0', textAlign: 'center' }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.3em', textTransform: 'uppercase', color: '#334155', marginBottom: 28 }}>
          terpee for partners
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 600, margin: '0 0 10px' }}>Partner dashboard</h1>
        <p style={{ ...muted, margin: '0 0 28px' }}>
          Connect your point of sale so your customers earn Terpee points when they shop with you.
        </p>
        <button
          onClick={google}
          disabled={loading}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 10, padding: '11px 20px', borderRadius: 8,
            background: '#f8fafc', color: '#0f172a', border: 'none', fontSize: 14, fontWeight: 500,
            cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.7 : 1,
          }}
        >
          <GoogleMark /> {loading ? 'Opening Google…' : 'Continue with Google'}
        </button>
        {error && <div style={{ color: '#fca5a5', fontSize: 13, marginTop: 16 }}>{error}</div>}
        <p style={{ ...muted, fontSize: 12, marginTop: 28 }}>
          Use the Google account Terpee invited. Need access? Contact your Terpee rep.
        </p>
      </div>
    </Shell>
  )
}

/* ── Signed in ─────────────────────────────────────────────────────────────── */

function Portal() {
  const { partnerId } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [me, setMe] = useState<{ email: string | null; partners: Partner[] } | null>(null)
  const [error, setError] = useState<string | null>(null)

  // After Square, the callback names the partner it connected.
  const returnedPartner = params.get('partner_id')
  const selected = partnerId ?? returnedPartner ?? me?.partners[0]?.id

  useEffect(() => {
    api.partnerPortal.me().then(setMe).catch(err => setError(err.message))
  }, [])

  async function signOut() {
    await supabase.auth.signOut()
    navigate('/partner', { replace: true })
  }

  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.3em', textTransform: 'uppercase', color: '#334155' }}>
        terpee for partners
      </div>
      {me && me.partners.length > 1 && selected && (
        <select
          value={selected}
          onChange={e => navigate(`/partner/${e.target.value}`)}
          style={selectStyle}
          aria-label="Partner"
        >
          {me.partners.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      )}
      <span style={{ marginLeft: 'auto', color: '#64748b', fontSize: 13 }}>{me?.email}</span>
      <button onClick={signOut} style={navBtnStyle}>Sign out</button>
    </div>
  )

  if (error) return <Shell>{header}<Banner tone="error" onClose={() => setError(null)}>{error}</Banner></Shell>
  if (!me) return <Shell>{header}<div style={muted}>Loading…</div></Shell>

  if (me.partners.length === 0) {
    return (
      <Shell>
        {header}
        <div style={{ maxWidth: 520, margin: '8vh auto 0', textAlign: 'center' }}>
          <h2 style={{ fontSize: 18, fontWeight: 600 }}>This Google account isn't linked to a partner</h2>
          <p style={muted}>
            You're signed in as <b style={{ color: '#cbd5e1' }}>{me.email ?? 'an account without an email'}</b>.
            Ask your Terpee rep to add this address to your store, or sign out and use the account they invited.
          </p>
        </div>
      </Shell>
    )
  }

  return (
    <Shell>
      {header}
      {selected && (
        <Dashboard
          key={selected}
          partnerId={selected}
          pos={params.get('pos')}
          reason={params.get('reason')}
          clearPos={() => {
            params.delete('pos'); params.delete('reason'); params.delete('partner_id'); params.delete('connection_id')
            setParams(params, { replace: true })
          }}
        />
      )}
    </Shell>
  )
}

function Dashboard({ partnerId, pos, reason, clearPos }: {
  partnerId: string
  pos: string | null
  reason: string | null
  clearPos: () => void
}) {
  const [partner, setPartner] = useState<PartnerPortalDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => { load() }, [partnerId])

  async function load() {
    try {
      setPartner(await api.partnerPortal.get(partnerId))
    } catch (err: any) {
      setError(err.message)
    }
  }

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label)
    setError(null)
    try {
      await fn()
      await load()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  async function connectSquare() {
    setBusy('connect')
    setError(null)
    try {
      const { authorize_url } = await api.partnerPortal.startOAuth(partnerId)
      window.location.href = authorize_url
    } catch (err: any) {
      setError(err.message)
      setBusy(null)
    }
  }

  const banners = (
    <>
      {pos === 'connected' && (
        <Banner tone="ok" onClose={clearPos}>
          Square is connected. Your last 7 days of orders will come in within 15 minutes.
        </Banner>
      )}
      {pos === 'error' && (
        <Banner tone="error" onClose={clearPos}>
          Square didn't connect{reason ? `: ${reason}` : '.'} You can try again below.
        </Banner>
      )}
      {error && <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>}
    </>
  )

  if (!partner) return <>{banners}{!error && <div style={muted}>Loading…</div>}</>

  const live = partner.connections.filter(c => c.status !== 'revoked')
  const wasConnected = partner.connections.some(c => c.status === 'revoked')

  return (
    <>
      <h2 style={{ margin: '0 0 20px', fontSize: 22, fontWeight: 600 }}>{partner.name}</h2>
      {banners}

      <Section
        title="Point of sale"
        action={live.length === 0 && (
          <button onClick={connectSquare} disabled={busy !== null} style={primaryBtn(busy !== null)}>
            {busy === 'connect' ? 'Opening Square…' : wasConnected ? 'Reconnect Square' : 'Connect Square'}
          </button>
        )}
      >
        {live.length === 0 ? (
          <div style={muted}>
            {wasConnected
              ? 'Your Square account is disconnected, so new purchases aren\'t earning points. Reconnect to pick up where you left off.'
              : 'Connect your Square account so purchases by Terpee members earn them points. Terpee only asks to read orders, customers and locations — it can\'t take payments or change anything in Square.'}
          </div>
        ) : (
          live.map(c => (
            <ConnectionCard
              key={c.id}
              connection={c}
              busy={busy}
              loadRuns={id => api.partnerPortal.runs(partnerId, id)}
              onPause={() => act('pause', () => api.partnerPortal.setConnectionStatus(partnerId, c.id, 'disabled'))}
              onResume={() => act('resume', () => api.partnerPortal.setConnectionStatus(partnerId, c.id, 'active'))}
              onReconnect={connectSquare}
              onDisconnect={() => {
                if (window.confirm('Disconnect your Square account? Purchases will stop earning your customers points until you reconnect.')) {
                  act('disconnect', () => api.partnerPortal.disconnect(partnerId, c.id))
                }
              }}
            />
          ))
        )}
      </Section>

      <Section title="Locations">
        {partner.locations.length === 0 ? (
          <div style={muted}>Your Square locations appear here once you connect.</div>
        ) : (
          <>
            <LocationsTable locations={partner.locations} />
            <div style={{ ...muted, fontSize: 12, marginTop: 8 }}>
              To change which locations earn points, contact your Terpee rep.
            </div>
          </>
        )}
      </Section>

      <Section title="Orders">
        <OrdersTable<PartnerPosOrder>
          reloadKey={partnerId}
          locations={partner.locations}
          load={q => api.partnerPortal.orders(partnerId, { members_only: q.filter || undefined, limit: q.limit, offset: q.offset })}
          filterLabel="Terpee members only"
          filterEmpty="No orders from Terpee members yet."
          customerColumn={{
            key: 'member', header: 'Terpee member',
            render: o => o.is_member
              ? <span style={{ color: '#86efac' }}>yes</span>
              : <span style={{ color: '#475569' }}>—</span>,
          } satisfies Column<PartnerPosOrder>}
        />
      </Section>
    </>
  )
}

/* ── Bits ──────────────────────────────────────────────────────────────────── */

function Shell({ children }: { children: React.ReactNode }) {
  return <div style={page}><div style={wrap}>{children}</div></div>
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.9 6.1C12.5 13.6 17.8 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.1 24.6c0-1.6-.1-3.1-.4-4.6H24v9.1h12.4c-.5 2.9-2.2 5.3-4.6 6.9l7.4 5.8c4.3-4 6.9-9.9 6.9-17.2z" />
      <path fill="#FBBC05" d="M10.6 28.6c-.5-1.4-.8-2.9-.8-4.6s.3-3.2.8-4.6l-7.9-6.1C1 16.6 0 20.2 0 24s1 7.4 2.7 10.7l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.8c-2.1 1.4-4.8 2.3-8.5 2.3-6.2 0-11.5-4.2-13.4-9.9l-7.9 6.1C6.6 42.6 14.6 48 24 48z" />
    </svg>
  )
}
