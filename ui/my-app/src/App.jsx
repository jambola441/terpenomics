import { useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'
import Login from './Login'
import AddProduct from './AddProduct'
import Products from './Products'
import ProductEdit from './ProductEdit'
import Customers from './Customers'
import CustomerEdit from './CustomerEdit'
import Purchases from './Purchases'
import CustomerPortal from './CustomerPortal'

import { BrowserRouter, Routes, Route } from 'react-router-dom'

function App() {
  const [count, setCount] = useState(0)

  return (
    <>
      <header>banger</header>
      <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/add-product" element={<AddProduct />} />
        <Route path="/products" element={<Products />} />
        <Route path="/products/:productId" element={<ProductEdit />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/customers/:customerId" element={<CustomerEdit />} />
        <Route path="/purchases" element={<Purchases />} />
        <Route path="/portal/:customerId" element={<CustomerPortal />} />
      </Routes>
      </BrowserRouter>
  </>
  )
}

export default App
