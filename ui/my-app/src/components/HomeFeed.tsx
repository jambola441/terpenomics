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
import { t, radius, font, categoryColor, categoryLabel, alpha } from '../theme'
import { FeedState, Pressable, Skeleton, Pill, ProductImage, PageTitle, StoreBullet } from './ui'
import { MarketNote, productKey } from './browse'
import { Icon, CategoryIcon, type IconName } from './Icon'
import { formatDist, formatDollars, haversineMi } from '../utils/format'
import { readEnum, readOne, useFilterParams, useScrollMemory, writeOne } from '../utils/browseState'

/** Per rail. Eight fills two 2×2 screens — enough to be worth a swipe, few
 *  enough that four rails per store stay a feed rather than a catalogue. */
const PER_RAIL = 8

const VIEWS = ['store', 'combined'] as const

const RAIL_LABELS: Record<FeedRail, { title: string; blurb: string; icon: IconName }> = {
  featured: { title: 'Featured', blurb: 'Picked by the store', icon: 'star' },
  new: { title: 'New arrivals', blurb: 'Just hit the shelf', icon: 'sparkles' },
  recommended: { title: 'For you', blurb: 'Based on what you buy', icon: 'heart' },
  deals: { title: 'Deals', blurb: 'Cheaper than elsewhere', icon: 'tag' },
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
  // Bumped when the shopper follows or unfollows, so the feed is rebuilt for
  // the new set of stores.
  const [followVersion, setFollowVersion] = useState(0)
  const firstLoadDone = useRef(false)
  // Bumped by Try again to rerun the load below.
  const [attempt, setAttempt] = useState(0)

  // The feed names every store the shopper follows, so the first load takes it
  // alone instead of asking for the stores first and the feed after: one round
  // trip before Home shows anything, not two.
  //
  // Refetch on filter or view change rather than reshaping client-side: each
  // rail is ranked and capped server-side, so a category filtered here would
  // leave whatever survived out of eight rows instead of its own eight.
  useEffect(() => {
    // While the picker is open the feed would only be thrown away; it is
    // fetched once, for the final set of stores, when the shopper taps Done.
    if (picking) return
    let live = true
    setFeed(null)
    setError(null)
    api.me.getFeed({ view, per_rail: PER_RAIL, category: category ?? undefined })
      .then(res => {
        if (!live) return
        setFeed(res)
        setPreferred(res.dispensaries)
        // Nobody followed yet: open the picker in its "pick a few, then Done"
        // mode, rather than closing it after the first Follow.
        if (!firstLoadDone.current && res.dispensaries.length === 0) setPicking(true)
        firstLoadDone.current = true
      })
      .catch(() => { if (live) setError('Could not load your feed.') })
    return () => { live = false }
  }, [view, category, followVersion, picking, attempt])

  function changeFollowed(next: PortalDispensary[]) {
    setPreferred(next)
    setFollowVersion(v => v + 1)
  }

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
        <FeedState kind="error" message={error} style={{ height: '100%' }} onRetry={() => setAttempt(n => n + 1)} />
      </div>
    )
  }

  if (!preferred) {
    return <div style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', background: t.bg }}><HomeSkeleton /></div>
  }

  if (preferred.length === 0 || picking) {
    return (
      <StorePicker
        preferred={preferred}
        onChange={changeFollowed}
        onDone={picking ? () => setPicking(false) : undefined}
      />
    )
  }

  return (
    <div ref={scrollRef} style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: 'calc(env(safe-area-inset-top, 0px) + 26px) 16px 6px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <PageTitle
          style={{ minWidth: 0 }}
          sub={<>{preferred.length} {preferred.length === 1 ? 'store' : 'stores'} · what&apos;s on the shelf now</>}
        >
          Your stores
        </PageTitle>
        <button
          onClick={() => setPicking(true)}
          style={{
            flexShrink: 0, background: 'transparent', border: `1px solid ${t.borderStrong}`,
            borderRadius: radius.md, color: t.text1, cursor: 'pointer', marginTop: 4,
            fontSize: font.size.small + 1, fontWeight: font.weight.semibold, padding: '7px 12px',
            display: 'inline-flex', alignItems: 'center', gap: 6,
          }}
        >
          <Icon name="edit" size={14} />
          Edit
        </button>
      </div>

      {/* View toggle — a segmented control, not two buttons */}
      <div role="group" aria-label="Feed view" style={{
        display: 'flex', gap: 2, margin: '14px 16px 0', padding: 3,
        background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.md,
      }}>
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
              label={categoryLabel(name)}
              category={name}
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
            color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold,
            fontSize: font.size.heading, letterSpacing: '-0.015em', lineHeight: 1.2,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {dispensary.name}
          </div>
          <div className="num" style={{ color: t.text3, fontSize: font.size.caption, marginTop: 2 }}>
            {total.toLocaleString()} in stock{dispensary.accepts_pickup ? ' · pickup' : ''}
          </div>
        </div>
        <span style={{ color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.semibold, flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 2 }}>
          See all <Icon name="chevron-right" size={15} />
        </span>
      </Pressable>

      {empty ? (
        <div style={{
          margin: '8px 16px 0', padding: '18px 16px', textAlign: 'center',
          background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.lg,
          color: t.text3, fontSize: font.size.small,
        }}>
          {category ? `No ${categoryLabel(category).toLowerCase()} in stock here right now.` : 'Nothing in stock here right now.'}
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
        message={category ? `No ${categoryLabel(category).toLowerCase()} across your stores right now.` : 'Nothing in stock across your stores.'}
        icon={category ? <CategoryIcon category={category} size={22} /> : 'leaf'}
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '0 16px 10px' }}>
        <Icon name={icon} size={15} color={t.text3} />
        <span style={{ color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.callout }}>
          {title}
        </span>
        <span style={{ color: t.text3, fontSize: font.size.caption }}>{blurb}</span>
      </div>

      {items.length === 0 ? (
        <div style={{
          margin: '0 16px', padding: '14px 16px',
          background: 'transparent', border: `1px dashed ${t.borderStrong}`, borderRadius: radius.lg,
          color: t.text3, fontSize: font.size.caption, textAlign: 'center',
        }}>
          No picks from this store right now.
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
        {/* Square, and as wide as the card: a product shot is the whole
            reason to look at a rail, and a 96px band cropped it to a strip. */}
        <ProductImage
          src={listing.image_url}
          alt={listing.display_name}
          category={listing.scraped_category}
        />

        {/* Same corners as a browse card: the size top-left, where a shopper
            already looks for it, and the rail's own badge opposite. */}
        {listing.variant && <CornerTag label={listing.variant} side="left" />}

        {/* Only the deals rail earns a badge: elsewhere the saving is a fact
            about the product, not the reason it is on screen. */}
        {rail === 'deals' && saving != null && saving > 0 && (
          <span className="num" style={{
            position: 'absolute', top: 8, right: 8,
            background: t.success, color: t.accentInk,
            fontFamily: font.family.mono, fontSize: font.size.micro + 0.5, fontWeight: font.weight.medium,
            borderRadius: radius.sm, padding: '3px 7px',
          }}>
            Save {formatDollars(saving)}
          </span>
        )}
      </div>

      <div style={{ padding: '10px 11px 12px', display: 'flex', flexDirection: 'column', flex: 1 }}>
        {/* Price first, then name, then brand -- a browse card's order. */}
        <div className="num" style={listing.price_cents != null ? {
          color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout + 1,
          letterSpacing: '-0.01em', marginBottom: 4,
        } : { color: t.text3, fontSize: font.size.caption, marginBottom: 4 }}>
          {listing.price_cents != null ? formatDollars(listing.price_cents) : 'Price not listed'}
        </div>

        <div style={{
          color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small + 1,
          lineHeight: 1.3, height: '2.6em', overflow: 'hidden',
        }}>
          {listing.display_name}
        </div>

        {listing.scraped_brand && (
          <div
            onClick={e => { e.stopPropagation(); onOpenBrand() }}
            style={{
              color: t.text3, fontSize: font.size.caption, marginTop: 3,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              cursor: 'pointer',
            }}
          >
            {listing.scraped_brand}
          </div>
        )}

        {listing.subtype && (
          <div style={{ marginTop: 8 }}>
            <Pill color={color} tone="category">{listing.subtype}</Pill>
          </div>
        )}

        {/* Pinned to the bottom so cards in a rail line up. */}
        <div style={{ marginTop: 'auto', paddingTop: 8 }}>
          {/* In the combined view a card has to say whose shelf it is on, and
              how many of the shopper's other stores also have it. */}
          {store && (
            <div style={{
              color: t.text2, fontSize: font.size.caption, marginBottom: 2,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {store.name}
              {listing.preferred_store_count > 1 && ` · at ${listing.preferred_store_count} of yours`}
            </div>
          )}
          <MarketNote market={listing.market} priceCents={listing.price_cents} />
        </div>
      </div>
    </Pressable>
  )
}

/** The size chip a browse card wears in the top-left of its image. */
function CornerTag({ label, side }: { label: string; side: 'left' | 'right' }) {
  return (
    <span style={{
      position: 'absolute', top: 8, [side]: 8,
      background: 'rgba(12, 15, 13, 0.78)', color: t.text1,
      backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
      fontFamily: font.family.mono, fontSize: font.size.micro + 0.5, fontWeight: font.weight.medium,
      padding: '3px 7px', borderRadius: radius.sm,
    }}>
      {label}
    </span>
  )
}

function ViewTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      style={{
        flex: 1, cursor: 'pointer',
        background: active ? t.surface3 : 'transparent',
        border: 'none', boxShadow: active ? 'var(--e-1)' : 'none',
        borderRadius: radius.sm, padding: '8px 0',
        color: active ? t.text1 : t.text3,
        fontSize: font.size.small + 1, fontWeight: active ? font.weight.semibold : font.weight.medium,
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
                <Skeleton height={0} radius={radius.lg} style={{ aspectRatio: '1 / 1', height: 'auto' }} />
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
    <div style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: 'calc(env(safe-area-inset-top, 0px) + 26px) 16px 6px' }}>
        <PageTitle>{preferred.length === 0 ? 'Pick your stores' : 'Your stores'}</PageTitle>
        <div style={{ color: t.text2, fontSize: font.size.body, marginTop: 8, lineHeight: 1.55, maxWidth: 420 }}>
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
              border: 'none', borderRadius: radius.md,
              color: preferred.length === 0 ? t.text4 : t.accentInk,
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
                  border: `1px solid ${isFollowed ? t.accentDim : t.border}`,
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
                  <div style={{ marginTop: 7 }}>
                    {d.accepts_pickup
                      ? <Pill color={t.success}><Icon name="bag" size={11} strokeWidth={2} />Pickup</Pill>
                      : <Pill>In-store only</Pill>}
                  </div>
                </div>
                <button
                  onClick={() => toggle(d)}
                  disabled={pending.has(d.id)}
                  style={{
                    flexShrink: 0, cursor: pending.has(d.id) ? 'default' : 'pointer',
                    background: isFollowed ? t.accentTint : 'transparent',
                    border: `1px solid ${isFollowed ? t.accentDim : t.borderStrong}`,
                    borderRadius: radius.md, padding: '8px 12px',
                    color: isFollowed ? t.accent : t.text1,
                    fontSize: font.size.small + 1, fontWeight: font.weight.semibold,
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                  }}
                >
                  <Icon name={isFollowed ? 'check' : 'plus'} size={14} strokeWidth={2} />
                  {isFollowed ? 'Following' : 'Follow'}
                </button>
              </div>
            )
          })}
          <button
            onClick={() => navigate('/portal/map')}
            style={{
              marginTop: 4, background: 'transparent', border: `1px dashed ${t.borderStrong}`,
              borderRadius: radius.lg, color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium,
              padding: 12, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            <Icon name="map" size={15} />
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
  const [broken, setBroken] = useState(false)
  // No logo: the store's subway bullet, the same disc it wears on the map.
  if (!logo || broken) return <StoreBullet name={dispensary.name} address={dispensary.address} size={size} />
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0, overflow: 'hidden',
      background: t.surface2, border: `1px solid ${t.border}`,
    }}>
      <img src={logo} alt="" onError={() => setBroken(true)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
    </div>
  )
}

function CategoryChip({ label, active, color, category, onClick }: {
  label: string
  active: boolean
  color?: string
  category?: string
  onClick: () => void
}) {
  const accent = color ?? t.accent
  const tint = (a: number) => accent.startsWith('#') ? alpha(accent, a) : `color-mix(in srgb, ${accent} ${a * 100}%, transparent)`
  return (
    <button
      onClick={onClick}
      style={{
        flexShrink: 0, cursor: 'pointer', whiteSpace: 'nowrap',
        fontSize: font.size.small + 1, fontWeight: active ? font.weight.semibold : font.weight.medium,
        padding: category ? '7px 13px 7px 10px' : '7px 13px', borderRadius: radius.pill,
        background: active ? tint(0.12) : t.surface2,
        border: `1px solid ${active ? tint(0.6) : t.border}`,
        color: active ? accent : t.text2,
        display: 'inline-flex', alignItems: 'center', gap: 6,
        transition: 'all var(--t-fast)',
      }}
    >
      {category && <CategoryIcon category={category} size={15} color={active ? accent : undefined} />}
      {label}
    </button>
  )
}
