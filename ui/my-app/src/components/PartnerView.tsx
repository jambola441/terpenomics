/* ============================================================================
   PartnerView — one partner store: what it is, where, when it's open, and
   how shopping there earns points.
   ========================================================================== */

import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import api, { ApiError } from '../api/client'
import type { PortalPartnerLocation, PortalPartnerPage } from '../types'
import { t, radius, font } from '../theme'
import { openStatus, weekHours } from '../utils/hours'
import { directionsUrl, telHref } from '../utils/partnerPlaces'
import { earnLine } from '../utils/pointsProgram'
import { BackButton, BrandMark, CollapsibleBlock, FeedState, Label, PageTitle } from './ui'
import { Icon } from './Icon'

const APPLE = typeof navigator !== 'undefined' && /iPhone|iPad|Macintosh/.test(navigator.userAgent)

export default function PartnerView({ slug, onBack, onHowItWorks, onSendReceipt, onShowOnMap }: {
  slug: string
  onBack: () => void
  onHowItWorks: () => void
  onSendReceipt: () => void
  /** Open the map on this store's pin. */
  onShowOnMap: (locationId: string) => void
}) {
  const [data, setData] = useState<PortalPartnerPage | null>(null)
  const [error, setError] = useState<'missing' | 'failed' | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    setError(null)
    setData(null)
    api.portal.getPartner(slug)
      .then(r => { if (live) setData(r) })
      .catch(err => { if (live) setError(err instanceof ApiError && err.status === 404 ? 'missing' : 'failed') })
    return () => { live = false }
  }, [slug, attempt])

  const shell = (children: ReactNode) => (
    <div style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: 'calc(env(safe-area-inset-top, 0px) + 16px) 16px 32px', maxWidth: 560, margin: '0 auto' }}>
        <BackButton onClick={onBack} />
        {children}
      </div>
    </div>
  )

  if (error === 'missing') return shell(<FeedState kind="empty" icon="pin" message="This store isn't a partner any more" />)
  if (error) return shell(<FeedState kind="error" message="Couldn't load this store" onRetry={() => setAttempt(n => n + 1)} />)
  if (!data) return shell(<FeedState kind="loading" message="Loading…" />)

  return shell(
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, margin: '16px 0 14px' }}>
        <BrandMark name={data.name} imageUrl={data.logo_url} size={64} />
        <PageTitle sub={data.category ?? 'Partner store'} size={font.size.display} style={{ minWidth: 0 }}>{data.name}</PageTitle>
      </div>

      {data.description && (
        <p style={{ color: t.text2, fontSize: font.size.body, lineHeight: 1.55, margin: '0 0 10px' }}>{data.description}</p>
      )}
      {data.website_url && (
        <a href={data.website_url} target="_blank" rel="noopener noreferrer" style={{ color: t.accent, fontSize: font.size.small + 1, fontWeight: font.weight.semibold, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          {data.website_url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}
          <Icon name="arrow-up-right" size={14} />
        </a>
      )}

      <div style={{ background: t.accentTint, border: `1px solid ${t.accentDim}`, borderRadius: radius.lg, padding: 16, margin: '20px 0 28px' }}>
        <div style={{ color: t.accent, fontSize: font.size.callout, fontWeight: font.weight.bold, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="drop" size={17} strokeWidth={2} />
          {earnLine(data.program)}
        </div>
        <div style={{ color: t.text2, fontSize: font.size.small + 1, lineHeight: 1.55, marginTop: 6 }}>
          Give the phone number you sign in with at checkout. Points are yours {data.program.pending_days} days later.
          Forgot? Send the receipt within {data.program.claim_window_days} days.
        </div>
        <div style={{ display: 'flex', gap: 16, marginTop: 10, flexWrap: 'wrap' }}>
          <button onClick={onSendReceipt} style={linkBtn}>Send a receipt</button>
          <button onClick={onHowItWorks} style={linkBtn}>How points work</button>
        </div>
      </div>

      <Label style={{ marginBottom: 4 }}>{data.locations.length > 1 ? `${data.locations.length} locations` : 'Location'}</Label>
      {data.locations.length === 0 ? (
        <div style={{ color: t.text3, fontSize: font.size.small + 1, padding: '10px 0' }}>No store address yet.</div>
      ) : (
        data.locations.map(loc => <LocationRow key={loc.id} location={loc} onShowOnMap={onShowOnMap} />)
      )}
    </>,
  )
}

function LocationRow({ location: loc, onShowOnMap }: { location: PortalPartnerLocation; onShowOnMap: (id: string) => void }) {
  const status = openStatus(loc.hours, loc.timezone)
  const directions = directionsUrl(loc, APPLE)
  return (
    <div style={{ padding: '14px 0', borderBottom: `1px solid ${t.border}` }}>
      <div style={{ color: t.text1, fontSize: font.size.callout, fontWeight: font.weight.semibold }}>{loc.name}</div>
      {loc.address && <div style={{ color: t.text2, fontSize: font.size.small + 1, marginTop: 2 }}>{loc.address}</div>}
      {status && (
        <div style={{ fontSize: font.size.small + 1, marginTop: 4, color: status.open ? t.success : t.text3, fontWeight: font.weight.medium }}>
          {status.text}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
        {directions && (
          <a href={directions} target="_blank" rel="noopener noreferrer" style={actionBtn}>
            <Icon name="navigate" size={15} /> Directions
          </a>
        )}
        {loc.lat != null && loc.lng != null && (
          <button onClick={() => onShowOnMap(loc.id)} style={{ ...actionBtn, cursor: 'pointer' }}>
            <Icon name="map" size={15} /> Show on map
          </button>
        )}
        {loc.phone && (
          <a href={telHref(loc.phone)} style={actionBtn}>
            <Icon name="phone" size={15} /> {loc.phone}
          </a>
        )}
      </div>
      {loc.hours && loc.hours.length > 0 && (
        <CollapsibleBlock title="Hours" style={{ marginTop: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 16, rowGap: 4, fontSize: font.size.small + 1 }}>
            {weekHours(loc.hours).map(d => (
              <div key={d.day} style={{ display: 'contents' }}>
                <span style={{ color: t.text3 }}>{d.label}</span>
                <span style={{ color: d.text === 'Closed' ? t.text3 : t.text1 }}>{d.text}</span>
              </div>
            ))}
          </div>
        </CollapsibleBlock>
      )}
    </div>
  )
}

const linkBtn: CSSProperties = {
  background: 'none', border: 'none', padding: '4px 0', cursor: 'pointer',
  color: t.accent, fontSize: font.size.small + 1, fontWeight: font.weight.semibold,
}

const actionBtn: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 40, padding: '0 14px',
  borderRadius: radius.pill, background: t.surface2, border: `1px solid ${t.border}`,
  color: t.text1, fontSize: font.size.small + 1, fontWeight: font.weight.semibold, textDecoration: 'none',
}
