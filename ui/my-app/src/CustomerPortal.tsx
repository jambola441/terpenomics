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

import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams, useMatch, Navigate, useLocation } from 'react-router-dom'
import api from './api/client'
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
import OnboardingScreen from './components/OnboardingScreen'
import type { CartItem, CustomerProfile, Order } from './types'
import type { Session } from '@supabase/supabase-js'
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

function NotLinkedScreen({ message, onSignOut }: { message: string; onSignOut: () => void }) {
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
        <Icon name="unlink" size={22} />
      </div>
      <div style={{
        color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold,
        fontSize: font.size.display, marginBottom: 10, letterSpacing: '-0.015em',
      }}>
        Couldn't open your account
      </div>
      <div style={{ color: t.text3, fontSize: font.size.body, lineHeight: 1.6, maxWidth: 300 }}>
        {message === 'not_linked'
          ? "Your sign-in isn't connected to a customer account yet."
          : message}
        {' '}Customers sign in with their phone number.
      </div>
      <button
        onClick={onSignOut}
        style={{
          marginTop: 22, background: 'none', border: `1px solid ${t.borderStrong}`, borderRadius: radius.md,
          color: t.text1, fontSize: font.size.body, fontWeight: font.weight.semibold, padding: '10px 18px', cursor: 'pointer',
        }}
      >
        Sign out
      </button>
    </div>
  )
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
  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [profileError, setProfileError] = useState<string | null>(null)
  const customerId = profile?.id ?? null

  const [cart, setCart] = useState<CartItem[]>([])
  const [cartOpen, setCartOpen] = useState(false)

  const [orders, setOrders] = useState<Order[]>([])
  const [ordersLoading, setOrdersLoading] = useState(true)
  const [ordersError, setOrdersError] = useState<string | null>(null)
  const [cancellingIds, setCancellingIds] = useState<Set<string>>(new Set())

  // Track Supabase session
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  // Resolve customer ID once session is available, auto-linking on first login
  useEffect(() => {
    if (!session) return
    api.me.getProfile()
      .then(setProfile)
      .catch(() =>
        api.me.linkCustomer()
          .then(() => api.me.getProfile())
          .then(setProfile)
          .catch(err => setProfileError(err.message ?? 'not_linked'))
      )
  }, [session])

  // Orders come from /me/orders, which identifies the customer by token, so this
  // waits on the session rather than on customerId.
  useEffect(() => {
    if (!session) return
    setOrdersLoading(true)
    api.orders.list()
      .then(setOrders)
      .catch(() => setOrdersError('Could not load your orders.'))
      .finally(() => setOrdersLoading(false))
  }, [session])

  async function handleCancelOrder(orderId: string) {
    setCancellingIds(prev => new Set(prev).add(orderId))
    try {
      const updated = await api.orders.cancel(orderId)
      setOrders(prev => prev.map(o => (o.id === orderId ? updated : o)))
    } catch {
      setOrdersError('Could not cancel that order.')
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
      const fresh = confirm(
        `Your cart has items from ${other.dispensaryName}. An order can only be picked up from one store.\n\n`
        + `Empty your cart and add this from ${item.dispensaryName} instead?`,
      )
      if (!fresh) return false
      setCart([{ ...item, quantity: 1 }])
      return true
    }

    const existing = cart.find(i => i.listingId === item.listingId)
    if (existing && existing.quantity >= MAX_QTY_PER_LINE) {
      alert(`You can reserve up to ${MAX_QTY_PER_LINE} of one item per order.`)
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
  if (profileError) return <NotLinkedScreen message={profileError} onSignOut={handleSignOut} />
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

  return (
    <div style={{ position: 'fixed', inset: 0, background: t.bg, overflow: 'hidden' }}>
      {/* A product or a listing opens over whichever section the shopper is in;
          otherwise the section decides. */}
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
          cancellingIds={cancellingIds}
          onSignOut={handleSignOut}
        />
      )}

      <CartDrawer
        items={cart}
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        onRemove={handleRemoveFromCart}
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
      {cartCount > 0 && !cartOpen && (
        <button
          onClick={() => setCartOpen(true)}
          style={{
            position: 'fixed', bottom: 84, left: 12, right: 12, height: 46,
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

      {/* Floating bottom nav */}
      <nav style={{
        position: 'fixed', bottom: 16, left: 12, right: 12, height: 60,
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
