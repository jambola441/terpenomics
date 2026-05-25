import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api from './api/client'
import type { Product } from './types'

const NULL_SENTINEL = '__null__'

type DetailListing = {
  id: string
  dispensary_id: string
  dispensary_name: string
  dispensary_slug: string
  scraped_name: string | null
  price_cents: number | null
  variant: string | null
  sku: string | null
  url: string | null
  image_url: string | null
  in_stock: boolean
  classification: string | null
  scraped_at: string | null
}

type DetailResponse = {
  product: Product
  listings: DetailListing[]
}

function fmt(cents: number | null) {
  return cents != null ? `$${(cents / 100).toFixed(2)}` : '—'
}

export default function ProductDetail() {
  const [data, setData] = useState<DetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const brand        = params.get('brand')        ?? undefined
  const category     = params.get('category')     ?? undefined
  const subtype      = params.get('subtype')       ?? undefined
  const product_line = params.get('product_line') ?? undefined
  const strain       = params.get('strain')        ?? undefined
  const variant      = params.get('variant')       ?? undefined

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.products.getDetail({ brand, category, subtype, product_line, strain, variant })
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [brand, category, subtype, product_line, strain, variant])

  function displayVal(v: string | null | undefined) {
    if (!v || v === NULL_SENTINEL) return <span style={{ color: '#475569' }}>—</span>
    return v
  }

  const p = data?.product

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin/products')} style={navBtnStyle}>← Products</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Product Detail</h2>
        </div>

        {loading && <div style={{ color: '#475569' }}>Loading…</div>}
        {error && <div style={{ color: '#f87171' }}>{error}</div>}

        {p && (
          <>
            {/* Tuple identity card */}
            <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, padding: 20, marginBottom: 28 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 16 }}>
                <Stat label="Brand"        value={displayVal(p.brand)} />
                <Stat label="Category"    value={<span style={{ ...badge, ...categoryColor(p.category) }}>{p.category}</span>} />
                <Stat label="Subtype"     value={displayVal(p.subtype)} />
                <Stat label="Product Line" value={displayVal(p.product_line)} />
                <Stat label="Strain"      value={<span style={{ color: '#a5b4fc' }}>{p.strain ?? '—'}</span>} />
                <Stat label="Variant"     value={displayVal(p.variant)} />
              </div>

              <div style={{ height: 1, background: '#1e293b', margin: '16px 0' }} />

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 16 }}>
                <Stat label="Stores"     value={<span style={{ color: p.dispensary_count > 1 ? '#86efac' : '#94a3b8' }}>{p.dispensary_count}</span>} />
                <Stat label="Listings"   value={String(p.listing_count)} />
                <Stat label="Min price"  value={fmt(p.min_price_cents)} />
                <Stat label="Max price"  value={fmt(p.max_price_cents)} />
                <Stat label="In stock"   value={p.any_in_stock ? <span style={{ color: '#86efac' }}>Yes</span> : <span style={{ color: '#475569' }}>No</span>} />
              </div>
            </div>

            {/* Listings table */}
            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Listings ({data!.listings.length})
            </h3>

            {data!.listings.length === 0 ? (
              <div style={{ color: '#475569' }}>No listings found.</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                    <th style={thStyle}>Dispensary</th>
                    <th style={thStyle}>Scraped Name</th>
                    <th style={thStyle}>SKU</th>
                    <th style={thStyle}>Price</th>
                    <th style={thStyle}>Class</th>
                    <th style={thStyle}>In Stock</th>
                    <th style={thStyle}>Scraped</th>
                    <th style={thStyle}></th>
                  </tr>
                </thead>
                <tbody>
                  {data!.listings.map(l => (
                    <tr key={l.id} style={{ borderBottom: '1px solid #0f172a', cursor: 'pointer' }}
                      onClick={() => navigate(`/admin/listings/${l.id}`)}
                      onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = '#0f172a'}
                      onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'}
                    >
                      <td style={{ ...tdStyle, color: '#f1f5f9', fontWeight: 500 }}>{l.dispensary_name}</td>
                      <td style={{ ...tdStyle, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {l.scraped_name ?? <span style={{ color: '#475569' }}>—</span>}
                      </td>
                      <td style={{ ...tdStyle, color: '#64748b', fontFamily: 'monospace', fontSize: 11 }}>
                        {l.sku ?? <span style={{ color: '#475569' }}>—</span>}
                      </td>
                      <td style={tdStyle}>{fmt(l.price_cents)}</td>
                      <td style={tdStyle}>
                        {l.classification ?? <span style={{ color: '#475569' }}>—</span>}
                      </td>
                      <td style={tdStyle}>
                        {l.in_stock
                          ? <span style={{ color: '#86efac' }}>✓</span>
                          : <span style={{ color: '#475569' }}>✗</span>}
                      </td>
                      <td style={{ ...tdStyle, color: '#475569', fontSize: 11 }}>
                        {l.scraped_at ? new Date(l.scraped_at).toLocaleDateString() : '—'}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right' }} onClick={e => e.stopPropagation()}>
                        {l.url && (
                          <a href={l.url} target="_blank" rel="noopener noreferrer"
                            style={{ color: '#6366f1', textDecoration: 'none', fontSize: 14 }}
                            title={l.url}>↗</a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 14, color: '#cbd5e1', fontWeight: 500 }}>{value}</div>
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

const badge: React.CSSProperties = { padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 500 }
const thStyle: React.CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
