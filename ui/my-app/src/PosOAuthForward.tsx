import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { API_BASE } from './api/client'
import { t } from './theme'

/**
 * The POS OAuth redirect URL can be registered on this site's own domain
 * (https://terpenomics.generic.tech/pos/oauth/square/callback) rather than the
 * API's. Square sends the browser here; this hands the query string -- code and
 * state, or the error -- straight to the API's callback, which finishes the
 * connection and redirects back to /admin/partners.
 *
 * A full-page navigation, not a fetch: the API answers with a redirect, and the
 * browser has to follow it.
 */
export default function PosOAuthForward() {
  const { provider = '' } = useParams()

  useEffect(() => {
    window.location.replace(
      `${API_BASE}/pos/oauth/${encodeURIComponent(provider)}/callback${window.location.search}`,
    )
  }, [provider])

  return (
    <div style={{ minHeight: '100vh', background: t.bg, color: t.text2, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>
      Finishing the connection…
    </div>
  )
}
