// src/ProductEdit.tsx
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import supabase  from './utils/supabase'

type Terpene = { name: string; percent?: number | null }

type Product = {
  id: string
  name: string
  brand?: string | null
  category: string
  is_active: boolean
  terpenes: Terpene[]
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
      const res = await fetch(`${API_BASE}/admin/products/${pid}`, { headers })
      if (!res.ok) throw new Error(await res.text())
      const p: Product = await res.json()

      setName(p.name ?? '')
      setBrand(p.brand ?? '')
      setCategory(p.category ?? 'other')
      setIsActive(Boolean(p.is_active))
      setTerpenes(p.terpenes?.length ? p.terpenes.map(t => ({ name: t.name, percent: t.percent ?? null })) : [{ name: '' }])
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

        <div style={{ marginTop: 16 }}>
          <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
        </div>

        {msg && <p>{msg}</p>}
      </form>
    </div>
  )
}
