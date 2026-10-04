import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { navBtnStyle, type Column } from './components/AdminTable'
import api from './api/client'
import type { PartnerDetail as Detail, PartnerMember, PosOrder } from './types'
import { inputStyle, primaryBtn, when } from './utils/partners'
import { Banner, ConnectionCard, LocationsTable, OrdersTable, Section, muted, page, wrap } from './components/partnerUi'

/**
 * One partner: connect their POS, watch the sync, see what came in.
 *
 * Connecting is OAuth. "Connect Square" asks the API for Square's consent URL
 * and sends the browser there; whoever signs in approves with the partner's
 * Square account, and Square sends them back to /admin/partners, which
 * forwards here with ?pos=connected.
 *
 * There is deliberately no "sync now" button: scripts/pos_sync.py runs every
 * 15 minutes, and the runs table below is its log.
 */
export default function PartnerDetail() {
  const { partnerId = '' } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [partner, setPartner] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [editingName, setEditingName] = useState<string | null>(null)

  const justConnected = params.get('pos') === 'connected'

  useEffect(() => { load() }, [partnerId])

  async function load() {
    setError(null)
    try {
      setPartner(await api.partners.get(partnerId))
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
      const { authorize_url } = await api.partners.startOAuth('square', partnerId)
      window.location.href = authorize_url
    } catch (err: any) {
      setError(err.message)
      setBusy(null)
    }
  }

  if (!partner) {
    return (
      <div style={page}>
        <div style={wrap}>
          <button onClick={() => navigate('/admin/partners')} style={navBtnStyle}>← Partners</button>
          <div style={{ color: error ? '#f87171' : '#475569', padding: 16 }}>{error ? `Error: ${error}` : 'Loading…'}</div>
        </div>
      </div>
    )
  }

  const live = partner.connections.filter(c => c.status !== 'revoked')
  const revoked = partner.connections.filter(c => c.status === 'revoked')

  return (
    <div style={page}>
      <div style={wrap}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/admin/partners')} style={navBtnStyle}>← Partners</button>
          {editingName === null ? (
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, cursor: 'text' }} title="Click to rename" onClick={() => setEditingName(partner.name)}>
              {partner.name}
            </h2>
          ) : (
            <form
              onSubmit={e => {
                e.preventDefault()
                const name = editingName.trim()
                if (name && name !== partner.name) act('rename', () => api.partners.update(partnerId, { name }))
                setEditingName(null)
              }}
              style={{ display: 'flex', gap: 6 }}
            >
              <input autoFocus value={editingName} onChange={e => setEditingName(e.target.value)} style={inputStyle} onBlur={() => setEditingName(null)} />
            </form>
          )}
          <span style={{ color: '#64748b', fontFamily: 'monospace', fontSize: 13 }}>{partner.slug}</span>
          <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#94a3b8', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={partner.is_active}
              disabled={busy !== null}
              onChange={e => act('active', () => api.partners.update(partnerId, { is_active: e.target.checked }))}
            />
            Active partner
          </label>
        </div>

        {justConnected && (
          <Banner tone="ok" onClose={() => { params.delete('pos'); setParams(params, { replace: true }) }}>
            Square is connected. The last 7 days of orders will come in on the next sync (within 15 minutes).
          </Banner>
        )}
        {error && <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>}

        {/* ── Point of sale ─────────────────────────────────────────────── */}
        <Section
          title="Point of sale"
          action={live.length === 0 && (
            <button onClick={connectSquare} disabled={busy !== null} style={primaryBtn(busy !== null)}>
              {busy === 'connect' ? 'Opening Square…' : revoked.length ? 'Reconnect Square' : 'Connect Square'}
            </button>
          )}
        >
          {live.length === 0 ? (
            <div style={muted}>
              Not connected. Add the partner under “Partner logins” below so they can connect Square
              themselves at /partner, or use “Connect Square” here and approve with their Square account.
            </div>
          ) : (
            live.map(c => (
              <ConnectionCard
                key={c.id}
                connection={c}
                busy={busy}
                loadRuns={id => api.partners.runs(id, 10)}
                onPause={() => act('pause', () => api.partners.setConnectionStatus(c.id, 'disabled'))}
                onResume={() => act('resume', () => api.partners.setConnectionStatus(c.id, 'active'))}
                onReconnect={connectSquare}
                onDisconnect={() => {
                  if (window.confirm(`Disconnect ${partner.name}'s Square account? Orders already pulled are kept; new ones stop coming in.`)) {
                    act('disconnect', () => api.partners.disconnect(c.id))
                  }
                }}
              />
            ))
          )}
          {revoked.length > 0 && live.length === 0 && (
            <div style={{ ...muted, marginTop: 8 }}>
              Previously connected ({revoked.map(c => c.external_merchant_id).join(', ')}). Reconnecting the
              same Square account picks up where it left off.
            </div>
          )}
        </Section>

        {/* ── Locations ─────────────────────────────────────────────────── */}
        <Section title="Locations">
          {partner.locations.length === 0 ? (
            <div style={muted}>Locations are imported from the POS when it connects.</div>
          ) : (
            <LocationsTable
              locations={partner.locations}
              busy={busy !== null}
              onToggle={loc => act('location', () => api.partners.updateLocation(loc.id, { is_active: !loc.is_active }))}
            />
          )}
        </Section>

        {/* ── Partner logins ────────────────────────────────────────────── */}
        <Section title="Partner logins">
          <MembersPanel
            partnerId={partnerId}
            members={partner.members}
            busy={busy !== null}
            onInvite={email => act('invite', () => api.partners.inviteMember(partnerId, email))}
            onRemove={m => {
              if (window.confirm(`Remove ${m.email}'s access to ${partner.name}?`)) {
                act('remove', () => api.partners.removeMember(m.id))
              }
            }}
          />
        </Section>

        {/* ── Orders ────────────────────────────────────────────────────── */}
        <Section title="Orders">
          <OrdersTable<PosOrder>
            reloadKey={partnerId}
            locations={partner.locations}
            load={q => api.partners.orders({ partner_id: partnerId, unmatched: q.filter || undefined, limit: q.limit, offset: q.offset })}
            filterLabel="Unmatched only"
            filterEmpty="No unmatched orders."
            customerColumn={{
              key: 'customer', header: 'Customer', stopPropagation: true,
              render: o => o.customer_id ? (
                <a
                  href={`/admin/customers/${o.customer_id}`}
                  onClick={e => { e.preventDefault(); navigate(`/admin/customers/${o.customer_id}`) }}
                  style={{ color: '#a5b4fc', textDecoration: 'none' }}
                >
                  matched <span style={{ color: '#64748b' }}>{MATCH_LABEL[o.matched_via ?? ''] ?? ''}</span>
                </a>
              ) : o.contact_purged_at ? (
                <span style={{ color: '#475569' }}>unclaimed (expired)</span>
              ) : (
                <span style={{ color: '#64748b' }}>{o.has_contact ? 'not a member' : 'no phone on order'}</span>
              ),
            } satisfies Column<PosOrder>}
          />
        </Section>
      </div>
    </div>
  )
}

const MATCH_LABEL: Record<string, string> = {
  phone: 'by phone', link: 'repeat shopper', receipt: 'receipt', sale: 'from sale',
}

/* ── Partner logins ────────────────────────────────────────────────────────── */

/**
 * Who can sign in to this partner's own dashboard at /partner. Adding an email is
 * the whole invite: whoever signs in with Google as that address gets in.
 */
function MembersPanel({ partnerId, members, busy, onInvite, onRemove }: {
  partnerId: string
  members: PartnerMember[]
  busy: boolean
  onInvite: (email: string) => void
  onRemove: (m: PartnerMember) => void
}) {
  const [email, setEmail] = useState('')
  const portal = `${window.location.origin}/partner`

  return (
    <div>
      <div style={{ ...muted, marginBottom: 10 }}>
        Partners manage their own Square connection at{' '}
        <a href={portal} style={{ color: '#a5b4fc' }}>{portal}</a>, signing in with Google. Add the
        Google email of each person who should have access.
      </div>
      <form
        onSubmit={e => {
          e.preventDefault()
          if (email.trim()) { onInvite(email.trim()); setEmail('') }
        }}
        style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}
        key={partnerId}
      >
        <input
          type="email"
          placeholder="owner@theirshop.com"
          value={email}
          onChange={e => setEmail(e.target.value)}
          style={{ ...inputStyle, flex: '1 1 260px' }}
        />
        <button type="submit" disabled={busy || !email.trim()} style={primaryBtn(busy || !email.trim())}>Add login</button>
      </form>
      {members.length === 0 ? (
        <div style={muted}>No one yet.</div>
      ) : (
        members.map(m => (
          <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #1e293b', fontSize: 13 }}>
            <span style={{ color: '#f1f5f9' }}>{m.email}</span>
            <span style={{ color: '#64748b', fontSize: 12 }}>
              {m.signed_in ? `last signed in ${when(m.last_login_at)}` : 'invited, not signed in yet'}
            </span>
            <button onClick={() => onRemove(m)} disabled={busy} style={{ ...navBtnStyle, marginLeft: 'auto', color: '#fca5a5', borderColor: '#7f1d1d' }}>
              Remove
            </button>
          </div>
        ))
      )}
    </div>
  )
}
