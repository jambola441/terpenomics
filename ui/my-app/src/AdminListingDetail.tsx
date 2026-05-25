import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from './api/client'
import type { Listing } from './types'

const NULL_SENTINEL = '__null__'
function enc(v: string | null) { return v ?? NULL_SENTINEL }

function tupleProductUrl(l: Listing) {
  const p = new URLSearchParams({
    brand:        enc(l.scraped_brand),
    category:     l.scraped_category ?? '',
    subtype:      enc(l.subtype),
    product_line: enc(l.product_line),
    strain:       enc(l.strain),
    variant:      enc(l.variant),
  })
  return `/admin/products/detail?${p.toString()}`
}

function fmt(cents: number | null) {
  return cents != null ? `$${(cents / 100).toFixed(2)}` : null
}

export default function AdminListingDetail() {
  const { listingId } = useParams<{ listingId: string }>()
  const navigate = useNavigate()
  const [listing, setListing] = useState<Listing | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!listingId) return
    api.listings.get(listingId)
      .then(setListing)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [listingId])

  async function saveField(field: 'product_line' | 'strain', value: string) {
    if (!listingId) return
    const updated = await api.listings.update(listingId, { [field]: value })
    setListing(updated)
  }

  if (loading) return <div style={{ padding: 24, background: '#080d18', minHeight: '100vh', color: '#475569' }}>Loading…</div>
  if (error || !listing) return <div style={{ padding: 24, background: '#080d18', minHeight: '100vh', color: '#f87171' }}>{error ?? 'Not found'}</div>

  const l = listing

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>

        {/* Nav */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/admin/listings')} style={navBtnStyle}>← Listings</button>
          {l.scraped_category && (
            <a
              href={tupleProductUrl(l)}
              onClick={e => { e.preventDefault(); navigate(tupleProductUrl(l)) }}
              style={{ ...navBtnStyle, color: '#a5b4fc', borderColor: '#3730a3', textDecoration: 'none' }}
            >
              View product →
            </a>
          )}
          <a
            href={`/admin/dispensaries/${l.dispensary_id}`}
            onClick={e => { e.preventDefault(); navigate(`/admin/dispensaries/${l.dispensary_id}`) }}
            style={{ ...navBtnStyle, textDecoration: 'none' }}
          >
            {l.dispensary_name}
          </a>
          {l.url && (
            <a href={l.url} target="_blank" rel="noopener noreferrer" style={{ ...navBtnStyle, color: '#6366f1', borderColor: '#4338ca', textDecoration: 'none' }}>
              View on site ↗
            </a>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: l.image_url ? '200px 1fr' : '1fr', gap: 28, alignItems: 'start' }}>

          {/* Image */}
          {l.image_url && (
            <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, overflow: 'hidden', aspectRatio: '1', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <img
                src={l.image_url}
                alt={l.scraped_name ?? ''}
                style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                onError={e => (e.currentTarget.style.display = 'none')}
              />
            </div>
          )}

          {/* Main card */}
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 24 }}>
            <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 700, color: '#f1f5f9' }}>
              {l.scraped_name ?? <span style={{ color: '#475569' }}>Unnamed listing</span>}
            </h2>
            {l.scraped_brand && (
              <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 20 }}>{l.scraped_brand}</div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 16, marginBottom: 20 }}>
              <StatField label="Category">{l.scraped_category ? <span style={{ ...badge, ...categoryColor(l.scraped_category) }}>{l.scraped_category}</span> : dash}</StatField>
              <StatField label="Subtype">{l.subtype ?? dash}</StatField>
              <InlineEditField
                label="Product Line"
                value={l.product_line}
                onSave={v => saveField('product_line', v)}
              />
              <InlineEditField
                label="Strain"
                value={l.strain}
                onSave={v => saveField('strain', v)}
                inputColor="#a5b4fc"
              />
              <StatField label="Classification">{l.classification ?? dash}</StatField>
              <StatField label="Variant">{l.variant ?? dash}</StatField>
              <StatField label="Price">{fmt(l.price_cents) ?? dash}</StatField>
              <StatField label="SKU"><span style={{ fontFamily: 'monospace', fontSize: 11, color: '#64748b' }}>{l.sku ?? dash}</span></StatField>
              <StatField label="In Stock">{l.in_stock ? <span style={{ color: '#86efac' }}>Yes</span> : <span style={{ color: '#475569' }}>No</span>}</StatField>
              <StatField label="Active">{l.is_active ? <span style={{ color: '#86efac' }}>Yes</span> : <span style={{ color: '#475569' }}>No</span>}</StatField>
              <StatField label="Scraped">{l.scraped_at ? new Date(l.scraped_at).toLocaleDateString() : dash}</StatField>
            </div>

            {l.description && (
              <>
                <div style={{ height: 1, background: '#1e293b', marginBottom: 16 }} />
                <div style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>{l.description}</div>
              </>
            )}
          </div>
        </div>

        {/* IDs / metadata footer */}
        <div style={{ marginTop: 20, background: '#0a0f1c', border: '1px solid #1e293b', borderRadius: 8, padding: '14px 18px', display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <MetaRow label="Listing ID" value={l.id} mono />
          <MetaRow label="Dispensary ID" value={l.dispensary_id} mono />
          <MetaRow label="Created" value={new Date(l.created_at).toLocaleString()} />
          <MetaRow label="Updated" value={new Date(l.updated_at).toLocaleString()} />
        </div>

      </div>
    </div>
  )
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

function InlineEditField({
  label,
  value,
  onSave,
  inputColor,
}: {
  label: string
  value: string | null
  onSave: (v: string) => Promise<void>
  inputColor?: string
}) {
  const [draft, setDraft] = useState(value ?? '')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Keep draft in sync when the parent refreshes the listing after a save
  useEffect(() => {
    setDraft(value ?? '')
  }, [value])

  async function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter') return
    const next = draft.trim()
    const prev = value ?? ''
    if (next === prev) return
    if (savedTimer.current) clearTimeout(savedTimer.current)
    setStatus('saving')
    try {
      await onSave(next)
      setStatus('saved')
      savedTimer.current = setTimeout(() => setStatus('idle'), 2000)
    } catch {
      setStatus('error')
      savedTimer.current = setTimeout(() => setStatus('idle'), 3000)
    }
  }

  const dirty = status === 'idle' && draft.trim() !== (value ?? '')

  const indicator =
    status === 'saving' ? <span style={{ color: '#475569', fontSize: 13 }}>…</span>
    : status === 'saved'  ? <span style={{ color: '#86efac', fontSize: 13 }}>✓</span>
    : status === 'error'  ? <span style={{ color: '#f87171', fontSize: 13 }}>✕</span>
    : dirty               ? <span style={{ color: '#475569', fontSize: 13 }}>?</span>
    : null

  return (
    <div>
      <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <input
          value={draft}
          onChange={e => { setDraft(e.target.value); setStatus('idle') }}
          onKeyDown={handleKeyDown}
          placeholder="—"
          style={{
            fontSize: 14,
            fontWeight: 500,
            fontFamily: "'Inter', system-ui, sans-serif",
            color: inputColor ?? '#cbd5e1',
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid #1e293b',
            outline: 'none',
            width: '100%',
            padding: '2px 0',
          }}
          onFocus={e => (e.currentTarget.style.borderBottomColor = '#3730a3')}
          onBlur={e => (e.currentTarget.style.borderBottomColor = '#1e293b')}
        />
        {indicator}
      </div>
    </div>
  )
}

const dash = <span style={{ color: '#475569' }}>—</span>

function StatField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 500, color: '#cbd5e1' }}>{children}</div>
    </div>
  )
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 11, color: '#64748b', fontFamily: mono ? 'monospace' : undefined }}>{value}</div>
    </div>
  )
}

const CATEGORY_COLORS: Record<string, { background: string; color: string }> = {
  flower:      { background: '#14532d', color: '#86efac' },
  preroll:     { background: '#1a2e05', color: '#a3e635' },
  vaporizers:  { background: '#1e1b4b', color: '#a5b4fc' },
  concentrate: { background: '#431407', color: '#fdba74' },
  edible:      { background: '#4a1942', color: '#f0abfc' },
  tinctures:   { background: '#0c4a6e', color: '#7dd3fc' },
  topical:     { background: '#3b3a2a', color: '#fde68a' },
  merch:       { background: '#1c1917', color: '#a8a29e' },
}
function categoryColor(cat: string) {
  return CATEGORY_COLORS[cat] ?? { background: '#1e293b', color: '#94a3b8' }
}

const badge: React.CSSProperties = { padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 600 }
const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
