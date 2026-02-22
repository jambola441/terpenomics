// src/Products.tsx
import { useEffect, useState } from 'react'
import supabase from './utils/supabase'

type Terpene = {
  name: string
  percent?: number | null
}

type Product = {
  id: string
  name: string
  brand?: string | null
  category: string
  is_active: boolean
  terpenes?: Terpene[]
}

export default function Products() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchProducts()
  }, [])

  async function fetchProducts() {
    setLoading(true)
    setError(null)

    const {
      data: { session },
    } = await supabase.auth.getSession()

    try {
      const res = await fetch('https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev/admin/products', {
        headers: {
          Authorization: `Bearer ${session?.access_token ?? ''}`,
        },
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || 'Failed to fetch products')
      }

      const data = await res.json()
      setProducts(data)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <p style={{ padding: 24 }}>Loading…</p>
  if (error) return <p style={{ padding: 24 }}>Error: {error}</p>

  return (
    <div style={{ padding: 24 }}>
      <h1>Products</h1>

      {products.length === 0 ? (
        <p>No products found.</p>
      ) : (
        <table border={1} cellPadding={8} style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Brand</th>
              <th>Category</th>
              <th>Active</th>
              <th>Terpenes</th>
            </tr>
          </thead>
          <tbody>
            {products.map(p => (
              <tr key={p.id}>
                <td><a href={`/products/${p.id}`}>{p.name}</a></td>
                <td>{p.brand ?? '—'}</td>
                <td>{p.category}</td>
                <td>{p.is_active ? 'Yes' : 'No'}</td>
                <td>
                  {p.terpenes && p.terpenes.length > 0 ? (
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                      {p.terpenes.map((t, i) => (
                        <li key={i}>
                          {t.name}
                          {t.percent != null ? ` (${t.percent}%)` : ''}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
