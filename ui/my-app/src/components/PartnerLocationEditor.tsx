import { useState, type CSSProperties, type FormEvent } from 'react'
import api from '../api/client'
import type { GeocodeHit, PartnerLocation } from '../types'
import { navBtnStyle } from './AdminTable'
import { inputStyle, primaryBtn } from '../utils/partners'
import { t } from '../theme'

/**
 * Add or edit one partner store (admin). A store from the POS keeps the POS's
 * name and address, and its coordinates and phone when the POS sends them; this
 * fills what the POS leaves out. A store added by hand, for a partner without a
 * POS, is all typed here. Either way, "Find on map" looks the address up and the
 * pick is what puts the store on the customers' map.
 */
export default function PartnerLocationEditor({ partnerId, location, onDone, onCancel }: {
  partnerId: string
  /** Absent to add a store. */
  location?: PartnerLocation
  onDone: () => void
  onCancel: () => void
}) {
  const fromPos = !!location?.connection_id
  const [name, setName] = useState(location?.name ?? '')
  const [address, setAddress] = useState(location?.address ?? '')
  const [phone, setPhone] = useState(location?.phone ?? '')
  const [spot, setSpot] = useState<{ lat: number; lng: number; label?: string } | null>(
    location?.lat != null && location?.lng != null ? { lat: location.lat, lng: location.lng } : null)
  const [query, setQuery] = useState(location?.address ?? '')
  const [hits, setHits] = useState<GeocodeHit[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label)
    setError(null)
    try {
      await work()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const find = () => run('find', async () => setHits(await api.partners.geocode(query.trim())))

  const save = (e: FormEvent) => {
    e.preventDefault()
    run('save', async () => {
      const where = { lat: spot?.lat ?? null, lng: spot?.lng ?? null, phone: phone.trim() || null }
      if (!location) {
        await api.partners.createLocation(partnerId, { name: name.trim(), address: address.trim() || null, ...where })
      } else {
        await api.partners.updateLocation(location.id, fromPos ? where : { name: name.trim(), address: address.trim() || null, ...where })
      }
      onDone()
    })
  }

  const remove = () => {
    if (location && window.confirm(`Delete ${location.name}? Customers will no longer see it.`)) {
      run('delete', async () => { await api.partners.deleteLocation(location.id); onDone() })
    }
  }

  const label: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, color: t.text2 }
  const field: CSSProperties = { ...inputStyle, fontSize: 14 }
  const posNote = <span style={{ color: t.text3 }}> — from the POS</span>

  return (
    <form onSubmit={save} style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: 10, padding: 16, marginBottom: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontWeight: 600 }}>{location ? `Edit ${location.name}` : 'Add a store'}</div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <label style={{ ...label, flex: '1 1 200px' }}>
          <span>Name{fromPos && posNote}</span>
          <input value={name} onChange={e => setName(e.target.value)} disabled={fromPos} required placeholder="Main Street" style={field} />
        </label>
        <label style={{ ...label, flex: '1 1 160px' }}>
          Phone
          <input value={phone} onChange={e => setPhone(e.target.value)} inputMode="tel" placeholder="(845) 555-0100" style={field} />
        </label>
      </div>
      <label style={label}>
        <span>Address{fromPos && posNote}</span>
        <input
          value={address}
          onChange={e => { setAddress(e.target.value); if (!hits) setQuery(e.target.value) }}
          disabled={fromPos}
          placeholder="279 Lake Dr, Lake Peekskill, NY 10537"
          style={field}
        />
      </label>

      <div style={label}>
        <span>On the map</span>
        <div style={{ fontSize: 13, color: spot ? t.text1 : t.text3 }}>
          {spot ? (
            <>
              {spot.label ?? 'Placed'} <span style={{ color: t.text3 }}>({spot.lat.toFixed(5)}, {spot.lng.toFixed(5)})</span>{' '}
              <button type="button" onClick={() => setSpot(null)} style={{ ...navBtnStyle, padding: '2px 8px', marginLeft: 6 }}>Remove</button>
            </>
          ) : 'Not placed: customers see the store in the list, not on the map.'}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); if (query.trim().length >= 3) find() } }}
            aria-label="Address to look up"
            placeholder="Address to look up"
            style={{ ...field, flex: '1 1 260px' }}
          />
          <button type="button" onClick={find} disabled={query.trim().length < 3 || !!busy} style={navBtnStyle}>
            {busy === 'find' ? 'Looking…' : 'Find on map'}
          </button>
        </div>
        {hits && (hits.length === 0 ? (
          <div style={{ fontSize: 13, color: t.text3 }}>No match. Try the street and town only.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {hits.map(h => (
              <button
                type="button"
                key={`${h.lat},${h.lng}`}
                onClick={() => { setSpot(h); setHits(null) }}
                style={{ ...navBtnStyle, justifyContent: 'flex-start', textAlign: 'left', whiteSpace: 'normal', lineHeight: 1.4 }}
              >
                {h.label}
              </button>
            ))}
          </div>
        ))}
      </div>

      {error && <div style={{ color: t.danger, fontSize: 13 }}>{error}</div>}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button type="submit" disabled={!!busy || !name.trim()} style={primaryBtn(!!busy || !name.trim())}>
          {busy === 'save' ? 'Saving…' : location ? 'Save' : 'Add store'}
        </button>
        <button type="button" onClick={onCancel} disabled={!!busy} style={navBtnStyle}>Cancel</button>
        {location && !fromPos && (
          <button type="button" onClick={remove} disabled={!!busy} style={{ ...navBtnStyle, marginLeft: 'auto', color: t.danger, borderColor: t.dangerEdge }}>
            Delete
          </button>
        )}
      </div>
    </form>
  )
}
