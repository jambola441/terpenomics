/* ============================================================================
   HomeFeed — the portal's landing screen.

   A shopper does not browse "all dispensaries in Brooklyn"; they buy from the
   two or three stores they can actually get to. So the feed is built from the
   stores they follow.

   Two ways to read that, toggled:

     By store   each followed store gets its own block. This is how someone
                shops when they are deciding where to go.
     Combined   the same rails pooled across every followed store, a product
                shown once at whichever of them sells it cheapest. This is how
                someone shops when they want a thing and do not mind whose
                shelf it is on.

   Either way the content is four rails — featured, new arrivals, recommended,
   deals — each a 2×2 grid that scrolls sideways. A single long row of
   everything a store stocks was the old shape, and it answered a question the
   shopper had already answered by following the store.

   Following nothing is the first-run state, not an error — the screen then
   becomes a store picker, ordered by distance, and turns into the feed as soon
   as they pick one.
   ========================================================================== */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api from '../api/client'
import type {
  Feed, FeedListing, FeedRail, FeedRails, FeedSection, FeedView, PortalDispensary,
} from '../types'
import { FEED_RAILS } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { FeedState, Pressable, Skeleton, Pill, ProductImage } from './ui'
import { CATEGORY_EMOJI, productKey } from './browse'
import { formatDist, formatDollars, haversineMi } from '../utils/format'
import { readEnum, readOne, useFilterParams, useScrollMemory, writeOne } from '../utils/browseState'

/** Per rail. Eight fills two 2×2 screens — enough to be worth a swipe, few
 *  enough that four rails per store stay a feed rather than a catalogue. */
const PER_RAIL = 8

const VIEWS = ['store', 'combined'] as const

const RAIL_LABELS: Record<FeedRail, { title: string; blurb: string; icon: string }> = {
  featured: { title: 'Featured', blurb: 'Picked by the store', icon: '★' },
  new: { title: 'New arrivals', blurb: 'Just hit the shelf', icon: '✦' },
  recommended: { title: 'For you', blurb: 'Based on what you buy', icon: '◆' },
  deals: { title: 'Deals', blurb: 'Cheaper than elsewhere', icon: '↓' },
}

interface Props {
  onOpenListing: (dispensaryId: string, listingId: string) => void
  onOpenDispensary: (dispensaryId: string) => void
  /** Open the product page; `brand` is null when the listing has no brand. */
  onOpenProduct: (brand: string | null, productKey: string) => void
}

export default function HomeFeed({ onOpenListing, onOpenDispensary, onOpenProduct }: Props) {
  const [feed, setFeed] = useState<Feed | null>(null)
  const [preferred, setPreferred] = useState<PortalDispensary[] | null>(null)
  // In the URL so a Back from a listing lands on the feed as it was left.
  const [initialParams] = useSearchParams()
  const [view, setView] = useState<FeedView>(() => readEnum(initialParams, 'view', VIEWS, 'store'))
  const [category, setCategory] = useState<string | null>(() => readOne(initialParams, 'category'))
  const scrollRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [picking, setPicking] = useState(false)

  useEffect(() => {
    api.me.listPreferredDispensaries()
      .then(setPreferred)
      .catch(() => setError('Could not load your stores.'))
  }, [])

  // Refetch on filter or view change rather than reshaping client-side: each
  // rail is ranked and capped server-side, so a category filtered here would
  // leave whatever survived out of eight rows instead of its own eight.
  useEffect(() => {
    if (!preferred) return
    if (preferred.length === 0) {
      setFeed(null)
      return
    }
    let live = true
    setFeed(null)
    api.me.getFeed({ view, per_rail: PER_RAIL, category: category ?? undefined })
      .then(res => { if (live) setFeed(res) })
      .catch(() => { if (live) setError('Could not load your feed.') })
    return () => { live = false }
  }, [preferred, view, category])

  // Which categories the followed stores actually carry — a filter offering
  // something none of them stock is a dead end.
  const [categories, setCategories] = useState<string[]>([])
  useEffect(() => {
    api.portal.getCategories()
      .then(rows => setCategories(rows.map(c => c.name)))
      .catch(() => setCategories([]))
  }, [])

  useFilterParams({
    category: writeOne(category),
    view: view === 'store' ? [] : [view],
  })
  useScrollMemory(scrollRef, feed != null)

  const storesById = useMemo(
    () => new Map((feed?.dispensaries ?? []).map(d => [d.id, d])),
    [feed],
  )

  const openProduct = (listing: FeedListing) => onOpenProduct(listing.scraped_brand, productKey({
    category: listing.scraped_category,
    subtype: listing.subtype,
    product_line: listing.product_line,
    strain: listing.strain,
    variant: listing.variant,
  }))

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
    <div ref={scrollRef} style={{ height: 'calc(100dvh - 64px)', overflowY: 'auto', background: t.bg }}>
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

      {/* View toggle */}
      <div style={{ display: 'flex', gap: 6, padding: '14px 16px 0' }}>
        <ViewTab label="By store" active={view === 'store'} onClick={() => setView('store')} />
        <ViewTab label="Combined" active={view === 'combined'} onClick={() => setView('combined')} />
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

      {feed === null ? (
        <HomeSkeleton />
      ) : feed.view === 'combined' ? (
        <CombinedFeed
          rails={feed.combined}
          storesById={storesById}
          category={category}
          onOpenListing={onOpenListing}
          onOpenProduct={openProduct}
        />
      ) : (
        <>
          {feed.sections.map(section => (
            <StoreSection
              key={section.dispensary.id}
              section={section}
              category={category}
              onOpenListing={onOpenListing}
              onOpenDispensary={onOpenDispensary}
              onOpenProduct={openProduct}
            />
          ))}
        </>
      )}
      <div style={{ height: 28 }} />
    </div>
  )
}

/* ── One store's block of rails ────────────────────────────────────────────── */

function StoreSection({ section, category, onOpenListing, onOpenDispensary, onOpenProduct }: {
  section: FeedSection
  category: string | null
  onOpenListing: (dispensaryId: string, listingId: string) => void
  onOpenDispensary: (dispensaryId: string) => void
  onOpenProduct: (listing: FeedListing) => void
}) {
  const { dispensary, rails, total } = section
  const empty = FEED_RAILS.every(rail => rails[rail].length === 0)

  return (
    <div style={{ marginBottom: 14 }}>
      <Pressable
        onClick={() => onOpenDispensary(dispensary.id)}
        style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '20px 16px 6px', width: '100%' }}
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

      {empty ? (
        <div style={{
          margin: '8px 16px 0', padding: '18px 16px', textAlign: 'center',
          background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.lg,
          color: t.text3, fontSize: font.size.small,
        }}>
          {category ? `No ${category} in stock here right now.` : 'Nothing in stock here right now.'}
        </div>
      ) : (
        FEED_RAILS.map(rail => (
          <Rail
            key={rail}
            rail={rail}
            items={rails[rail]}
            onOpenListing={listing => onOpenListing(dispensary.id, listing.id)}
            onOpenProduct={onOpenProduct}
          />
        ))
      )}
    </div>
  )
}

/* ── Every store at once ───────────────────────────────────────────────────── */

function CombinedFeed({ rails, storesById, category, onOpenListing, onOpenProduct }: {
  rails: FeedRails | null
  storesById: Map<string, PortalDispensary>
  category: string | null
  onOpenListing: (dispensaryId: string, listingId: string) => void
  onOpenProduct: (listing: FeedListing) => void
}) {
  if (!rails || FEED_RAILS.every(rail => rails[rail].length === 0)) {
    return (
      <FeedState
        kind="empty"
        message={category ? `No ${category} across your stores right now.` : 'Nothing in stock across your stores.'}
        icon="🌿"
        style={{ padding: '48px 16px' }}
      />
    )
  }

  return (
    <div style={{ marginTop: 6 }}>
      {FEED_RAILS.map(rail => (
        <Rail
          key={rail}
          rail={rail}
          items={rails[rail]}
          storesById={storesById}
          onOpenListing={listing => {
            if (listing.dispensary_id) onOpenListing(listing.dispensary_id, listing.id)
          }}
          onOpenProduct={onOpenProduct}
        />
      ))}
    </div>
  )
}

/* ── A rail: two rows deep, scrolling sideways ─────────────────────────────── */

function Rail({ rail, items, storesById, onOpenListing, onOpenProduct }: {
  rail: FeedRail
  items: FeedListing[]
  storesById?: Map<string, PortalDispensary>
  onOpenListing: (listing: FeedListing) => void
  onOpenProduct: (listing: FeedListing) => void
}) {
  // An empty rail says nothing worth the vertical space — except Featured,
  // which is empty because nobody has curated it yet, and saying so is how the
  // store learns the slot exists.
  if (items.length === 0 && rail !== 'featured') return null

  const { title, blurb, icon } = RAIL_LABELS[rail]

  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '0 16px 9px' }}>
        <span style={{ color: t.accent, fontSize: font.size.small }} aria-hidden>{icon}</span>
        <span style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout, letterSpacing: '-0.01em' }}>
          {title}
        </span>
        <span style={{ color: t.text4, fontSize: font.size.caption }}>{blurb}</span>
      </div>

      {items.length === 0 ? (
        <div style={{
          margin: '0 16px', padding: '14px 16px',
          background: t.surface2, border: `1px dashed ${t.border}`, borderRadius: radius.lg,
          color: t.text3, fontSize: font.size.caption, textAlign: 'center',
        }}>
          Nothing featured here yet.
        </div>
      ) : (
        // Two rows, filled column by column, so a swipe moves through pairs.
        <div
          className="no-scrollbar"
          style={{
            display: 'grid',
            gridTemplateRows: 'repeat(2, auto)',
            gridAutoFlow: 'column',
            gridAutoColumns: 'minmax(148px, 46%)',
            gap: 10,
            overflowX: 'auto',
            padding: '0 16px 4px',
            scrollSnapType: 'x proximity',
          }}
        >
          {items.map(listing => (
            <FeedCard
              key={`${listing.dispensary_id ?? ''}-${listing.id}`}
              listing={listing}
              rail={rail}
              store={listing.dispensary_id ? storesById?.get(listing.dispensary_id) : undefined}
              onOpen={() => onOpenListing(listing)}
              onOpenBrand={() => onOpenProduct(listing)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function FeedCard({ listing, rail, store, onOpen, onOpenBrand }: {
  listing: FeedListing
  rail: FeedRail
  store?: PortalDispensary
  onOpen: () => void
  onOpenBrand: () => void
}) {
  const color = categoryColor(listing.scraped_category)
  const saving = listing.saving_cents

  return (
    <Pressable
      onClick={onOpen}
      lift
      style={{
        scrollSnapAlign: 'start',
        background: t.surface1, border: `1px solid ${t.border}`,
        borderRadius: radius.lg, overflow: 'hidden', textAlign: 'left',
        display: 'flex', flexDirection: 'column',
      }}
    >
      <div style={{ position: 'relative' }}>
        <ProductImage
          src={listing.image_url}
          alt={listing.display_name}
          category={listing.scraped_category}
          height={96}
        />
        {/* Only the deals rail earns a badge: elsewhere the saving is a fact
            about the product, not the reason it is on screen. */}
        {rail === 'deals' && saving != null && saving > 0 && (
          <span style={{
            position: 'absolute', top: 7, left: 7,
            background: t.accent, color: t.accentInk,
            fontSize: font.size.caption, fontWeight: font.weight.bold,
            borderRadius: radius.pill, padding: '2px 7px',
          }}>
            Save {formatDollars(saving)}
          </span>
        )}
      </div>

      <div style={{ padding: '8px 10px 10px', display: 'flex', flexDirection: 'column', flex: 1 }}>
        {listing.scraped_brand && (
          <div
            onClick={e => { e.stopPropagation(); onOpenBrand() }}
            style={{
              color: t.accent, fontSize: font.size.caption, fontWeight: font.weight.semibold,
              marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              cursor: 'pointer',
            }}
          >
            {listing.scraped_brand}
          </div>
        )}
        <div style={{
          color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small,
          lineHeight: 1.3, height: '2.6em', overflow: 'hidden',
        }}>
          {listing.display_name}
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

        {/* In the combined view a card has to say whose shelf it is on, and how
            many of the shopper's other stores also have it. */}
        {store && (
          <div style={{
            color: t.text3, fontSize: font.size.caption, marginTop: 6,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {store.name}
            {listing.other_store_count > 1 && ` · at ${listing.other_store_count} of yours`}
          </div>
        )}
      </div>
    </Pressable>
  )
}

function ViewTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      style={{
        flex: 1, cursor: 'pointer',
        background: active ? alpha(t.accent, 0.14) : t.surface2,
        border: `1px solid ${active ? t.accent : t.border}`,
        borderRadius: radius.pill, padding: '9px 0',
        color: active ? t.accent : t.text3,
        fontSize: font.size.small, fontWeight: active ? font.weight.bold : font.weight.medium,
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
          <div style={{ padding: '0 16px 9px' }}><Skeleton width={110} height={12} /></div>
          <div className="no-scrollbar" style={{
            display: 'grid', gridTemplateRows: 'repeat(2, auto)', gridAutoFlow: 'column',
            gridAutoColumns: 'minmax(148px, 46%)', gap: 10, padding: '0 16px', overflow: 'hidden',
          }}>
            {[0, 1, 2, 3].map(i => (
              <div key={i}>
                <Skeleton height={96} radius={radius.lg} />
                <div style={{ padding: '8px 2px' }}>
                  <Skeleton width="70%" height={10} style={{ marginBottom: 6 }} />
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
