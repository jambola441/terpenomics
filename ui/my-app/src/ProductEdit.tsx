// src/ProductEdit.tsx
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import supabase  from './utils/supabase'

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

const API_BASE = 'https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev'

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

  const pid = useMemo(() => (productId ?? '').trim(), [productId])

  useEffect(() => {
    if (!pid) return
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid])

  async function authHeader() {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (!token) throw new Error('Not authenticated')
    return { Authorization: `Bearer ${token}` }
  }

  async function load() {
    setLoading(true)
    setError(null)
    setMsg(null)
    try {
      const headers = await authHeader()
      const [productRes, terpenesRes, cannabinoidsRes] = await Promise.all([
        fetch(`${API_BASE}/admin/products/${pid}`, { headers }),
        fetch(`${API_BASE}/admin/products/terpenes`, { headers }),
        fetch(`${API_BASE}/admin/products/cannabinoids`, { headers }),
      ])

      if (!productRes.ok) throw new Error(await productRes.text())
      if (!terpenesRes.ok) throw new Error(await terpenesRes.text())
      if (!cannabinoidsRes.ok) throw new Error(await cannabinoidsRes.text())

      const p: Product = await productRes.json()
      const terps: { name: string }[] = await terpenesRes.json()
      const cannabs: Cannabinoid[] = await cannabinoidsRes.json()

      setAllTerpenes(terps)
      setAllCannabinoids(cannabs)

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

  function addTerpeneRow() {
    setTerpenes(prev => [...prev, { name: '' }])
  }

  function removeTerpeneRow(idx: number) {
    setTerpenes(prev => prev.filter((_, i) => i !== idx))
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

  function addCannabinoidRow() {
    setCannabinoids(prev => [...prev, { name: '', family: 'thc' }])
  }

  function removeCannabinoidRow(idx: number) {
    setCannabinoids(prev => prev.filter((_, i) => i !== idx))
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setMsg(null)

    try {
      const headers = await authHeader()
      const payload = {
        name,
        brand: brand || null,
        category,
        is_active: isActive,
        terpenes: terpenes
          .filter(t => t.name.trim() !== '')
          .map(t => ({
            name: t.name.trim(),
            percent: t.percent === '' ? null : t.percent ?? null,
          })),
        cannabinoids: cannabinoids
          .filter(c => allCannabinoids.some(ac => ac.name === c.name.trim()))
          .map(c => ({
            name: c.name.trim(),
            family: c.family,
            percent: c.percent === '' ? null : c.percent ?? null,
          })),
      }

      const res = await fetch(`${API_BASE}/admin/products/${pid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify(payload),
      })

      if (!res.ok) throw new Error(await res.text())
      setMsg('Saved')
      await load()
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div style={{ padding: 24 }}>Loading…</div>
  if (error) return <div style={{ padding: 24 }}>Error: {error}</div>

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Edit Product</h1>
        <button type="button" onClick={() => navigate(-1)}>Back</button>
      </div>

      <datalist id="terpene-options">
        {allTerpenes.map(t => <option key={t.name} value={t.name} />)}
      </datalist>

      <datalist id="cannabinoid-options">
        {allCannabinoids.map(c => <option key={c.name} value={c.name} />)}
      </datalist>

      <form onSubmit={save}>
        <div style={{ marginBottom: 10 }}>
          <label>Name</label>
          <input value={name} onChange={e => setName(e.target.value)} required style={{ width: '100%' }} />
        </div>

        <div style={{ marginBottom: 10 }}>
          <label>Brand</label>
          <input value={brand} onChange={e => setBrand(e.target.value)} style={{ width: '100%' }} />
        </div>

        <div style={{ marginBottom: 10 }}>
          <label>Category</label>
          <select value={category} onChange={e => setCategory(e.target.value)} style={{ width: '100%' }}>
            <option value="flower">flower</option>
            <option value="cart">cart</option>
            <option value="edible">edible</option>
            <option value="concentrate">concentrate</option>
            <option value="preroll">preroll</option>
            <option value="tincture">tincture</option>
            <option value="topical">topical</option>
            <option value="merch">merch</option>
            <option value="other">other</option>
          </select>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label>
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
            {' '}Active
          </label>
        </div>

        <h3>Terpenes</h3>

        {terpenes.map((t, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input
              list="terpene-options"
              placeholder="Name"
              value={t.name}
              onChange={e => updateTerpene(i, 'name', e.target.value)}
              style={{ flex: 2 }}
            />
            <input
              placeholder="%"
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={t.percent ?? ''}
              onChange={e => updateTerpene(i, 'percent', e.target.value === '' ? null : Number(e.target.value))}
              style={{ width: 120 }}
            />
            {terpenes.length > 1 && (
              <button type="button" onClick={() => removeTerpeneRow(i)}>✕</button>
            )}
          </div>
        ))}

        <button type="button" onClick={addTerpeneRow}>+ Add terpene</button>

        <h3>Cannabinoids</h3>

        {cannabinoids.map((c, i) => {
          const knownFamily = allCannabinoids.find(ac => ac.name === c.name.trim())?.family
          return (
            <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
              <input
                list="cannabinoid-options"
                placeholder="Name"
                value={c.name}
                onChange={e => handleCannabinoidNameChange(i, e.target.value)}
                style={{ flex: 2 }}
              />
              <span style={{ width: 60, textAlign: 'center', fontWeight: 600, opacity: knownFamily ? 1 : 0.3 }}>
                {knownFamily ? knownFamily.toUpperCase() : '—'}
              </span>
              <input
                placeholder="%"
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={c.percent ?? ''}
                onChange={e => updateCannabinoidPercent(i, e.target.value === '' ? null : Number(e.target.value))}
                style={{ width: 120 }}
              />
              {cannabinoids.length > 1 && (
                <button type="button" onClick={() => removeCannabinoidRow(i)}>✕</button>
              )}
            </div>
          )
        })}

        <button type="button" onClick={addCannabinoidRow}>+ Add cannabinoid</button>

        <div style={{ marginTop: 16 }}>
          <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
        </div>

        {msg && <p>{msg}</p>}
      </form>
    </div>
  )
}
