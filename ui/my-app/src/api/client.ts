import supabase from '../utils/supabase'
import type {
  Customer,
  Product,
  Purchase,
  PurchaseRow,
  TerpeneScoresResponse,
  ProductTerpenesMap,
  Cannabinoid,
  ListParams,
  PurchaseListParams,
  CustomerPurchasesParams,
  TerpeneScoresParams,
  RecommendedProduct,
  PurchaseCreateParams,
  PurchaseItemCreateParams,
  PurchaseItem,
  PortalPurchase,
  PortalProduct,
  FeedbackResponse,
  Feedback,
  LabReport,
  LabReportUpload,
  LabReportResult,
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

// Centralized API client
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
    list: (params?: ListParams) =>
      authenticatedFetch<Product[]>(`/admin/products${buildQueryString(params)}`),
    
    get: (id: string) =>
      authenticatedFetch<Product>(`/admin/products/${id}`),
    
    create: (data: any) =>
      authenticatedFetch<{ id: string }>(`/admin/products`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    
    update: (id: string, data: any) =>
      authenticatedFetch<Product>(`/admin/products/${id}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    
    getTerpenes: (productIds: string[]) =>
      authenticatedFetch<ProductTerpenesMap>(`/admin/products/terpenes?product_ids=${productIds.join(',')}`),

    getCannabinoids: (productIds: string[]) =>
      authenticatedFetch<Record<string, Cannabinoid[]>>(`/admin/products/cannabinoids?product_ids=${productIds.join(',')}`),

    listAllTerpenes: () =>
      authenticatedFetch<{ name: string }[]>(`/admin/products/terpenes`),

    listAllCannabinoids: () =>
      authenticatedFetch<Cannabinoid[]>(`/admin/products/cannabinoids`),
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

    process: async (labReportIds: string[], productId?: string): Promise<LabReportResult[]> => {
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
          product_id: productId ?? null,
        }),
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `Processing failed with status ${res.status}`)
      }

      return res.json()
    },
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

    getProducts: (params?: { q?: string; limit?: number; offset?: number }) =>
      portalFetch<PortalProduct[]>(`/customer/products${buildQueryString(params)}`),

    getProduct: (productId: string) =>
      portalFetch<PortalProduct>(`/customer/products/${productId}`),
  },
}

export default api
