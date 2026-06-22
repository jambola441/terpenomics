import Login from './Login'
import AdminHome from './AdminHome'
import AddProduct from './AddProduct'
import Products from './Products'
import ProductDetail from './ProductDetail'
import Customers from './Customers'
import CustomerEdit from './CustomerEdit'
import Purchases from './Purchases'
import Dispensaries from './Dispensaries'
import DispensaryEdit from './DispensaryEdit'
import DispensaryListingsAdmin from './DispensaryListingsAdmin'
import CustomerRegister from './CustomerRegister'
import CustomerPortal from './CustomerPortal'
import LabReportUpload from './LabReportUpload'
import LabReportDetail from './LabReportDetail'
import ListingMatch from './ListingMatch'
import Listings from './Listings'
import AdminListingDetail from './AdminListingDetail'

import { BrowserRouter, Routes, Route } from 'react-router-dom'

function App() {
  return (
    <>
      <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/admin" element={<AdminHome />} />
        <Route path="/admin/add-product" element={<AddProduct />} />
        <Route path="/admin/products" element={<Products />} />
        <Route path="/admin/products/detail" element={<ProductDetail />} />
        <Route path="/admin/customers" element={<Customers />} />
        <Route path="/admin/customers/new" element={<CustomerRegister />} />
        <Route path="/admin/customers/:customerId" element={<CustomerEdit />} />
        <Route path="/admin/purchases" element={<Purchases />} />
        <Route path="/admin/lab-reports" element={<LabReportUpload />} />
        <Route path="/admin/lab-reports/:reportId" element={<LabReportDetail />} />
        <Route path="/admin/dispensaries" element={<Dispensaries />} />
        <Route path="/admin/dispensaries/:dispensaryId" element={<DispensaryEdit />} />
        <Route path="/admin/dispensaries/:dispensaryId/listings" element={<DispensaryListingsAdmin />} />
        <Route path="/admin/listings" element={<Listings />} />
        <Route path="/admin/listings/match" element={<ListingMatch />} />
        <Route path="/admin/listings/:listingId" element={<AdminListingDetail />} />
        <Route path="/portal/*" element={<CustomerPortal />} />
      </Routes>
      </BrowserRouter>
  </>
  )
}

export default App
