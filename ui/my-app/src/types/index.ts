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
  /** How this store's price stands against the others carrying the same
   *  product. Every row of a store's menu carries one -- a product nobody else
   *  has reads as a zero count rather than being absent. Optional because the
   *  listing detail response spells the same facts out as `price_context`
   *  alongside the stores themselves. */
  market?: ListingPriceContext
}

/** The same product on another store's shelf. */
export type ListingAlternative = {
  listing_id: string
  price_cents: number | null
  url: string | null
  dispensary: PortalDispensary
}

/** How this store's price sits against everyone else carrying the product. */
export type ListingPriceContext = {
  other_store_count: number
  min_cents: number | null
  avg_cents: number | null
  max_cents: number | null
  is_cheapest: boolean
}

/** A neighbour on the same shelf — same category, ideally same brand and form. */
export type SimilarListing = {
  id: string
  display_name: string
  scraped_brand: string | null
  scraped_category: string | null
  subtype: string | null
  strain: string | null
  product_line: string | null
  variant: string | null
  price_cents: number | null
  image_url: string | null
}

export type ListingDetail = DispensaryListing & {
  dispensary_id: string
  dispensary_name: string
  dispensary_slug: string
  dispensary_accepts_pickup: boolean
  /** The whole store record, for the card that describes where this is sold. */
  dispensary: PortalDispensary
  in_stock: boolean
  classification: string | null
  description: string | null

  /** The key the product page is addressed by, so this screen can link to the
   *  cross-store view without rebuilding it. */
  product_key: string
  /** When a scrape last confirmed this row; null until one has. */
  last_seen_at: string | null

  also_available_at: ListingAlternative[]
  price_context: ListingPriceContext
  similar_at_dispensary: SimilarListing[]
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
  /** The brand's own logo, picked in the admin; absent from an API that predates it. */
  logo_url?: string | null
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

/** A product and every store carrying it, independent of brand.
 *  `brand` is null for products the stores publish unbranded. */
export type PortalProductDetail = PortalBrandProduct & {
  brand: string | null
}

export type PortalBrandDetail = {
  name: string
  image_url: string | null
  logo_url?: string | null
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

/* ── Brand catalogs ─────────────────────────────────────────────────────────
   A brand catalog is the products a brand says it makes, scraped from its own
   storefront. Postgres holds it; `data/catalogs/<slug>.json` is a generated
   export, and that file — not the table — is what enrichment reads. So an edit
   made in this UI does not reach enrichment until the export is regenerated,
   which is what `CatalogExportStatus` exists to make visible.
   ────────────────────────────────────────────────────────────────────────── */

export type CatalogExportStatus = {
  path: string
  file_exists: boolean
  file_readable: boolean
  file_generated_at: string | null
  db_entry_count: number
  file_entry_count: number | null
  added: number
  removed: number
  changed: number
  metadata_changed: boolean
  /** False means enrichment is still being shown the old catalog. */
  in_sync: boolean
  sample: { kind: 'added' | 'removed' | 'changed'; name: string; variant: string | null }[]
}

export type BrandCatalog = {
  id: string
  brand_slug: string
  brand_name: string
  source_url: string | null
  source_method: string
  fetched_at: string | null
  created_at: string
  updated_at: string
  entry_count: number
  active_entry_count: number
  /** Listings currently resolved to one of this catalog's entries. */
  listing_count: number
}

export type BrandCatalogRow = BrandCatalog & { export: CatalogExportStatus }

export type BrandCatalogEntry = {
  id: string
  catalog_id: string
  /** The source's own variant id. Null on hand-added entries. */
  external_id: string | null
  name: string
  product_line: string | null
  category: string | null
  subtype: string | null
  strain: string | null
  variant: string | null
  attributes: Record<string, unknown> | null
  match_terms: string[]
  is_active: boolean
  first_seen_at: string
  last_seen_at: string
  verified_by: string | null
  verified_at: string | null
  /** Claims that still hold, {field: value}. */
  verified_fields: Record<string, unknown>
  /** Claims made against a name this entry no longer has — not to be trusted. */
  lapsed_fields: string[]
  listing_count: number | null
}

export type BrandCatalogDetail = {
  catalog: BrandCatalog
  categories: string[]
  export: CatalogExportStatus
  total: number
  entries: BrandCatalogEntry[]
}

export type BrandCatalogEntryPage = {
  total: number
  entries: BrandCatalogEntry[]
}

/** A listing that resolves to a catalog entry, as the entry's accordion shows it. */
export type CatalogEntryListing = {
  id: string
  dispensary: { id: string; name: string; slug: string }
  scraped_name: string | null
  /** The store's own size, kept as typed. */
  variant: string | null
  /** The size the product page groups on: the store's, or the catalog's when the store mistyped it. */
  size: string | null
  price_cents: number | null
  in_stock: boolean
  is_active: boolean
  url: string | null
  image_url: string | null
  /** exact, jev or manual is trusted; jev_review is a suggestion the listing does not take. */
  match_method: string | null
  match_confidence: number | null
  last_seen_at: string | null
}

export type CatalogEntryListings = {
  entry_id: string
  /** Every listing that resolves here, inactive ones included (the entry's listing_count). */
  total: number
  listings: CatalogEntryListing[]
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

/** The rails a feed is built from, in the order they are shown. */
export const FEED_RAILS = ['featured', 'new', 'recommended', 'deals'] as const
export type FeedRail = typeof FEED_RAILS[number]

export type FeedRails = Record<FeedRail, FeedListing[]>

/** One followed store's slice of the home feed. */
export type FeedSection = {
  dispensary: PortalDispensary
  /** Everything in stock at that store, across all rails. */
  total: number
  rails: FeedRails
}

/** `store` keeps the followed stores separate; `combined` pools them. */
export type FeedView = 'store' | 'combined'

export type Feed = {
  view: FeedView
  /** Populated for the store view. */
  sections: FeedSection[]
  /** Populated for the combined view. */
  combined: FeedRails | null
  /** Every store the feed drew from, so combined cards can name theirs. */
  dispensaries: PortalDispensary[]
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

  /** What the deals rail's ranking knew: this price against the average
   *  elsewhere. Positive means cheaper here. */
  saving_cents: number | null

  /** How many of the shopper's *own* stores carry this — a different question
   *  from `market.other_store_count`, which counts every store we track. Only
   *  the combined view knows it, and only after deduping. */
  preferred_store_count: number

  /** How the price stands against the whole market, in the shape every other
   *  surface uses. Optional so an older response degrades rather than blanks. */
  market?: ListingPriceContext

  /** Only in the combined view, where a rail mixes stores. */
  dispensary_id?: string
}

/** The signed-in customer as `/me` returns them. */
export type CustomerProfile = {
  id: string
  /** Display name, composed from first_name + last_name once signed up. */
  name: string | null
  first_name: string | null
  last_name: string | null
  phone: string | null
  email: string | null
  marketing_opt_in: boolean
  onboarding: Onboarding
}

/** Sign-up state and what to show for it (routes_me.py, services/consent.py). */
export type Onboarding = {
  complete: boolean
  missing: Array<'first_name' | 'age_21' | 'terms'>
  prefill: { first_name: string | null; last_name: string | null }
  disclosures: {
    terms: { version: string; terms_url: string | null; privacy_url: string | null }
    age_21: { version: string; text: string }
    marketing_sms: { version: string; text: string }
  }
}

/** POST /me/onboarding. Versions echo the disclosures that were displayed. */
export type OnboardingPayload = {
  first_name: string
  last_name?: string | null
  age_21: boolean
  terms_version: string
  marketing_sms_opt_in: boolean
  marketing_sms_version?: string | null
  platform?: 'ios' | 'android' | 'web'
}

/** POST /me. Turning marketing texts on needs the disclosure version shown. */
export type ProfileUpdate = {
  name?: string
  first_name?: string
  last_name?: string
  marketing_opt_in?: boolean
  marketing_sms_version?: string
  platform?: 'ios' | 'android' | 'web'
}

/* ── Partner stores + POS connectors (routes/admin/partners.py) ─────────────── */

export type Partner = {
  id: string
  name: string
  slug: string
  is_active: boolean
  logo_url: string | null
  created_at: string
  updated_at: string
}

export type PartnerLocation = {
  id: string
  partner_id: string
  connection_id: string | null
  external_location_id: string | null
  name: string
  address: string | null
  timezone: string | null
  is_active: boolean
}

export type PosConnectionStatus = 'active' | 'error' | 'disabled' | 'revoked'

/** Credentials never leave the API; `has_credentials` is all the UI gets. */
export type PosConnection = {
  id: string
  partner_id: string
  provider: string
  status: PosConnectionStatus
  external_merchant_id: string
  scopes: string | null
  has_credentials: boolean
  token_expires_at: string | null
  sync_cursor: string | null
  syncing: boolean
  last_synced_at: string | null
  last_error: string | null
  consecutive_failures: number
  created_at: string
  updated_at: string
}

export type PartnerMember = {
  id: string
  partner_id: string
  email: string
  signed_in: boolean
  invited_at: string
  last_login_at: string | null
}

export type PartnerDetail = Partner & {
  locations: PartnerLocation[]
  connections: PosConnection[]
  members: PartnerMember[]
}

/** /partner/partners/:id — the same minus who has logins. */
export type PartnerPortalDetail = Omit<PartnerDetail, 'members'>

export type PartnerMe = { email: string | null; partners: Partner[] }

export type PosSyncRun = {
  id: string
  connection_id: string
  status: 'running' | 'ok' | 'error'
  since: string | null
  started_at: string
  finished_at: string | null
  orders_fetched: number
  orders_inserted: number
  orders_updated: number
  orders_matched: number
  error: string | null
}

/** What every view of a partner order has: the sale itself, never the shopper. */
export type PosOrderBase = {
  id: string
  partner_id: string
  connection_id: string
  partner_location_id: string | null
  external_order_id: string
  kind: 'sale' | 'return'
  source_external_order_id: string | null
  state: 'open' | 'completed' | 'canceled'
  currency: string
  total_cents: number
  tax_cents: number
  tip_cents: number
  discount_cents: number
  refunded_cents: number
  ordered_at: string
  closed_at: string | null
  items: { name: string; variation: string | null; quantity: string; total_cents: number }[]
}

/** The admin's view: which customer it matched and how. */
export type PosOrder = PosOrderBase & {
  /** Points this order has earned so far (net of refunds); admin listing only. */
  points?: number
  customer_id: string | null
  matched_via: 'link' | 'phone' | 'receipt' | 'sale' | null
  matched_at: string | null
  has_contact: boolean
  contact_purged_at: string | null
}

/** The partner's view: only whether the shopper was a Terpee member. */
export type PartnerPosOrder = PosOrderBase & { is_member: boolean }

export type PosOrderPage = { total: number; items: PosOrder[] }

/* ── Terpee points (connectors/points.py) ───────────────────────────────────── */

export type PointsEntry = {
  id: string
  kind: 'earn' | 'receipt' | 'refund' | 'adjust'
  points: number
  partner_name: string | null
  pos_order_id: string | null
  eligible_cents: number
  created_at: string
  available_at: string
  pending: boolean
  note: string | null
}

export type PointsSummary = {
  available: number
  pending: number
  points_per_dollar: number
  pending_days: number
  entries: PointsEntry[]
}

/* ── Receipt uploads (connectors/receipts.py) ───────────────────────────────── */

export type ReceiptStatus = 'pending' | 'approved' | 'rejected'

/** A receipt as its customer sees it. */
export type MyReceipt = {
  id: string
  partner_id: string
  partner_name: string | null
  status: ReceiptStatus
  purchased_on: string | null
  customer_note: string | null
  subtotal_cents: number | null
  points: number | null
  reject_reason: string | null
  created_at: string
  reviewed_at: string | null
}

export type PartnerOption = { id: string; name: string; logo_url?: string | null }

/** A receipt in the admin review queue. */
export type AdminReceipt = MyReceipt & {
  customer_id: string
  customer_name: string | null
  customer_phone: string | null
  reviewed_by: string | null
  image_content_type: string
  /** Set when approved by matching a synced POS order. */
  pos_order_id: string | null
  /** Whether the receipt reader has read the photo yet. */
  read_status: 'read' | 'pending' | 'failed'
}

/** What Claude read off the photo (connectors/receipt_reader.py ReceiptRead). */
export type ReceiptRead = {
  is_receipt: boolean
  legible: boolean
  merchant_name: string | null
  partner_id: string | null
  purchase_date: string | null
  purchase_time: string | null
  subtotal_cents: number | null
  tax_cents: number | null
  tip_cents: number | null
  total_cents: number | null
  card_brand: string | null
  card_last4: string | null
  receipt_number: string | null
  confidence: 'low' | 'medium' | 'high'
  notes: string | null
}

/** A synced POS order that may be the purchase on the receipt. */
export type ReceiptOrderCandidate = {
  id: string
  ordered_at: string
  total_cents: number
  tax_cents: number
  tip_cents: number
  subtotal_cents: number
  cards: string[]
  score: number
  signals: string[]
  strength: 'exact' | 'likely' | 'weak'
  /** Who already earned on this order, if anyone. */
  claimed: null | 'this_customer' | 'other_customer'
}

export type ReceiptFlag = { code: string; message: string; level: 'bad' | 'warn' | 'info' }

export type ReceiptReading = {
  read: ReceiptRead | null
  read_model: string | null
  read_at: string | null
  read_error: string | null
  /** The store has a POS connected, so a matching sale is expected. */
  has_pos: boolean
  candidates: ReceiptOrderCandidate[]
  best_order_id: string | null
  flags: ReceiptFlag[]
  suggestion: 'approve_order' | 'approve_subtotal' | 'reject_duplicate' | 'review'
}

export type AdminReceiptDetail = AdminReceipt & {
  points_per_dollar: number
  pending_days: number
  /** Purchase date more than 30 days ago. Flagged, not refused. */
  stale: boolean
  partners: PartnerOption[]
  duplicate_receipts: { id: string; status: ReceiptStatus; purchased_on: string | null; subtotal_cents: number | null; created_at: string }[]
  nearby_orders: { id: string; ordered_at: string; total_cents: number; subtotal_cents: number; same_customer: boolean; matched: boolean }[]
  reading: ReceiptReading
}

export type AdminReceiptQueue = {
  counts: Record<ReceiptStatus, number>
  items: AdminReceipt[]
}

/** A brand in the admin's logo picker (routes/admin/brand_logos.py). */
export type BrandLogoRow = {
  brand_key: string
  brand_name: string
  listing_count: number
  logo_url: string | null
  site_url: string | null
  chosen_by: string | null
  updated_at: string | null
}

export type LogoCandidate = { url: string; kind: string }
