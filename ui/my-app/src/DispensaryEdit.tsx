import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from './api/client'
import type { Dispensary } from './types'

const POS_TYPES = ['none', 'alleaves', 'leaflogix']

export default function DispensaryEdit() {
  const { dispensaryId } = useParams<{ dispensaryId: string }>()
  const navigate = useNavigate()
  const isNew = dispensaryId === 'new'

  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [location, setLocation] = useState('')
  const [address, setAddress] = useState('')
  const [lat, setLat] = useState('')
  const [lng, setLng] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [posType, setPosType] = useState('none')
  const [posTenantId, setPosTenantId] = useState('')

  useEffect(() => {
    if (isNew) return
    api.dispensaries.get(dispensaryId!)
      .then(fill)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [dispensaryId])

  function fill(d: Dispensary) {
    setName(d.name ?? '')
    setSlug(d.slug ?? '')
    setWebsiteUrl(d.website_url ?? '')
    setLocation(d.location ?? '')
    setAddress(d.address ?? '')
    setLat(d.lat != null ? String(d.lat) : '')
    setLng(d.lng != null ? String(d.lng) : '')
    setIsActive(d.is_active)
    setPosType(d.pos_type ?? 'none')
    setPosTenantId(d.pos_tenant_id ?? '')
  }

  function autoSlug(n: string) {
    return n.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !slug.trim()) {
      setError('Name and slug are required.')
      return
    }
    setSaving(true)
    setError(null)
    setMsg(null)

    const payload = {
      name: name.trim(),
      slug: slug.trim(),
      website_url: websiteUrl.trim() || null,
      location: location.trim() || null,
      address: address.trim() || null,
      lat: lat !== '' ? parseFloat(lat) : null,
      lng: lng !== '' ? parseFloat(lng) : null,
      is_active: isActive,
      pos_type: posType,
      pos_tenant_id: posTenantId.trim() || null,
    }

    try {
      if (isNew) {
        const d = await api.dispensaries.create(payload)
        navigate(`/admin/dispensaries/${d.id}`, { replace: true })
      } else {
        const d = await api.dispensaries.update(dispensaryId!, payload)
        fill(d)
        setMsg('Saved')
      }
    } catch (err: any) {
      setError(err.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div style={{ padding: 24, background: '#080d18', minHeight: '100vh', color: '#475569' }}>Loading…</div>

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 560, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 32 }}>
          <button onClick={() => navigate('/admin/dispensaries')} style={navBtnStyle}>← Dispensaries</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>{isNew ? 'New Dispensary' : 'Edit Dispensary'}</h2>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>

            <Field label="Name *">
              <input
                value={name}
                onChange={e => {
                  setName(e.target.value)
                  if (isNew) setSlug(autoSlug(e.target.value))
                }}
                placeholder="Brooklyn Organic Buds"
                style={inputStyle}
                disabled={saving}
              />
            </Field>

            <Field label="Slug *">
              <input
                value={slug}
                onChange={e => setSlug(e.target.value)}
                placeholder="brooklyn-organic-buds"
                style={{ ...inputStyle, fontFamily: 'monospace' }}
                disabled={saving}
              />
            </Field>

            <Field label="Website URL">
              <input
                value={websiteUrl}
                onChange={e => setWebsiteUrl(e.target.value)}
                placeholder="https://..."
                style={inputStyle}
                disabled={saving}
              />
            </Field>

            <div style={{ borderTop: '1px solid #1e293b', paddingTop: 18 }}>
              <div style={{ ...labelStyle, marginBottom: 14, color: '#64748b', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Location</div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <Field label="Address">
                  <input
                    value={address}
                    onChange={e => setAddress(e.target.value)}
                    placeholder="123 Main St, Brooklyn, NY 11201"
                    style={inputStyle}
                    disabled={saving}
                  />
                </Field>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <Field label="Latitude">
                    <input
                      value={lat}
                      onChange={e => setLat(e.target.value)}
                      placeholder="40.6782"
                      type="number"
                      step="any"
                      style={inputStyle}
                      disabled={saving}
                    />
                  </Field>
                  <Field label="Longitude">
                    <input
                      value={lng}
                      onChange={e => setLng(e.target.value)}
                      placeholder="-73.9442"
                      type="number"
                      step="any"
                      style={inputStyle}
                      disabled={saving}
                    />
                  </Field>
                </div>

                <Field label="Location (legacy)">
                  <input
                    value={location}
                    onChange={e => setLocation(e.target.value)}
                    placeholder="Brooklyn, NY"
                    style={inputStyle}
                    disabled={saving}
                  />
                </Field>
              </div>
            </div>

            <div style={{ borderTop: '1px solid #1e293b', paddingTop: 18 }}>
              <div style={{ ...labelStyle, marginBottom: 14, color: '#64748b', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em' }}>POS Integration</div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <Field label="POS Type">
                  <select
                    value={posType}
                    onChange={e => setPosType(e.target.value)}
                    style={{ ...inputStyle, cursor: 'pointer' }}
                    disabled={saving}
                  >
                    {POS_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </Field>

                {posType !== 'none' && (
                  <Field label="POS Tenant ID">
                    <input
                      value={posTenantId}
                      onChange={e => setPosTenantId(e.target.value)}
                      placeholder="tenant identifier"
                      style={inputStyle}
                      disabled={saving}
                    />
                  </Field>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #1e293b', paddingTop: 18 }}>
              <span style={labelStyle}>Active</span>
              <Toggle checked={isActive} onChange={setIsActive} disabled={saving} />
            </div>
          </div>

          {error && <div style={{ color: '#f87171', fontSize: 13, marginTop: 12 }}>{error}</div>}
          {msg && <div style={{ color: '#86efac', fontSize: 13, marginTop: 12 }}>{msg}</div>}

          <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: '10px 24px',
                background: saving ? '#1e293b' : '#4f46e5',
                border: 'none',
                borderRadius: 8,
                color: saving ? '#475569' : '#fff',
                fontSize: 14,
                fontWeight: 600,
                cursor: saving ? 'default' : 'pointer',
              }}
            >
              {saving ? 'Saving…' : isNew ? 'Create Dispensary' : 'Save Changes'}
            </button>
            <button type="button" onClick={() => navigate('/admin/dispensaries')} disabled={saving} style={navBtnStyle}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ ...labelStyle, marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  )
}

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      style={{
        width: 44, height: 24, borderRadius: 12, border: 'none',
        background: checked ? '#4f46e5' : '#1e293b',
        position: 'relative', cursor: disabled ? 'default' : 'pointer', transition: 'background 0.2s', flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute', top: 3, left: checked ? 23 : 3,
        width: 18, height: 18, borderRadius: '50%',
        background: checked ? '#fff' : '#475569', transition: 'left 0.2s',
      }} />
    </button>
  )
}

const labelStyle: React.CSSProperties = { fontSize: 13, color: '#94a3b8', fontWeight: 500 }
const inputStyle: React.CSSProperties = {
  width: '100%', background: '#080d18', border: '1px solid #1e293b',
  borderRadius: 8, color: '#f1f5f9', fontSize: 14, padding: '10px 12px',
  outline: 'none', boxSizing: 'border-box',
}
const navBtnStyle: React.CSSProperties = {
  padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b',
  borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13,
}
