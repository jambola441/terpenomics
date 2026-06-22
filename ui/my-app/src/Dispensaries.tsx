import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AdminTable, navBtnStyle, Dash, type Column } from './components/AdminTable'
import api from './api/client'
import type { Dispensary } from './types'

export default function Dispensaries() {
  const navigate = useNavigate()
  const [dispensaries, setDispensaries] = useState<Dispensary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { fetch() }, [])

  async function fetch() {
    setLoading(true)
    setError(null)
    try {
      setDispensaries(await api.dispensaries.list({ limit: 200 }))
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const columns: Column<Dispensary>[] = [
    { key: 'name', header: 'Name', td: { color: '#f1f5f9', fontWeight: 500 }, render: d => d.name },
    { key: 'slug', header: 'Slug', td: { color: '#64748b', fontFamily: 'monospace' }, render: d => d.slug },
    { key: 'address', header: 'Address', render: d => d.address ?? d.location ?? <Dash /> },
    { key: 'coords', header: 'Coords', td: { fontFamily: 'monospace', fontSize: 11 },
      render: d => d.lat != null && d.lng != null ? `${d.lat.toFixed(5)}, ${d.lng.toFixed(5)}` : <Dash /> },
    { key: 'pos', header: 'POS',
      render: d => d.pos_type !== 'none' ? <span style={{ color: '#a5b4fc' }}>{d.pos_type}</span> : <Dash /> },
    { key: 'active', header: 'Active',
      render: d => d.is_active ? <span style={{ color: '#86efac' }}>Yes</span> : <span style={{ color: '#475569' }}>No</span> },
  ]

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Dispensaries</h2>
          <button
            onClick={() => navigate('/admin/dispensaries/new')}
            style={{ ...navBtnStyle, color: '#a5b4fc', borderColor: '#3730a3' }}
          >
            + New
          </button>
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>Error: {error}</div>}

        {loading ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : dispensaries.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>No dispensaries yet.</div>
        ) : (
          <AdminTable
            columns={columns}
            rows={dispensaries}
            rowKey={d => d.id}
            onRowClick={d => navigate(`/admin/dispensaries/${d.id}`)}
          />
        )}
      </div>
    </div>
  )
}
