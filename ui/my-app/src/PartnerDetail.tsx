import { useEffect, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { AdminTable, badge, navBtnStyle, Dash, type Column } from './components/AdminTable'
import api from './api/client'
import type { PartnerDetail as Detail, PartnerLocation, PosConnection, PosOrder, PosOrderPage, PosSyncRun } from './types'
import { ago, inputStyle, money, primaryBtn, when } from './utils/partners'

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
              Not connected. “Connect Square” opens Square's sign-in — approve it with the partner's
              Square account (or have them do it). We only ask to read orders, customers and locations.
            </div>
          ) : (
            live.map(c => (
              <ConnectionCard
                key={c.id}
                connection={c}
                busy={busy}
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

        {/* ── Orders ────────────────────────────────────────────────────── */}
        <Section title="Orders">
          <OrdersTable partnerId={partnerId} locations={partner.locations} />
        </Section>
      </div>
    </div>
  )
}

/* ── Connection card ───────────────────────────────────────────────────────── */

const STATUS_STYLE: Record<string, CSSProperties> = {
  active:   { background: '#14532d', color: '#86efac' },
  disabled: { background: '#1e293b', color: '#94a3b8' },
  error:    { background: '#450a0a', color: '#fca5a5' },
  revoked:  { background: '#1e293b', color: '#64748b' },
}

function ConnectionCard({ connection: c, busy, onPause, onResume, onReconnect, onDisconnect }: {
  connection: PosConnection
  busy: string | null
  onPause: () => void
  onResume: () => void
  onReconnect: () => void
  onDisconnect: () => void
}) {
  const [runs, setRuns] = useState<PosSyncRun[] | null>(null)

  useEffect(() => {
    api.partners.runs(c.id, 10).then(setRuns).catch(() => setRuns([]))
  }, [c.id, c.updated_at])

  // An auth error means Square no longer accepts our token; only a fresh OAuth fixes it.
  const needsReconnect = c.status === 'error' && /AuthError/.test(c.last_error ?? '')

  return (
    <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{c.provider}</span>
        <span style={{ ...badge, ...STATUS_STYLE[c.status] }}>{c.status}</span>
        {c.syncing && <span style={{ ...badge, background: '#1e1b4b', color: '#a5b4fc' }}>syncing</span>}
        <span style={{ color: '#475569', fontSize: 12, fontFamily: 'monospace' }}>merchant {c.external_merchant_id}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {needsReconnect ? (
            <button onClick={onReconnect} disabled={busy !== null} style={primaryBtn(busy !== null)}>Reconnect</button>
          ) : c.status === 'active' ? (
            <button onClick={onPause} disabled={busy !== null} style={navBtnStyle}>Pause</button>
          ) : (
            <button onClick={onResume} disabled={busy !== null} style={navBtnStyle}>{c.status === 'error' ? 'Retry' : 'Resume'}</button>
          )}
          <button onClick={onDisconnect} disabled={busy !== null} style={{ ...navBtnStyle, color: '#fca5a5', borderColor: '#7f1d1d' }}>
            Disconnect
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 28, marginTop: 14, fontSize: 13, flexWrap: 'wrap' }}>
        <Stat label="Last sync" value={ago(c.last_synced_at)} title={when(c.last_synced_at)} />
        <Stat label="Orders through" value={when(c.sync_cursor)} />
        <Stat label="Token expires" value={when(c.token_expires_at)} />
        {c.consecutive_failures > 0 && <Stat label="Failures in a row" value={String(c.consecutive_failures)} />}
      </div>

      {c.last_error && (
        <div style={{ marginTop: 12, fontSize: 12, color: '#fca5a5', fontFamily: 'monospace', wordBreak: 'break-word' }}>
          {c.last_error}
        </div>
      )}
      {c.status === 'active' && !c.last_synced_at && (
        <div style={{ ...muted, marginTop: 12 }}>Waiting for the first sync — it runs every 15 minutes.</div>
      )}

      {runs && runs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Recent syncs</div>
          <AdminTable
            columns={runColumns}
            rows={runs}
            rowKey={r => r.id}
          />
        </div>
      )}
    </div>
  )
}

const runColumns: Column<PosSyncRun>[] = [
  { key: 'started', header: 'Started', td: { fontSize: 12 }, render: r => when(r.started_at) },
  {
    key: 'status', header: 'Result',
    render: r => <span style={{ ...badge, ...(r.status === 'ok' ? STATUS_STYLE.active : r.status === 'error' ? STATUS_STYLE.error : { background: '#1e1b4b', color: '#a5b4fc' }) }}>{r.status}</span>,
  },
  { key: 'fetched', header: 'Fetched', align: 'right', render: r => r.orders_fetched },
  { key: 'new', header: 'New', align: 'right', render: r => r.orders_inserted },
  { key: 'updated', header: 'Updated', align: 'right', render: r => r.orders_updated },
  { key: 'matched', header: 'Matched', align: 'right', render: r => r.orders_matched },
  { key: 'error', header: 'Error', td: { fontSize: 12, color: '#fca5a5', maxWidth: 280 }, render: r => r.error ?? <Dash /> },
]

/* ── Locations ─────────────────────────────────────────────────────────────── */

function LocationsTable({ locations, busy, onToggle }: {
  locations: PartnerLocation[]
  busy: boolean
  onToggle: (loc: PartnerLocation) => void
}) {
  const columns: Column<PartnerLocation>[] = [
    { key: 'name', header: 'Store', td: { color: '#f1f5f9', fontWeight: 500 }, render: l => l.name },
    { key: 'address', header: 'Address', render: l => l.address ?? <Dash /> },
    { key: 'tz', header: 'Timezone', td: { fontSize: 12, color: '#64748b' }, render: l => l.timezone ?? <Dash /> },
    {
      key: 'active', header: 'Earns points', stopPropagation: true,
      render: l => (
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
          <input type="checkbox" checked={l.is_active} disabled={busy} onChange={() => onToggle(l)} />
          {l.is_active ? 'yes' : 'no'}
        </label>
      ),
    },
  ]
  return <AdminTable columns={columns} rows={locations} rowKey={l => l.id} />
}

/* ── Orders ────────────────────────────────────────────────────────────────── */

const PAGE = 25

const MATCH_LABEL: Record<string, string> = {
  phone: 'by phone', link: 'repeat shopper', receipt: 'receipt', sale: 'from sale',
}

function OrdersTable({ partnerId, locations }: { partnerId: string; locations: PartnerLocation[] }) {
  const navigate = useNavigate()
  const [data, setData] = useState<PosOrderPage | null>(null)
  const [unmatched, setUnmatched] = useState(false)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    api.partners.orders({ partner_id: partnerId, unmatched: unmatched || undefined, limit: PAGE, offset })
      .then(setData)
      .catch(err => setError(err.message))
  }, [partnerId, unmatched, offset])

  const locName = new Map(locations.map(l => [l.id, l.name]))

  const columns: Column<PosOrder>[] = [
    { key: 'when', header: 'Ordered', td: { fontSize: 12 }, render: o => when(o.ordered_at) },
    { key: 'store', header: 'Store', render: o => (o.partner_location_id && locName.get(o.partner_location_id)) || <Dash /> },
    {
      key: 'total', header: 'Total', align: 'right',
      render: o => (
        <span style={{ color: o.kind === 'return' ? '#fca5a5' : '#f1f5f9' }}>
          {o.kind === 'return' ? '−' : ''}{money(o.total_cents, o.currency)}
        </span>
      ),
    },
    {
      key: 'state', header: 'State',
      render: o => (
        <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {o.kind === 'return' && <span style={{ ...badge, background: '#450a0a', color: '#fca5a5' }}>return</span>}
          <span style={{ ...badge, ...(o.state === 'completed' ? STATUS_STYLE.active : o.state === 'canceled' ? STATUS_STYLE.revoked : STATUS_STYLE.disabled) }}>{o.state}</span>
          {o.refunded_cents > 0 && <span style={{ ...badge, background: '#422006', color: '#fbbf24' }}>refunded {money(o.refunded_cents, o.currency)}</span>}
        </span>
      ),
    },
    {
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
    },
    { key: 'items', header: 'Items', align: 'right', render: o => o.items.length },
  ]

  const total = data?.total ?? 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10, fontSize: 13, color: '#94a3b8' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
          <input type="checkbox" checked={unmatched} onChange={e => { setUnmatched(e.target.checked); setOffset(0) }} />
          Unmatched only
        </label>
        <span style={{ marginLeft: 'auto', color: '#475569' }}>
          {total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total.toLocaleString()}` : ''}
        </span>
        {total > PAGE && (
          <>
            <button onClick={() => setOffset(Math.max(0, offset - PAGE))} disabled={offset === 0} style={navBtnStyle}>←</button>
            <button onClick={() => setOffset(offset + PAGE)} disabled={offset + PAGE >= total} style={navBtnStyle}>→</button>
          </>
        )}
      </div>

      {error && <div style={{ color: '#f87171', marginBottom: 8 }}>Error: {error}</div>}

      {!data ? (
        <div style={muted}>Loading…</div>
      ) : data.items.length === 0 ? (
        <div style={muted}>{unmatched ? 'No unmatched orders.' : 'No orders yet. They appear after the first sync.'}</div>
      ) : (
        <>
          <AdminTable columns={columns} rows={data.items} rowKey={o => o.id} onRowClick={o => setOpen(open === o.id ? null : o.id)} />
          {open && (() => {
            const o = data.items.find(x => x.id === open)
            if (!o) return null
            return (
              <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, padding: 14, marginTop: 10, fontSize: 13 }}>
                <div style={{ color: '#64748b', fontFamily: 'monospace', fontSize: 12, marginBottom: 8 }}>
                  {o.external_order_id}{o.source_external_order_id ? ` · returns ${o.source_external_order_id}` : ''}
                </div>
                {o.items.map((i, n) => (
                  <div key={n} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', color: '#cbd5e1' }}>
                    <span>{i.quantity !== '1' ? `${i.quantity} × ` : ''}{i.name}{i.variation ? ` (${i.variation})` : ''}</span>
                    <span>{money(i.total_cents, o.currency)}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', gap: 18, marginTop: 10, color: '#64748b', fontSize: 12 }}>
                  <span>tax {money(o.tax_cents, o.currency)}</span>
                  <span>tip {money(o.tip_cents, o.currency)}</span>
                  <span>discounts {money(o.discount_cents, o.currency)}</span>
                </div>
              </div>
            )
          })()}
        </>
      )}
    </div>
  )
}

/* ── Bits ──────────────────────────────────────────────────────────────────── */

const page: CSSProperties = { padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }
const wrap: CSSProperties = { maxWidth: 1000, margin: '0 auto' }
const muted: CSSProperties = { color: '#475569', fontSize: 13, lineHeight: 1.7 }

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section style={{ marginBottom: 32 }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12, minHeight: 34 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: '#cbd5e1' }}>{title}</h3>
        <div style={{ marginLeft: 'auto' }}>{action}</div>
      </div>
      {children}
    </section>
  )
}

function Stat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div title={title}>
      <div style={{ fontSize: 11, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>{label}</div>
      <div style={{ color: '#cbd5e1' }}>{value}</div>
    </div>
  )
}

function Banner({ tone, children, onClose }: { tone: 'ok' | 'error'; children: ReactNode; onClose: () => void }) {
  const s = tone === 'ok'
    ? { background: '#052e16', border: '1px solid #166534', color: '#86efac' }
    : { background: '#450a0a', border: '1px solid #7f1d1d', color: '#fca5a5' }
  return (
    <div style={{ ...s, borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 13, display: 'flex', gap: 12 }}>
      <span style={{ flex: 1 }}>{children}</span>
      <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>×</button>
    </div>
  )
}
