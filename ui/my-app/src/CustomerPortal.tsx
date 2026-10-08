/* ============================================================================
   CustomerPortal — the shell.

   Everything a section needs lives in that section's own file; this file owns
   only what is genuinely shared: the auth gate, the cart, and which of the six
   sections is on screen.

   The sections are Home (a feed of the stores you follow), Brands, Categories,
   Search, Map and Profile. Brands and Categories used to be reachable only by
   scrolling a rail on the home screen, which made the two biggest ways to
   browse the catalogue the two hardest to find.
   ========================================================================== */

import { useState, useEffect, type CSSProperties } from 'react'
import { useNavigate, useSearchParams, useMatch, Navigate, useLocation } from 'react-router-dom'
import api, { ApiError } from './api/client'
import supabase from './utils/supabase'
import DispensaryMap from './components/DispensaryMap'
import HomeFeed from './components/HomeFeed'
import BrandsPage from './components/BrandsPage'
import BrandView from './components/BrandView'
import ProductView from './components/ProductView'
import CategoriesPage from './components/CategoriesPage'
import CategoryView from './components/CategoryView'
import SearchView from './components/SearchView'
import ListingDetailView from './components/ListingDetail'
import ProfileView from './components/ProfileView'
import CartDrawer from './components/CartDrawer'
import ConfirmSheet from './components/ConfirmSheet'
import OnboardingScreen from './components/OnboardingScreen'
import type { CartItem, CustomerProfile, Order } from './types'
import type { Session } from '@supabase/auth-js'
import { t, radius, font, motion } from './theme'
import { FeedState } from './components/ui'
import { Icon, type IconName } from './components/Icon'
import 'leaflet/dist/leaflet.css'

/** Mirrors MAX_QTY_PER_LINE in routes/orders.py. */
const MAX_QTY_PER_LINE = 12

type Tab = 'home' | 'brands' | 'categories' | 'search' | 'map' | 'profile'

const TABS: { key: Tab; label: string; icon: IconName }[] = [
  { key: 'home', label: 'Home', icon: 'home' },
  { key: 'brands', label: 'Brands', icon: 'tag' },
  { key: 'categories', label: 'Shop', icon: 'grid' },
  { key: 'search', label: 'Search', icon: 'search' },
  { key: 'map', label: 'Map', icon: 'pin' },
  { key: 'profile', label: 'You', icon: 'user' },
]

/** Detail screens sit inside a section rather than beside it, so the nav keeps
 *  showing where the shopper is while they drill down. */
const SECTION_OF: Record<string, Tab> = {
  brands: 'brands',
  categories: 'categories',
  search: 'search',
  map: 'map',
  profile: 'profile',
  home: 'home',
}

type AccountProblem = 'not_linked' | 'unreachable'

/** /me, linking the sign-in to a customer first if this is its first visit.
 *  Only a 404 means "not linked yet". A timeout or a 500 is an outage, and
 *  linking on one used to turn a blip into "your account isn't connected". */
async function loadProfile(): Promise<CustomerProfile> {
  try {
    return await api.me.getProfile()
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 404) throw err
  }
  await api.me.linkCustomer()
  return api.me.getProfile()
}

function AccountProblemScreen({ problem, onRetry, onSignOut }: {
  problem: AccountProblem
  onRetry: () => void
  onSignOut: () => void
}) {
  const unreachable = problem === 'unreachable'
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: '100dvh', padding: '0 32px', background: t.bg, textAlign: 'center',
    }}>
      <div style={{
        width: 52, height: 52, borderRadius: '50%', marginBottom: 18,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: t.surface2, border: `1px solid ${t.border}`, color: t.text3,
      }}>
        <Icon name={unreachable ? 'alert' : 'unlink'} size={22} />
      </div>
      <div style={{
        color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold,
        fontSize: font.size.display, marginBottom: 10, letterSpacing: '-0.015em',
      }}>
        {unreachable ? "Can't reach Terpee right now" : "Couldn't open your account"}
      </div>
      <div style={{ color: t.text3, fontSize: font.size.body, lineHeight: 1.6, maxWidth: 300 }}>
        {unreachable
          ? "Check your connection and try again. You're still signed in."
          : "Your sign-in isn't connected to a customer account yet. Customers sign in with their phone number."}
      </div>
      <button
        onClick={onRetry}
        style={{
          marginTop: 22, minWidth: 160, background: t.accent, border: 'none', borderRadius: radius.md,
          color: t.accentInk, fontSize: font.size.body, fontWeight: font.weight.bold, padding: '12px 18px', cursor: 'pointer',
        }}
      >
        Try again
      </button>
      {/* Signing back in costs a text and can't fix an outage, so it is only
          offered when the account itself is the problem. */}
      {!unreachable && (
        <button
          onClick={onSignOut}
          style={{
            marginTop: 10, minWidth: 160, background: 'none', border: `1px solid ${t.borderStrong}`, borderRadius: radius.md,
            color: t.text1, fontSize: font.size.body, fontWeight: font.weight.semibold, padding: '11px 18px', cursor: 'pointer',
          }}
        >
          Sign out
        </button>
      )}
    </div>
  )
}

/* The cart is kept per shopper on this device, so a refresh, the browser
   discarding a background tab, or closing it doesn't empty it. Prices and stock
   are checked again when the order is placed; a cart older than a day is
   dropped rather than shown with prices that may have moved. */
const CART_TTL_MS = 24 * 60 * 60 * 1000
const cartKey = (userId: string) => `terpee:cart:${userId}`

function readCart(userId: string): CartItem[] {
  try {
    const saved = JSON.parse(localStorage.getItem(cartKey(userId)) ?? 'null')
    if (!saved || !Array.isArray(saved.items) || Date.now() - saved.savedAt > CART_TTL_MS) return []
    return saved.items
  } catch {
    return []
  }
}

function writeCart(userId: string, items: CartItem[]) {
  try {
    if (items.length) localStorage.setItem(cartKey(userId), JSON.stringify({ savedAt: Date.now(), items }))
    else localStorage.removeItem(cartKey(userId))
  } catch {
    // Storage full or blocked (private mode): the cart still works for this visit.
  }
}

export default function CustomerPortal() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()

  // A product page and a listing page can open under any section, and keep the
  // shopper there. Both used to live only under one section, so opening a
  // product from Shop moved you to Brands and opening a listing moved you to
  // Map -- the same tap landing in a different part of the app.
  const matchProduct = useMatch('/portal/:section/products/:productKey')
  const matchListing = useMatch('/portal/:section/listings/:dispensaryId/:listingId')
  const matchBrand = useMatch('/portal/brands/:brandName')
  const matchCategory = useMatch('/portal/categories/:category')
  const matchAisle = useMatch('/portal/map/:dispensaryId/aisle/:category')
  const matchDispensary = useMatch('/portal/map/:dispensaryId')
  // Products were addressed under their brand before they could exist without
  // one, and a listing was addressed under the store before sections could hold
  // one; both are kept so older links still resolve.
  const matchLegacyBrandProduct = useMatch('/portal/brands/:brandName/products/:productKey')
  const matchLegacyMapListing = useMatch('/portal/map/:dispensaryId/listings/:listingId')

  const productKey = matchProduct?.params.productKey
    ? decodeURIComponent(matchProduct.params.productKey) : null
  const productBrand = searchParams.get('brand')
  const selectedBrandName = matchBrand?.params.brandName
    ? decodeURIComponent(matchBrand.params.brandName) : null
  const selectedCategory = matchCategory?.params.category
    ? decodeURIComponent(matchCategory.params.category) : null
  const selectedListingId = matchListing?.params.listingId ?? null
  const selectedListingDispensaryId = matchListing?.params.dispensaryId ?? null
  const selectedDispensaryId = (matchDispensary ?? matchAisle)?.params.dispensaryId ?? null

  const section = location.pathname.split('/')[2] ?? ''
  const activeTab: Tab = SECTION_OF[section] ?? 'home'

  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const userId = session?.user.id ?? null
  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [profileProblem, setProfileProblem] = useState<AccountProblem | null>(null)
  const [profileAttempt, setProfileAttempt] = useState(0)
  const customerId = profile?.id ?? null

  const [cart, setCart] = useState<CartItem[]>([])
  const [cartOwner, setCartOwner] = useState<string | null>(null)
  const [cartOpen, setCartOpen] = useState(false)
  // An item from a second store, waiting on "start a new cart?".
  const [pendingSwitch, setPendingSwitch] = useState<{ item: CartItem; from: string } | null>(null)
  // A short line over the cart bar ("up to 12 of one item"), gone on its own.
  const [notice, setNotice] = useState<string | null>(null)
  useEffect(() => {
    if (!notice) return
    const id = setTimeout(() => setNotice(null), 3500)
    return () => clearTimeout(id)
  }, [notice])

  const [orders, setOrders] = useState<Order[]>([])
  const [ordersLoading, setOrdersLoading] = useState(true)
  const [ordersError, setOrdersError] = useState<string | null>(null)
  const [ordersAttempt, setOrdersAttempt] = useState(0)
  const [cancellingIds, setCancellingIds] = useState<Set<string>>(new Set())
  // Per order: a failed cancel is that order's problem, and must not hide the
  // others' pickup codes.
  const [cancelErrors, setCancelErrors] = useState<Record<string, string>>({})

  // Pick up this shopper's saved cart as soon as we know who they are. Done
  // while rendering rather than in an effect so the first save below already
  // sees it, and never writes an empty cart over the saved one.
  if (userId && cartOwner !== userId) {
    setCartOwner(userId)
    setCart(readCart(userId))
  }
  useEffect(() => {
    if (cartOwner) writeCart(cartOwner, cart)
  }, [cartOwner, cart])

  // Track Supabase session
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  // The account and orders are keyed on the user, not the session object:
  // onAuthStateChange hands over a new object for the same session (at start
  // and on every token refresh), which used to load both two or three times.
  useEffect(() => {
    if (!userId) return
    let cancelled = false
    setProfileProblem(null)
    loadProfile()
      .then(p => { if (!cancelled) setProfile(p) })
      .catch(err => {
        if (cancelled) return
        // A 4xx is about this account; anything else (5xx, offline) is an outage.
        const aboutAccount = err instanceof ApiError && err.status >= 400 && err.status < 500
        setProfileProblem(aboutAccount ? 'not_linked' : 'unreachable')
      })
    return () => { cancelled = true }
  }, [userId, profileAttempt])

  // Orders come from /me/orders, which identifies the customer by token, so this
  // waits on the sign-in rather than on customerId.
  useEffect(() => {
    if (!userId) return
    let cancelled = false
    setOrdersLoading(true)
    setOrdersError(null)
    api.orders.list()
      .then(list => { if (!cancelled) { setOrders(list); setOrdersError(null) } })
      .catch(() => { if (!cancelled) setOrdersError('Could not load your orders.') })
      .finally(() => { if (!cancelled) setOrdersLoading(false) })
    return () => { cancelled = true }
  }, [userId, ordersAttempt])

  async function handleCancelOrder(orderId: string) {
    setCancellingIds(prev => new Set(prev).add(orderId))
    setCancelErrors(prev => {
      const next = { ...prev }
      delete next[orderId]
      return next
    })
    try {
      const updated = await api.orders.cancel(orderId)
      setOrders(prev => prev.map(o => (o.id === orderId ? updated : o)))
    } catch (err) {
      // The API's 4xx details are written for people ("already picked up");
      // anything else gets a plain line.
      const message = err instanceof ApiError && err.status >= 400 && err.status < 500 && err.message
        ? err.message
        : "Couldn't cancel this order. Check your connection and try again."
      setCancelErrors(prev => ({ ...prev, [orderId]: message }))
    } finally {
      setCancellingIds(prev => {
        const next = new Set(prev)
        next.delete(orderId)
        return next
      })
    }
  }

  async function handleSignOut() {
    // This device only: the default scope is global, which would sign the
    // account out everywhere, and each sign-in by text costs a message.
    await supabase.auth.signOut({ scope: 'local' })
  }

  /**
   * Returns whether the item went in. An order is placed with one store, and
   * POST /me/orders rejects a mixed cart, so adding from a second store asks
   * to start over rather than failing later at checkout. Quantity is capped at
   * the backend's per-line limit (MAX_QTY_PER_LINE in routes/orders.py) for
   * the same reason.
   */
  function handleAddToCart(item: CartItem): boolean {
    const other = cart.find(i => i.dispensaryId !== item.dispensaryId)
    if (other) {
      // Asked in a sheet with labelled answers; the item goes in only if the
      // shopper says to start over.
      setPendingSwitch({ item, from: other.dispensaryName })
      return false
    }

    const existing = cart.find(i => i.listingId === item.listingId)
    if (existing && existing.quantity >= MAX_QTY_PER_LINE) {
      setNotice(`You can reserve up to ${MAX_QTY_PER_LINE} of one item per order.`)
      return false
    }

    setCart(prev => {
      const index = prev.findIndex(i => i.listingId === item.listingId)
      if (index !== -1) {
        const next = [...prev]
        next[index] = { ...next[index], quantity: next[index].quantity + 1 }
        return next
      }
      return [...prev, item]
    })
    return true
  }

  function handleRemoveFromCart(listingId: string) {
    setCart(prev => prev.filter(i => i.listingId !== listingId))
  }

  /** The cart's stepper. Zero removes the line; the cap is the backend's. */
  function handleSetQuantity(listingId: string, quantity: number) {
    setCart(prev => quantity <= 0
      ? prev.filter(i => i.listingId !== listingId)
      : prev.map(i => (i.listingId === listingId ? { ...i, quantity: Math.min(quantity, MAX_QTY_PER_LINE) } : i)))
  }

  // Drill-downs stay in the section the shopper is browsing.
  const openProduct = (brand: string | null, key: string) =>
    navigate(
      `/portal/${activeTab}/products/${encodeURIComponent(key)}`
      + (brand ? `?brand=${encodeURIComponent(brand)}` : ''),
    )
  const openListing = (dispensaryId: string, listingId: string) =>
    navigate(`/portal/${activeTab}/listings/${dispensaryId}/${listingId}`)

  // Auth / loading gates
  if (session === undefined) {
    return <div style={{ height: '100dvh', background: t.bg }}><FeedState kind="loading" message="Loading…" style={{ height: '100%' }} /></div>
  }
  // The portal has no login screen of its own — the one at "/" is the only
  // sign-in surface, so it stays the single place SMS, email and social
  // sign-in are wired up. Carry where they were headed so signing in returns
  // them there rather than dropping them on the portal home.
  if (!session) {
    return <Navigate to="/" replace state={{ from: location.pathname + location.search }} />
  }
  if (profileProblem) {
    return (
      <AccountProblemScreen
        problem={profileProblem}
        onRetry={() => setProfileAttempt(n => n + 1)}
        onSignOut={handleSignOut}
      />
    )
  }
  if (!profile || !customerId) {
    return <div style={{ height: '100dvh', background: t.bg }}><FeedState kind="loading" message="Loading…" style={{ height: '100%' }} /></div>
  }
  // Sign-up is server state: the API refuses orders until it is done, and a
  // terms change can send a signed-up customer back through it.
  if (!profile.onboarding.complete) {
    return <OnboardingScreen profile={profile} onDone={setProfile} onSignOut={handleSignOut} />
  }

  // "Account" was this section's name before Profile absorbed feedback and the
  // account details; old links and bookmarks still point at it.
  if (section === 'account') {
    return <Navigate to="/portal/profile" replace />
  }
  if (matchLegacyBrandProduct?.params.brandName && matchLegacyBrandProduct.params.productKey) {
    const { brandName, productKey: legacyKey } = matchLegacyBrandProduct.params
    return <Navigate replace to={`/portal/brands/products/${legacyKey}?brand=${encodeURIComponent(decodeURIComponent(brandName))}`} />
  }
  if (matchLegacyMapListing?.params.dispensaryId && matchLegacyMapListing.params.listingId) {
    const { dispensaryId: legacyStore, listingId: legacyListing } = matchLegacyMapListing.params
    return <Navigate replace to={`/portal/map/listings/${legacyStore}/${legacyListing}`} />
  }

  const cartCount = cart.reduce((sum, i) => sum + i.quantity, 0)
  const cartBarShown = cartCount > 0 && !cartOpen
  // Where screens end, so the fixed bars at the bottom never cover what's on
  // them: every section sizes itself to this, and the map's sheets sit on it.
  // Without the cart bar it's the old 64px, just over the nav's top edge; with
  // it, everything moves above the cart bar rather than under it. Both include
  // the home-indicator inset on a home-screen install.
  const shellStyle = {
    position: 'fixed', inset: 0, background: t.bg, overflow: 'hidden',
    '--chrome-bottom': `calc(${cartBarShown ? 138 : 64}px + env(safe-area-inset-bottom, 0px))`,
  } as CSSProperties

  return (
    <div style={shellStyle}>
      {/* A product or a listing opens over whichever section the shopper is in;
          otherwise the section decides. */}
      <main>
      {selectedListingId && selectedListingDispensaryId ? (
        <ListingDetailView
          dispensaryId={selectedListingDispensaryId}
          listingId={selectedListingId}
          onAddToCart={handleAddToCart}
          cartQuantity={cart.filter(i => i.listingId === selectedListingId).reduce((s, i) => s + i.quantity, 0)}
          onOpenListing={openListing}
          onOpenDispensary={id => navigate(`/portal/map/${id}`)}
          onOpenProduct={openProduct}
        />
      ) : productKey ? (
        <ProductView
          brandName={productBrand}
          productKey={productKey}
          onBack={() => navigate(-1)}
          onListingClick={openListing}
        />
      ) : activeTab === 'home' ? (
        <HomeFeed
          onOpenListing={openListing}
          onOpenDispensary={dispensaryId => navigate(`/portal/map/${dispensaryId}`)}
          onOpenProduct={openProduct}
        />
      ) : activeTab === 'brands' ? (
        selectedBrandName ? (
          <BrandView
            brandName={selectedBrandName}
            onBack={() => navigate(-1)}
            onOpenProduct={key => openProduct(selectedBrandName, key)}
          />
        ) : (
          <BrandsPage onOpenBrand={name => navigate('/portal/brands/' + encodeURIComponent(name))} />
        )
      ) : activeTab === 'categories' ? (
        selectedCategory ? (
          <CategoryView
            categoryName={selectedCategory}
            onBack={() => navigate(-1)}
            onOpenProduct={openProduct}
          />
        ) : (
          <CategoriesPage
            onOpenCategory={name => navigate('/portal/categories/' + encodeURIComponent(name))}
          />
        )
      ) : activeTab === 'search' ? (
        <SearchView
          initialCategory={searchParams.get('category')}
          onOpenProduct={openProduct}
        />
      ) : activeTab === 'map' ? (
        <DispensaryMap
          activeDispensaryId={selectedDispensaryId}
          onAddToCart={handleAddToCart}
          cart={cart}
        />
      ) : (
        <ProfileView
          session={session}
          customerId={customerId}
          orders={orders}
          ordersLoading={ordersLoading}
          ordersError={ordersError}
          onCancelOrder={handleCancelOrder}
          onRetryOrders={() => setOrdersAttempt(n => n + 1)}
          cancellingIds={cancellingIds}
          cancelErrors={cancelErrors}
          onSignOut={handleSignOut}
        />
      )}
      </main>

      <CartDrawer
        items={cart}
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        onRemove={handleRemoveFromCart}
        onSetQuantity={handleSetQuantity}
        maxQuantity={MAX_QTY_PER_LINE}
        onClear={() => setCart([])}
        onPlaced={(order) => {
          // The cart is now an order; keep the list fresh without a refetch.
          setCart([])
          setOrders(prev => [order, ...prev])
        }}
        onViewOrders={() => { setCartOpen(false); navigate('/portal/profile/orders') }}
      />

      {/* Cart bar — above the nav, and only once there is something in it. Six
          sections leave no room for a permanent cart button, and an empty cart
          is not worth a permanent slot anyway. */}
      {cartBarShown && (
        <button
          onClick={() => setCartOpen(true)}
          style={{
            position: 'fixed', bottom: 'calc(84px + env(safe-area-inset-bottom, 0px))', left: 12, right: 12, height: 46,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: t.accent, border: 'none', borderRadius: radius.lg,
            color: t.accentInk, fontWeight: font.weight.bold, fontSize: font.size.callout,
            padding: '0 14px 0 16px', cursor: 'pointer', zIndex: 2100,
            boxShadow: 'var(--e-3)',
          }}
        >
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9 }}>
            <Icon name="bag" size={18} strokeWidth={2} />
            <span className="num">{cartCount} {cartCount === 1 ? 'item' : 'items'} in cart</span>
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
            View <Icon name="chevron-right" size={17} strokeWidth={2} />
          </span>
        </button>
      )}

      {notice && (
        <div role="status" style={{
          position: 'fixed', left: 16, right: 16, zIndex: 2150,
          bottom: `calc(${cartBarShown ? 142 : 88}px + env(safe-area-inset-bottom, 0px))`,
          background: t.surface3, border: `1px solid ${t.borderStrong}`, borderRadius: radius.md,
          color: t.text1, fontSize: font.size.body, padding: '10px 14px', boxShadow: 'var(--e-3)',
          animation: 'ds-fade-in 0.2s ease',
        }}>
          {notice}
        </div>
      )}

      <ConfirmSheet
        open={pendingSwitch !== null}
        title="Start a new cart?"
        confirmLabel="Start new cart"
        cancelLabel="Keep my cart"
        onConfirm={() => {
          if (pendingSwitch) setCart([{ ...pendingSwitch.item, quantity: 1 }])
          setPendingSwitch(null)
          setNotice('Cart started at the new store.')
        }}
        onCancel={() => setPendingSwitch(null)}
      >
        Your cart has items from {pendingSwitch?.from}. An order is picked up at one store, so adding
        this from {pendingSwitch?.item.dispensaryName} empties your cart first.
      </ConfirmSheet>

      {/* Floating bottom nav */}
      <nav style={{
        position: 'fixed', bottom: 'calc(16px + env(safe-area-inset-bottom, 0px))', left: 12, right: 12, height: 60,
        background: 'rgba(19, 23, 20, 0.88)',
        backdropFilter: 'blur(20px) saturate(140%)', WebkitBackdropFilter: 'blur(20px) saturate(140%)',
        borderRadius: radius.xl, border: `1px solid ${t.border}`,
        boxShadow: 'var(--e-3)',
        display: 'flex', alignItems: 'center', zIndex: 2100, padding: '0 4px',
      }}>
        {TABS.map(tab => {
          const active = activeTab === tab.key
          return (
            <button
              key={tab.key}
              onClick={() => navigate('/portal/' + tab.key)}
              aria-current={active ? 'page' : undefined}
              style={{
                flex: 1, height: '100%', padding: '0 2px',
                background: 'none', border: 'none', cursor: 'pointer',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4,
                color: active ? t.accent : t.text3,
                borderRadius: radius.lg, transition: `color ${motion.fast}`,
              }}
            >
              <span style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 40, height: 26, borderRadius: radius.pill,
                background: active ? t.accentTint : 'transparent',
                transition: `background ${motion.fast}`,
              }}>
                <Icon name={tab.icon} size={19} strokeWidth={active ? 2 : 1.75} />
              </span>
              <span style={{ fontSize: 10, fontWeight: active ? font.weight.semibold : font.weight.medium, letterSpacing: '0.01em' }}>
                {tab.label}
              </span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}
