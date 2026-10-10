import { useEffect, useState, type CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'
import api from './api/client'
import type { BrandLogoRow, LogoCandidate } from './types'
import { navBtnStyle } from './components/AdminTable'
import { BrandMark } from './components/ui'
import { Icon } from './components/Icon'
import { inputStyle, primaryBtn } from './utils/partners'
import { t, font, radius } from './theme'

/**
 * Brand logos — each big brand's own logo, read off its site.
 *
 * Brand tiles used to show whichever product photo sorted first. Here a person
 * reads a brand's home page for the images it names as its logo, sees each on the
 * light tile it will sit on (and on dark, to catch a white logo), and picks one;
 * or uploads a file when the site's logo can't be read. The API stores it at a web
 * size in Terpee's own storage (routes/admin/brand_logos.py).
 */
export default function BrandLogos() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<BrandLogoRow[]>([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setLoading(true)
    const id = setTimeout(() => {
      api.brandLogos.list({ limit: 80, q: q.trim() || undefined })
        .then(r => { if (live) { setRows(r); setError(null) } })
        .catch(e => { if (live) setError(e.message) })
        .finally(() => { if (live) setLoading(false) })
    }, q ? 300 : 0)
    return () => { live = false; clearTimeout(id) }
  }, [q])

  const replace = (row: BrandLogoRow) =>
    setRows(prev => prev.map(r => (r.brand_key === row.brand_key ? { ...r, ...row } : r)))

  const done = rows.filter(r => r.logo_url).length

  return (
    <div style={{ padding: 24, background: t.bg, minHeight: '100vh', color: t.text1 }}>
      <div style={{ maxWidth: 1000, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}><Icon name="arrow-left" size={14} />Admin</button>
          <h1 style={{ margin: 0, fontFamily: font.family.display, fontSize: font.size.display, fontWeight: 600, letterSpacing: '-0.015em' }}>Brand Logos</h1>
        </div>

        <div style={{ fontSize: 12, color: t.text3, marginBottom: 18, lineHeight: 1.7 }}>
          The brands with the most listings, biggest first. Find a brand's logo on its own site and
          pick the one that reads well on the light tile; upload a file when the site's can't be read.
          A brand without one shows a product photo or its initial. {!loading && `${done} of ${rows.length} have a logo.`}
        </div>

        <input
          placeholder="Find a brand"
          value={q}
          onChange={e => setQ(e.target.value)}
          style={{ ...inputStyle, width: '100%', boxSizing: 'border-box', marginBottom: 16 }}
        />

        {error && <div style={{ color: t.danger, marginBottom: 16 }}>Error: {error}</div>}
        {loading && rows.length === 0 ? (
          <div style={{ color: t.text3, padding: 16 }}>Loading…</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {rows.map(row => <BrandRow key={row.brand_key} row={row} onSaved={replace} />)}
          </div>
        )}
      </div>
    </div>
  )
}

function BrandRow({ row, onSaved }: { row: BrandLogoRow; onSaved: (row: BrandLogoRow) => void }) {
  const [site, setSite] = useState(row.site_url ?? '')
  const [found, setFound] = useState<LogoCandidate[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label)
    setError(null)
    try {
      await work()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  const find = () => run('find', async () => {
    let url = site.trim()
    if (url && !/^https?:\/\//i.test(url)) url = `https://${url}`
    setSite(url)
    const res = await api.brandLogos.candidates(row.brand_key, url)
    setFound(res.candidates)
  })

  const choose = (c: LogoCandidate) => run(c.url, async () => {
    onSaved(await api.brandLogos.choose(row.brand_key, { brand_name: row.brand_name, image_url: c.url, site_url: site || null }))
    setFound(null)
  })

  const upload = (file: File) => run('upload', async () => {
    onSaved(await api.brandLogos.upload(row.brand_key, row.brand_name, file))
    setFound(null)
  })

  const remove = () => run('remove', async () => {
    await api.brandLogos.remove(row.brand_key)
    onSaved({ ...row, logo_url: null })
  })

  return (
    <div style={{ background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <BrandMark name={row.brand_name} imageUrl={row.logo_url} size={52} />
        <div style={{ flex: '1 1 160px', minWidth: 0 }}>
          <div style={{ fontWeight: 600 }}>{row.brand_name}</div>
          <div style={{ fontSize: 12, color: t.text3 }}>
            {row.listing_count.toLocaleString()} listings{row.logo_url && row.chosen_by ? ` · picked by ${row.chosen_by}` : ''}
          </div>
        </div>
        <input
          placeholder="brand site, e.g. https://brand.com"
          value={site}
          onChange={e => setSite(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && site.trim()) find() }}
          aria-label={`${row.brand_name} site`}
          style={{ ...inputStyle, flex: '2 1 220px' }}
        />
        <button onClick={find} disabled={!site.trim() || !!busy} style={primaryBtn(!site.trim() || !!busy)}>
          {busy === 'find' ? 'Reading…' : 'Find logos'}
        </button>
        <label style={{ ...secondaryBtn, opacity: busy ? 0.6 : 1 }}>
          {busy === 'upload' ? 'Uploading…' : 'Upload'}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/svg+xml"
            disabled={!!busy}
            onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = '' }}
            style={{ display: 'none' }}
          />
        </label>
        {row.logo_url && (
          <button onClick={remove} disabled={!!busy} style={{ ...secondaryBtn, color: t.danger }}>Remove</button>
        )}
      </div>

      {error && <div style={{ color: t.danger, fontSize: 13, marginTop: 10 }}>{error}</div>}

      {found && (
        found.length === 0 ? (
          <div style={{ color: t.text3, fontSize: 13, marginTop: 12 }}>
            The page names no logo. Upload one instead.
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
            {found.map(c => (
              <Candidate key={c.url} c={c} busy={busy === c.url} disabled={!!busy} onChoose={() => choose(c)} />
            ))}
          </div>
        )
      )}
    </div>
  )
}

/** One candidate, on the light tile it would sit on and on dark, so a white logo
 *  that vanishes on the tile is caught before it's picked. Hidden if it won't load. */
function Candidate({ c, busy, disabled, onChoose }: {
  c: LogoCandidate; busy: boolean; disabled: boolean; onChoose: () => void
}) {
  const [broken, setBroken] = useState(false)
  const [size, setSize] = useState<string | null>(null)
  if (broken) return null
  const plate: CSSProperties = { width: 88, height: 88, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 8, boxSizing: 'border-box' }
  return (
    <div style={{ width: 188, border: `1px solid ${t.border}`, borderRadius: radius.md, overflow: 'hidden', background: t.surface2 }}>
      <div style={{ display: 'flex' }}>
        {[t.tile, '#141815'].map(bg => (
          <div key={bg} style={{ ...plate, background: bg }}>
            <img
              src={c.url}
              alt=""
              referrerPolicy="no-referrer"
              onError={() => setBroken(true)}
              onLoad={e => setSize(`${e.currentTarget.naturalWidth}×${e.currentTarget.naturalHeight}`)}
              style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
            />
          </div>
        ))}
      </div>
      <div style={{ padding: '6px 8px', display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{ flex: 1, minWidth: 0, fontSize: 11, color: t.text3, lineHeight: 1.4 }}>
          {c.kind}{size ? ` · ${size}` : ''}
        </div>
        <button onClick={onChoose} disabled={disabled} style={{ ...secondaryBtn, padding: '4px 10px' }}>
          {busy ? 'Saving…' : 'Use'}
        </button>
      </div>
    </div>
  )
}

const secondaryBtn: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 12px', borderRadius: 8,
  fontSize: 13, fontWeight: 600, background: 'transparent', border: `1px solid ${t.borderStrong}`,
  color: t.text1, cursor: 'pointer',
}
