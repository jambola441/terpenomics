import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AdminTable, badge, navBtnStyle, Dash, type Column } from './components/AdminTable'
import api from './api/client'
import type { BrandCatalogRow, CatalogExportStatus } from './types'

/**
 * Brand catalogs — the products a brand says it makes.
 *
 * The Export column is the one that matters. Postgres is the system of record,
 * but the catalog read path in enrichment is the generated
 * `data/catalogs/<slug>.json` file, so a catalog whose export is stale is one the
 * model is not actually seeing. It is a column rather than a detail-page footnote
 * so a stale catalog is visible without opening it.
 */
export default function BrandCatalogs() {
  const navigate = useNavigate()
  const [catalogs, setCatalogs] = useState<BrandCatalogRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setCatalogs(await api.brandCatalogs.list({ limit: 200 }))
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const columns: Column<BrandCatalogRow>[] = [
    { key: 'brand', header: 'Brand', td: { color: '#f1f5f9', fontWeight: 500 }, render: c => c.brand_name },
    { key: 'slug', header: 'Slug', td: { color: '#64748b', fontFamily: 'monospace' }, render: c => c.brand_slug },
    { key: 'source', header: 'Source', td: { color: '#94a3b8', fontSize: 12 }, render: c => c.source_method },
    {
      key: 'entries', header: 'Entries', align: 'right',
      render: c => (
        <span>
          {c.active_entry_count}
          {c.entry_count !== c.active_entry_count && (
            <span style={{ color: '#475569' }}> / {c.entry_count}</span>
          )}
        </span>
      ),
    },
    {
      key: 'listings', header: 'Listings', align: 'right',
      render: c => (c.listing_count ? c.listing_count.toLocaleString() : <Dash />),
    },
    {
      key: 'fetched', header: 'Fetched', td: { fontSize: 12 },
      render: c => (c.fetched_at ? c.fetched_at.slice(0, 10) : <Dash />),
    },
    { key: 'export', header: 'Export', render: c => <ExportBadge status={c.export} /> },
  ]

  const stale = catalogs.filter(c => !c.export.in_sync).length

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1000, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Brand Catalogs</h2>
          <button
            onClick={() => navigate('/admin/brand-catalogs/new')}
            style={{ ...navBtnStyle, color: '#a5b4fc', borderColor: '#3730a3' }}
          >
            + New
          </button>
        </div>

        <div style={{ fontSize: 12, color: '#475569', marginBottom: 18, lineHeight: 1.7 }}>
          A catalog is what a brand says it makes — the external referent enrichment is
          checked against. Edits here change the database; enrichment loads the generated{' '}
          <code style={{ color: '#64748b' }}>data/catalogs/&lt;slug&gt;.json</code> export, so an
          edit reaches it only once that export is regenerated.
          {stale > 0 && (
            <span style={{ color: '#fbbf24' }}>
              {' '}{stale} catalog{stale === 1 ? '' : 's'} below {stale === 1 ? 'has' : 'have'} an
              out-of-date export.
            </span>
          )}
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>Error: {error}</div>}

        {loading ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : catalogs.length === 0 ? (
          <div style={{ color: '#475569', padding: 16, lineHeight: 1.8 }}>
            No catalogs yet. Acquire one with{' '}
            <code style={{ color: '#64748b' }}>scripts/brand_catalog.py fetch</code> then{' '}
            <code style={{ color: '#64748b' }}>push</code>, or start a hand-curated one with “+ New”.
          </div>
        ) : (
          <AdminTable
            columns={columns}
            rows={catalogs}
            rowKey={c => c.id}
            onRowClick={c => navigate(`/admin/brand-catalogs/${c.id}`)}
          />
        )}
      </div>
    </div>
  )
}

/** Whether the generated export still agrees with the database. */
export function ExportBadge({ status }: { status: CatalogExportStatus }) {
  if (!status.file_exists) {
    return <span style={{ ...badge, background: '#450a0a', color: '#fca5a5' }}>no file</span>
  }
  if (!status.file_readable) {
    return <span style={{ ...badge, background: '#450a0a', color: '#fca5a5' }}>unreadable</span>
  }
  if (status.in_sync) {
    return <span style={{ ...badge, background: '#14532d', color: '#86efac' }}>in sync</span>
  }
  const parts = [
    status.added ? `+${status.added}` : null,
    status.removed ? `−${status.removed}` : null,
    status.changed ? `~${status.changed}` : null,
  ].filter(Boolean)
  return (
    <span style={{ ...badge, background: '#422006', color: '#fbbf24' }}>
      stale {parts.length ? parts.join(' ') : 'meta'}
    </span>
  )
}
