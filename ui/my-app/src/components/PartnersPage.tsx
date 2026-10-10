/* ============================================================================
   PartnersPage — where to earn Terpee points.

   Points were explained in one line on the Points pane, and the only list of
   partners was the picker inside the receipt upload. This says what a partner
   store is, how earning works, and lists every partner nearest first (once the
   browser shares a position), each opening its own page.
   ========================================================================== */

import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import type { PortalPartners } from '../types'
import { t, radius, font } from '../theme'
import { formatDist } from '../utils/format'
import { nearestStore, sortPartners, type Position } from '../utils/partnerPlaces'
import { PARTNER_DEFINITION, earnLine } from '../utils/pointsProgram'
import { BackButton, BrandMark, FeedState, PageTitle, Pressable } from './ui'
import { PointsSteps } from './HowPointsWork'
import { Icon } from './Icon'

export default function PartnersPage({ onBack, onOpenPartner, onHowItWorks }: {
  onBack: () => void
  onOpenPartner: (slug: string) => void
  onHowItWorks: () => void
}) {
  const [data, setData] = useState<PortalPartners | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [pos, setPos] = useState<Position | null>(null)

  useEffect(() => {
    let live = true
    setError(false)
    api.portal.getPartners()
      .then(r => { if (live) setData(r) })
      .catch(() => { if (live) setError(true) })
    return () => { live = false }
  }, [attempt])

  useEffect(() => {
    navigator.geolocation?.getCurrentPosition(p => setPos({ lat: p.coords.latitude, lng: p.coords.longitude }))
  }, [])

  const partners = useMemo(() => sortPartners(data?.partners ?? [], pos), [data, pos])

  return (
    <div style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: 'calc(env(safe-area-inset-top, 0px) + 16px) 16px 32px', maxWidth: 560, margin: '0 auto' }}>
        <BackButton onClick={onBack} />
        <PageTitle sub={PARTNER_DEFINITION} style={{ margin: '16px 0 20px' }}>Partner stores</PageTitle>

        {error ? (
          <FeedState kind="error" message="Couldn't load partner stores" onRetry={() => setAttempt(n => n + 1)} />
        ) : !data ? (
          <FeedState kind="loading" message="Loading partner stores…" />
        ) : (
          <>
            <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: '16px 16px 14px', marginBottom: 24 }}>
              <PointsSteps program={data.program} compact />
              <button
                onClick={onHowItWorks}
                style={{
                  marginTop: 12, background: 'none', border: 'none', padding: '6px 0', cursor: 'pointer',
                  color: t.accent, fontSize: font.size.small + 1, fontWeight: font.weight.semibold,
                  display: 'inline-flex', alignItems: 'center', gap: 2,
                }}
              >
                How points work <Icon name="chevron-right" size={15} />
              </button>
            </div>

            {partners.length === 0 ? (
              <FeedState
                kind="empty"
                icon="pin"
                message="No partner stores yet"
                hint="Local businesses are joining. Check back soon."
              />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {partners.map(p => {
                  const near = nearestStore(p, pos)
                  const stores = p.locations.length
                  const where = near
                    ? `${formatDist(near.miles)}${stores > 1 ? ` · ${stores} stores` : ''}`
                    : stores === 1 ? p.locations[0].address ?? '1 store' : stores > 1 ? `${stores} stores` : null
                  return (
                    <Pressable
                      key={p.id}
                      onClick={() => onOpenPartner(p.slug)}
                      lift
                      style={{
                        display: 'flex', gap: 14, alignItems: 'flex-start', padding: 14,
                        background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg,
                      }}
                    >
                      <BrandMark name={p.name} imageUrl={p.logo_url} size={52} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ color: t.text1, fontSize: font.size.callout, fontWeight: font.weight.semibold }}>{p.name}</div>
                        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
                          {[p.category, where].filter(Boolean).join(' · ')}
                        </div>
                        {p.description && (
                          <div style={{
                            color: t.text2, fontSize: font.size.small + 1, lineHeight: 1.45, marginTop: 6,
                            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                          }}>
                            {p.description}
                          </div>
                        )}
                        <div style={{ color: t.accent, fontSize: font.size.small, fontWeight: font.weight.semibold, marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                          <Icon name="drop" size={13} strokeWidth={2} />
                          {earnLine(data.program)}
                        </div>
                      </div>
                      <Icon name="chevron-right" size={18} color={t.text3} style={{ alignSelf: 'center' }} />
                    </Pressable>
                  )
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
