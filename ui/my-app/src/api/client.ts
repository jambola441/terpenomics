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
  CatalogExportStatus,
  PortalDispensary,
  Feed,
  FeedView,
  CustomerProfile,
} from '../types'

// Get API base URL from environment variable or use default
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev'

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

// Unauthenticated fetch for customer portal (no Supabase session needed)
async function portalFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed with status ${res.status}`)
  }

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
    headers: {
      'Content-Type': 'application/json',
      ...headers,
      ...options.headers,
    },
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed with status ${res.status}`)
  }

  return res.json()
}

// SMS login endpoints. Unauthenticated by definition, and their errors go
// straight on screen, so surface FastAPI's `detail` string rather than the raw
// JSON body that portalFetch would throw.
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
    const detail = typeof payload?.detail === 'string' ? payload.detail : null
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
    
    getRecommendedProducts: (id: string, params?: { limit?: number, window_days?: number }) =>
      authenticatedFetch<RecommendedProduct[]>(`/admin/customers/${id}/recommended-products${buildQueryString(params)}`),
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
      authFetch<{ challenge_id: string; expires_in: number; resend_in: number }>(
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
    getProfile: () =>
      authenticatedFetch<CustomerProfile>(`/me`),

    /** Name and marketing opt-in only — phone and email are identity, not profile. */
    updateProfile: (payload: { name?: string; marketing_opt_in?: boolean }) =>
      authenticatedFetch<CustomerProfile>(`/me`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    linkCustomer: (payload?: { phone?: string; email?: string; name?: string }) =>
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
    getFeed: (params?: { view?: FeedView; per_rail?: number; category?: string }) =>
      authenticatedFetch<Feed>(`/me/feed${buildQueryString(params)}`),
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

    getRecommendations: (customerId: string, params?: { limit?: number; window_days?: number }) =>
      portalFetch<RecommendedProduct[]>(`/customer/${customerId}/recommendations${buildQueryString(params)}`),

    getProducts: (params?: { q?: string; category?: string; brand?: string; limit?: number; offset?: number }) =>
      portalFetch<PortalProduct[]>(`/customer/products${buildQueryString(params)}`),

    getProduct: (productId: string) =>
      portalFetch<PortalProduct>(`/customer/products/${productId}`),

    getDispensaries: () =>
      portalFetch<PortalDispensary[]>(`/customer/dispensaries`),

    getDispensaryFilterOptions: (dispensaryId: string) =>
      portalFetch<{ brands: string[]; variants: string[] }>(`/customer/dispensaries/${dispensaryId}/filter-options`),

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
