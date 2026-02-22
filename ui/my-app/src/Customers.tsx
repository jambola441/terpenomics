// src/Customers.tsx
import { useEffect, useState } from 'react'
import supabase  from './utils/supabase'

type Customer = {
  id: string
  name?: string | null
  phone?: string | null
  email?: string | null
  marketing_opt_in: boolean
  last_visit_at?: string | null
}

export default function Customers() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchCustomers()
  }, [])

  async function fetchCustomers() {
    setLoading(true)
    setError(null)

    const {
      data: { session },
    } = await supabase.auth.getSession()

    try {
      const res = await fetch('https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev/admin/customers', {
        headers: {
          Authorization: `Bearer ${session?.access_token ?? ''}`,
        },
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || 'Failed to fetch customers')
      }

      const data = await res.json()
      setCustomers(data)
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
      <h1>Customers</h1>

      {customers.length === 0 ? (
        <p>No customers found.</p>
      ) : (
        <table border={1} cellPadding={8} style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Marketing</th>
              <th>Last Visit</th>
            </tr>
          </thead>
          <tbody>
            {customers.map(c => (
              <tr key={c.id}>
                <td><a href={`/customers/${c.id}`}>{c.name ?? '—'}</a></td>
                <td>{c.email ?? '—'}</td>
                <td>{c.phone ?? '—'}</td>
                <td>{c.marketing_opt_in ? 'Yes' : 'No'}</td>
                <td>{c.last_visit_at ? new Date(c.last_visit_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
