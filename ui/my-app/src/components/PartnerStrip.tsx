/* ============================================================================
   PartnerStrip — Home's row of partner stores, where purchases earn points.

   Partners had no place on Home, so a shopper only met them by opening You →
   Points. One slim row, nearest first when the browser already shares where it
   is (Home never asks), each opening the partner's page. Nothing shows until
   there is a partner to show.
   ========================================================================== */

import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import type { PortalPartners } from '../types'
import { t, radius, font } from '../theme'
import { formatDist } from '../utils/format'
import { nearestStore, sortPartners, type Position } from '../utils/partnerPlaces'
import { BrandMark, Pressable, SectionHeader } from './ui'
import { Icon } from './Icon'

/** Where the browser is, only if it already may say: no prompt from Home. */
function useGrantedPosition(): Position | null {
  const [pos, setPos] = useState<Position | null>(null)
  useEffect(() => {
    let live = true
    navigator.permissions?.query({ name: 'geolocation' as PermissionName })
      .then(p => {
        if (p.state !== 'granted') return
        navigator.geolocation.getCurrentPosition(g => { if (live) setPos({ lat: g.coords.latitude, lng: g.coords.longitude }) })
      })
      .catch(() => {})
    return () => { live = false }
  }, [])
  return pos
}

export default function PartnerStrip({ onOpenPartner, onSeeAll }: {
  onOpenPartner: (slug: string) => void
  onSeeAll: () => void
}) {
  const [data, setData] = useState<PortalPartners | null>(null)
  const pos = useGrantedPosition()

  useEffect(() => {
    let live = true
    api.portal.getPartners().then(r => { if (live) setData(r) }).catch(() => {})
    return () => { live = false }
  }, [])

  const partners = useMemo(() => sortPartners(data?.partners ?? [], pos).slice(0, 8), [data, pos])
  if (!data || partners.length === 0) return null

  return (
    <section aria-label="Earn points at partner stores" style={{ margin: '18px 0 2px' }}>
      <SectionHeader
        title="Earn points"
        icon={<Icon name="drop" size={17} color={t.accent} strokeWidth={2} />}
        action="Partner stores"
        onAction={onSeeAll}
        style={{ padding: '0 16px' }}
      />
      <div className="no-scrollbar" style={{ display: 'flex', gap: 10, overflowX: 'auto', padding: '10px 16px 4px' }}>
        {partners.map(p => {
          const near = nearestStore(p, pos)
          return (
            <Pressable
              key={p.id}
              onClick={() => onOpenPartner(p.slug)}
              style={{
                flex: '0 0 auto', width: 220, display: 'flex', alignItems: 'center', gap: 10, padding: 10,
                background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg,
              }}
            >
              <BrandMark name={p.name} imageUrl={p.logo_url} size={40} />
              <div style={{ minWidth: 0 }}>
                <div style={{ color: t.text1, fontSize: font.size.small + 1, fontWeight: font.weight.semibold, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {p.name}
                </div>
                <div style={{ color: t.text3, fontSize: font.size.caption, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {[p.category, near ? formatDist(near.miles) : null].filter(Boolean).join(' · ') || 'Partner store'}
                </div>
              </div>
            </Pressable>
          )
        })}
      </div>
    </section>
  )
}
