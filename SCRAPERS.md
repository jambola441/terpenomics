# Scrapers

All dispensary metadata lives in **`dispensaries.json`** at the project root — that is the
single source of truth. Scrapers read from it; do not create per-scraper `stores.json` files.

Scraped CSVs go to **`data/scrapes/<slug>_listings.csv`**.

---

## Architecture

| Platform | How it works | Scraper |
|---|---|---|
| `dutchie_graphql` | POST to `dutchie.com/graphql` — `FilteredProducts` query with `dispensaryId`. No auth; `curl_cffi safari17_0` TLS impersonation bypasses Cloudflare. Covers WP-embed iframe stores AND Dutchie eCommerce Next.js stores. | `prototypes/dutchie-scraper/scrape_graphql.py` |
| `tymber` | GET `ecom-api.blaze.me/api/v1/products/` — `X-Store: <blaze_id>` header, no auth. | `prototypes/tymber-scraper/scrape_blaze.py` |
| `alleaves` | POST to `app.alleaves.com` — requires `ALLEAVES_USER` / `ALLEAVES_PASS` env vars. Cross-references Carrot/Typesense storefront for published products and real prices. | `prototypes/alleaves-scraper/scrape.py` |
| `travel_agency` | GET `thetravelagency.co/menu.data` — Remix turbo-stream JSON, no auth. | `prototypes/travel-agency-scraper/scrape.py` |
| `flowhub` | Remix HTML, dispensary.shop domain. Scraper in `prototypes/dutchie-scraper/scrape.py` (shared with dutchie_plus). | `prototypes/dutchie-scraper/scrape.py` |
| `dutchie_plus` | Remix HTML, Dutchie Plus storefront. | `prototypes/dutchie-scraper/scrape.py` |
| `shopify` / `sweedpos` | Not yet implemented. | — |

---

## Running scrapers

### Dutchie GraphQL — batch all stores

```bash
python prototypes/dutchie-scraper/scrape_graphql.py --all
# CSVs → data/scrapes/<slug>_listings.csv
```

Single store:

```bash
python prototypes/dutchie-scraper/scrape_graphql.py \
  --dutchie-id 66d24bbc7ee915c729faa0a0 \
  --dispensary-slug soulmate-fort-greene \
  --name "Soulmate"
```

### Tymber/BLAZE — batch all stores

```bash
python prototypes/tymber-scraper/scrape_blaze.py --all
```

Single store:

```bash
python prototypes/tymber-scraper/scrape_blaze.py \
  --blaze-id 31157479-283f-402f-92d4-36b7a01524b1 \
  --dispensary-slug bedford-club-bk \
  --name "Bedford Club"
```

### Alleaves

Requires credentials:

```bash
export ALLEAVES_USER=your@email.com
export ALLEAVES_PASS=yourpassword
python prototypes/alleaves-scraper/scrape.py
```

### The Travel Agency

```bash
python prototypes/travel-agency-scraper/scrape.py
```

---

## Dispensary registry

All 31 Brooklyn dispensaries. Status: **active** = scraper confirmed working; **pending** = not yet run; **inactive** = returns 0 products; **unsupported** = platform not implemented.

| Name | Slug | Platform | Status | Neighborhood |
|---|---|---|---|---|
| Coney Island Cannabis | coney-island-cannabis | dutchie_plus | pending | Coney Island |
| The Plug | the-plug-crown-heights | flowhub | pending | Crown Heights |
| Grow Together | grow-together-bk | flowhub | pending | — |
| The Emerald Dispensary | emerald-dispensary-bk | dutchie_graphql | **active** | Bushwick |
| Hii NYC Williamsburg | hii-nyc-williamsburg | dutchie_graphql | **active** | Williamsburg |
| Hii NYC Bay Ridge | hii-nyc-bay-ridge | dutchie_graphql | **active** | Bay Ridge |
| The Garden Club | garden-club-carroll-gardens | dutchie_graphql | **active** | Carroll Gardens |
| Herbology | herbology-bed-stuy | dutchie_graphql | **active** | Bed-Stuy |
| Fireleaf | fireleaf-canarsie | dutchie_graphql | **active** | Canarsie |
| Twisted Vibration | twisted-vibration-wburg | dutchie_graphql | **active** | Williamsburg |
| By Any Other Name | by-any-other-name-bk | dutchie_graphql | **active** | — |
| StashMaster NYC | stashmaster-nyc | dutchie_graphql | **active** | — |
| Kaya Bliss Dispensary | kaya-bliss-bay-ridge | dutchie_graphql | **active** | Bay Ridge |
| Kaya Bliss Brooklyn Heights | kaya-bliss-brooklyn-heights | dutchie_graphql | **active** | Brooklyn Heights |
| RNR Dispensary | rnr-dispensary-bk | dutchie_graphql | **active** | — |
| OC Dispensary | oc-dispensary-bk | dutchie_graphql | **active** | — |
| Soulmate | soulmate-fort-greene | dutchie_graphql | **active** | Fort Greene |
| Quality Control Dispensary | quality-control-brighton-beach | dutchie_graphql | **active** | Brighton Beach |
| Milligrams | milligrams-greenpoint | dutchie_graphql | **active** | Greenpoint |
| Dagmar Cannabis Williamsburg | dagmar-cannabis-wburg | dutchie_graphql | **active** | Williamsburg |
| Greene Street | greene-street-sheepshead-bay | dutchie_graphql | **active** | Sheepshead Bay |
| Emerald Dispensary Carroll Gardens | emerald-dispensary-carroll-gardens | dutchie_graphql | **active** | Carroll Gardens |
| Bedford Club | bedford-club-bk | tymber | **active** | — |
| Happy Munkey Brooklyn | happy-munkey-bk | tymber | inactive | Downtown Brooklyn |
| The Spot Dispensary | the-spot-bk | tymber | **active** | — |
| Ignyte Red Hook | ignyte-red-hook | tymber | **active** | Red Hook |
| Hold Up Roll Up | hold-up-roll-up | tymber | **active** | — |
| Brooklyn Organic Buds | brooklyn-organic-buds | alleaves | pending | — |
| The Travel Agency | travel-agency-ny | travel_agency | pending | — |
| Misha's Flower Shop | mishas-flower-shop-bk | sweedpos | unsupported | — |
| Happy Buds Brooklyn | happy-buds-bk | shopify | unsupported | — |

---

## Adding a new dispensary

1. Identify the platform (check the site's network requests or CDN assets).
2. Get the platform ID:
   - **dutchie_graphql**: find `dutchie_id` via `filteredDispensaries(filter: {cNameOrID: cname})` or from the WP embed init JS URL (`dutchie.com/api/v2/embedded-menu/{id}.js`).
   - **tymber**: find `blaze_id` in `ecom-api.blaze.me` XHR headers on the store's menu page.
3. Add an entry to `dispensaries.json` with `"status": "pending"`.
4. Run the appropriate scraper with the new ID to verify, then set `"status": "active"`.
5. Run the smoke test: `pytest tests/test_smoke.py -k <slug> -m live`.
