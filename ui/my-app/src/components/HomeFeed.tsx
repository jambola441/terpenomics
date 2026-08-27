/* ============================================================================
   HomeFeed — the portal's landing screen.

   A shopper does not browse "all dispensaries in Brooklyn"; they buy from the
   two or three stores they can actually get to. So the feed is built from the
   stores they follow: one section per store, each a rail of what is on the
   shelf there right now, with a category filter that applies across all of
   them at once.

   Following nothing is the first-run state, not an error — the screen then
   becomes a store picker, ordered by distance, and turns into the feed as soon
   as they pick one.
   ========================================================================== */

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { FeedListing, FeedSection, PortalDispensary } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { FeedState, Pressable, Skeleton, Pill, ProductImage } from './ui'
import { CATEGORY_EMOJI, productKey } from './browse'
import { formatDist, formatDollars, haversineMi } from '../utils/format'

/** How much of each store's shelf a section shows before "see all". */
const PER_DISPENSARY = 12

interface Props {
  onOpenListing: (dispensaryId: string, listingId: string) => void
  onOpenDispensary: (dispensaryId: string) => void
  onOpenBrandProduct: (brand: string, productKey: string) => void
}

export default function HomeFeed({ onOpenListing, onOpenDispensary, onOpenBrandProduct }: Props) {
  const [sections, setSections] = useState<FeedSection[] | null>(null)
  const [preferred, setPreferred] = useState<PortalDispensary[] | null>(null)
  const [category, setCategory] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [picking, setPicking] = useState(false)

  useEffect(() => {
    api.me.listPreferredDispensaries()
      .then(setPreferred)
      .catch(() => setError('Could not load your stores.'))
  }, [])

  // Refetch on filter change rather than slicing client-side: the section cap is
  // applied per store server-side, so filtering here would leave a category with
  // whatever happened to survive out of twelve rows instead of its own twelve.
  useEffect(() => {
    if (!preferred) return
    if (preferred.length === 0) {
      setSections([])
      return
    }
    let live = true
    setSections(null)
    api.me.getFeed({ per_dispensary: PER_DISPENSARY, category: category ?? undefined })
      .then(res => { if (live) setSections(res.sections) })
      .catch(() => { if (live) setError('Could not load your feed.') })
    return () => { live = false }
  }, [preferred, category])

  // Which categories the followed stores actually carry — a filter offering
  // something none of them stock is a dead end.
  const [categories, setCategories] = useState<string[]>([])
  useEffect(() => {
    api.portal.getCategories()
      .then(rows => setCategories(rows.map(c => c.name)))
      .catch(() => setCategories([]))
  }, [])

  if (error) {
    return (
      <div style={{ height: '100dvh', background: t.bg }}>
        <FeedState kind="error" message={error} style={{ height: '100%' }} />
      </div>
    )
  }

  if (!preferred) {
    return <div style={{ height: 'calc(100dvh - 64px)', background: t.bg }}><HomeSkeleton /></div>
  }

  if (preferred.length === 0 || picking) {
    return (
      <StorePicker
        preferred={preferred}
        onChange={setPreferred}
        onDone={picking ? () => setPicking(false) : undefined}
      />
    )
  }

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: '22px 16px 6px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero, letterSpacing: '-0.02em' }}>
            Your stores
          </div>
          <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
            {preferred.length} {preferred.length === 1 ? 'store' : 'stores'} · what&apos;s on the shelf now
          </div>
        </div>
        <button
          onClick={() => setPicking(true)}
          style={{
            flexShrink: 0, background: t.surface2, border: `1px solid ${t.border}`,
            borderRadius: radius.pill, color: t.text2, cursor: 'pointer',
            fontSize: font.size.small, fontWeight: font.weight.semibold, padding: '7px 14px',
          }}
        >
          Edit
        </button>
      </div>

      {/* Category filter, applied across every followed store at once. */}
      {categories.length > 0 && (
        <div
          className="no-scrollbar"
          style={{ display: 'flex', gap: 8, overflowX: 'auto', padding: '12px 16px 4px' }}
        >
          <CategoryChip label="All" active={category === null} onClick={() => setCategory(null)} />
          {categories.map(name => (
            <CategoryChip
              key={name}
              label={`${CATEGORY_EMOJI[name] ?? '📦'} ${name}`}
              color={categoryColor(name)}
              active={category === name}
              onClick={() => setCategory(category === name ? null : name)}
            />
          ))}
        </div>
      )}

      {sections === null ? (
        <HomeSkeleton />
      ) : (
        <>
          {sections.map(section => (
            <StoreSection
              key={section.dispensary.id}
              section={section}
              category={category}
              onOpenListing={onOpenListing}
              onOpenDispensary={onOpenDispensary}
              onOpenBrandProduct={onOpenBrandProduct}
            />
          ))}
          <div style={{ height: 28 }} />
        </>
      )}
    </div>
  )
}

/* ── One store's slice of the feed ─────────────────────────────────────────── */

function StoreSection({ section, category, onOpenListing, onOpenDispensary, onOpenBrandProduct }: {
  section: FeedSection
  category: string | null
  onOpenListing: (dispensaryId: string, listingId: string) => void
  onOpenDispensary: (dispensaryId: string) => void
  onOpenBrandProduct: (brand: string, productKey: string) => void
}) {
  const { dispensary, listings, total } = section
  const more = total - listings.length

  return (
    <div style={{ marginBottom: 8 }}>
      <Pressable
        onClick={() => onOpenDispensary(dispensary.id)}
        style={{
          display: 'flex', alignItems: 'center', gap: 11,
          padding: '18px 16px 11px', width: '100%',
        }}
      >
        <StoreAvatar dispensary={dispensary} size={38} />
        <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
          <div style={{
            color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.title,
            letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {dispensary.name}
          </div>
          <div style={{ color: t.text3, fontSize: font.size.caption, marginTop: 1 }}>
            {total.toLocaleString()} in stock{dispensary.accepts_pickup ? ' · pickup' : ''}
          </div>
        </div>
        <span style={{ color: t.accent, fontSize: font.size.small, fontWeight: font.weight.semibold, flexShrink: 0 }}>
          See all ›
        </span>
      </Pressable>

      {listings.length === 0 ? (
        <div style={{
          margin: '0 16px', padding: '18px 16px', textAlign: 'center',
          background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.lg,
          color: t.text3, fontSize: font.size.small,
        }}>
          {category ? `No ${category} in stock here right now.` : 'Nothing in stock here right now.'}
        </div>
      ) : (
        <div
          className="no-scrollbar"
          style={{
            display: 'flex', gap: 12, overflowX: 'auto',
            padding: '0 16px 6px', scrollSnapType: 'x proximity',
          }}
        >
          {listings.map(listing => (
            <FeedCard
              key={listing.id}
              listing={listing}
              onOpen={() => onOpenListing(dispensary.id, listing.id)}
              onOpenBrand={
                listing.scraped_brand
                  ? () => onOpenBrandProduct(listing.scraped_brand as string, productKey({
                      category: listing.scraped_category,
                      subtype: listing.subtype,
                      product_line: listing.product_line,
                      strain: listing.strain,
                      variant: listing.variant,
                    }))
                  : undefined
              }
            />
          ))}
          {more > 0 && (
            <Pressable
              onClick={() => onOpenDispensary(dispensary.id)}
              style={{
                width: 148, flexShrink: 0, scrollSnapAlign: 'start',
                background: t.surface2, border: `1px dashed ${t.border}`, borderRadius: radius.lg,
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}
            >
              <span style={{ color: t.accent, fontWeight: font.weight.bold, fontSize: font.size.title }}>
                +{more.toLocaleString()}
              </span>
              <span style={{ color: t.text3, fontSize: font.size.caption }}>more in store</span>
            </Pressable>
          )}
        </div>
      )}
    </div>
  )
}

function FeedCard({ listing, onOpen, onOpenBrand }: {
  listing: FeedListing
  onOpen: () => void
  onOpenBrand?: () => void
}) {
  const color = categoryColor(listing.scraped_category)
  const name = listing.scraped_name || listing.strain || listing.product_line || '—'

  return (
    <Pressable
      onClick={onOpen}
      lift
      style={{
        width: 148, flexShrink: 0, scrollSnapAlign: 'start',
        background: t.surface1, border: `1px solid ${t.border}`,
        borderRadius: radius.lg, overflow: 'hidden', textAlign: 'left',
      }}
    >
      <ProductImage
        src={listing.image_url}
        alt={name}
        category={listing.scraped_category}
        height={108}
      />
      <div style={{ padding: '9px 10px 11px' }}>
        {listing.scraped_brand && (
          <div
            onClick={onOpenBrand ? (e => { e.stopPropagation(); onOpenBrand() }) : undefined}
            style={{
              color: onOpenBrand ? t.accent : t.text3, fontSize: font.size.caption,
              fontWeight: font.weight.semibold, marginBottom: 2,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              cursor: onOpenBrand ? 'pointer' : 'default',
            }}
          >
            {listing.scraped_brand}
          </div>
        )}
        <div style={{
          color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small,
          lineHeight: 1.3, height: '2.6em', overflow: 'hidden',
        }}>
          {name}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, marginTop: 7 }}>
          <span style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.small + 1 }}>
            {listing.price_cents != null ? formatDollars(listing.price_cents) : '—'}
          </span>
          {listing.variant && (
            <span style={{
              color, fontSize: font.size.caption, fontWeight: font.weight.semibold,
              background: alpha(color, 0.12), borderRadius: radius.pill, padding: '2px 7px',
            }}>
              {listing.variant}
            </span>
          )}
        </div>
      </div>
    </Pressable>
  )
}

/* ── Choosing which stores the feed is built from ──────────────────────────── */

function StorePicker({ preferred, onChange, onDone }: {
  preferred: PortalDispensary[]
  onChange: (next: PortalDispensary[]) => void
  onDone?: () => void
}) {
  const navigate = useNavigate()
  const [all, setAll] = useState<PortalDispensary[] | null>(null)
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)
  const [pending, setPending] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.portal.getDispensaries()
      .then(setAll)
      .catch(() => setError('Could not load dispensaries.'))
    navigator.geolocation?.getCurrentPosition(pos => {
      setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude })
    })
  }, [])

  const followed = useMemo(() => new Set(preferred.map(d => d.id)), [preferred])

  const sorted = useMemo(() => {
    if (!all) return []
    if (!userPos) return all
    return [...all].sort((a, b) => {
      if (a.lat == null || a.lng == null) return 1
      if (b.lat == null || b.lng == null) return -1
      return haversineMi(userPos.lat, userPos.lng, a.lat, a.lng)
        - haversineMi(userPos.lat, userPos.lng, b.lat, b.lng)
    })
  }, [all, userPos])

  async function toggle(dispensary: PortalDispensary) {
    setPending(prev => new Set(prev).add(dispensary.id))
    try {
      const next = followed.has(dispensary.id)
        ? await api.me.removePreferredDispensary(dispensary.id)
        : await api.me.addPreferredDispensary(dispensary.id)
      onChange(next)
    } catch {
      setError('That did not save. Try again.')
    } finally {
      setPending(prev => {
        const copy = new Set(prev)
        copy.delete(dispensary.id)
        return copy
      })
    }
  }

  return (
    <div style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: '22px 16px 6px' }}>
        <div style={{ color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.hero, letterSpacing: '-0.02em' }}>
          {onDone ? 'Your stores' : 'Pick your stores'}
        </div>
        <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 4, lineHeight: 1.5 }}>
          Your home feed is built from the stores you follow. Pick the ones you actually shop at —
          you can change this any time.
        </div>
      </div>

      {error && (
        <div style={{ color: t.danger, fontSize: font.size.small, padding: '8px 16px' }}>{error}</div>
      )}

      {onDone && (
        <div style={{ padding: '10px 16px 0' }}>
          <button
            onClick={onDone}
            disabled={preferred.length === 0}
            style={{
              width: '100%', boxSizing: 'border-box',
              background: preferred.length === 0 ? t.surface2 : t.accent,
              border: 'none', borderRadius: radius.lg,
              color: preferred.length === 0 ? t.text3 : t.accentInk,
              fontWeight: font.weight.bold, fontSize: font.size.callout,
              padding: 13, cursor: preferred.length === 0 ? 'default' : 'pointer',
            }}
          >
            Done
          </button>
        </div>
      )}

      {all === null ? (
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[0, 1, 2, 3].map(i => <Skeleton key={i} height={72} radius={radius.lg} />)}
        </div>
      ) : (
        <div style={{ padding: '14px 16px 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {sorted.map(d => {
            const isFollowed = followed.has(d.id)
            const dist = (userPos && d.lat != null && d.lng != null)
              ? haversineMi(userPos.lat, userPos.lng, d.lat, d.lng)
              : null
            return (
              <div
                key={d.id}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: 12,
                  background: t.surface1, borderRadius: radius.lg,
                  border: `1px solid ${isFollowed ? alpha(t.accent, 0.35) : t.border}`,
                }}
              >
                <StoreAvatar dispensary={d} size={44} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.body,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {d.name}
                  </div>
                  <div style={{ color: t.text3, fontSize: font.size.caption, marginTop: 2 }}>
                    {d.address ?? '—'}{dist != null ? ` · ${formatDist(dist)}` : ''}
                  </div>
                  <div style={{ marginTop: 6 }}>
                    {d.accepts_pickup
                      ? <Pill color={categoryColor('flower')} tone="category">🛒 Pickup</Pill>
                      : <Pill>In-store only</Pill>}
                  </div>
                </div>
                <button
                  onClick={() => toggle(d)}
                  disabled={pending.has(d.id)}
                  style={{
                    flexShrink: 0, cursor: pending.has(d.id) ? 'default' : 'pointer',
                    background: isFollowed ? alpha(t.accent, 0.14) : 'transparent',
                    border: `1px solid ${isFollowed ? t.accent : t.border}`,
                    borderRadius: radius.pill, padding: '8px 14px',
                    color: isFollowed ? t.accent : t.text2,
                    fontSize: font.size.small, fontWeight: font.weight.semibold,
                  }}
                >
                  {isFollowed ? '✓ Following' : 'Follow'}
                </button>
              </div>
            )
          })}
          <button
            onClick={() => navigate('/portal/map')}
            style={{
              marginTop: 4, background: 'transparent', border: `1px solid ${t.border}`,
              borderRadius: radius.lg, color: t.text3, fontSize: font.size.small,
              padding: 12, cursor: 'pointer',
            }}
          >
            Find stores on the map
          </button>
        </div>
      )}
    </div>
  )
}

/* ── Shared bits ───────────────────────────────────────────────────────────── */

function StoreAvatar({ dispensary, size }: { dispensary: PortalDispensary; size: number }) {
  const logo = dispensary.logo_url || dispensary.banner_url
  return (
    <div style={{
      width: size, height: size, borderRadius: radius.md, flexShrink: 0, overflow: 'hidden',
      background: t.surface2, border: `1px solid ${t.border}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      {logo ? (
        <img
          src={logo}
          alt=""
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: size * 0.45 }}>
          {dispensary.name.charAt(0).toUpperCase()}
        </span>
      )}
    </div>
  )
}

function CategoryChip({ label, active, color, onClick }: {
  label: string
  active: boolean
  color?: string
  onClick: () => void
}) {
  const accent = color ?? t.accent
  return (
    <button
      onClick={onClick}
      style={{
        flexShrink: 0, cursor: 'pointer', whiteSpace: 'nowrap', textTransform: 'capitalize',
        fontSize: font.size.small, fontWeight: active ? font.weight.bold : font.weight.medium,
        padding: '7px 13px', borderRadius: radius.pill,
        background: active ? alpha(accent, 0.14) : t.surface2,
        border: `1px solid ${active ? accent : t.border}`,
        color: active ? accent : t.text3,
        transition: 'all var(--t-fast)',
      }}
    >
      {label}
    </button>
  )
}

function HomeSkeleton() {
  return (
    <div style={{ padding: '8px 0' }}>
      {[0, 1].map(section => (
        <div key={section}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '18px 16px 11px' }}>
            <Skeleton width={38} height={38} radius={radius.md} />
            <div style={{ flex: 1 }}>
              <Skeleton width={150} height={15} style={{ marginBottom: 6 }} />
              <Skeleton width={90} height={11} />
            </div>
          </div>
          <div className="no-scrollbar" style={{ display: 'flex', gap: 12, padding: '0 16px', overflow: 'hidden' }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{ width: 148, flexShrink: 0 }}>
                <Skeleton height={108} radius={radius.lg} />
                <div style={{ padding: '10px 2px' }}>
                  <Skeleton width="70%" height={11} style={{ marginBottom: 7 }} />
                  <Skeleton width="90%" height={12} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
