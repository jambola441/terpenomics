import { Link, useNavigate } from 'react-router-dom'
import supabase from './utils/supabase'
import { t, font, radius, motion } from './theme'
import { Icon, Logo } from './components/Icon'

const sections = [
  { label: 'Products',       path: '/admin/products',       icon: 'package',  desc: 'Browse and edit the product catalog' },
  { label: 'Customers',      path: '/admin/customers',      icon: 'users',    desc: 'View customer profiles and history' },
  { label: 'Pickup Orders',  path: '/admin/orders',         icon: 'bag',      desc: 'Incoming orders to prepare for pickup' },
  { label: 'Purchases',      path: '/admin/purchases',      icon: 'receipt',  desc: 'All purchase transactions' },
  { label: 'Lab Reports',    path: '/admin/lab-reports',    icon: 'flask',    desc: 'Upload and review COAs' },
  { label: 'Dispensaries',   path: '/admin/dispensaries',   icon: 'store',    desc: 'Manage dispensary locations and POS settings' },
  { label: 'Listings',       path: '/admin/listings',       icon: 'list',     desc: 'Browse all scraped listings' },
  { label: 'Receipts',       path: '/admin/receipts',       icon: 'scan',     desc: 'Customer receipt uploads to review: read the subtotal, award points' },
  { label: 'Partner Stores', path: '/admin/partners',       icon: 'building', desc: 'Non-dispensary partners whose purchases earn Terpee points; connect their Square' },
  { label: 'Brand Catalogs', path: '/admin/brand-catalogs', icon: 'tag',      desc: "Products a brand says it makes — the referent enrichment is checked against" },
]

const rowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 16,
  padding: '18px 20px',
  background: t.surface1,
  border: `1px solid ${t.border}`,
  borderRadius: radius.lg,
  textDecoration: 'none',
  color: 'inherit',
  fontWeight: 400,
  transition: `border-color ${motion.fast}, background ${motion.fast}`,
}

const labelStyle = { fontSize: font.size.callout, fontWeight: 600, color: t.text1, marginBottom: 3 }
const descStyle = { fontSize: 13, color: t.text3, lineHeight: 1.45 }

function hover(e, on, accent = false) {
  const el = e.currentTarget
  if (accent) {
    el.style.borderColor = on ? t.accentDim : t.border
  } else {
    el.style.background = on ? t.surface2 : t.surface1
    el.style.borderColor = on ? t.borderStrong : t.border
  }
}

export default function AdminHome() {
  const navigate = useNavigate()

  async function signOut() {
    // This device only: the default scope is global, which would sign the
    // account out everywhere, and each sign-in by text costs a message.
    await supabase.auth.signOut({ scope: 'local' })
    navigate('/staff', { replace: true })
  }

  return (
    <div style={{ minHeight: '100vh', background: t.bg, padding: '56px 24px' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ marginBottom: 40, position: 'relative' }}>
          <button
            type="button"
            onClick={signOut}
            style={{
              position: 'absolute', top: 0, right: 0,
              display: 'inline-flex', alignItems: 'center', gap: 6,
              background: 'transparent', border: `1px solid ${t.borderStrong}`, borderRadius: radius.md,
              color: t.text2, fontSize: 13, padding: '6px 12px', cursor: 'pointer',
            }}
          >
            <Icon name="log-out" size={15} />
            Sign out
          </button>
          <Logo size={26} />
          <div style={{
            marginTop: 10,
            fontFamily: font.family.mono,
            fontSize: font.size.caption,
            fontWeight: 500,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: t.text3,
          }}>
            Admin
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <Link
            to="/portal"
            style={{ ...rowStyle, background: t.accentTint, marginBottom: 8 }}
            onMouseEnter={e => hover(e, true, true)}
            onMouseLeave={e => hover(e, false, true)}
          >
            <Icon name="mark" size={22} color={t.accent} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ ...labelStyle, color: t.accent }}>Customer Portal</div>
              <div style={descStyle}>View the customer-facing storefront</div>
            </div>
            <Icon name="chevron-right" size={18} color={t.accent} />
          </Link>

          {sections.map(s => (
            <Link
              key={s.path}
              to={s.path}
              style={rowStyle}
              onMouseEnter={e => hover(e, true)}
              onMouseLeave={e => hover(e, false)}
            >
              <Icon name={s.icon} size={20} color={t.text3} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={labelStyle}>{s.label}</div>
                <div style={descStyle}>{s.desc}</div>
              </div>
              <Icon name="chevron-right" size={18} color={t.text3} />
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
