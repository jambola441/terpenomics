/* ============================================================================
   partnerUi.tsx — the building blocks of a partner's page, shared by the admin
   view (PartnerDetail.tsx) and the partner's own portal (PartnerPortal.tsx).
   Anything that differs between the two — which endpoints to call, what the
   customer column may reveal — comes in as a prop.
   ========================================================================== */

import { useEffect, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { AdminTable, badge, navBtnStyle, Dash, type Column } from './AdminTable'
import type { PartnerLocation, PosConnection, PosOrderBase, PosSyncRun } from '../types'
import { ago, money, primaryBtn, when } from '../utils/partners'
import { Icon } from './Icon'
import { t, font } from '../theme'
/* ── Connection card ───────────────────────────────────────────────────────── */

export const STATUS_STYLE: Record<string, CSSProperties> = {
  active:   { background: t.successTint, color: t.success },
  disabled: { background: t.surface2, color: t.text2 },
  error:    { background: t.dangerTint, color: t.danger },
  revoked:  { background: t.surface2, color: t.text3 },
}

export function ConnectionCard({ connection: c, busy, loadRuns, onPause, onResume, onReconnect, onDisconnect }: {
  connection: PosConnection
  busy: string | null
  /** Recent sync runs for this connection; admin and partner read them from different endpoints. */
  loadRuns: (connectionId: string) => Promise<PosSyncRun[]>
  onPause: () => void
  onResume: () => void
  onReconnect: () => void
  onDisconnect: () => void
}) {
  const [runs, setRuns] = useState<PosSyncRun[] | null>(null)

  useEffect(() => {
    loadRuns(c.id).then(setRuns).catch(() => setRuns([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c.id, c.updated_at])

  // An auth error means Square no longer accepts our token; only a fresh OAuth fixes it.
  const needsReconnect = c.status === 'error' && /AuthError/.test(c.last_error ?? '')

  return (
    <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 10, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{c.provider}</span>
        <span style={{ ...badge, ...STATUS_STYLE[c.status] }}>{c.status}</span>
        {c.syncing && <span style={{ ...badge, background: t.infoTint, color: t.info }}>syncing</span>}
        <span style={{ color: t.text3, fontSize: 12, fontFamily: font.family.mono }}>merchant {c.external_merchant_id}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {needsReconnect ? (
            <button onClick={onReconnect} disabled={busy !== null} style={primaryBtn(busy !== null)}>Reconnect</button>
          ) : c.status === 'active' ? (
            <button onClick={onPause} disabled={busy !== null} style={navBtnStyle}>Pause</button>
          ) : (
            <button onClick={onResume} disabled={busy !== null} style={navBtnStyle}>{c.status === 'error' ? 'Retry' : 'Resume'}</button>
          )}
          <button onClick={onDisconnect} disabled={busy !== null} style={{ ...navBtnStyle, color: t.danger, borderColor: t.dangerEdge }}>
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
        <div style={{ marginTop: 12, fontSize: 12, color: t.danger, fontFamily: font.family.mono, wordBreak: 'break-word' }}>
          {c.last_error}
        </div>
      )}
      {c.status === 'active' && !c.last_synced_at && (
        <div style={{ ...muted, marginTop: 12 }}>Waiting for the first sync — it runs every 15 minutes.</div>
      )}

      {runs && runs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, color: t.text3, fontFamily: font.family.mono, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Recent syncs</div>
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

export const runColumns: Column<PosSyncRun>[] = [
  { key: 'started', header: 'Started', td: { fontSize: 12 }, render: r => when(r.started_at) },
  {
    key: 'status', header: 'Result',
    render: r => <span style={{ ...badge, ...(r.status === 'ok' ? STATUS_STYLE.active : r.status === 'error' ? STATUS_STYLE.error : { background: t.infoTint, color: t.info }) }}>{r.status}</span>,
  },
  { key: 'fetched', header: 'Fetched', align: 'right', render: r => r.orders_fetched },
  { key: 'new', header: 'New', align: 'right', render: r => r.orders_inserted },
  { key: 'updated', header: 'Updated', align: 'right', render: r => r.orders_updated },
  { key: 'matched', header: 'Matched', align: 'right', render: r => r.orders_matched },
  { key: 'error', header: 'Error', td: { fontSize: 12, color: t.danger, maxWidth: 280 }, render: r => r.error ?? <Dash /> },
]

/* ── Locations ─────────────────────────────────────────────────────────────── */

/** `onToggle` makes "earns points" editable (admin); without it the column is read-only. */
export function LocationsTable({ locations, busy = false, onToggle }: {
  locations: PartnerLocation[]
  busy?: boolean
  onToggle?: (loc: PartnerLocation) => void
}) {
  const columns: Column<PartnerLocation>[] = [
    { key: 'name', header: 'Store', td: { color: t.text1, fontWeight: 500 }, render: l => l.name },
    { key: 'address', header: 'Address', render: l => l.address ?? <Dash /> },
    { key: 'tz', header: 'Timezone', td: { fontSize: 12, color: t.text3 }, render: l => l.timezone ?? <Dash /> },
    {
      key: 'active', header: 'Earns points', stopPropagation: true,
      render: l => onToggle ? (
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
          <input type="checkbox" checked={l.is_active} disabled={busy} onChange={() => onToggle(l)} />
          {l.is_active ? 'yes' : 'no'}
        </label>
      ) : (l.is_active ? 'yes' : 'no'),
    },
  ]
  return <AdminTable columns={columns} rows={locations} rowKey={l => l.id} />
}

/* ── Orders ────────────────────────────────────────────────────────────────── */

export const PAGE = 25

export type OrdersQuery = { filter: boolean; limit: number; offset: number }

/**
 * Paginated partner orders with one checkbox filter. The caller supplies how to
 * load a page and what the "customer" column says: the admin page links to the
 * matched customer, the partner portal only says whether the shopper was a member.
 */
export function OrdersTable<T extends PosOrderBase>({ load, reloadKey, locations, filterLabel, filterEmpty, customerColumn }: {
  load: (q: OrdersQuery) => Promise<{ total: number; items: T[] }>
  /** Changes when a different partner is shown; `load` itself may change every render. */
  reloadKey: string
  locations: PartnerLocation[]
  filterLabel: string
  filterEmpty: string
  customerColumn: Column<T>
}) {
  const [data, setData] = useState<{ total: number; items: T[] } | null>(null)
  const [unmatched, setUnmatched] = useState(false)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    load({ filter: unmatched, limit: PAGE, offset })
      .then(setData)
      .catch(err => setError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey, unmatched, offset])

  const locName = new Map(locations.map(l => [l.id, l.name]))

  const columns: Column<T>[] = [
    { key: 'when', header: 'Ordered', td: { fontSize: 12 }, render: o => when(o.ordered_at) },
    { key: 'store', header: 'Store', render: o => (o.partner_location_id && locName.get(o.partner_location_id)) || <Dash /> },
    {
      key: 'total', header: 'Total', align: 'right',
      render: o => (
        <span style={{ color: o.kind === 'return' ? t.danger : t.text1 }}>
          {o.kind === 'return' ? '−' : ''}{money(o.total_cents, o.currency)}
        </span>
      ),
    },
    {
      key: 'state', header: 'State',
      render: o => (
        <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {o.kind === 'return' && <span style={{ ...badge, background: t.dangerTint, color: t.danger }}>return</span>}
          <span style={{ ...badge, ...(o.state === 'completed' ? STATUS_STYLE.active : o.state === 'canceled' ? STATUS_STYLE.revoked : STATUS_STYLE.disabled) }}>{o.state}</span>
          {o.refunded_cents > 0 && <span style={{ ...badge, background: t.warningTint, color: t.warning }}>refunded {money(o.refunded_cents, o.currency)}</span>}
        </span>
      ),
    },
    customerColumn,
    { key: 'items', header: 'Items', align: 'right', render: o => o.items.length },
  ]

  const total = data?.total ?? 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10, fontSize: 13, color: t.text2 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
          <input type="checkbox" checked={unmatched} onChange={e => { setUnmatched(e.target.checked); setOffset(0) }} />
          {filterLabel}
        </label>
        <span style={{ marginLeft: 'auto', color: t.text3 }}>
          {total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total.toLocaleString()}` : ''}
        </span>
        {total > PAGE && (
          <>
            <button onClick={() => setOffset(Math.max(0, offset - PAGE))} disabled={offset === 0} style={navBtnStyle}><Icon name="arrow-left" size={14} label="Previous page" /></button>
            <button onClick={() => setOffset(offset + PAGE)} disabled={offset + PAGE >= total} style={navBtnStyle}><Icon name="arrow-right" size={14} label="Next page" /></button>
          </>
        )}
      </div>

      {error && <div style={{ color: t.danger, marginBottom: 8 }}>Error: {error}</div>}

      {!data ? (
        <div style={muted}>Loading…</div>
      ) : data.items.length === 0 ? (
        <div style={muted}>{unmatched ? filterEmpty : 'No orders yet. They appear after the first sync.'}</div>
      ) : (
        <>
          <AdminTable columns={columns} rows={data.items} rowKey={o => o.id} onRowClick={o => setOpen(open === o.id ? null : o.id)} />
          {open && (() => {
            const o = data.items.find(x => x.id === open)
            if (!o) return null
            return (
              <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 8, padding: 14, marginTop: 10, fontSize: 13 }}>
                <div style={{ color: t.text3, fontFamily: font.family.mono, fontSize: 12, marginBottom: 8 }}>
                  {o.external_order_id}{o.source_external_order_id ? ` · returns ${o.source_external_order_id}` : ''}
                </div>
                {o.items.map((i, n) => (
                  <div key={n} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', color: t.text2 }}>
                    <span>{i.quantity !== '1' ? `${i.quantity} × ` : ''}{i.name}{i.variation ? ` (${i.variation})` : ''}</span>
                    <span>{money(i.total_cents, o.currency)}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', gap: 18, marginTop: 10, color: t.text3, fontSize: 12 }}>
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

export const page: CSSProperties = { padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }
export const wrap: CSSProperties = { maxWidth: 1000, margin: '0 auto' }
export const muted: CSSProperties = { color: t.text3, fontSize: 13, lineHeight: 1.7 }

export function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section style={{ marginBottom: 32 }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12, minHeight: 34 }}>
        <h3 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.title, fontWeight: 600, color: t.text1 }}>{title}</h3>
        <div style={{ marginLeft: 'auto' }}>{action}</div>
      </div>
      {children}
    </section>
  )
}

export function Stat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div title={title}>
      <div style={{ fontSize: 11, color: t.text3, fontFamily: font.family.mono, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>{label}</div>
      <div style={{ color: t.text2 }}>{value}</div>
    </div>
  )
}

export function Banner({ tone, children, onClose }: { tone: 'ok' | 'error'; children: ReactNode; onClose: () => void }) {
  const s = tone === 'ok'
    ? { background: t.successTint, border: `1px solid ${t.successEdge}`, color: t.success }
    : { background: t.dangerTint, border: `1px solid ${t.dangerEdge}`, color: t.danger }
  return (
    <div style={{ ...s, borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 13, display: 'flex', alignItems: 'flex-start', gap: 12 }}>
      <Icon name={tone === 'ok' ? 'check-circle' : 'alert'} size={16} style={{ marginTop: 1 }} />
      <span style={{ flex: 1 }}>{children}</span>
      <button onClick={onClose} aria-label="Dismiss" style={{ display: 'inline-flex', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}><Icon name="close" size={16} /></button>
    </div>
  )
}
