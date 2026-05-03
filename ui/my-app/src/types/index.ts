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
  variant?: string | null
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

export type LabReport = {
  id: string
  status: 'pending' | 'extracted' | 'applied' | 'failed'
  lab_name: string | null
  lab_license: string | null
  test_date: string | null
  batch_id: string | null
  product_name_on_report: string | null
  total_terpenes: number | null
  pass_fail: string | null
  confidence: number | null
  product_id: string | null
  listing_id: string | null
  created_at: string | null
}

export type LabReportUpload = {
  lab_report_id: string
  filename: string | null
}

export type LabReportResult = {
  lab_report_id: string
  lab_name: string | null
  lab_license: string | null
  test_date: string | null
  batch_id: string | null
  product_name: string | null
  total_terpenes: number | null
  pass_fail: string | null
  terpenes: Terpene[]
  cannabinoids: Terpene[]
  confidence: number
  confidence_notes: string | null
  status: 'pending' | 'extracted' | 'applied' | 'failed'
  applied_to_product: boolean
}

export type LabReportDetail = LabReport & {
  terpenes: Terpene[]
  cannabinoids: Terpene[]
  confidence_notes: string | null
  product_name: string | null
}

export type MatchCandidate = {
  product_id: string
  product_name: string
  product_brand: string | null
  product_variant: string | null
  product_category: string
  score: number
  match_basis: string
  dispensary_slugs: { slug: string; url: string | null }[]
}

export type UnmatchedListing = {
  id: string
  dispensary_id: string
  dispensary_name: string
  dispensary_slug: string
  sku: string | null
  scraped_name: string | null
  scraped_brand: string | null
  scraped_category: string | null
  variant: string | null
  price_cents: number | null
  url: string | null
  in_stock: boolean
  candidates: MatchCandidate[]
}

export type DispensaryListing = {
  id: string
  scraped_name: string | null
  scraped_brand: string | null
  scraped_category: string | null
  price_cents: number | null
  variant: string | null
  url: string | null
  image_url: string | null
  product_id: string | null
  terpenes: Terpene[]
  cannabinoids: Cannabinoid[]
}

export type ListingDetail = DispensaryListing & {
  dispensary_id: string
  dispensary_name: string
  dispensary_slug: string
  dispensary_accepts_pickup: boolean
  in_stock: boolean
}

export type CartItem = {
  listingId: string
  dispensaryId: string
  dispensarySlug: string
  dispensaryName: string
  name: string
  brand: string | null
  variant: string | null
  price_cents: number | null
  url: string | null
  image_url: string | null
  quantity: number
}

export type Dispensary = {
  id: string
  name: string
  slug: string
  website_url: string | null
  location: string | null
  address: string | null
  lat: number | null
  lng: number | null
  is_active: boolean
  pos_type: string
  pos_tenant_id: string | null
  created_at: string
  updated_at: string
}

export type Listing = {
  id: string
  product_id: string | null
  product_name: string | null
  product_brand: string | null
  dispensary_id: string
  dispensary_name: string
  dispensary_slug: string
  scraped_name: string | null
  scraped_name_raw: string | null
  scraped_brand: string | null
  scraped_category: string | null
  price_cents: number | null
  variant: string | null
  sku: string | null
  url: string | null
  in_stock: boolean
  is_active: boolean
  scraped_at: string | null
  created_at: string
  updated_at: string
}
