import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'

import Login, { StaffLogin } from './Login'
import StaffGate from './StaffGate'
import AuthCallback from './AuthCallback'
import CustomerPortal from './CustomerPortal'
import { t } from './theme'

// Shoppers never open the staff, partner or legal pages, so those load on
// demand instead of riding in the bundle every customer downloads first.
const AdminHome = lazy(() => import('./AdminHome'))
const Products = lazy(() => import('./Products'))
const ProductDetail = lazy(() => import('./ProductDetail'))
const Customers = lazy(() => import('./Customers'))
const CustomerEdit = lazy(() => import('./CustomerEdit'))
const Purchases = lazy(() => import('./Purchases'))
const Orders = lazy(() => import('./Orders'))
const BrandCatalogs = lazy(() => import('./BrandCatalogs'))
const BrandCatalogEdit = lazy(() => import('./BrandCatalogEdit'))
const Dispensaries = lazy(() => import('./Dispensaries'))
const DispensaryEdit = lazy(() => import('./DispensaryEdit'))
const DispensaryListingsAdmin = lazy(() => import('./DispensaryListingsAdmin'))
const CustomerRegister = lazy(() => import('./CustomerRegister'))
const LabReportUpload = lazy(() => import('./LabReportUpload'))
const LabReportDetail = lazy(() => import('./LabReportDetail'))
const Listings = lazy(() => import('./Listings'))
const AdminListingDetail = lazy(() => import('./AdminListingDetail'))
const Partners = lazy(() => import('./Partners'))
const PartnerDetail = lazy(() => import('./PartnerDetail'))
const PosOAuthForward = lazy(() => import('./PosOAuthForward'))
const PartnerPortal = lazy(() => import('./PartnerPortal'))
const Receipts = lazy(() => import('./Receipts'))
const TermsPage = lazy(() => import('./Legal').then(m => ({ default: m.TermsPage })))
const PrivacyPage = lazy(() => import('./Legal').then(m => ({ default: m.PrivacyPage })))

function App() {
  return (
    <>
      <BrowserRouter>
      {/* The ground colour while a lazy page arrives, so it never flashes white. */}
      <Suspense fallback={<div style={{ minHeight: '100vh', background: t.bg }} />}>
      <Routes>
        {/* Customers sign in by text at "/"; staff have their own page. */}
        <Route path="/" element={<Login />} />
        <Route path="/staff" element={<StaffLogin />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route element={<StaffGate />}>
          <Route path="/admin" element={<AdminHome />} />
          <Route path="/admin/products" element={<Products />} />
          <Route path="/admin/products/detail" element={<ProductDetail />} />
          <Route path="/admin/customers" element={<Customers />} />
          <Route path="/admin/customers/new" element={<CustomerRegister />} />
          <Route path="/admin/customers/:customerId" element={<CustomerEdit />} />
          <Route path="/admin/purchases" element={<Purchases />} />
          <Route path="/admin/orders" element={<Orders />} />
          <Route path="/admin/lab-reports" element={<LabReportUpload />} />
          <Route path="/admin/lab-reports/:reportId" element={<LabReportDetail />} />
          <Route path="/admin/brand-catalogs" element={<BrandCatalogs />} />
          <Route path="/admin/brand-catalogs/:catalogId" element={<BrandCatalogEdit />} />
          <Route path="/admin/dispensaries" element={<Dispensaries />} />
          <Route path="/admin/dispensaries/:dispensaryId" element={<DispensaryEdit />} />
          <Route path="/admin/dispensaries/:dispensaryId/listings" element={<DispensaryListingsAdmin />} />
          <Route path="/admin/listings" element={<Listings />} />
          <Route path="/admin/listings/:listingId" element={<AdminListingDetail />} />
          <Route path="/admin/partners" element={<Partners />} />
          <Route path="/admin/partners/:partnerId" element={<PartnerDetail />} />
          <Route path="/admin/receipts" element={<Receipts />} />
        </Route>
        <Route path="/pos/oauth/:provider/callback" element={<PosOAuthForward />} />
        <Route path="/partner" element={<PartnerPortal />} />
        <Route path="/partner/:partnerId" element={<PartnerPortal />} />
        <Route path="/portal/*" element={<CustomerPortal />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
      </Routes>
      </Suspense>
      </BrowserRouter>
  </>
  )
}

export default App
