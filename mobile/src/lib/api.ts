// The customer-facing slice of the web client (ui/my-app/src/api/client.ts):
// SMS login, /me, orders, points and receipts, and the public portal endpoints. Admin endpoints stay
// web-only. Response types come from the web app so the two can't drift.
import type {
  CustomerProfile,
  OnboardingPayload,
  ProfileUpdate,
  Feed,
  FeedView,
  ListingDetail,
  MyReceipt,
  Order,
  PartnerOption,
  PointsSummary,
  PortalCategory,
  PortalCategoryDetail,
  PortalDispensary,
  PortalProductDetail,
} from '@web/types'
import { Platform } from 'react-native'
import supabase from './supabase'
import { API_BASE } from './config'

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

function query(params?: Record<string, unknown>): string {
  if (!params) return ''
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&')
  return qs ? `?${qs}` : ''
}

/** Every error surfaces FastAPI's `detail` string when there is one, since
 *  on a phone the message goes straight on screen. */
async function request<T>(path: string, init: RequestInit = {}, auth = false): Promise<T> {
  // A FormData body sets its own multipart Content-Type, boundary included.
  const headers: Record<string, string> = init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }
  if (auth) {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (!token) throw new ApiError('Not signed in', 401)
    headers.Authorization = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } })
  const text = await res.text()
  let payload: any = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    // Non-JSON body (proxy timeout, HTML error page) — fall back to the text.
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

const pub = <T,>(path: string, init?: RequestInit) => request<T>(path, init, false)
const authed = <T,>(path: string, init?: RequestInit) => request<T>(path, init, true)
const post = (body?: unknown): RequestInit => ({ method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  auth: {
    smsStart: (phone: string) =>
      pub<{ challenge_id: string; expires_in: number; resend_in: number; code_length?: number }>(`/auth/sms/start`, post({ phone })),

    smsVerify: (challengeId: string, code: string) =>
      pub<{ access_token: string; refresh_token: string; token_type: string; expires_in?: number; user_id: string }>(
        `/auth/sms/verify`,
        post({ challenge_id: challengeId, code }),
      ),
  },

  me: {
    getProfile: () => authed<CustomerProfile>(`/me`),

    updateProfile: (payload: ProfileUpdate) =>
      authed<CustomerProfile>(`/me`, post(payload)),

    /** Contact email: a code goes to the new address; it is saved on verify
     *  (routes/me_email.py). */
    startEmailChange: (email: string) =>
      authed<{ challenge_id: string; expires_in: number; resend_in: number }>(`/me/email/start`, post({ email })),

    verifyEmailChange: (challengeId: string, code: string) =>
      authed<CustomerProfile>(`/me/email/verify`, post({ challenge_id: challengeId, code })),

    removeEmail: () => authed<CustomerProfile>(`/me/email`, { method: 'DELETE' }),

    /** Deletes the login and scrubs the account (services/account_deletion.py). */
    deleteAccount: () => authed<null>(`/me`, { method: 'DELETE' }),

    completeOnboarding: (payload: OnboardingPayload) =>
      authed<CustomerProfile>(`/me/onboarding`, post(payload)),

    linkCustomer: () =>
      authed<{ customer_id: string; linked: boolean; created?: boolean }>(`/me/link-customer`, post({})),

    listPreferredDispensaries: () => authed<PortalDispensary[]>(`/me/preferred-dispensaries`),

    /** Follow or unfollow a store; both answer with the followed list. */
    addPreferredDispensary: (dispensaryId: string) =>
      authed<PortalDispensary[]>(`/me/preferred-dispensaries/${dispensaryId}`, { method: 'POST' }),
    removePreferredDispensary: (dispensaryId: string) =>
      authed<PortalDispensary[]>(`/me/preferred-dispensaries/${dispensaryId}`, { method: 'DELETE' }),

    getFeed: (params?: { view?: FeedView; per_rail?: number; category?: string }) =>
      authed<Feed>(`/me/feed${query(params)}`),

    /** Terpee points earned at partner stores. */
    getPoints: () => authed<PointsSummary>(`/me/points`),

    /** Partner stores a receipt can be claimed against. */
    getPartners: () => authed<PartnerOption[]>(`/me/partners`),

    getReceipts: () => authed<MyReceipt[]>(`/me/receipts`),

    /** Upload a receipt photo for review. `image` is a local file URI. */
    uploadReceipt: async (data: { partnerId: string; purchasedOn: string; note?: string; image: { uri: string; type: string; name: string } }) => {
      const form = new FormData()
      form.append('partner_id', data.partnerId)
      form.append('purchased_on', data.purchasedOn)
      if (data.note) form.append('note', data.note)
      if (Platform.OS === 'web') {
        form.append('image', await (await fetch(data.image.uri)).blob(), data.image.name)
      } else {
        // React Native's FormData takes a { uri, type, name } file reference.
        form.append('image', data.image as unknown as Blob)
      }
      return authed<MyReceipt>(`/me/receipts`, { method: 'POST', body: form })
    },
  },

  orders: {
    /** Prices come from the listings server-side; the client never sends a total. */
    create: (payload: { dispensary_id: string; items: { listing_id: string; quantity: number }[]; note?: string }) =>
      authed<Order>(`/me/orders`, post(payload)),

    list: (params?: { limit?: number; offset?: number }) => authed<Order[]>(`/me/orders${query(params)}`),
    get: (orderId: string) => authed<Order>(`/me/orders/${orderId}`),
    cancel: (orderId: string) => authed<Order>(`/me/orders/${orderId}/cancel`, post()),
  },

  portal: {
    getDispensaries: () => pub<PortalDispensary[]>(`/customer/dispensaries`),

    getListing: (dispensaryId: string, listingId: string) =>
      pub<ListingDetail>(`/customer/dispensaries/${dispensaryId}/listings/${listingId}`),

    /** One product with every store's offering. Omit brand for unbranded products. */
    getProductDetail: (key: string, brand?: string | null) =>
      pub<PortalProductDetail>(`/customer/products/detail${query({ key, brand: brand ?? undefined })}`),

    getCategories: () => pub<PortalCategory[]>(`/customer/categories`),

    getCategory: (name: string) => pub<PortalCategoryDetail>(`/customer/categories/${encodeURIComponent(name)}`),
  },
}
