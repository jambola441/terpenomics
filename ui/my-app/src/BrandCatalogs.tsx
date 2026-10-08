import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AdminTable, badge, navBtnStyle, Dash, type Column, primaryBtnStyle } from './components/AdminTable'
import api from './api/client'
import type { BrandCatalogRow, CatalogExportStatus } from './types'
import { t, font, tone } from './theme'
import { Icon } from './components/Icon'

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
  const [origin, setOrigin] = useState<CatalogOrigin | 'all'>('all')

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
    { key: 'brand', header: 'Brand', td: { color: t.text1, fontWeight: 500 }, render: c => c.brand_name },
    { key: 'slug', header: 'Slug', td: { color: t.text3, fontFamily: font.family.mono }, render: c => c.brand_slug },
    { key: 'source', header: 'Built from', render: c => <OriginBadge catalog={c} /> },
    {
      key: 'entries', header: 'Entries', align: 'right',
      render: c => (
        <span>
          {c.active_entry_count}
          {c.entry_count !== c.active_entry_count && (
            <span style={{ color: t.text3 }}> / {c.entry_count}</span>
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
  const counts = { site: 0, stores: 0, manual: 0 }
  catalogs.forEach(c => { counts[catalogOrigin(c.source_method)] += 1 })
  const shown = origin === 'all' ? catalogs : catalogs.filter(c => catalogOrigin(c.source_method) === origin)

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 1000, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h2 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Brand Catalogs</h2>
          <button
            onClick={() => navigate('/admin/brand-catalogs/new')}
            style={primaryBtnStyle}
          >
            <Icon name="plus" size={14} />New
          </button>
        </div>

        <div style={{ fontSize: 12, color: t.text3, marginBottom: 18, lineHeight: 1.7 }}>
          A catalog is what a brand says it makes — the external referent enrichment is
          checked against. Edits here change the database; enrichment loads the generated{' '}
          <code style={{ color: t.text2, fontFamily: font.family.mono }}>data/catalogs/&lt;slug&gt;.json</code> export, so an
          edit reaches it only once that export is regenerated.
          {stale > 0 && (
            <span style={{ color: t.warning }}>
              {' '}{stale} catalog{stale === 1 ? '' : 's'} below {stale === 1 ? 'has' : 'have'} an
              out-of-date export.
            </span>
          )}
        </div>

        {catalogs.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, fontSize: 12 }}>
            <span style={{ color: t.text3, fontFamily: font.family.mono, textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 11 }}>Built from</span>
            {(['all', 'site', 'stores', 'manual'] as const).map(o => (
              <button
                key={o}
                onClick={() => setOrigin(o)}
                style={{
                  ...navBtnStyle, fontSize: 12, padding: '3px 10px',
                  ...(origin === o ? { color: t.accent, borderColor: t.accentDim, background: t.accentTint } : {}),
                }}
              >
                {o === 'all' ? `All ${catalogs.length}` : `${ORIGIN_LABEL[o]} ${counts[o]}`}
              </button>
            ))}
          </div>
        )}

        {error && <div style={{ color: t.danger, marginBottom: 16 }}>Error: {error}</div>}

        {loading ? (
          <div style={{ color: t.text3, padding: 16 }}>Loading…</div>
        ) : catalogs.length === 0 ? (
          <div style={{ color: t.text3, padding: 16, lineHeight: 1.8 }}>
            No catalogs yet. Acquire one with{' '}
            <code style={{ color: t.text2, fontFamily: font.family.mono }}>scripts/brand_catalog.py fetch</code> then{' '}
            <code style={{ color: t.text2, fontFamily: font.family.mono }}>push</code>, or start a hand-curated one with “+ New”.
          </div>
        ) : (
          <AdminTable
            columns={columns}
            rows={shown}
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
    return <span style={{ ...badge, background: t.dangerTint, color: t.danger }}>no file</span>
  }
  if (!status.file_readable) {
    return <span style={{ ...badge, background: t.dangerTint, color: t.danger }}>unreadable</span>
  }
  if (status.in_sync) {
    return <span style={{ ...badge, background: t.successTint, color: t.success }}>in sync</span>
  }
  const parts = [
    status.added ? `+${status.added}` : null,
    status.removed ? `−${status.removed}` : null,
    status.changed ? `~${status.changed}` : null,
  ].filter(Boolean)
  return (
    <span style={{ ...badge, background: t.warningTint, color: t.warning }}>
      stale {parts.length ? parts.join(' ') : 'meta'}
    </span>
  )
}

/**
 * Where a catalog's entries came from. "site": read from the brand's own product
 * list by a recipe (scripts/storefront.py), so it has every product and size the brand
 * lists. "stores": the bootstrap built it from store listings (catalog_bootstrap.py),
 * and keeps a product in a size only when two or more stores list it, so a size or a
 * new strain one store carries is missing. "manual": started by hand here.
 */
export type CatalogOrigin = 'site' | 'stores' | 'manual'

const ORIGIN_LABEL: Record<CatalogOrigin, string> = { site: 'Brand site', stores: 'Store-built', manual: 'Manual' }

export function catalogOrigin(method: string): CatalogOrigin {
  if (method === 'listings_bootstrap') return 'stores'
  if (!method || method === 'manual') return 'manual'
  return 'site'
}

export function OriginBadge({ catalog }: { catalog: Pick<BrandCatalogRow, 'source_method' | 'source_url'> }) {
  const origin = catalogOrigin(catalog.source_method)
  const tn = tone[origin === 'site' ? 'success' : origin === 'stores' ? 'warning' : 'neutral']
  const style = { background: tn.bg, color: tn.fg }
  const label = <span style={{ ...badge, ...style }} title={catalog.source_method}>{ORIGIN_LABEL[origin]}</span>
  if (origin === 'site' && catalog.source_url) {
    let host = catalog.source_url
    try { host = new URL(catalog.source_url).host } catch { /* keep the raw url */ }
    return (
      <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
        {label}
        <a
          href={catalog.source_url}
          target="_blank"
          rel="noreferrer"
          onClick={e => e.stopPropagation()}
          style={{ color: t.text3, fontFamily: font.family.mono, fontSize: 11 }}
        >
          {host}
        </a>
      </span>
    )
  }
  return label
}
