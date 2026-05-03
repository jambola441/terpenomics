import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from './api/client'
import type { Listing } from './types'

type Terpene = { name: string; percent?: number | null }
type Cannabinoid = { name: string; family: 'thc' | 'cbd'; percent?: number | null }

type Product = {
  id: string
  name: string
  brand?: string | null
  category: string
  is_active: boolean
  terpenes: Terpene[]
  cannabinoids: Cannabinoid[]
}

const CATEGORIES = ['flower','vaporizers','cart','edible','concentrate','preroll','tinctures','topical','merch','other']

export default function ProductEdit() {
  const { productId } = useParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [brand, setBrand] = useState('')
  const [category, setCategory] = useState('flower')
  const [isActive, setIsActive] = useState(true)
  const [terpenes, setTerpenes] = useState<Terpene[]>([{ name: '' }])
  const [cannabinoids, setCannabinoids] = useState<Cannabinoid[]>([{ name: '', family: 'thc' }])

  const [allTerpenes, setAllTerpenes] = useState<{ name: string }[]>([])
  const [allCannabinoids, setAllCannabinoids] = useState<Cannabinoid[]>([])
  const [allBrands, setAllBrands] = useState<string[]>([])
  const [listings, setListings] = useState<Listing[]>([])
  const [unmatchingId, setUnmatchingId] = useState<string | null>(null)

  const pid = useMemo(() => (productId ?? '').trim(), [productId])

  useEffect(() => {
    if (!pid) return
    void load()
  }, [pid])

  async function load() {
    setLoading(true)
    setError(null)
    setMsg(null)
    try {
      const [p, terps, cannabs, brands, listingsData] = await Promise.all([
        api.products.get(pid) as Promise<Product>,
        api.products.listAllTerpenes(),
        api.products.listAllCannabinoids(),
        api.products.listAllBrands(),
        api.listings.list({ product_id: pid, limit: 200 }),
      ])
      setAllTerpenes(terps)
      setAllCannabinoids(cannabs)
      setAllBrands(brands)
      setListings(listingsData)
      setName(p.name ?? '')
      setBrand(p.brand ?? '')
      setCategory(p.category ?? 'other')
      setIsActive(Boolean(p.is_active))
      setTerpenes(p.terpenes?.length ? p.terpenes.map(t => ({ name: t.name, percent: t.percent ?? null })) : [{ name: '' }])
      setCannabinoids(p.cannabinoids?.length ? p.cannabinoids.map(c => ({ name: c.name, family: c.family, percent: c.percent ?? null })) : [{ name: '', family: 'thc' }])
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setLoading(false)
    }
  }

  function updateTerpene(idx: number, field: keyof Terpene, value: any) {
    setTerpenes(prev => prev.map((t, i) => (i === idx ? { ...t, [field]: value } : t)))
  }

  function handleCannabinoidNameChange(idx: number, value: string) {
    const match = allCannabinoids.find(c => c.name === value)
    setCannabinoids(prev => prev.map((c, i) =>
      i === idx ? { ...c, name: value, family: match ? match.family : c.family } : c
    ))
  }

  function updateCannabinoidPercent(idx: number, value: number | null) {
    setCannabinoids(prev => prev.map((c, i) => (i === idx ? { ...c, percent: value } : c)))
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setMsg(null)
    try {
      await api.products.update(pid, {
        name,
        brand: brand || null,
        category,
        is_active: isActive,
        terpenes: terpenes
          .filter(t => t.name.trim() !== '')
          .map(t => ({ name: t.name.trim(), percent: t.percent ?? null })),
        cannabinoids: cannabinoids
          .filter(c => allCannabinoids.some(ac => ac.name === c.name.trim()))
          .map(c => ({ name: c.name.trim(), family: c.family, percent: c.percent ?? null })),
      })
      setMsg('Saved')
      await load()
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleUnmatch(listingId: string) {
    setUnmatchingId(listingId)
    try {
      await api.listings.unmatch(listingId)
      setListings(prev => prev.filter(l => l.id !== listingId))
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setUnmatchingId(null)
    }
  }

  if (loading) return <div style={{ padding: 24, background: '#080d18', minHeight: '100vh', color: '#475569', fontFamily: "'Inter', system-ui, sans-serif" }}>Loading…</div>

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 760, margin: '0 auto' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 32 }}>
          <button onClick={() => navigate(-1)} style={navBtnStyle}>← Back</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>{name || 'Edit Product'}</h2>
          {!isActive && <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 10, background: '#1e293b', color: '#475569' }}>inactive</span>}
        </div>

        {error && <div style={{ marginBottom: 16, padding: '10px 14px', background: '#450a0a', color: '#fca5a5', borderRadius: 6, fontSize: 14 }}>{error}</div>}
        {msg && <div style={{ marginBottom: 16, padding: '10px 14px', background: '#14532d30', color: '#86efac', borderRadius: 6, fontSize: 14, border: '1px solid #14532d' }}>✓ {msg}</div>}

        <datalist id="terpene-options">{allTerpenes.map(t => <option key={t.name} value={t.name} />)}</datalist>
        <datalist id="cannabinoid-options">{allCannabinoids.map(c => <option key={c.name} value={c.name} />)}</datalist>
        <datalist id="brand-options">{allBrands.map(b => <option key={b} value={b} />)}</datalist>

        <form onSubmit={save}>
          {/* Core fields */}
          <div style={{ background: '#0a0f1a', border: '1px solid #1e293b', borderRadius: 10, padding: '20px 24px', marginBottom: 16 }}>
            <h3 style={sectionHeadStyle}>Details</h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={labelStyle}>Name</label>
                <input list="brand-options-name" value={name} onChange={e => setName(e.target.value)} required style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Brand</label>
                <input list="brand-options" value={brand} onChange={e => setBrand(e.target.value)} style={inputStyle} />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <label style={labelStyle}>Category</label>
                <select value={category} onChange={e => setCategory(e.target.value)} style={inputStyle}>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 2 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 14, color: '#94a3b8' }}>
                  <div
                    onClick={() => setIsActive(v => !v)}
                    style={{
                      width: 36, height: 20, borderRadius: 10, cursor: 'pointer', transition: 'background 0.2s',
                      background: isActive ? '#4f46e5' : '#1e293b', position: 'relative', flexShrink: 0,
                    }}
                  >
                    <div style={{
                      position: 'absolute', top: 3, left: isActive ? 19 : 3, width: 14, height: 14,
                      borderRadius: '50%', background: isActive ? '#fff' : '#475569', transition: 'left 0.2s',
                    }} />
                  </div>
                  Active
                </label>
              </div>
            </div>
          </div>

          {/* Terpenes */}
          <div style={{ background: '#0a0f1a', border: '1px solid #1e293b', borderRadius: 10, padding: '20px 24px', marginBottom: 16 }}>
            <h3 style={sectionHeadStyle}>Terpenes</h3>
            {terpenes.map((t, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                <input
                  list="terpene-options"
                  placeholder="Name"
                  value={t.name}
                  onChange={e => updateTerpene(i, 'name', e.target.value)}
                  style={{ ...inputStyle, flex: 2 }}
                />
                <input
                  placeholder="%"
                  type="number" min="0" max="100" step="0.001"
                  value={t.percent ?? ''}
                  onChange={e => updateTerpene(i, 'percent', e.target.value === '' ? null : Number(e.target.value))}
                  style={{ ...inputStyle, width: 100 }}
                />
                <button type="button" onClick={() => setTerpenes(prev => prev.filter((_, j) => j !== i))} style={removeBtnStyle}>✕</button>
              </div>
            ))}
            <button type="button" onClick={() => setTerpenes(prev => [...prev, { name: '' }])} style={addBtnStyle}>+ Add terpene</button>
          </div>

          {/* Cannabinoids */}
          <div style={{ background: '#0a0f1a', border: '1px solid #1e293b', borderRadius: 10, padding: '20px 24px', marginBottom: 24 }}>
            <h3 style={sectionHeadStyle}>Cannabinoids</h3>
            {cannabinoids.map((c, i) => {
              const knownFamily = allCannabinoids.find(ac => ac.name === c.name.trim())?.family
              return (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                  <input
                    list="cannabinoid-options"
                    placeholder="Name"
                    value={c.name}
                    onChange={e => handleCannabinoidNameChange(i, e.target.value)}
                    style={{ ...inputStyle, flex: 2 }}
                  />
                  <span style={{ width: 44, textAlign: 'center', fontSize: 11, fontWeight: 700, color: knownFamily === 'thc' ? '#a78bfa' : knownFamily === 'cbd' ? '#67e8f9' : '#334155', letterSpacing: '0.05em' }}>
                    {knownFamily ? knownFamily.toUpperCase() : '—'}
                  </span>
                  <input
                    placeholder="%"
                    type="number" min="0" max="100" step="0.01"
                    value={c.percent ?? ''}
                    onChange={e => updateCannabinoidPercent(i, e.target.value === '' ? null : Number(e.target.value))}
                    style={{ ...inputStyle, width: 100 }}
                  />
                  <button type="button" onClick={() => setCannabinoids(prev => prev.filter((_, j) => j !== i))} style={removeBtnStyle}>✕</button>
                </div>
              )
            })}
            <button type="button" onClick={() => setCannabinoids(prev => [...prev, { name: '', family: 'thc' }])} style={addBtnStyle}>+ Add cannabinoid</button>
          </div>

          <button type="submit" disabled={saving} style={{ padding: '10px 28px', fontSize: 14, fontWeight: 600, borderRadius: 6, border: 'none', background: saving ? '#1e293b' : '#4f46e5', color: saving ? '#475569' : '#fff', cursor: saving ? 'not-allowed' : 'pointer' }}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </form>

        {/* Listings */}
        {listings.length > 0 && (
          <div style={{ marginTop: 48 }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600, color: '#94a3b8' }}>
              Listings <span style={{ color: '#334155', fontWeight: 400 }}>({listings.length})</span>
            </h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                  <th style={thStyle}>Dispensary</th>
                  <th style={thStyle}>Scraped Name</th>
                  <th style={thStyle}>Category</th>
                  <th style={thStyle}>Variant</th>
                  <th style={thStyle}>Price</th>
                  <th style={thStyle}>Stock</th>
                  <th style={thStyle}>Scraped</th>
                  <th style={thStyle} />
                </tr>
              </thead>
              <tbody>
                {listings.map(l => (
                  <tr key={l.id} style={{ borderBottom: '1px solid #0f172a' }}>
                    <td style={tdStyle}>
                      {l.url
                        ? <a href={l.url} target="_blank" rel="noreferrer" style={{ color: '#64748b' }}>{l.dispensary_slug}</a>
                        : <span style={{ color: '#64748b' }}>{l.dispensary_slug}</span>}
                    </td>
                    <td style={tdStyle}>{l.scraped_name ?? <span style={{ color: '#334155' }}>—</span>}</td>
                    <td style={tdStyle}>{l.scraped_category ?? <span style={{ color: '#334155' }}>—</span>}</td>
                    <td style={tdStyle}>{l.variant ?? <span style={{ color: '#334155' }}>—</span>}</td>
                    <td style={{ ...tdStyle, fontVariantNumeric: 'tabular-nums' }}>
                      {l.price_cents != null ? `$${(l.price_cents / 100).toFixed(2)}` : <span style={{ color: '#334155' }}>—</span>}
                    </td>
                    <td style={tdStyle}>{l.in_stock ? <span style={{ color: '#86efac' }}>✓</span> : <span style={{ color: '#334155' }}>✗</span>}</td>
                    <td style={{ ...tdStyle, color: '#334155', fontSize: 12 }}>{l.scraped_at ? new Date(l.scraped_at).toLocaleDateString() : '—'}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>
                      <button
                        type="button"
                        onClick={() => handleUnmatch(l.id)}
                        disabled={unmatchingId === l.id}
                        style={{ padding: '3px 8px', fontSize: 11, background: 'transparent', border: '1px solid #1e293b', borderRadius: 4, color: '#475569', cursor: 'pointer' }}
                      >
                        {unmatchingId === l.id ? '…' : 'unmatch'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
const sectionHeadStyle: React.CSSProperties = { margin: '0 0 16px', fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#475569' }
const labelStyle: React.CSSProperties = { display: 'block', fontSize: 12, fontWeight: 500, color: '#64748b', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }
const inputStyle: React.CSSProperties = { width: '100%', padding: '8px 10px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#f1f5f9', fontSize: 14, boxSizing: 'border-box' }
const addBtnStyle: React.CSSProperties = { marginTop: 4, padding: '5px 12px', fontSize: 12, background: 'transparent', border: '1px solid #1e293b', borderRadius: 5, color: '#64748b', cursor: 'pointer' }
const removeBtnStyle: React.CSSProperties = { padding: '4px 8px', fontSize: 12, background: 'transparent', border: '1px solid #1e293b', borderRadius: 4, color: '#334155', cursor: 'pointer', flexShrink: 0 }
const thStyle: React.CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
