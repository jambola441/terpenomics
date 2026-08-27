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
import type { CartItem, Order } from './types'
import type { Session } from '@supabase/supabase-js'
import { t, radius, font } from './theme'
import { FeedState } from './components/ui'
import 'leaflet/dist/leaflet.css'

type Tab = 'home' | 'brands' | 'categories' | 'search' | 'map' | 'profile'

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'home', label: 'Home', icon: 'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z' },
  { key: 'brands', label: 'Brands', icon: 'M21.41 11.58l-9-9A2 2 0 0011 2H4a2 2 0 00-2 2v7a2 2 0 00.59 1.42l9 9a2 2 0 002.82 0l7-7a2 2 0 000-2.84zM6.5 8A1.5 1.5 0 118 6.5 1.5 1.5 0 016.5 8z' },
  { key: 'categories', label: 'Shop', icon: 'M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z' },
  { key: 'search', label: 'Search', icon: 'M15.5 14h-.79l-.28-.27A6.47 6.47 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z' },
  { key: 'map', label: 'Map', icon: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5A2.5 2.5 0 1114.5 9 2.5 2.5 0 0112 11.5z' },
  { key: 'profile', label: 'You', icon: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z' },
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

function NotLinkedScreen() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: '100dvh', padding: '0 32px', background: t.bg, textAlign: 'center',
    }}>
      <div style={{ fontSize: 40, marginBottom: 18 }}>🔗</div>
      <div style={{
        color: t.text1, fontWeight: font.weight.heavy, fontSize: font.size.heading,
        marginBottom: 12, letterSpacing: '-0.01em',
      }}>
        Account not linked
      </div>
      <div style={{ color: t.text3, fontSize: font.size.body, lineHeight: 1.6, maxWidth: 300 }}>
        Your email isn't connected to a customer account yet. Ask a staff member to link your account.
      </div>
    </div>
  )
}

export default function CustomerPortal() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()

  const matchBrandProduct = useMatch('/portal/brands/:brandName/products/:productKey')
  const matchBrand = useMatch('/portal/brands/:brandName')
  const matchCategory = useMatch('/portal/categories/:category')
  const matchListing = useMatch('/portal/map/:dispensaryId/listings/:listingId')
  const matchAisle = useMatch('/portal/map/:dispensaryId/aisle/:category')
  const matchDispensary = useMatch('/portal/map/:dispensaryId')

  const brandProductBrand = matchBrandProduct?.params.brandName
    ? decodeURIComponent(matchBrandProduct.params.brandName) : null
  const brandProductKey = matchBrandProduct?.params.productKey
    ? decodeURIComponent(matchBrandProduct.params.productKey) : null
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
  const [customerId, setCustomerId] = useState<string | null>(null)
  const [profileError, setProfileError] = useState<string | null>(null)

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
      .then(profile => setCustomerId(profile.id))
      .catch(() =>
        api.me.linkCustomer()
          .then(() => api.me.getProfile())
          .then(profile => setCustomerId(profile.id))
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
    await supabase.auth.signOut()
  }

  function handleAddToCart(item: CartItem) {
    setCart(prev => {
      const existing = prev.findIndex(i => i.listingId === item.listingId)
      if (existing !== -1) {
        const next = [...prev]
        next[existing] = { ...next[existing], quantity: next[existing].quantity + 1 }
        return next
      }
      return [...prev, item]
    })
  }

  function handleRemoveFromCart(listingId: string) {
    setCart(prev => prev.filter(i => i.listingId !== listingId))
  }

  const openBrandProduct = (brand: string, key: string) =>
    navigate(`/portal/brands/${encodeURIComponent(brand)}/products/${encodeURIComponent(key)}`)
  const openListing = (dispensaryId: string, listingId: string) =>
    navigate(`/portal/map/${dispensaryId}/listings/${listingId}`)

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
  if (profileError) return <NotLinkedScreen />
  if (!customerId) {
    return <div style={{ height: '100dvh', background: t.bg }}><FeedState kind="loading" message="Loading…" style={{ height: '100%' }} /></div>
  }

  // "Account" was this section's name before Profile absorbed feedback and the
  // account details; old links and bookmarks still point at it.
  if (section === 'account') {
    return <Navigate to="/portal/profile" replace />
  }

  const cartCount = cart.reduce((sum, i) => sum + i.quantity, 0)

  return (
    <div style={{ position: 'fixed', inset: 0, background: t.bg, overflow: 'hidden' }}>
      {/* ── Home ── */}
      {activeTab === 'home' && (
        <HomeFeed
          onOpenListing={openListing}
          onOpenDispensary={dispensaryId => navigate(`/portal/map/${dispensaryId}`)}
          onOpenBrandProduct={openBrandProduct}
        />
      )}

      {/* ── Brands: index → brand → product ── */}
      {activeTab === 'brands' && (
        brandProductBrand && brandProductKey ? (
          <ProductView
            brandName={brandProductBrand}
            productKey={brandProductKey}
            onBack={() => navigate(-1)}
            onListingClick={openListing}
          />
        ) : selectedBrandName ? (
          <BrandView
            brandName={selectedBrandName}
            onBack={() => navigate(-1)}
            onOpenProduct={key => openBrandProduct(selectedBrandName, key)}
          />
        ) : (
          <BrandsPage onOpenBrand={name => navigate('/portal/brands/' + encodeURIComponent(name))} />
        )
      )}

      {/* ── Categories: index → category ── */}
      {activeTab === 'categories' && (
        selectedCategory ? (
          <CategoryView
            categoryName={selectedCategory}
            onBack={() => navigate(-1)}
            onOpenBrandProduct={openBrandProduct}
            onOpenListing={openListing}
          />
        ) : (
          <CategoriesPage
            onOpenCategory={name => navigate('/portal/categories/' + encodeURIComponent(name))}
          />
        )
      )}

      {/* ── Search ── */}
      {activeTab === 'search' && (
        <SearchView
          initialCategory={searchParams.get('category')}
          onOpenBrandProduct={openBrandProduct}
          onOpenCategory={name => navigate('/portal/categories/' + encodeURIComponent(name))}
        />
      )}

      {/* ── Map: stores, aisles and listing detail ── */}
      {activeTab === 'map' && (
        selectedListingId && selectedListingDispensaryId ? (
          <ListingDetailView
            dispensaryId={selectedListingDispensaryId}
            listingId={selectedListingId}
            onAddToCart={handleAddToCart}
            cartQuantity={cart.filter(i => i.listingId === selectedListingId).reduce((s, i) => s + i.quantity, 0)}
          />
        ) : (
          <DispensaryMap
            activeDispensaryId={selectedDispensaryId}
            onAddToCart={handleAddToCart}
            cart={cart}
          />
        )
      )}

      {/* ── Profile ── */}
      {activeTab === 'profile' && (
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
        onViewOrders={() => { setCartOpen(false); navigate('/portal/profile') }}
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
            padding: '0 16px', cursor: 'pointer', zIndex: 2100,
            boxShadow: '0 6px 24px rgba(0,0,0,0.45)',
          }}
        >
          <span>{cartCount} {cartCount === 1 ? 'item' : 'items'} in cart</span>
          <span>View ›</span>
        </button>
      )}

      {/* Floating bottom nav */}
      <nav style={{
        position: 'fixed', bottom: 16, left: 12, right: 12, height: 58,
        background: 'rgba(14, 14, 14, 0.92)',
        backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)',
        borderRadius: 20, border: '1px solid rgba(255,255,255,0.07)',
        boxShadow: '0 4px 32px rgba(0,0,0,0.6)',
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
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3,
                color: active ? t.accent : '#555',
                borderRadius: 16, transition: 'color 0.15s',
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d={tab.icon} />
              </svg>
              <span style={{ fontSize: 9.5, fontWeight: active ? 700 : 400, letterSpacing: '0.02em' }}>
                {tab.label}
              </span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}
