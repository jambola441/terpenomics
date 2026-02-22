// src/AddProduct.tsx
import { useState } from 'react'
import  supabase  from './utils/supabase'

type TerpeneInput = {
  name: string
  percent?: number
}

export default function AddProduct() {
  const [name, setName] = useState('')
  const [brand, setBrand] = useState('')
  const [category, setCategory] = useState('flower')
  const [isActive, setIsActive] = useState(true)
  const [terpenes, setTerpenes] = useState<TerpeneInput[]>([{ name: '' }])
  const [msg, setMsg] = useState('')
  const [loading, setLoading] = useState(false)

  function updateTerpene(idx: number, field: keyof TerpeneInput, value: any) {
    setTerpenes(prev =>
      prev.map((t, i) => (i === idx ? { ...t, [field]: value } : t))
    )
  }

  function addTerpeneRow() {
    setTerpenes(prev => [...prev, { name: '' }])
  }

  function removeTerpeneRow(idx: number) {
    setTerpenes(prev => prev.filter((_, i) => i !== idx))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setMsg('')
    setLoading(true)

    const {
      data: { session },
    } = await supabase.auth.getSession()

    if (!session?.access_token) {
      setMsg('Not authenticated')
      setLoading(false)
      return
    }

    const payload = {
      name,
      brand: brand || null,
      category,
      is_active: isActive,
      terpenes: terpenes
        .filter(t => t.name.trim() !== '')
        .map(t => ({
          name: t.name.trim(),
          percent: t.percent ?? null,
        })),
    }

    try {
      const res = await fetch('https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev/admin/products', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || 'Request failed')
      }

      const data = await res.json()
      setMsg(`Created product ${data.id}`)
      setName('')
      setBrand('')
      setTerpenes([{ name: '' }])
    } catch (err: any) {
      setMsg(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 600 }}>
      <h2>Add Product</h2>

      <form onSubmit={handleSubmit}>
        <div>
          <label>Name</label>
          <input value={name} onChange={e => setName(e.target.value)} required />
        </div>

        <div>
          <label>Brand</label>
          <input value={brand} onChange={e => setBrand(e.target.value)} />
        </div>

        <div>
          <label>Category</label>
          <select value={category} onChange={e => setCategory(e.target.value)}>
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

        <div>
          <label>
            <input
              type="checkbox"
              checked={isActive}
              onChange={e => setIsActive(e.target.checked)}
            />
            Active
          </label>
        </div>

        <h4>Terpenes</h4>

        {terpenes.map((t, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input
              placeholder="Name"
              value={t.name}
              onChange={e => updateTerpene(i, 'name', e.target.value)}
              required
            />
            <input
              placeholder="%"
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={t.percent ?? ''}
              onChange={e =>
                updateTerpene(
                  i,
                  'percent',
                  e.target.value === '' ? undefined : Number(e.target.value)
                )
              }
            />
            {terpenes.length > 1 && (
              <button type="button" onClick={() => removeTerpeneRow(i)}>
                ✕
              </button>
            )}
          </div>
        ))}

        <button type="button" onClick={addTerpeneRow}>
          + Add terpene
        </button>

        <div style={{ marginTop: 16 }}>
          <button type="submit" disabled={loading}>
            {loading ? 'Saving…' : 'Create Product'}
          </button>
        </div>
      </form>

      {msg && <p>{msg}</p>}
    </div>
  )
}
