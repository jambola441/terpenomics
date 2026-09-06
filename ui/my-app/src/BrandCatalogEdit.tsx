import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AdminTable, badge, categoryColor, navBtnStyle, selectStyle, Dash, type Column } from './components/AdminTable'
import { ExportBadge } from './BrandCatalogs'
import api from './api/client'
import type { BrandCatalog, BrandCatalogEntry, CatalogExportStatus } from './types'

const LIMIT = 50

/** Fields scripts/verification.py will accept a human sign-off on. */
const VERIFIABLE = ['category', 'subtype', 'strain', 'product_line', 'variant'] as const

/** The editable text columns of an entry, in the order the form shows them. */
const TEXT_FIELDS = [
  { key: 'name', label: 'Name *', mono: false },
  { key: 'product_line', label: 'Product line', mono: false },
  { key: 'category', label: 'Category', mono: false },
  { key: 'subtype', label: 'Subtype', mono: false },
  { key: 'strain', label: 'Strain', mono: false },
  { key: 'variant', label: 'Variant', mono: false },
  { key: 'external_id', label: 'External ID (source variant id)', mono: true },
] as const

type FieldKey = typeof TEXT_FIELDS[number]['key']
type Draft = Record<FieldKey | 'match_terms', string>

function toDraft(e: BrandCatalogEntry | null): Draft {
  return {
    name: e?.name ?? '',
    product_line: e?.product_line ?? '',
    category: e?.category ?? '',
    subtype: e?.subtype ?? '',
    strain: e?.strain ?? '',
    variant: e?.variant ?? '',
    external_id: e?.external_id ?? '',
    match_terms: (e?.match_terms ?? []).join(', '),
  }
}

/**
 * One brand's catalog: its metadata, its entries, and the state of its export.
 *
 * Two behaviours here are correctness requirements rather than choices:
 *
 * - **Remove never deletes.** `listings.catalog_entry_id` is a foreign key to these
 *   rows, so removing one means `is_active = false`. The row stays, the listings
 *   that resolved to it keep their history, and it can be put back.
 * - **The export is separate state.** The catalog read path in enrichment is
 *   `data/catalogs/<slug>.json`, so nothing edited on this page reaches the model
 *   until the export is regenerated. The banner says so on every visit, and it is
 *   re-checked after every write rather than assumed.
 *
 * Variant is editable in the table itself, and rows are multi-selectable so one
 * variant can be applied to many at once. Variant earns that over the other columns
 * because it is the field a fetch most often gets wrong in a consistent way — a
 * whole product line landing with the size in the name and nothing in `variant` —
 * and fixing fifty of those one modal at a time is what stops it getting fixed.
 * Bulk actions are ordinary per-row requests in a loop, not a new endpoint: the
 * write path stays the single-entry one whose rules about `verified_*` are already
 * settled.
 */
export default function BrandCatalogEdit() {
  const { catalogId } = useParams<{ catalogId: string }>()
  const navigate = useNavigate()
  const isNew = catalogId === 'new'

  const [loading, setLoading] = useState(!isNew)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  // Catalog metadata
  const [catalog, setCatalog] = useState<BrandCatalog | null>(null)
  const [brandName, setBrandName] = useState('')
  const [brandSlug, setBrandSlug] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [sourceMethod, setSourceMethod] = useState('manual')
  const [savingMeta, setSavingMeta] = useState(false)

  // Export
  const [exportStatus, setExportStatus] = useState<CatalogExportStatus | null>(null)
  const [exporting, setExporting] = useState(false)

  // Entries
  const [entries, setEntries] = useState<BrandCatalogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [categories, setCategories] = useState<string[]>([])
  const [entriesLoading, setEntriesLoading] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('active')

  // The entry open in the editor: a row, or 'new', or nothing.
  const [editing, setEditing] = useState<BrandCatalogEntry | 'new' | null>(null)

  // Inline + bulk editing
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [inlineSavingId, setInlineSavingId] = useState<string | null>(null)
  const [bulkBusy, setBulkBusy] = useState<string | null>(null)
  /** Index of the last checkbox clicked, so shift-click can extend from it. */
  const anchorRef = useRef<number | null>(null)

  useEffect(() => {
    if (isNew) return
    loadMeta()
  }, [catalogId])

  const filterKey = `${q}|${category}|${status}`
  useEffect(() => {
    if (isNew) return
    setOffset(0)
    loadEntries(0)
  }, [catalogId, filterKey])

  function fillMeta(c: BrandCatalog) {
    setCatalog(c)
    setBrandName(c.brand_name)
    setBrandSlug(c.brand_slug)
    setSourceUrl(c.source_url ?? '')
    setSourceMethod(c.source_method)
  }

  /**
   * Catalog metadata, categories and export state. `limit: 1` because the entries
   * table is loaded by `loadEntries` — this endpoint returns a first page too, but
   * driving the table from one place keeps filtering and paging on a single path.
   */
  async function loadMeta() {
    setLoading(true)
    setError(null)
    try {
      const detail = await api.brandCatalogs.get(catalogId!, { limit: 1 })
      fillMeta(detail.catalog)
      setCategories(detail.categories)
      setExportStatus(detail.export)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadEntries(nextOffset: number) {
    setEntriesLoading(true)
    setError(null)
    try {
      const page = await api.brandCatalogs.listEntries(catalogId!, {
        q: q || undefined,
        category: category || undefined,
        is_active: status === 'all' ? undefined : status === 'active',
        limit: LIMIT,
        offset: nextOffset,
      })
      setEntries(prev => (nextOffset === 0 ? page.entries : [...prev, ...page.entries]))
      // A new filter is a new set of rows; carrying a selection across it would let a
      // bulk action hit entries that are no longer on screen.
      if (nextOffset === 0) { setSelected(new Set()); anchorRef.current = null }
      setTotal(page.total)
      setOffset(nextOffset)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setEntriesLoading(false)
    }
  }

  /** Re-read the export state. Called after every write: an edit makes it stale. */
  async function refreshExport() {
    try {
      setExportStatus(await api.brandCatalogs.exportStatus(catalogId!))
    } catch {
      // The banner going missing must not swallow the save that just succeeded.
    }
  }

  async function handleSaveMeta(e: React.FormEvent) {
    e.preventDefault()
    if (!brandName.trim()) { setError('Brand name is required.'); return }
    setSavingMeta(true); setError(null); setMsg(null)
    try {
      if (isNew) {
        const created = await api.brandCatalogs.create({
          brand_name: brandName.trim(),
          brand_slug: brandSlug.trim() || undefined,
          source_url: sourceUrl.trim() || null,
          source_method: sourceMethod.trim() || 'manual',
        })
        navigate(`/admin/brand-catalogs/${created.id}`, { replace: true })
      } else {
        const updated = await api.brandCatalogs.update(catalogId!, {
          brand_name: brandName.trim(),
          brand_slug: brandSlug.trim(),
          source_url: sourceUrl.trim() || null,
          source_method: sourceMethod.trim(),
        })
        fillMeta(updated)
        setExportStatus(updated.export)
        setMsg('Saved')
      }
    } catch (err: any) {
      setError(err.message ?? 'Save failed')
    } finally {
      setSavingMeta(false)
    }
  }

  async function handleRegenerate() {
    setExporting(true); setError(null); setMsg(null)
    try {
      const res = await api.brandCatalogs.regenerateExport(catalogId!)
      setExportStatus(res.export)
      setMsg(`Wrote ${res.written} — ${res.entry_count} entries, ${res.product_count} products`)
    } catch (err: any) {
      setError(err.message ?? 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  /** Replace one row in place, so a save does not reshuffle or refetch the table. */
  function replaceEntry(updated: BrandCatalogEntry) {
    setEntries(prev => prev.map(e => (e.id === updated.id ? updated : e)))
    if (editing && editing !== 'new' && editing.id === updated.id) setEditing(updated)
  }

  /**
   * Fold a saved row back into the table, dropping it if the current filter no longer
   * holds it. Removing a row while the filter says "active" should take it off screen
   * — it is no longer part of the answer to the question being asked.
   */
  function applyEntryUpdate(updated: BrandCatalogEntry) {
    if (status !== 'all' && updated.is_active !== (status === 'active')) {
      setEntries(prev => prev.filter(e => e.id !== updated.id))
      setTotal(t => Math.max(0, t - 1))
      setSelected(prev => {
        if (!prev.has(updated.id)) return prev
        const next = new Set(prev)
        next.delete(updated.id)
        return next
      })
      if (editing !== 'new' && editing?.id === updated.id) setEditing(null)
    } else {
      replaceEntry(updated)
    }
  }

  async function handleSetActive(entry: BrandCatalogEntry, isActive: boolean) {
    setError(null); setMsg(null)
    try {
      const updated = await api.brandCatalogs.setEntryActive(catalogId!, entry.id, isActive)
      applyEntryUpdate(updated)
      setMsg(isActive ? `Restored “${updated.name}”` : `Removed “${updated.name}” (deactivated, not deleted)`)
      refreshExport()
    } catch (err: any) {
      setError(err.message ?? 'Failed')
    }
  }

  /**
   * Save one field of one row from the table, without opening the editor.
   *
   * Same endpoint and same diff discipline as the editor: one key, so nothing the
   * user did not touch is rewritten. A no-op edit is dropped rather than sent — the
   * endpoint would accept it, but it would make the export stale for nothing.
   */
  async function handleInlineSave(entry: BrandCatalogEntry, field: 'variant', value: string) {
    const next = value.trim() || null
    if ((entry[field] ?? null) === next) return
    setError(null); setMsg(null)
    setInlineSavingId(entry.id)
    try {
      const updated = await api.brandCatalogs.updateEntry(catalogId!, entry.id, { [field]: next })
      replaceEntry(updated)
      setMsg(next
        ? `${field} = “${next}” on “${updated.name}” — regenerate the export to put it in front of enrichment`
        : `${field} cleared on “${updated.name}” — regenerate the export to put it in front of enrichment`)
      refreshExport()
    } catch (err: any) {
      setError(err.message ?? 'Save failed')
    } finally {
      setInlineSavingId(null)
    }
  }

  /** Checkbox click. Shift extends from the last one clicked, as in a file list. */
  function toggleRow(entry: BrandCatalogEntry, index: number, shift: boolean) {
    // Read the anchor and move it here, not inside the updater: React runs an
    // updater lazily at re-render, by which point `anchorRef.current` would already
    // be this click's index and every shift-click would cover a range of one.
    const anchor = anchorRef.current
    anchorRef.current = index
    const range = shift && anchor != null
      ? entries.slice(Math.min(anchor, index), Math.max(anchor, index) + 1)
      : [entry]
    setSelected(prev => {
      const next = new Set(prev)
      const turningOn = !prev.has(entry.id)
      for (const row of range) {
        if (turningOn) next.add(row.id)
        else next.delete(row.id)
      }
      return next
    })
  }

  /**
   * Apply a single-entry write across the selection.
   *
   * One request per row against the endpoints a single edit already uses. There is no
   * bulk endpoint and this does not add one: a second write path onto these columns
   * would have to re-derive the rules the single-entry handler owns (what an absent
   * key means, what a rename does to a sign-off), and a fifty-row admin edit is not
   * worth that. Sequential, so a failure part-way leaves a legible half-done state
   * with the rows that did save already visible, rather than an unordered scatter.
   */
  async function runBulk(
    progress: string,
    summary: (n: number) => string,
    fn: (entry: BrandCatalogEntry) => Promise<BrandCatalogEntry>,
  ) {
    const targets = entries.filter(e => selected.has(e.id))
    if (!targets.length) return
    setError(null); setMsg(null)
    const failures: string[] = []
    let done = 0
    for (const [i, entry] of targets.entries()) {
      setBulkBusy(`${progress} ${i + 1}/${targets.length}…`)
      try {
        applyEntryUpdate(await fn(entry))
        done++
      } catch (err: any) {
        failures.push(`${entry.name}: ${err.message ?? 'failed'}`)
      }
    }
    setBulkBusy(null)
    if (done) {
      setMsg(`${summary(done)} — regenerate the export to put ${done === 1 ? 'it' : 'them'} in front of enrichment`)
      refreshExport()
    }
    if (failures.length) {
      setError(`${failures.length} of ${targets.length} failed — ${failures.slice(0, 3).join('; ')}${failures.length > 3 ? ' …' : ''}`)
    }
  }

  if (loading) {
    return <div style={{ padding: 24, background: '#080d18', minHeight: '100vh', color: '#475569' }}>Loading…</div>
  }

  const columns: Column<BrandCatalogEntry>[] = [
    {
      key: 'name', header: 'Name', td: { color: '#f1f5f9', fontWeight: 500 },
      render: e => (
        <span style={{ opacity: e.is_active ? 1 : 0.45 }}>
          {e.name}
          {e.product_line && <span style={{ color: '#a5b4fc', fontWeight: 400 }}> · {e.product_line}</span>}
        </span>
      ),
    },
    {
      key: 'category', header: 'Category',
      render: e => e.category
        ? <span style={{ ...badge, ...categoryColor(e.category) }}>{e.category}</span>
        : <Dash />,
    },
    { key: 'subtype', header: 'Subtype', render: e => e.subtype ?? <Dash /> },
    { key: 'strain', header: 'Strain', render: e => e.strain ?? <Dash /> },
    {
      key: 'variant', header: 'Variant', td: { fontSize: 12 }, stopPropagation: true,
      render: e => (
        <InlineVariant
          entry={e}
          saving={inlineSavingId === e.id}
          onSave={value => handleInlineSave(e, 'variant', value)}
        />
      ),
    },
    {
      key: 'listings', header: 'Listings', align: 'right',
      render: e => (e.listing_count ? e.listing_count : <Dash />),
    },
    {
      key: 'verified', header: 'Verified',
      render: e => {
        const live = Object.keys(e.verified_fields ?? {})
        if (!live.length && !e.lapsed_fields.length) return <Dash />
        return (
          <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {live.map(f => (
              <span key={f} style={{ ...badge, background: '#14532d', color: '#86efac' }}>{f}</span>
            ))}
            {e.lapsed_fields.map(f => (
              <span key={f} title="Claim made against a different name — re-confirm"
                    style={{ ...badge, background: '#422006', color: '#fbbf24' }}>{f} lapsed</span>
            ))}
          </span>
        )
      },
    },
    {
      key: 'actions', header: '', align: 'right', stopPropagation: true,
      render: e => (
        <button
          onClick={() => handleSetActive(e, !e.is_active)}
          title={e.is_active
            ? 'Deactivate. Never a delete — listings point at this row.'
            : 'Put this entry back in the catalog.'}
          style={{
            ...navBtnStyle,
            padding: '3px 9px', fontSize: 12,
            color: e.is_active ? '#fca5a5' : '#86efac',
            borderColor: e.is_active ? '#7f1d1d' : '#14532d',
          }}
        >
          {e.is_active ? 'Remove' : 'Restore'}
        </button>
      ),
    },
  ]

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin/brand-catalogs')} style={navBtnStyle}>← Brand Catalogs</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
            {isNew ? 'New Brand Catalog' : catalog?.brand_name}
          </h2>
          {!isNew && catalog && (
            <span style={{ color: '#475569', fontSize: 13 }}>
              {catalog.active_entry_count} active of {catalog.entry_count} entries ·{' '}
              {catalog.listing_count.toLocaleString()} listings resolved
            </span>
          )}
        </div>

        {error && <div style={{ color: '#f87171', fontSize: 13, marginBottom: 12 }}>{error}</div>}
        {msg && <div style={{ color: '#86efac', fontSize: 13, marginBottom: 12 }}>{msg}</div>}

        {!isNew && exportStatus && (
          <ExportPanel status={exportStatus} busy={exporting} onRegenerate={handleRegenerate} />
        )}

        <form onSubmit={handleSaveMeta}>
          <div style={cardStyle}>
            <div style={sectionLabel}>Catalog</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <Field label="Brand name *">
                <input value={brandName} onChange={e => setBrandName(e.target.value)}
                       style={inputStyle} disabled={savingMeta} placeholder="Ayrloom" />
              </Field>
              <Field label="Slug (names the export file)">
                <input value={brandSlug} onChange={e => setBrandSlug(e.target.value)}
                       style={{ ...inputStyle, fontFamily: 'monospace' }} disabled={savingMeta}
                       placeholder="ayrloom" />
              </Field>
              <Field label="Source URL">
                <input value={sourceUrl} onChange={e => setSourceUrl(e.target.value)}
                       style={inputStyle} disabled={savingMeta}
                       placeholder="https://ayrloom.com/products.json?limit=250" />
              </Field>
              <Field label="Source method">
                <input value={sourceMethod} onChange={e => setSourceMethod(e.target.value)}
                       style={inputStyle} disabled={savingMeta}
                       placeholder="shopify_products_json | ld_json | rendered_page | manual" />
              </Field>
            </div>
            {!isNew && catalog && (
              <div style={{ fontSize: 12, color: '#475569', marginTop: 14 }}>
                Last fetched {catalog.fetched_at ? new Date(catalog.fetched_at).toLocaleString() : 'never'}.
                Only <code>scripts/brand_catalog.py fetch</code> can set that — it records when the
                source was actually read.
              </div>
            )}
            <div style={{ marginTop: 16 }}>
              <button type="submit" disabled={savingMeta} style={primaryBtn(savingMeta)}>
                {savingMeta ? 'Saving…' : isNew ? 'Create Catalog' : 'Save Catalog'}
              </button>
            </div>
          </div>
        </form>

        {isNew ? (
          <div style={{ color: '#475569', fontSize: 13, marginTop: 20 }}>
            Entries can be added once the catalog exists.
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '28px 0 14px', flexWrap: 'wrap' }}>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Entries</h3>
              <span style={{ color: '#475569', fontSize: 12 }}>
                {entries.length} of {total} shown
              </span>
              <form
                onSubmit={e => { e.preventDefault(); setQ(searchInput.trim()) }}
                style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}
              >
                <input
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                  placeholder="Search name, strain, line, variant, id"
                  style={{ ...inputStyle, width: 280, padding: '5px 10px', fontSize: 13 }}
                />
                <button type="submit" style={navBtnStyle}>Search</button>
                {q && (
                  <button type="button" style={navBtnStyle}
                          onClick={() => { setSearchInput(''); setQ('') }}>
                    Clear
                  </button>
                )}
              </form>
              <select value={category} onChange={e => setCategory(e.target.value)} style={selectStyle}>
                <option value="">All categories</option>
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                <option value="__null__">(uncategorised)</option>
              </select>
              <select value={status} onChange={e => setStatus(e.target.value)} style={selectStyle}>
                <option value="active">Active</option>
                <option value="inactive">Removed</option>
                <option value="all">All</option>
              </select>
              <button
                onClick={() => setEditing('new')}
                style={{ ...navBtnStyle, color: '#a5b4fc', borderColor: '#3730a3' }}
              >
                + New entry
              </button>
            </div>

            {editing && (
              <EntryEditor
                key={editing === 'new' ? 'new' : editing.id}
                catalogId={catalogId!}
                entry={editing === 'new' ? null : editing}
                onClose={() => setEditing(null)}
                onSaved={(saved, created) => {
                  if (created) {
                    setEntries(prev => [saved, ...prev])
                    setTotal(t => t + 1)
                  } else {
                    replaceEntry(saved)
                  }
                  setEditing(saved)
                  setMsg('Entry saved — regenerate the export to put it in front of enrichment')
                  refreshExport()
                }}
                onSetActive={handleSetActive}
                onError={setError}
              />
            )}

            {selected.size > 0 && (
              <BulkBar
                count={selected.size}
                busy={bulkBusy}
                anyInactive={entries.some(e => selected.has(e.id) && !e.is_active)}
                onClear={() => { setSelected(new Set()); anchorRef.current = null }}
                onSetVariant={value => runBulk(
                  'Setting variant',
                  n => `Set variant to “${value}” on ${n} ${n === 1 ? 'entry' : 'entries'}`,
                  e => api.brandCatalogs.updateEntry(catalogId!, e.id, { variant: value }),
                )}
                onClearVariant={() => runBulk(
                  'Clearing variant',
                  n => `Cleared variant on ${n} ${n === 1 ? 'entry' : 'entries'}`,
                  e => api.brandCatalogs.updateEntry(catalogId!, e.id, { variant: null }),
                )}
                onSetActive={isActive => runBulk(
                  isActive ? 'Restoring' : 'Removing',
                  n => isActive
                    ? `Restored ${n} ${n === 1 ? 'entry' : 'entries'}`
                    : `Removed ${n} ${n === 1 ? 'entry' : 'entries'} (deactivated, not deleted)`,
                  e => api.brandCatalogs.setEntryActive(catalogId!, e.id, isActive),
                )}
              />
            )}

            {entries.length === 0 ? (
              <div style={{ color: '#475569', padding: 16 }}>
                {entriesLoading ? 'Loading…' : 'No entries match these filters.'}
              </div>
            ) : (
              <AdminTable
                columns={columns}
                rows={entries}
                rowKey={e => e.id}
                onRowClick={e => setEditing(e)}
                selection={{
                  selected,
                  onToggle: toggleRow,
                  onToggleAll: checked => {
                    setSelected(checked ? new Set(entries.map(e => e.id)) : new Set())
                    anchorRef.current = null
                  },
                }}
              />
            )}

            {entries.length < total && (
              <div style={{ marginTop: 16, textAlign: 'center' }}>
                <button
                  onClick={() => loadEntries(offset + LIMIT)}
                  disabled={entriesLoading}
                  style={navBtnStyle}
                >
                  {entriesLoading ? 'Loading…' : 'Load more'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

/* ── Export state ───────────────────────────────────────────────────────────── */

/**
 * The gap between the database and the file enrichment reads.
 *
 * Given its own panel rather than a line of small print because it is the one way
 * this screen can mislead: every edit below looks like it took effect, and none of
 * it reaches the model until the export is rewritten.
 */
function ExportPanel({ status, busy, onRegenerate }: {
  status: CatalogExportStatus
  busy: boolean
  onRegenerate: () => void
}) {
  const ok = status.in_sync
  return (
    <div style={{
      background: ok ? '#0c1a12' : '#1a1405',
      border: `1px solid ${ok ? '#14532d' : '#422006'}`,
      borderRadius: 10, padding: '14px 18px', marginBottom: 20,
      display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
    }}>
      <ExportBadge status={status} />
      <div style={{ fontSize: 13, color: ok ? '#86efac' : '#fbbf24', lineHeight: 1.6, flex: 1, minWidth: 320 }}>
        {ok ? (
          <>
            <code style={{ color: '#64748b' }}>{status.path}</code> matches the database
            ({status.db_entry_count} active entries). Enrichment is seeing what is stored here.
          </>
        ) : (
          <>
            <code style={{ color: '#a16207' }}>{status.path}</code>{' '}
            {status.file_exists
              ? <>disagrees with the database: {status.added} to add, {status.removed} to remove,{' '}
                 {status.changed} changed{status.metadata_changed ? ', plus catalog metadata' : ''}.</>
              : <>has not been generated yet ({status.db_entry_count} active entries here).</>}
            {' '}Enrichment reads that file, so these edits are not in front of the model until it is regenerated.
            {status.sample.length > 0 && (
              <div style={{ color: '#a16207', fontSize: 12, marginTop: 6 }}>
                {status.sample.map((s, i) => (
                  <span key={i}>{i > 0 && ' · '}{s.kind} {s.name}{s.variant ? ` (${s.variant})` : ''}</span>
                ))}
              </div>
            )}
          </>
        )}
        {status.file_generated_at && (
          <div style={{ color: '#475569', fontSize: 11, marginTop: 6 }}>
            File written {new Date(status.file_generated_at).toLocaleString()}
            {status.file_entry_count != null && ` · ${status.file_entry_count} entries`}
          </div>
        )}
      </div>
      <button onClick={onRegenerate} disabled={busy} style={primaryBtn(busy)}>
        {busy ? 'Writing…' : 'Regenerate export'}
      </button>
    </div>
  )
}

/* ── Inline variant cell ────────────────────────────────────────────────────── */

/**
 * The variant column, editable where it is read.
 *
 * Click to edit, Enter or blur to save, Escape to abandon. Blur saves rather than
 * cancels because the common motion is to fix a cell and click straight into the
 * next one — cancelling there would silently drop the edit the user just typed.
 * Escape is the way out, and it has to beat the blur it causes, hence `abandoned`.
 *
 * The draft is local to the cell: the row itself is only rewritten by the response
 * to the save, so a failed request leaves the table showing what is actually stored.
 */
function InlineVariant({ entry, saving, onSave }: {
  entry: BrandCatalogEntry
  saving: boolean
  onSave: (value: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(entry.variant ?? '')
  const abandoned = useRef(false)

  // A save, a bulk edit or a reload can change the stored value under an idle cell.
  useEffect(() => {
    if (!editing) setValue(entry.variant ?? '')
  }, [entry.variant, editing])

  const signedOff = 'variant' in (entry.verified_fields ?? {})

  function commit() {
    setEditing(false)
    if (abandoned.current) { abandoned.current = false; setValue(entry.variant ?? ''); return }
    onSave(value)
  }

  if (saving) {
    return <span style={{ color: '#64748b' }}>saving…</span>
  }

  if (!editing) {
    return (
      <span
        onClick={() => { abandoned.current = false; setEditing(true) }}
        title={signedOff
          ? 'Signed off. Editing overwrites the value a person vouched for — click to edit.'
          : 'Click to edit'}
        style={{
          cursor: 'text', display: 'inline-block', minWidth: 60, padding: '2px 4px',
          borderRadius: 4, borderBottom: '1px dashed #1e293b',
          opacity: entry.is_active ? 1 : 0.45,
        }}
      >
        {entry.variant ?? <Dash />}
        {signedOff && <span style={{ color: '#86efac', marginLeft: 5 }} title="signed off">✓</span>}
      </span>
    )
  }

  return (
    <input
      autoFocus
      value={value}
      onChange={e => setValue(e.target.value)}
      onFocus={e => e.currentTarget.select()}
      onBlur={commit}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.currentTarget.blur() }
        else if (e.key === 'Escape') { abandoned.current = true; e.currentTarget.blur() }
      }}
      placeholder="(empty)"
      style={{
        width: '100%', minWidth: 90, background: '#080d18', border: '1px solid #3730a3',
        borderRadius: 6, color: '#f1f5f9', fontSize: 12, padding: '4px 7px',
        outline: 'none', boxSizing: 'border-box',
      }}
    />
  )
}

/* ── Bulk actions ───────────────────────────────────────────────────────────── */

/**
 * What can be done to the current selection.
 *
 * Only the actions that are already safe one row at a time: a variant edit, and the
 * deactivate/restore flag. Nothing here deletes, for the same reason nothing else on
 * this page does — listings carry a foreign key to these rows.
 *
 * Clearing a variant and removing rows both ask first. They are the two that destroy
 * something the user cannot see all of at once: with fifty rows selected, "clear" is
 * fifty edits from one click.
 */
function BulkBar({ count, busy, anyInactive, onClear, onSetVariant, onClearVariant, onSetActive }: {
  count: number
  busy: string | null
  anyInactive: boolean
  onClear: () => void
  onSetVariant: (value: string) => void
  onClearVariant: () => void
  onSetActive: (isActive: boolean) => void
}) {
  const [variant, setVariant] = useState('')
  const disabled = busy !== null
  const noun = `${count} ${count === 1 ? 'entry' : 'entries'}`

  return (
    <div style={{
      background: '#0f172a', border: '1px solid #3730a3', borderRadius: 10,
      padding: '12px 16px', marginBottom: 12,
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    }}>
      <span style={{ fontSize: 13, color: '#a5b4fc', fontWeight: 600 }}>{noun} selected</span>

      <form
        onSubmit={e => { e.preventDefault(); if (variant.trim()) { onSetVariant(variant.trim()); setVariant('') } }}
        style={{ display: 'flex', gap: 8, alignItems: 'center' }}
      >
        <input
          value={variant}
          onChange={e => setVariant(e.target.value)}
          disabled={disabled}
          placeholder="variant to apply"
          style={{ ...inputStyle, width: 190, padding: '6px 10px', fontSize: 13 }}
        />
        <button
          type="submit"
          disabled={disabled || !variant.trim()}
          style={{ ...navBtnStyle, color: '#a5b4fc', borderColor: '#3730a3', opacity: disabled || !variant.trim() ? 0.5 : 1 }}
        >
          Set variant on {count}
        </button>
      </form>

      <button
        disabled={disabled}
        onClick={() => { if (confirm(`Clear the variant on ${noun}?`)) onClearVariant() }}
        style={{ ...navBtnStyle, opacity: disabled ? 0.5 : 1 }}
      >
        Clear variant
      </button>

      <button
        disabled={disabled}
        onClick={() => { if (confirm(`Remove ${noun} from the catalog? They are deactivated, not deleted.`)) onSetActive(false) }}
        style={{ ...navBtnStyle, color: '#fca5a5', borderColor: '#7f1d1d', opacity: disabled ? 0.5 : 1 }}
      >
        Remove
      </button>

      {anyInactive && (
        <button
          disabled={disabled}
          onClick={() => onSetActive(true)}
          style={{ ...navBtnStyle, color: '#86efac', borderColor: '#14532d', opacity: disabled ? 0.5 : 1 }}
        >
          Restore
        </button>
      )}

      <button disabled={disabled} onClick={onClear} style={{ ...navBtnStyle, marginLeft: 'auto' }}>
        Clear selection
      </button>

      <div style={{ flexBasis: '100%', fontSize: 11, color: '#475569' }}>
        {busy ?? 'Shift-click a checkbox to select a range. Each action is one save per row against the same endpoint a single edit uses, so a partial failure still leaves the rows that saved.'}
      </div>
    </div>
  )
}

/* ── Entry editor ───────────────────────────────────────────────────────────── */

/**
 * Edit one entry, or create one.
 *
 * The update payload is a *diff*: only fields the user actually changed are sent,
 * because the endpoint treats an absent key as "leave alone" and an explicit null as
 * "clear this column". Sending the whole form would turn every save into a rewrite
 * of fields nobody touched.
 *
 * `first_seen_at` and the verified_* columns are not in the form at all — the API
 * rejects them outright, and a sign-off is a separate, named action below.
 */
function EntryEditor({ catalogId, entry, onClose, onSaved, onSetActive, onError }: {
  catalogId: string
  entry: BrandCatalogEntry | null
  onClose: () => void
  onSaved: (saved: BrandCatalogEntry, created: boolean) => void
  onSetActive: (entry: BrandCatalogEntry, isActive: boolean) => void
  onError: (message: string) => void
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(entry))
  const [saving, setSaving] = useState(false)
  const [verifyBy, setVerifyBy] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [checked, setChecked] = useState<string[]>(() => Object.keys(entry?.verified_fields ?? {}))

  const isCreate = entry === null
  const original = toDraft(entry)

  function set(key: keyof Draft, value: string) {
    setDraft(prev => ({ ...prev, [key]: value }))
  }

  async function handleSave() {
    if (!draft.name.trim()) { onError('Name is required.'); return }
    setSaving(true)
    try {
      const terms = draft.match_terms.split(',').map(t => t.trim()).filter(Boolean)
      if (isCreate) {
        const payload: Record<string, unknown> = { name: draft.name.trim() }
        for (const f of TEXT_FIELDS) {
          if (f.key !== 'name' && draft[f.key].trim()) payload[f.key] = draft[f.key].trim()
        }
        if (terms.length) payload.match_terms = terms
        onSaved(await api.brandCatalogs.createEntry(catalogId, payload), true)
      } else {
        const payload: Record<string, unknown> = {}
        for (const f of TEXT_FIELDS) {
          if (draft[f.key] !== original[f.key]) {
            payload[f.key] = draft[f.key].trim() || null
          }
        }
        if (draft.match_terms !== original.match_terms) payload.match_terms = terms
        if (Object.keys(payload).length === 0) { onError('Nothing changed.'); setSaving(false); return }
        onSaved(await api.brandCatalogs.updateEntry(catalogId, entry.id, payload), false)
      }
    } catch (err: any) {
      onError(err.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleVerify() {
    if (!entry) return
    if (!verifyBy.trim()) { onError('Say who is signing off.'); return }
    setVerifying(true)
    try {
      // Sign off on the entry's stored values, not the unsaved draft: a claim has to
      // be about what is actually in the row.
      const fields: Record<string, unknown> = {}
      for (const f of checked) fields[f] = (entry as any)[f]
      const clear = Object.keys(entry.verified_fields ?? {}).filter(f => !checked.includes(f))
      onSaved(await api.brandCatalogs.verifyEntry(catalogId, entry.id, {
        fields, verified_by: verifyBy.trim(), clear,
      }), false)
    } catch (err: any) {
      onError(err.message ?? 'Sign-off failed')
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div style={{ ...cardStyle, marginBottom: 18, borderColor: '#3730a3' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <div style={sectionLabel}>{isCreate ? 'New entry' : 'Edit entry'}</div>
        {entry && !entry.is_active && (
          <span style={{ ...badge, background: '#422006', color: '#fbbf24' }}>removed from catalog</span>
        )}
        {entry && entry.listing_count ? (
          <span style={{ fontSize: 12, color: '#64748b' }}>
            {entry.listing_count} listing{entry.listing_count === 1 ? '' : 's'} resolve here
          </span>
        ) : null}
        <button onClick={onClose} style={{ ...navBtnStyle, marginLeft: 'auto' }}>Close</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {TEXT_FIELDS.map(f => (
          <Field key={f.key} label={f.label}>
            <input
              value={draft[f.key]}
              onChange={e => set(f.key, e.target.value)}
              disabled={saving}
              style={f.mono ? { ...inputStyle, fontFamily: 'monospace', fontSize: 12 } : inputStyle}
            />
          </Field>
        ))}
        <Field label="Match terms (comma separated)">
          <input
            value={draft.match_terms}
            onChange={e => set('match_terms', e.target.value)}
            disabled={saving}
            style={{ ...inputStyle, fontFamily: 'monospace', fontSize: 12 }}
          />
        </Field>
      </div>

      {entry?.attributes && (
        <div style={{ marginTop: 14 }}>
          <div style={{ ...labelStyle, marginBottom: 6 }}>Attributes (read-only)</div>
          <pre style={{
            margin: 0, background: '#080d18', border: '1px solid #1e293b', borderRadius: 8,
            padding: 10, fontSize: 12, color: '#94a3b8', overflowX: 'auto',
          }}>{JSON.stringify(entry.attributes, null, 2)}</pre>
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, marginTop: 18, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={handleSave} disabled={saving} style={primaryBtn(saving)}>
          {saving ? 'Saving…' : isCreate ? 'Create entry' : 'Save entry'}
        </button>
        {entry && (
          <button
            onClick={() => onSetActive(entry, !entry.is_active)}
            style={{
              ...navBtnStyle,
              color: entry.is_active ? '#fca5a5' : '#86efac',
              borderColor: entry.is_active ? '#7f1d1d' : '#14532d',
            }}
          >
            {entry.is_active ? 'Remove from catalog' : 'Restore to catalog'}
          </button>
        )}
        {entry && (
          <span style={{ fontSize: 11, color: '#475569' }}>
            First seen {new Date(entry.first_seen_at).toLocaleDateString()} · last seen on source{' '}
            {new Date(entry.last_seen_at).toLocaleDateString()} — neither is changed by an edit.
            Removing sets a flag; the row is never deleted, because listings point at it.
          </span>
        )}
      </div>

      {entry && (
        <div style={{ borderTop: '1px solid #1e293b', marginTop: 18, paddingTop: 16 }}>
          <div style={{ ...sectionLabel, marginBottom: 10 }}>Human sign-off</div>
          <div style={{ fontSize: 12, color: '#475569', marginBottom: 12, lineHeight: 1.6 }}>
            A signed field is one the pipeline is not allowed to overwrite. Signed here rather
            than on a listing, one sign-off covers every store carrying this product. Renaming the
            entry lapses its claims rather than carrying them onto text nobody read.
            {entry.lapsed_fields.length > 0 && (
              <span style={{ color: '#fbbf24' }}> Lapsed, needs re-confirming: {entry.lapsed_fields.join(', ')}.</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
            {VERIFIABLE.map(f => (
              <label key={f} style={{ fontSize: 13, color: '#94a3b8', display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={checked.includes(f)}
                  onChange={e => setChecked(prev => e.target.checked ? [...prev, f] : prev.filter(x => x !== f))}
                />
                {f}
                <span style={{ color: '#475569' }}>
                  {(entry as any)[f] ? `= ${(entry as any)[f]}` : '= (empty)'}
                </span>
              </label>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 12, alignItems: 'center' }}>
            <input
              value={verifyBy}
              onChange={e => setVerifyBy(e.target.value)}
              placeholder="signed off by"
              style={{ ...inputStyle, width: 200, padding: '6px 10px', fontSize: 13 }}
            />
            <button onClick={handleVerify} disabled={verifying} style={navBtnStyle}>
              {verifying ? 'Signing…' : 'Save sign-off'}
            </button>
            {entry.verified_at && (
              <span style={{ fontSize: 11, color: '#475569' }}>
                Last signed by {entry.verified_by} on {new Date(entry.verified_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Shared bits (same tokens as DispensaryEdit) ────────────────────────────── */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ ...labelStyle, marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  )
}

const labelStyle: React.CSSProperties = { fontSize: 13, color: '#94a3b8', fontWeight: 500 }
const sectionLabel: React.CSSProperties = {
  fontSize: 11, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em',
  fontWeight: 500, marginBottom: 14,
}
const cardStyle: React.CSSProperties = {
  background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 20,
}
const inputStyle: React.CSSProperties = {
  width: '100%', background: '#080d18', border: '1px solid #1e293b',
  borderRadius: 8, color: '#f1f5f9', fontSize: 14, padding: '9px 12px',
  outline: 'none', boxSizing: 'border-box',
}
function primaryBtn(busy: boolean): React.CSSProperties {
  return {
    padding: '9px 20px', background: busy ? '#1e293b' : '#4f46e5', border: 'none',
    borderRadius: 8, color: busy ? '#475569' : '#fff', fontSize: 14, fontWeight: 600,
    cursor: busy ? 'default' : 'pointer', whiteSpace: 'nowrap',
  }
}
