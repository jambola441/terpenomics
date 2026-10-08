import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AdminTable, badge, navBtnStyle, type Column } from './components/AdminTable'
import api from './api/client'
import type { Partner } from './types'
import { inputStyle, primaryBtn, slugify } from './utils/partners'
import { t, font } from './theme'
import { Icon } from './components/Icon'

/**
 * Partner stores — non-dispensary businesses whose purchases earn Terpee points.
 *
 * Also the landing page for the POS OAuth round-trip: the API redirects the
 * browser here with ?pos=connected&partner_id=… (or ?pos=error&reason=…), and a
 * successful connect is forwarded on to that partner's page.
 */
export default function Partners() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [partners, setPartners] = useState<Partner[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [creating, setCreating] = useState(false)

  const pos = params.get('pos')
  const returnedPartner = params.get('partner_id')
  const reason = params.get('reason')

  useEffect(() => {
    if (pos === 'connected' && returnedPartner) {
      navigate(`/admin/partners/${returnedPartner}?pos=connected`, { replace: true })
      return
    }
    load()
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setPartners(await api.partners.list({ limit: 200 }))
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !slug.trim()) return
    setCreating(true)
    setError(null)
    try {
      const p = await api.partners.create({ name: name.trim(), slug: slug.trim() })
      navigate(`/admin/partners/${p.id}`)
    } catch (err: any) {
      setError(err.message)
      setCreating(false)
    }
  }

  const columns: Column<Partner>[] = [
    { key: 'name', header: 'Partner', td: { color: t.text1, fontWeight: 500 }, render: p => p.name },
    { key: 'slug', header: 'Slug', td: { color: t.text3, fontFamily: font.family.mono }, render: p => p.slug },
    {
      key: 'status', header: 'Status',
      render: p => p.is_active
        ? <span style={{ ...badge, background: t.successTint, color: t.success }}>active</span>
        : <span style={{ ...badge, background: t.surface2, color: t.text2 }}>inactive</span>,
    },
    { key: 'created', header: 'Added', td: { fontSize: 12 }, render: p => p.created_at.slice(0, 10) },
  ]

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 1000, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h2 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Partner Stores</h2>
        </div>

        <div style={{ fontSize: 12, color: t.text3, marginBottom: 18, lineHeight: 1.7 }}>
          Businesses whose purchases earn customers Terpee points. Add a partner, then connect
          their point-of-sale from the partner's page — orders sync in every 15 minutes and are
          matched to customers by phone number.
        </div>

        {pos === 'error' && (
          <div style={{ background: t.dangerTint, border: `1px solid ${t.dangerEdge}`, color: t.danger, borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 13 }}>
            The POS connection did not go through{reason ? `: ${reason}` : '.'}
          </div>
        )}

        <form onSubmit={create} style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
          <input
            placeholder="Partner name (e.g. Bean Co Coffee)"
            value={name}
            onChange={e => {
              setName(e.target.value)
              if (!slugTouched) setSlug(slugify(e.target.value))
            }}
            style={{ ...inputStyle, flex: '2 1 240px' }}
          />
          <input
            placeholder="slug"
            value={slug}
            onChange={e => { setSlug(e.target.value); setSlugTouched(true) }}
            style={{ ...inputStyle, flex: '1 1 160px', fontFamily: font.family.mono }}
          />
          <button type="submit" disabled={creating || !name.trim() || !slug.trim()} style={primaryBtn(creating || !name.trim() || !slug.trim())}>
            {creating ? 'Adding…' : <><Icon name="plus" size={14} />Add partner</>}
          </button>
        </form>

        {error && <div style={{ color: t.danger, marginBottom: 16 }}>Error: {error}</div>}

        {loading ? (
          <div style={{ color: t.text3, padding: 16 }}>Loading…</div>
        ) : partners.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>No partners yet. Add the first one above.</div>
        ) : (
          <AdminTable
            columns={columns}
            rows={partners}
            rowKey={p => p.id}
            onRowClick={p => navigate(`/admin/partners/${p.id}`)}
          />
        )}
      </div>
    </div>
  )
}
