import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from './api/client'

export default function CustomerRegister() {
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [marketing, setMarketing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() && !phone.trim() && !email.trim()) {
      setError('Provide at least a name, phone, or email.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const customer = await api.customers.create({
        name: name.trim() || null,
        phone: phone.trim() || null,
        email: email.trim() || null,
        marketing_opt_in: marketing,
      })
      navigate(`/admin/customers/${customer.id}`)
    } catch (err: any) {
      setError(err.message ?? 'Failed to create customer')
      setSaving(false)
    }
  }

  return (
    <div style={{
      padding: 24,
      fontFamily: "'Inter', system-ui, sans-serif",
      background: '#080d18',
      minHeight: '100vh',
      color: '#f1f5f9',
    }}>
      <div style={{ maxWidth: 480, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 32 }}>
          <button onClick={() => navigate('/admin/customers')} style={navBtnStyle}>← Customers</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Register Customer</h2>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{
            background: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: 10,
            padding: 24,
            display: 'flex',
            flexDirection: 'column',
            gap: 18,
          }}>
            <Field label="Name">
              <input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. Alex Johnson"
                style={inputStyle}
                disabled={saving}
              />
            </Field>

            <Field label="Phone">
              <input
                value={phone}
                onChange={e => setPhone(e.target.value)}
                placeholder="e.g. +1 555 000 0000"
                style={inputStyle}
                disabled={saving}
              />
            </Field>

            <Field label="Email">
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="e.g. alex@example.com"
                style={inputStyle}
                disabled={saving}
              />
            </Field>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={labelStyle}>Marketing opt-in</span>
              <Toggle checked={marketing} onChange={setMarketing} disabled={saving} />
            </div>
          </div>

          {error && (
            <div style={{ color: '#f87171', fontSize: 13, marginTop: 12 }}>{error}</div>
          )}

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
              {saving ? 'Registering…' : 'Register Customer'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/admin/customers')}
              disabled={saving}
              style={navBtnStyle}
            >
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
        width: 44,
        height: 24,
        borderRadius: 12,
        border: 'none',
        background: checked ? '#4f46e5' : '#1e293b',
        position: 'relative',
        cursor: disabled ? 'default' : 'pointer',
        transition: 'background 0.2s',
        flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute',
        top: 3,
        left: checked ? 23 : 3,
        width: 18,
        height: 18,
        borderRadius: '50%',
        background: checked ? '#fff' : '#475569',
        transition: 'left 0.2s',
      }} />
    </button>
  )
}

const labelStyle: React.CSSProperties = { fontSize: 13, color: '#94a3b8', fontWeight: 500 }
const inputStyle: React.CSSProperties = {
  width: '100%',
  background: '#080d18',
  border: '1px solid #1e293b',
  borderRadius: 8,
  color: '#f1f5f9',
  fontSize: 14,
  padding: '10px 12px',
  outline: 'none',
  boxSizing: 'border-box',
}
const navBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  background: '#0f172a',
  border: '1px solid #1e293b',
  borderRadius: 6,
  color: '#94a3b8',
  cursor: 'pointer',
  fontSize: 13,
}
