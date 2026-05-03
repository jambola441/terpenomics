import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Slug</th>
                <th style={thStyle}>Address</th>
                <th style={thStyle}>Coords</th>
                <th style={thStyle}>POS</th>
                <th style={thStyle}>Active</th>
              </tr>
            </thead>
            <tbody>
              {dispensaries.map(d => (
                <tr
                  key={d.id}
                  style={{ borderBottom: '1px solid #0f172a', cursor: 'pointer' }}
                  onClick={() => navigate(`/admin/dispensaries/${d.id}`)}
                  onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = '#0f172a'}
                  onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'}
                >
                  <td style={{ ...tdStyle, color: '#f1f5f9', fontWeight: 500 }}>{d.name}</td>
                  <td style={{ ...tdStyle, color: '#64748b', fontFamily: 'monospace' }}>{d.slug}</td>
                  <td style={tdStyle}>{d.address ?? d.location ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>
                    {d.lat != null && d.lng != null
                      ? `${d.lat.toFixed(5)}, ${d.lng.toFixed(5)}`
                      : <span style={{ color: '#475569' }}>—</span>}
                  </td>
                  <td style={tdStyle}>{d.pos_type !== 'none' ? <span style={{ color: '#a5b4fc' }}>{d.pos_type}</span> : <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{d.is_active ? <span style={{ color: '#86efac' }}>Yes</span> : <span style={{ color: '#475569' }}>No</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
