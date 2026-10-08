import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AdminTable, navBtnStyle, Dash, type Column, primaryBtnStyle } from './components/AdminTable'
import api from './api/client'
import type { Dispensary } from './types'
import { t, font } from './theme'
import { Icon } from './components/Icon'

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
    { key: 'name', header: 'Name', td: { color: t.text1, fontWeight: 500 }, render: d => d.name },
    { key: 'slug', header: 'Slug', td: { color: t.text3, fontFamily: font.family.mono }, render: d => d.slug },
    { key: 'address', header: 'Address', render: d => d.address ?? d.location ?? <Dash /> },
    { key: 'coords', header: 'Coords', td: { fontFamily: font.family.mono, fontSize: 11 },
      render: d => d.lat != null && d.lng != null ? `${d.lat.toFixed(5)}, ${d.lng.toFixed(5)}` : <Dash /> },
    { key: 'pos', header: 'POS',
      render: d => d.pos_type !== 'none' ? <span style={{ color: t.info }}>{d.pos_type}</span> : <Dash /> },
    { key: 'active', header: 'Active',
      render: d => d.is_active ? <span style={{ color: t.success }}>Yes</span> : <span style={{ color: t.text3 }}>No</span> },
  ]

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h2 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Dispensaries</h2>
          <button
            onClick={() => navigate('/admin/dispensaries/new')}
            style={primaryBtnStyle}
          >
            <Icon name="plus" size={14} />New
          </button>
        </div>

        {error && <div style={{ color: t.danger, marginBottom: 16 }}>Error: {error}</div>}

        {loading ? (
          <div style={{ color: t.text3, padding: 16 }}>Loading…</div>
        ) : dispensaries.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>No dispensaries yet.</div>
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
