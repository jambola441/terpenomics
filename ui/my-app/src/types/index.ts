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

// Products are a derived VIEW — no id, no CRUD
export type Product = {
  brand: string | null
  category: string
  subtype: string | null
  product_line: string | null
  strain: string | null
  variant: string | null
  listing_count: number
  dispensary_count: number
  min_price_cents: number | null
  max_price_cents: number | null
  any_in_stock: boolean
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
  listing_id: string | null
  product_name: string | null
  dispensary_id: string | null
  variant: string | null
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

export type PurchaseCreateParams = {
  customer_id: string
  purchased_at?: string
  source?: 'manual' | 'pos_import'
  external_id?: string
  notes?: string
}

export type PurchaseItemCreateParams = {
  listing_id: string
  quantity: number
  line_amount_cents: number
}

export type PortalPurchaseItem = {
  id: string
  purchase_id: string
  listing_id: string | null
  product_name: string | null
  product_category: string | null
  variant: string | null
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
  /** What the shopper reads. Derived server-side from the enriched fields,
   *  falling back to a cleaned `scraped_name` -- see services/display_name.py. */
  display_name: string
  brand: string | null
  category: string
  subtype: string | null
  product_line: string | null
  strain: string | null
  variant: string | null
  listing_count: number
  dispensary_count: number
  min_price_cents: number | null
  max_price_cents: number | null
  any_in_stock: boolean
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
  applied_to_listing: boolean
}

export type LabReportDetail = LabReport & {
  terpenes: Terpene[]
  cannabinoids: Terpene[]
  confidence_notes: string | null
  product_name: string | null
}

export type DispensaryListing = {
  id: string
  /** What the shopper reads. Derived server-side from the enriched fields,
   *  falling back to a cleaned `scraped_name` -- see services/display_name.py. */
  display_name: string
  /** The store's own catalogue string. Kept for search and provenance; show
   *  `display_name` instead. */
  scraped_name: string | null
  scraped_brand: string | null
  scraped_category: string | null
  subtype: string | null
  strain: string | null
  product_line: string | null
  price_cents: number | null
  variant: string | null
  url: string | null
  image_url: string | null
  in_stock: boolean
  terpenes: Terpene[]
  cannabinoids: Cannabinoid[]
}

export type ListingDetail = DispensaryListing & {
  dispensary_id: string
  dispensary_name: string
  dispensary_slug: string
  dispensary_accepts_pickup: boolean
  in_stock: boolean
  classification: string | null
  description: string | null
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

export type OrderStatus = 'submitted' | 'ready' | 'completed' | 'cancelled'

export type OrderItem = {
  id: string
  listing_id: string | null
  name: string
  brand: string | null
  variant: string | null
  image_url: string | null
  quantity: number
  unit_price_cents: number | null
  line_amount_cents: number
}

export type Order = {
  id: string
  status: OrderStatus
  /** Read out at the counter to collect the order. */
  pickup_code: string
  total_amount_cents: number
  note: string | null
  submitted_at: string
  ready_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  dispensary_id: string
  dispensary_name: string | null
  dispensary_slug: string | null
  dispensary_address: string | null
  /** Always 'pay_at_pickup' — nothing is charged online. */
  payment_method: string
  items: OrderItem[]
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
  dispensary_id: string
  dispensary_name: string
  dispensary_slug: string
  scraped_name: string | null
  scraped_brand: string | null
  scraped_category: string | null
  subtype: string | null
  strain: string | null
  product_line: string | null
  price_cents: number | null
  variant: string | null
  sku: string | null
  url: string | null
  image_url: string | null
  in_stock: boolean
  is_active: boolean
  classification: string | null
  description: string | null
  scraped_at: string | null
  created_at: string
  updated_at: string
}

export type PortalBrand = {
  name: string
  listing_count: number
  image_url: string | null
}

export type PortalCategory = {
  name: string
  listing_count: number
  image_url: string | null
}

export type PortalBrandOffering = {
  listing_id: string
  dispensary_id: string
  dispensary_name: string
  dispensary_slug: string
  lat: number | null
  lng: number | null
  price_cents: number | null
  in_stock: boolean
  url: string | null
}

export type PortalBrandProduct = {
  key: string
  name: string
  category: string | null
  subtype: string | null
  product_line: string | null
  strain: string | null
  variant: string | null
  image_url: string | null
  min_price_cents: number | null
  dispensary_count: number
  offerings: PortalBrandOffering[]
}

export type PortalBrandDetail = {
  name: string
  image_url: string | null
  product_count: number
  dispensary_count: number
  products: PortalBrandProduct[]
}

/** A store carrying products in a category. Sent once; offerings index into it. */
export type PortalCategoryDispensary = {
  id: string
  name: string
  slug: string
  lat: number | null
  lng: number | null
}

/**
 * One store's price for a product. Deliberately thin — the store's name and
 * coordinates live in `PortalCategoryDetail.dispensaries[dispensary_index]`,
 * because repeating them per offering was most of this response's weight.
 */
export type PortalCategoryOffering = {
  dispensary_index: number
  price_cents: number | null
  /**
   * Present only on products with no brand. A branded product opens the
   * brand-product view, addressed by key; an unbranded one has no such page,
   * so it needs a specific listing to navigate to.
   */
  listing_id?: string
}

export type PortalCategoryProduct = {
  key: string
  name: string
  brand: string | null
  category: string | null
  subtype: string | null
  product_line: string | null
  strain: string | null
  variant: string | null
  image_url: string | null
  min_price_cents: number | null
  max_price_cents: number | null
  dispensary_count: number
  offerings: PortalCategoryOffering[]
}

export type PortalCategoryDetail = {
  name: string
  image_url: string | null
  product_count: number
  dispensary_count: number
  brand_count: number
  truncated: boolean
  /** Every store appearing in `products[].offerings`, in index order. */
  dispensaries: PortalCategoryDispensary[]
  products: PortalCategoryProduct[]
}

/** A store as the portal sees it — the shape both `/customer/dispensaries` and
 *  `/me/preferred-dispensaries` return. */
export type PortalDispensary = {
  id: string
  name: string
  slug: string
  address: string | null
  lat: number | null
  lng: number | null
  website_url: string | null
  accepts_pickup: boolean
  logo_url: string | null
  banner_url: string | null
}

/** One followed store's slice of the home feed. */
export type FeedSection = {
  dispensary: PortalDispensary
  /** Everything in stock at that store, of which `listings` is the first page. */
  total: number
  listings: FeedListing[]
}

/** A feed card. Lighter than `DispensaryListing`: the feed shows no lab data,
 *  so the endpoint does not carry terpenes or cannabinoids. */
export type FeedListing = {
  id: string
  /** What the shopper reads. Derived server-side from the enriched fields,
   *  falling back to a cleaned `scraped_name` -- see services/display_name.py. */
  display_name: string
  scraped_name: string | null
  scraped_brand: string | null
  scraped_category: string | null
  subtype: string | null
  strain: string | null
  product_line: string | null
  price_cents: number | null
  variant: string | null
  url: string | null
  image_url: string | null
  in_stock: boolean
}

/** The signed-in customer as `/me` returns them. */
export type CustomerProfile = {
  id: string
  name: string | null
  phone: string | null
  email: string | null
  marketing_opt_in: boolean
}
