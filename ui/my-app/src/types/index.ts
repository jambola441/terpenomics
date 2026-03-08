// Shared types across the application

export type Feedback = 'like' | 'dislike' | 'neutral' | null

export type Terpene = {
  name: string
  percent?: number | null
}

export type Cannabinoid = {
  name: string
  family: 'thc' | 'cbd'
  percent?: number | null
}

export type Product = {
  id: string
  name: string
  brand?: string | null
  category: string
  is_active: boolean
  terpenes?: Terpene[]
  cannabinoids?: Cannabinoid[]
}

export type Customer = {
  id: string
  name?: string | null
  phone?: string | null
  email?: string | null
  marketing_opt_in: boolean
  last_visit_at?: string | null
  auth_user_id?: string | null
}

export type PurchaseItem = {
  id: string
  product_id: string
  product_name: string
  quantity: number
  line_amount_cents?: number | null
  feedback?: Feedback
  feedback_at?: string | null
}

export type Purchase = {
  id: string
  purchased_at: string
  total_amount_cents: number
  source: string
  notes?: string | null
  items: PurchaseItem[]
}

export type PurchaseRow = {
  id: string
  purchased_at: string
  total_amount_cents: number
  source: string
  external_id?: string | null
  notes?: string | null
  customer_id: string
  customer_name?: string | null
  customer_phone?: string | null
  item_count?: number | null
}

export type TerpeneScoreRow = {
  terpene: string
  score: number
  likes: number
  dislikes: number
  neutrals: number
}

export type TerpeneScoresResponse = {
  customer_id: string
  window_days: number
  cutoff: string
  scores: TerpeneScoreRow[]
}

export type ProductTerpenesMap = Record<string, Terpene[]>

// API Parameter types
export type ListParams = {
  q?: string
  limit?: number
  offset?: number
}

export type PurchaseListParams = ListParams & {
  source?: string
}

export type CustomerPurchasesParams = {
  limit?: number
  offset?: number
}

export type TerpeneScoresParams = {
  window_days?: number
}

export type RecommendedProduct = {
  id: string
  name: string
  brand?: string | null
  category: string
  score: number
  terpenes: Terpene[]
  purchased_count: number
}

export type PurchaseCreateParams = {
  customer_id: string
  purchased_at?: string
  source?: 'manual' | 'pos_import'
  external_id?: string
  notes?: string
}

export type PurchaseItemCreateParams = {
  product_id: string
  quantity: number
  line_amount_cents: number
  external_id?: string
}

export type PortalPurchaseItem = {
  id: string
  purchase_id: string
  product_id: string
  product_name: string
  product_category: string
  quantity: number
  line_amount_cents?: number | null
  feedback?: Feedback
  feedback_at?: string | null
}

export type PortalPurchase = {
  id: string
  purchased_at: string
  total_amount_cents: number
  source: string
  notes?: string | null
  items: PortalPurchaseItem[]
}

export type FeedbackResponse = {
  id: string
  feedback: Feedback
  feedback_at: string | null
}

export type PortalProduct = {
  id: string
  name: string
  brand?: string | null
  category: string
  terpenes: Terpene[]
  cannabinoids: Cannabinoid[]
}
