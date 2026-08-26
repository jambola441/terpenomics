import { Link } from 'react-router-dom'

const sections = [
  { label: 'Products',       path: '/admin/products',       desc: 'Browse and edit the product catalog' },
  { label: 'Customers',      path: '/admin/customers',      desc: 'View customer profiles and history' },
  { label: 'Pickup Orders',  path: '/admin/orders',         desc: 'Incoming orders to prepare for pickup' },
  { label: 'Purchases',      path: '/admin/purchases',      desc: 'All purchase transactions' },
  { label: 'Lab Reports',    path: '/admin/lab-reports',    desc: 'Upload and review COAs' },
  { label: 'Dispensaries',   path: '/admin/dispensaries',   desc: 'Manage dispensary locations and POS settings' },
  { label: 'Listings',       path: '/admin/listings',       desc: 'Browse all scraped listings' },
  { label: 'Match Listings', path: '/admin/listings/match', desc: 'Link scraped listings to products' },
]

export default function AdminHome() {
  return (
    <div style={{
      minHeight: '100vh',
      background: '#080d18',
      fontFamily: "'Inter', system-ui, sans-serif",
      padding: '64px 40px',
    }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.3em',
          textTransform: 'uppercase',
          color: '#334155',
          marginBottom: 56,
        }}>
          terpenomics admin
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <Link
            to="/portal"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '22px 24px',
              background: '#0a1a0a',
              border: '1px solid #1a3320',
              borderRadius: 10,
              textDecoration: 'none',
              color: 'inherit',
              marginBottom: 8,
              transition: 'border-color 0.15s, background 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = '#0d1f0d'
              e.currentTarget.style.borderColor = '#2d5c3a'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = '#0a1a0a'
              e.currentTarget.style.borderColor = '#1a3320'
            }}
          >
            <div>
              <div style={{ fontSize: 15, fontWeight: 500, color: '#a8e063', marginBottom: 5 }}>
                Customer Portal
              </div>
              <div style={{ fontSize: 13, color: '#4a7c4e' }}>View the customer-facing storefront</div>
            </div>
            <span style={{ color: '#4a7c4e', fontSize: 18 }}>→</span>
          </Link>

          {sections.map(s => (
            <Link
              key={s.path}
              to={s.path}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '22px 24px',
                background: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: 10,
                textDecoration: 'none',
                color: 'inherit',
                transition: 'border-color 0.15s, background 0.15s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = '#111827'
                e.currentTarget.style.borderColor = '#334155'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = '#0f172a'
                e.currentTarget.style.borderColor = '#1e293b'
              }}
            >
              <div>
                <div style={{ fontSize: 15, fontWeight: 500, color: '#f1f5f9', marginBottom: 5 }}>
                  {s.label}
                </div>
                <div style={{ fontSize: 13, color: '#475569' }}>{s.desc}</div>
              </div>
              <span style={{ color: '#334155', fontSize: 18 }}>→</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
