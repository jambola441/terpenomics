import supabase from '../utils/supabase'
import type {
  Customer,
  Product,
  Purchase,
  PurchaseRow,
  TerpeneScoresResponse,
  ListParams,
  PurchaseListParams,
  CustomerPurchasesParams,
  TerpeneScoresParams,
  PurchaseCreateParams,
  PurchaseItemCreateParams,
  PurchaseItem,
  PortalPurchase,
  Order,
  OrderStatus,
  PortalProduct,
  PortalBrand,
  PortalBrandDetail,
  PortalProductDetail,
  PortalCategory,
  PortalCategoryDetail,
  FeedbackResponse,
  Feedback,
  LabReport,
  LabReportDetail,
  LabReportUpload,
  LabReportResult,
  Listing,
  Dispensary,
  DispensaryListing,
  ListingDetail,
  BrandCatalogRow,
  BrandCatalogDetail,
  BrandCatalogEntry,
  BrandCatalogEntryPage,
  CatalogEntryListings,
  CatalogExportStatus,
  PortalDispensary,
  Feed,
  FeedView,
  CustomerProfile,
  OnboardingPayload,
  ProfileUpdate,
  Partner,
  PartnerDetail,
  PartnerLocation,
  PosConnection,
  PosSyncRun,
  PosOrderPage,
  PartnerMember,
  PartnerMe,
  PartnerPortalDetail,
  PartnerPosOrder,
  PointsSummary,
  MyReceipt,
  PartnerOption,
  AdminReceiptQueue,
  AdminReceiptDetail,
  ReceiptStatus,
} from '../types'

// Get API base URL from environment variable or use default
export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev'

/** How long a read may take before it counts as failed. A hung request
 *  otherwise leaves a skeleton up forever with nothing to press; failing lets
 *  the screen offer Try again. Generous, because a sleeping API instance takes
 *  20-30 s to wake.
 *
 *  Reads only: giving up on a write in the browser doesn't stop it on the
 *  server, so a retry could place an order or save a change twice. */
const REQUEST_TIMEOUT_MS = 30_000

/** The caller's signal if it passed one; for a read, the timeout. */
function withTimeout(method: string | undefined, signal?: AbortSignal | null): AbortSignal | undefined {
  if (signal) return signal
  return !method || method.toUpperCase() === 'GET' ? AbortSignal.timeout(REQUEST_TIMEOUT_MS) : undefined
}

// Helper function to build query string from params
function buildQueryString(params?: Record<string, any>): string {
  if (!params) return ''
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, String(value))
    }
  })
  const qs = searchParams.toString()
  return qs ? `?${qs}` : ''
}

// Helper function to get auth headers
async function getAuthHeaders() {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error('Not authenticated')
  return { Authorization: `Bearer ${token}` }
}

/** FastAPI's `detail` as text: a string, or a structured detail's `message`
 *  (e.g. onboarding_required). Anything else falls back to the raw body. */
async function errorMessage(res: Response): Promise<string> {
  const text = await res.text()
  try {
    const detail = JSON.parse(text)?.detail
    if (typeof detail === 'string') return detail
    if (typeof detail?.message === 'string') return detail.message
  } catch {
    // Not JSON (proxy timeout, HTML error page).
  }
  return text || `Request failed with status ${res.status}`
}

// Unauthenticated fetch for customer portal (no Supabase session needed)
/* Recent answers to public catalogue reads, reused for a minute, so going to
   another tab and back doesn't fetch and redraw the same page again. Nothing
   about the shopper is kept: their purchases are excluded, and /me goes
   through authenticatedFetch. A failed read is dropped at once, so Try again
   really tries again. The server caches the heavy ones too
   (services/response_cache.py); this saves the trip. */
const CATALOGUE_TTL_MS = 60_000
const CATALOGUE_MAX = 100
const catalogue = new Map<string, { at: number; answer: Promise<unknown> }>()

async function portalFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const cacheable = (!options.method || options.method === 'GET') && !path.includes('/purchases')
  if (!cacheable) return portalRequest<T>(path, options)

  const hit = catalogue.get(path)
  if (hit && Date.now() - hit.at < CATALOGUE_TTL_MS) return hit.answer as Promise<T>
  const answer = portalRequest<T>(path, options)
  catalogue.delete(path)
  catalogue.set(path, { at: Date.now(), answer })
  answer.catch(() => { if (catalogue.get(path)?.answer === answer) catalogue.delete(path) })
  // Oldest first in insertion order; drop it once the map is full.
  if (catalogue.size > CATALOGUE_MAX) catalogue.delete(catalogue.keys().next().value!)
  return answer
}

async function portalRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    signal: withTimeout(options.method, options.signal),
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!res.ok) {
    throw new ApiError(await errorMessage(res), res.status)
  }

  // DELETE /me and other no-content responses have no body to parse.
  if (res.status === 204) return null as T
  return res.json()
}

// Generic fetch wrapper
async function authenticatedFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    signal: withTimeout(options.method, options.signal),
    headers: {
      'Content-Type': 'application/json',
      ...headers,
      ...options.headers,
    },
  })

  if (!res.ok) {
    throw new ApiError(await errorMessage(res), res.status)
  }

  // DELETE /me and other no-content responses have no body to parse.
  if (res.status === 204) return null as T
  return res.json()
}

// Multipart upload with the session token. Content-Type is left to the
// browser so it can add the multipart boundary. FastAPI's `detail` string is
// surfaced as the error message, since these errors go straight on screen.
async function authenticatedUpload<T>(path: string, form: FormData): Promise<T> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: form })
  if (!res.ok) {
    let message = `Upload failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') message = body.detail
    } catch { /* keep the generic message */ }
    throw new Error(message)
  }
  return res.json()
}

/** A failed API call. `status` lets a caller tell "no such thing" (404) from an
 *  outage, which call for different answers; every fetch helper throws one. */
export class ApiError extends Error {
  status: number
  retryAfter?: number

  constructor(message: string, status: number, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

// SMS login endpoints. Unauthenticated by definition, and their errors go
// straight on screen, so surface FastAPI's `detail` string rather than the raw
// JSON body that portalFetch would throw.
async function authFetch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const text = await res.text()
  let payload: any = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    // Non-JSON error body (proxy timeout, HTML error page) — fall back to text.
  }

  if (!res.ok) {
    // detail is usually a string; structured ones (e.g. onboarding_required)
    // carry their human-readable text in `message`.
    const detail = typeof payload?.detail === 'string' ? payload.detail
      : typeof payload?.detail?.message === 'string' ? payload.detail.message : null
    const retryAfter = Number(res.headers.get('Retry-After'))
    throw new ApiError(
      detail || text || `Request failed with status ${res.status}`,
      res.status,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined,
    )
  }

  return payload as T
}

// Centralized API client
/** Entry search/filter/paging. `category: '__null__'` selects uncategorised. */
export type CatalogEntryParams = {
  q?: string
  category?: string
  is_active?: boolean
  limit?: number
  offset?: number
}

export type AdminOrderRow = {
  id: string
  status: OrderStatus
  pickup_code: string
  total_amount_cents: number
  note: string | null
  submitted_at: string
  dispensary_id: string
  dispensary_name: string | null
  customer_id: string
  customer_name: string | null
  customer_phone: string | null
  item_count: number
}

export type AdminOrderDetail = Omit<Order, 'dispensary_slug' | 'dispensary_address'> & {
  customer_id: string
  customer_name: string | null
  customer_phone: string | null
  customer_email: string | null
  /** Statuses this order may legally move to next; empty once terminal. */
  allowed_transitions: OrderStatus[]
}

/** A feed request started early by api.me.startFeed, until Home claims it. */
let feedHeadStart: { url: string; at: number; promise: Promise<Feed> } | null = null
/** Older than this, Home asks again rather than show what it fetched. */
const FEED_HEAD_START_MS = 15_000

export const api = {
  customers: {
    list: (params?: ListParams) =>
      authenticatedFetch<Customer[]>(`/admin/customers${buildQueryString(params)}`),
    
    get: (id: string) =>
      authenticatedFetch<Customer>(`/admin/customers/${id}`),
    
    create: (data: Partial<Customer>) =>
      authenticatedFetch<Customer>(`/admin/customers`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    
    update: (id: string, data: Partial<Customer>) =>
      authenticatedFetch<Customer>(`/admin/customers/${id}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    
    getPurchases: (id: string, params?: CustomerPurchasesParams) =>
      authenticatedFetch<Purchase[]>(`/admin/customers/${id}/purchases${buildQueryString(params)}`),
    
    getTerpeneScores: (id: string, params?: TerpeneScoresParams) =>
      authenticatedFetch<TerpeneScoresResponse>(`/admin/customers/${id}/terpene-scores${buildQueryString(params)}`),
  },

  products: {
    list: (params?: ListParams & { brand?: string; category?: string; in_stock?: boolean; sort?: string; order?: string }) =>
      authenticatedFetch<Product[]>(`/admin/products${buildQueryString(params)}`),

    getDetail: (params: { brand?: string; category?: string; subtype?: string; product_line?: string; strain?: string; variant?: string }) =>
      authenticatedFetch<{ product: Product; listings: any[] }>(`/admin/products/detail${buildQueryString(params)}`),

    listAllBrands: () =>
      authenticatedFetch<string[]>(`/admin/products/brands`),
  },

  purchases: {
    list: (params?: PurchaseListParams) =>
      authenticatedFetch<PurchaseRow[]>(`/admin/purchases${buildQueryString(params)}`),
    
    create: (data: PurchaseCreateParams) =>
      authenticatedFetch<Purchase>(`/admin/purchases`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    
    finalize: (id: string) =>
      authenticatedFetch<Purchase>(`/admin/purchases/${id}/finalize`, {
        method: 'POST',
      }),
  },

  purchaseItems: {
    create: (purchaseId: string, data: PurchaseItemCreateParams) =>
      authenticatedFetch<PurchaseItem>(`/admin/purchases/${purchaseId}/items`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    
    createBatch: (purchaseId: string, items: PurchaseItemCreateParams[]) =>
      authenticatedFetch<PurchaseItem[]>(`/admin/purchases/${purchaseId}/items/batch`, {
        method: 'POST',
        body: JSON.stringify(items),
      }),
    
    updateFeedback: (itemId: string, feedback: string | null) =>
      authenticatedFetch<any>(`/admin/purchase-items/${itemId}/feedback`, {
        method: 'POST',
        body: JSON.stringify({ feedback }),
      }),
  },

  labReports: {
    list: (params?: { limit?: number; offset?: number }) =>
      authenticatedFetch<LabReport[]>(`/admin/lab-reports${buildQueryString(params)}`),

    get: (id: string) =>
      authenticatedFetch<LabReportDetail>(`/admin/lab-reports/${id}`),

    assign: (id: string, listingId: string | null) =>
      authenticatedFetch<LabReport>(`/admin/lab-reports/${id}`, {
        method: 'POST',
        body: JSON.stringify({ listing_id: listingId }),
      }),

    upload: async (files: File[]): Promise<LabReportUpload[]> => {
      const { data } = await supabase.auth.getSession()
      const token = data.session?.access_token
      if (!token) throw new Error('Not authenticated')

      const form = new FormData()
      for (const file of files) {
        form.append('files', file)
      }

      // Do NOT set Content-Type — the browser sets it with the multipart boundary
      const res = await fetch(`${API_BASE}/admin/lab-reports/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `Upload failed with status ${res.status}`)
      }

      return res.json()
    },

    process: async (labReportIds: string[], listingId?: string): Promise<LabReportResult[]> => {
      const { data } = await supabase.auth.getSession()
      const token = data.session?.access_token
      if (!token) throw new Error('Not authenticated')

      const res = await fetch(`${API_BASE}/admin/lab-reports/process`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          lab_report_ids: labReportIds,
          listing_id: listingId ?? null,
        }),
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `Processing failed with status ${res.status}`)
      }

      return res.json()
    },
  },

  dispensaries: {
    list: (params?: { q?: string; limit?: number; offset?: number }) =>
      authenticatedFetch<Dispensary[]>(`/admin/dispensaries${buildQueryString(params)}`),

    get: (id: string) =>
      authenticatedFetch<Dispensary>(`/admin/dispensaries/${id}`),

    create: (data: Partial<Dispensary>) =>
      authenticatedFetch<Dispensary>(`/admin/dispensaries`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    update: (id: string, data: Partial<Dispensary>) =>
      authenticatedFetch<Dispensary>(`/admin/dispensaries/${id}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },

  /**
   * Brand catalogs. Note the split system of record: Postgres holds the catalog,
   * but enrichment reads the generated `data/catalogs/<slug>.json` export, so
   * every response carries an `export` block and nothing is really live until
   * `regenerateExport` has run.
   */
  brandCatalogs: {
    list: (params?: { q?: string; limit?: number; offset?: number }) =>
      authenticatedFetch<BrandCatalogRow[]>(`/admin/brand-catalogs${buildQueryString(params)}`),

    get: (id: string, params?: CatalogEntryParams) =>
      authenticatedFetch<BrandCatalogDetail>(`/admin/brand-catalogs/${id}${buildQueryString(params)}`),

    create: (data: { brand_name: string; brand_slug?: string; source_url?: string | null; source_method?: string }) =>
      authenticatedFetch<BrandCatalogRow>(`/admin/brand-catalogs`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    update: (id: string, data: { brand_name?: string; brand_slug?: string; source_url?: string | null; source_method?: string }) =>
      authenticatedFetch<BrandCatalogRow>(`/admin/brand-catalogs/${id}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    listEntries: (id: string, params?: CatalogEntryParams) =>
      authenticatedFetch<BrandCatalogEntryPage>(`/admin/brand-catalogs/${id}/entries${buildQueryString(params)}`),

    /** The listings at every store that resolve to this entry, active ones first. */
    entryListings: (id: string, entryId: string) =>
      authenticatedFetch<CatalogEntryListings>(`/admin/brand-catalogs/${id}/entries/${entryId}/listings`),

    createEntry: (id: string, data: Partial<BrandCatalogEntry>) =>
      authenticatedFetch<BrandCatalogEntry>(`/admin/brand-catalogs/${id}/entries`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    /**
     * Field edits only. An omitted key is left alone and an explicit null clears
     * the column, so send exactly what changed. The endpoint rejects any attempt
     * to write first_seen_at, last_seen_at or the verified_* columns.
     */
    updateEntry: (id: string, entryId: string, data: Record<string, unknown>) =>
      authenticatedFetch<BrandCatalogEntry>(`/admin/brand-catalogs/${id}/entries/${entryId}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    /**
     * "Remove" is a flag, never a delete: listings carry a foreign key to these
     * rows. Pass is_active true to put an entry back.
     */
    setEntryActive: (id: string, entryId: string, isActive: boolean) =>
      authenticatedFetch<BrandCatalogEntry>(`/admin/brand-catalogs/${id}/entries/${entryId}/deactivate`, {
        method: 'POST',
        body: JSON.stringify({ is_active: isActive }),
      }),

    verifyEntry: (id: string, entryId: string, data: { fields: Record<string, unknown>; verified_by: string; clear?: string[] }) =>
      authenticatedFetch<BrandCatalogEntry>(`/admin/brand-catalogs/${id}/entries/${entryId}/verify`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    exportStatus: (id: string) =>
      authenticatedFetch<CatalogExportStatus>(`/admin/brand-catalogs/${id}/export`),

    /** Rewrite data/catalogs/<slug>.json from the database. */
    regenerateExport: (id: string) =>
      authenticatedFetch<{ written: string; entry_count: number; product_count: number; export: CatalogExportStatus }>(
        `/admin/brand-catalogs/${id}/export`,
        { method: 'POST' },
      ),
  },

  /**
   * Partner stores (non-dispensaries whose purchases earn Terpee points) and
   * their POS connections. Syncing is not here: scripts/pos_sync.py runs on a
   * schedule. Connecting is OAuth — `startOAuth` returns the POS consent URL to
   * send the browser to, and the POS redirects back to /admin/partners.
   */
  partners: {
    list: (params?: { limit?: number; offset?: number }) =>
      authenticatedFetch<Partner[]>(`/admin/partners${buildQueryString(params)}`),

    get: (id: string) =>
      authenticatedFetch<PartnerDetail>(`/admin/partners/${id}`),

    create: (data: { name: string; slug: string; logo_url?: string | null }) =>
      authenticatedFetch<Partner>(`/admin/partners`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    update: (id: string, data: { name?: string; slug?: string; logo_url?: string | null; is_active?: boolean }) =>
      authenticatedFetch<Partner>(`/admin/partners/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),

    updateLocation: (locationId: string, data: { name?: string; is_active?: boolean }) =>
      authenticatedFetch<PartnerLocation>(`/admin/partner-locations/${locationId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),

    startOAuth: (provider: string, partnerId: string) =>
      authenticatedFetch<{ authorize_url: string }>(
        `/admin/pos-connections/oauth/${provider}/start${buildQueryString({ partner_id: partnerId })}`,
      ),

    /** Pause ('disabled'), resume, or re-enable a connection that hit errors. */
    setConnectionStatus: (connectionId: string, status: 'active' | 'disabled') =>
      authenticatedFetch<PosConnection>(`/admin/pos-connections/${connectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),

    /** Revoke at the POS and drop credentials. Orders already pulled are kept. */
    disconnect: (connectionId: string) =>
      authenticatedFetch<PosConnection>(`/admin/pos-connections/${connectionId}`, { method: 'DELETE' }),

    runs: (connectionId: string, limit = 10) =>
      authenticatedFetch<PosSyncRun[]>(`/admin/pos-connections/${connectionId}/runs${buildQueryString({ limit })}`),

    orders: (params: { partner_id?: string; unmatched?: boolean; limit?: number; offset?: number }) =>
      authenticatedFetch<PosOrderPage>(`/admin/pos-orders${buildQueryString(params)}`),

    /** Let someone sign in to this partner's /partner dashboard with Google as `email`. */
    inviteMember: (partnerId: string, email: string) =>
      authenticatedFetch<PartnerMember>(`/admin/partners/${partnerId}/members`, {
        method: 'POST',
        body: JSON.stringify({ email }),
      }),

    removeMember: (memberId: string) =>
      authenticatedFetch<{ ok: boolean }>(`/admin/partner-members/${memberId}`, { method: 'DELETE' }),

    /** A customer's Terpee points balance and ledger. */
    customerPoints: (customerId: string) =>
      authenticatedFetch<PointsSummary>(`/admin/customers/${customerId}/points`),
  },

  /** Admin review queue for customer receipt uploads. */
  receipts: {
    list: (status: ReceiptStatus | 'all' = 'pending') =>
      authenticatedFetch<AdminReceiptQueue>(`/admin/receipts${buildQueryString({ status })}`),

    get: (id: string) =>
      authenticatedFetch<AdminReceiptDetail>(`/admin/receipts/${id}`),

    /** The photo as an object URL (it needs the bearer token, so an <img src> can't fetch it). */
    imageUrl: async (id: string) => {
      const headers = await getAuthHeaders()
      const res = await fetch(`${API_BASE}/admin/receipts/${id}/image`, { headers })
      if (!res.ok) throw new Error(`Image failed to load (${res.status})`)
      return URL.createObjectURL(await res.blob())
    },

    /** Approve by the matching synced POS order, or by subtotal and date. */
    approve: (id: string, data: { pos_order_id: string } | { subtotal_cents: number; purchased_on: string; partner_id?: string }) =>
      authenticatedFetch<AdminReceiptDetail>(`/admin/receipts/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    reject: (id: string, reason: string) =>
      authenticatedFetch<AdminReceiptDetail>(`/admin/receipts/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),

    void: (id: string, reason: string) =>
      authenticatedFetch<AdminReceiptDetail>(`/admin/receipts/${id}/void`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),
  },

  /**
   * The partner's own portal (/partner). Same signed-in Supabase session as
   * everything else; the API only answers for partners this person was invited to.
   */
  partnerPortal: {
    me: () => authenticatedFetch<PartnerMe>(`/partner/me`),

    get: (partnerId: string) =>
      authenticatedFetch<PartnerPortalDetail>(`/partner/partners/${partnerId}`),

    startOAuth: (partnerId: string, provider = 'square') =>
      authenticatedFetch<{ authorize_url: string }>(`/partner/partners/${partnerId}/oauth/${provider}/start`),

    setConnectionStatus: (partnerId: string, connectionId: string, status: 'active' | 'disabled') =>
      authenticatedFetch<PosConnection>(`/partner/partners/${partnerId}/connections/${connectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),

    disconnect: (partnerId: string, connectionId: string) =>
      authenticatedFetch<PosConnection>(`/partner/partners/${partnerId}/connections/${connectionId}`, { method: 'DELETE' }),

    runs: (partnerId: string, connectionId: string) =>
      authenticatedFetch<PosSyncRun[]>(`/partner/partners/${partnerId}/connections/${connectionId}/runs`),

    orders: (partnerId: string, params: { members_only?: boolean; limit?: number; offset?: number }) =>
      authenticatedFetch<{ total: number; items: PartnerPosOrder[] }>(
        `/partner/partners/${partnerId}/orders${buildQueryString(params)}`,
      ),
  },

  adminOrders: {
    list: (params?: { status?: OrderStatus; dispensary_id?: string; limit?: number; offset?: number }) =>
      authenticatedFetch<AdminOrderRow[]>(`/admin/orders${buildQueryString(params)}`),

    get: (id: string) =>
      authenticatedFetch<AdminOrderDetail>(`/admin/orders/${id}`),

    setStatus: (id: string, status: Exclude<OrderStatus, 'submitted'>) =>
      authenticatedFetch<AdminOrderDetail>(`/admin/orders/${id}/status`, {
        method: 'POST',
        body: JSON.stringify({ status }),
      }),
  },

  listings: {
    list: (params?: { q?: string; dispensary_id?: string; category?: string; brand?: string; subtype?: string; classification?: string; in_stock?: boolean; sort?: string; order?: string; limit?: number; offset?: number }) =>
      authenticatedFetch<Listing[]>(`/admin/listings${buildQueryString(params)}`),

    get: (id: string) =>
      authenticatedFetch<Listing>(`/admin/listings/${id}`),

    update: (id: string, data: { product_line?: string; strain?: string }) =>
      authenticatedFetch<Listing>(`/admin/listings/${id}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    filterOptions: () =>
      authenticatedFetch<{ dispensaries: { id: string; name: string }[]; brands: string[]; classifications: string[]; subtypes: string[] }>(`/admin/listings/filter-options`),
  },

  auth: {
    smsStart: (phone: string) =>
      // code_length is missing from an API that predates it.
      authFetch<{ challenge_id: string; expires_in: number; resend_in: number; code_length?: number }>(
        `/auth/sms/start`,
        { phone },
      ),

    smsVerify: (challengeId: string, code: string) =>
      authFetch<{
        access_token: string
        refresh_token: string
        token_type: string
        expires_in?: number
        user_id: string
      }>(`/auth/sms/verify`, { challenge_id: challengeId, code }),
  },

  me: {
    /** Stores where purchases earn Terpee points. */
    getPartners: () =>
      authenticatedFetch<PartnerOption[]>(`/me/partners`),

    /** Upload a receipt photo for review. */
    uploadReceipt: (data: { partnerId: string; purchasedOn: string; note?: string; image: Blob; filename?: string }) => {
      const form = new FormData()
      form.append('partner_id', data.partnerId)
      form.append('purchased_on', data.purchasedOn)
      if (data.note) form.append('note', data.note)
      form.append('image', data.image, data.filename ?? 'receipt.jpg')
      return authenticatedUpload<MyReceipt>(`/me/receipts`, form)
    },

    getReceipts: () =>
      authenticatedFetch<MyReceipt[]>(`/me/receipts`),

    /** Terpee points earned at partner stores. */
    getPoints: () =>
      authenticatedFetch<PointsSummary>(`/me/points`),

    getProfile: () =>
      authenticatedFetch<CustomerProfile>(`/me`),

    /** Name and marketing opt-in only — phone and email are identity, not profile. */
    updateProfile: (payload: ProfileUpdate) =>
      authenticatedFetch<CustomerProfile>(`/me`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    /** Contact email: a code goes to the new address; it is saved on verify
     *  (routes/me_email.py). */
    startEmailChange: (email: string) =>
      authenticatedFetch<{ challenge_id: string; expires_in: number; resend_in: number }>(`/me/email/start`, {
        method: 'POST',
        body: JSON.stringify({ email }),
      }),

    verifyEmailChange: (challengeId: string, code: string) =>
      authenticatedFetch<CustomerProfile>(`/me/email/verify`, {
        method: 'POST',
        body: JSON.stringify({ challenge_id: challengeId, code }),
      }),

    removeEmail: () =>
      authenticatedFetch<CustomerProfile>(`/me/email`, { method: 'DELETE' }),

    /** Deletes the login and scrubs the account (services/account_deletion.py). */
    deleteAccount: () =>
      authenticatedFetch<null>(`/me`, { method: 'DELETE' }),

    /** Sign-up, and catching up after a terms change. */
    completeOnboarding: (payload: OnboardingPayload) =>
      authenticatedFetch<CustomerProfile>(`/me/onboarding`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    /** Which customer the login joins is decided by the token alone. */
    linkCustomer: (payload?: { name?: string }) =>
      authenticatedFetch<{ customer_id: string; linked: boolean; created?: boolean }>(`/me/link-customer`, {
        method: 'POST',
        body: JSON.stringify(payload ?? {}),
      }),

    /** The stores the home feed is built from. Every mutation returns the whole
     *  updated set, so the caller replaces its state rather than refetching. */
    listPreferredDispensaries: () =>
      authenticatedFetch<PortalDispensary[]>(`/me/preferred-dispensaries`),

    addPreferredDispensary: (dispensaryId: string) =>
      authenticatedFetch<PortalDispensary[]>(`/me/preferred-dispensaries/${dispensaryId}`, {
        method: 'POST',
      }),

    removePreferredDispensary: (dispensaryId: string) =>
      authenticatedFetch<PortalDispensary[]>(`/me/preferred-dispensaries/${dispensaryId}`, {
        method: 'DELETE',
      }),

    /** The home feed. `store` keeps the followed stores separate, `combined`
     *  pools and dedupes them; both are ranked server-side because two of the
     *  four rails compare against every store we track. */
    getFeed: (params?: { view?: FeedView; per_rail?: number; category?: string }) => {
      const url = `/me/feed${buildQueryString(params)}`
      const early = feedHeadStart
      feedHeadStart = null
      if (early && early.url === url && Date.now() - early.at < FEED_HEAD_START_MS) {
        // A failed head start (say, a first sign-in not linked yet) gets a
        // fresh request rather than an error.
        return early.promise.catch(() => authenticatedFetch<Feed>(url))
      }
      return authenticatedFetch<Feed>(url)
    },

    /** Ask for the feed now, beside /me, instead of after it: Home's first
     *  getFeed with the same parameters takes this request over, which saves
     *  it a round trip on every visit that opens on Home. */
    startFeed: (params?: { view?: FeedView; per_rail?: number; category?: string }) => {
      const url = `/me/feed${buildQueryString(params)}`
      const promise = authenticatedFetch<Feed>(url)
      promise.catch(() => { /* handed to getFeed, which retries */ })
      feedHeadStart = { url, at: Date.now(), promise }
    },

    /** Forget a head start, when the signed-in user changes: it was fetched
     *  as whoever started it. */
    dropFeedHeadStart: () => { feedHeadStart = null },
  },

  /**
   * Pickup orders. Authenticated, unlike `portal` below: the customer is
   * resolved from the Supabase token rather than a UUID in the path, because
   * placing an order commits a real person to collecting goods.
   */
  orders: {
    create: (payload: { dispensary_id: string; items: { listing_id: string; quantity: number }[]; note?: string }) =>
      authenticatedFetch<Order>(`/me/orders`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    list: (params?: { limit?: number; offset?: number }) =>
      authenticatedFetch<Order[]>(`/me/orders${buildQueryString(params)}`),

    get: (orderId: string) =>
      authenticatedFetch<Order>(`/me/orders/${orderId}`),

    cancel: (orderId: string) =>
      authenticatedFetch<Order>(`/me/orders/${orderId}/cancel`, { method: 'POST' }),
  },

  portal: {
    getPurchases: (customerId: string, params?: { limit?: number; offset?: number }) =>
      portalFetch<PortalPurchase[]>(`/customer/${customerId}/purchases${buildQueryString(params)}`),

    setFeedback: (customerId: string, itemId: string, feedback: Feedback | null) =>
      portalFetch<FeedbackResponse>(`/customer/${customerId}/purchase-items/${itemId}/feedback`, {
        method: 'POST',
        body: JSON.stringify({ feedback }),
      }),


    getProducts: (params?: { q?: string; category?: string; brand?: string; limit?: number; offset?: number }) =>
      portalFetch<PortalProduct[]>(`/customer/products${buildQueryString(params)}`),

    getProduct: (productId: string) =>
      portalFetch<PortalProduct>(`/customer/products/${productId}`),

    getDispensaries: () =>
      portalFetch<PortalDispensary[]>(`/customer/dispensaries`),

    getDispensaryFilterOptions: (dispensaryId: string) =>
      // `categories` is missing from an API that predates it.
      portalFetch<{ brands: string[]; variants: string[]; categories?: { name: string; count: number }[] }>(`/customer/dispensaries/${dispensaryId}/filter-options`),

    getDispensaryListings: (dispensaryId: string, params?: { category?: string; brand?: string; variant?: string; q?: string; inStock?: boolean; limit?: number; offset?: number }) =>
      portalFetch<DispensaryListing[]>(`/customer/dispensaries/${dispensaryId}/listings${buildQueryString(params)}`),

    getListing: (dispensaryId: string, listingId: string) =>
      portalFetch<ListingDetail>(`/customer/dispensaries/${dispensaryId}/listings/${listingId}`),

    getBrands: (params?: { q?: string; limit?: number; offset?: number; sort?: 'listings' | 'name' }) =>
      portalFetch<PortalBrand[]>(`/customer/brands${buildQueryString(params)}`),

    getBrand: (name: string) =>
      portalFetch<PortalBrandDetail>(`/customer/brands/${encodeURIComponent(name)}`),

    /** One product with its offerings. Brand is a filter, not a prerequisite:
     *  omitting it asks for the unbranded product with that key. */
    getProductDetail: (key: string, brand?: string | null) =>
      portalFetch<PortalProductDetail>(
        `/customer/products/detail${buildQueryString({ key, brand: brand ?? undefined })}`,
      ),

    getCategories: () =>
      portalFetch<PortalCategory[]>(`/customer/categories`),

    getCategory: (name: string) =>
      portalFetch<PortalCategoryDetail>(`/customer/categories/${encodeURIComponent(name)}`),
  },
}

export default api
