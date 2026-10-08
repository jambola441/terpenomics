import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from './api/client'
import type { Dispensary } from './types'
import { t, font, tone } from './theme'
import { Icon } from './components/Icon'
import { navBtnStyle } from './components/AdminTable'

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

  if (loading) return <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text3 }}>Loading…</div>

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 560, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 32 }}>
          <button onClick={() => navigate('/admin/dispensaries')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Dispensaries</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>{isNew ? 'New Dispensary' : 'Edit Dispensary'}</h1>
          {!isNew && (
            <button
              onClick={() => navigate(`/admin/dispensaries/${dispensaryId}/listings`)}
              style={{ ...navBtnStyle, marginLeft: 'auto', color: tone.accent.fg, borderColor: tone.accent.edge }}
            >
              View listings<Icon name="arrow-right" size={14} />
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>

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
                style={{ ...inputStyle, fontFamily: font.family.mono }}
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

            <div style={{ borderTop: `1px solid ${t.border}`, paddingTop: 18 }}>
              <div style={{ ...labelStyle, marginBottom: 14, color: t.text3, fontSize: 11, fontFamily: font.family.mono, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Location</div>

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

            <div style={{ borderTop: `1px solid ${t.border}`, paddingTop: 18 }}>
              <div style={{ ...labelStyle, marginBottom: 14, color: t.text3, fontSize: 11, fontFamily: font.family.mono, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em' }}>POS Integration</div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <Field label="POS Type">
                  <select
                    value={posType}
                    onChange={e => setPosType(e.target.value)}
                    style={{ ...inputStyle, cursor: 'pointer' }}
                    disabled={saving}
                  >
                    {POS_TYPES.map(pt => <option key={pt} value={pt}>{pt}</option>)}
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

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: `1px solid ${t.border}`, paddingTop: 18 }}>
              <span style={labelStyle}>Active</span>
              <Toggle checked={isActive} onChange={setIsActive} disabled={saving} />
            </div>
          </div>

          {error && <div style={{ color: t.danger, fontSize: 13, marginTop: 12 }}>{error}</div>}
          {msg && <div style={{ color: t.success, fontSize: 13, marginTop: 12 }}>{msg}</div>}

          <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: '10px 24px',
                background: saving ? t.surface2 : t.accent,
                border: 'none',
                borderRadius: 8,
                color: saving ? t.text4 : t.accentInk,
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
        background: checked ? t.accent : t.surface3,
        position: 'relative', cursor: disabled ? 'default' : 'pointer', transition: 'background 0.2s', flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute', top: 3, left: checked ? 23 : 3,
        width: 18, height: 18, borderRadius: '50%',
        background: checked ? t.accentInk : t.text3, transition: 'left 0.2s',
      }} />
    </button>
  )
}

const labelStyle: React.CSSProperties = { fontSize: 13, color: t.text2, fontWeight: 500 }
const inputStyle: React.CSSProperties = {
  width: '100%', background: t.surface2, border: `1px solid ${t.border}`,
  borderRadius: 8, color: t.text1, fontSize: 14, padding: '10px 12px',
  outline: 'none', boxSizing: 'border-box',
}
