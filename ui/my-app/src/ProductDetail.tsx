import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api from './api/client'
import type { Product } from './types'
import { t, font } from './theme'
import { Icon } from './components/Icon'
import { badge, categoryColor, navBtnStyle, pageWrap, tdStyle, thStyle } from './components/AdminTable'

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
    if (!v || v === NULL_SENTINEL) return <span style={{ color: t.text3 }}>—</span>
    return v
  }

  const p = data?.product

  return (
    <div style={pageWrap}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin/products')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Products</button>
          <h2 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Product Detail</h2>
        </div>

        {loading && <div style={{ color: t.text3 }}>Loading…</div>}
        {error && <div style={{ color: t.danger }}>{error}</div>}

        {p && (
          <>
            {/* Tuple identity card */}
            <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 8, padding: 20, marginBottom: 28 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 16 }}>
                <Stat label="Brand"        value={displayVal(p.brand)} />
                <Stat label="Category"    value={<span style={{ ...badge, ...categoryColor(p.category) }}>{p.category}</span>} />
                <Stat label="Subtype"     value={displayVal(p.subtype)} />
                <Stat label="Product Line" value={displayVal(p.product_line)} />
                <Stat label="Strain"      value={<span style={{ color: t.text1 }}>{p.strain ?? '—'}</span>} />
                <Stat label="Variant"     value={displayVal(p.variant)} />
              </div>

              <div style={{ height: 1, background: t.border, margin: '16px 0' }} />

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 16 }}>
                <Stat label="Stores"     value={<span style={{ color: p.dispensary_count > 1 ? t.success : t.text2 }}>{p.dispensary_count}</span>} />
                <Stat label="Listings"   value={String(p.listing_count)} />
                <Stat label="Min price"  value={fmt(p.min_price_cents)} />
                <Stat label="Max price"  value={fmt(p.max_price_cents)} />
                <Stat label="In stock"   value={p.any_in_stock ? <span style={{ color: t.success }}>Yes</span> : <span style={{ color: t.text3 }}>No</span>} />
              </div>
            </div>

            {/* Listings table */}
            <h3 style={{ margin: '0 0 12px', fontFamily: font.family.display, fontSize: font.size.title, fontWeight: 600, color: t.text1 }}>
              Listings ({data!.listings.length})
            </h3>

            {data!.listings.length === 0 ? (
              <div style={{ color: t.text3 }}>No listings found.</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ color: t.text3, textAlign: 'left', borderBottom: `1px solid ${t.borderStrong}` }}>
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
                    <tr key={l.id} style={{ borderBottom: `1px solid ${t.border}`, cursor: 'pointer' }}
                      onClick={() => navigate(`/admin/listings/${l.id}`)}
                      onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = t.surface2}
                      onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'}
                    >
                      <td style={{ ...tdStyle, color: t.text1, fontWeight: 500 }}>{l.dispensary_name}</td>
                      <td style={{ ...tdStyle, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {l.scraped_name ?? <span style={{ color: t.text3 }}>—</span>}
                      </td>
                      <td style={{ ...tdStyle, color: t.text3, fontFamily: font.family.mono, fontSize: 11 }}>
                        {l.sku ?? <span style={{ color: t.text3 }}>—</span>}
                      </td>
                      <td style={tdStyle}>{fmt(l.price_cents)}</td>
                      <td style={tdStyle}>
                        {l.classification ?? <span style={{ color: t.text3 }}>—</span>}
                      </td>
                      <td style={tdStyle}>
                        {l.in_stock
                          ? <Icon name="check" size={15} color={t.success} label="In stock" />
                          : <Icon name="close" size={15} color={t.text4} label="Out of stock" />}
                      </td>
                      <td style={{ ...tdStyle, color: t.text3, fontSize: 11 }}>
                        {l.scraped_at ? new Date(l.scraped_at).toLocaleDateString() : '—'}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right' }} onClick={e => e.stopPropagation()}>
                        {l.url && (
                          <a href={l.url} target="_blank" rel="noopener noreferrer"
                            style={{ color: t.accent, textDecoration: 'none', display: 'inline-flex' }}
                            title={l.url}><Icon name="arrow-up-right" size={15} label="Open on store site" /></a>
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
      <div style={{ fontSize: 11, color: t.text3, fontFamily: font.family.mono, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 14, color: t.text2, fontWeight: 500 }}>{value}</div>
    </div>
  )
}
