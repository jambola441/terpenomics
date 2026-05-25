# Brooklyn Licensed Cannabis Dispensaries

**Last updated:** 2026-05-23  
**Source:** NYS OCM Dispensary Location Verification + individual site fingerprinting

## Full Roster

| # | Name | Neighborhood | License Type | Website | Menu URL | Platform | Confidence | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | Brooklyn Organic Buds | (existing) | adult-use retail | brooklynorganicbuds.com | https://brooklynorganicbuds.com/store/product | Alleaves | confirmed | Reference instance — already in system |
| 2 | Grow Together | Sheepshead Bay | CAURD | growtogetherbk.com | https://dutchie.com/dispensary/grow-together-brooklyn | Dutchie | confirmed | |
| 3 | BK Exotic / Brooklyn Exotic | Flatbush | CAURD | brooklynexotic.com | https://brooklynexotic.com/shop | Dispense | confirmed | |
| 4 | The Emerald Dispensary | Bushwick | CAURD | theemeralddispensary.com | https://theemeralddispensary.com/shop/ | Dutchie | confirmed | WP embed; `dtche` params confirmed |
| 5 | Tiki Leaves | Coney Island | CAURD | tikileaves.com | — | Unknown | low | Site offline as of 2026-05-23; possibly in-store only |
| 6 | Matawana | Park Slope | CAURD | matawanany.com | https://shop.matawanany.com/brooklyn | Sweedpos | confirmed | |
| 7 | Misha's Flower Shop | Bushwick | CAURD | mishasflowershop.com | https://shop.mishasflowershop.com/mishasflower/menu/ | Dutchie | confirmed | |
| 8 | The Travel Agency Downtown Brooklyn | Downtown BK | CAURD | thetravelagency.co | https://www.thetravelagency.co/menu/ | Custom (Leaflogix-backed) | confirmed | In-house frontend |
| 9 | Hii NYC Williamsburg | Williamsburg | CAURD | hiinyc.com | https://hiinyc.com/stores/hii-williamsburg | Dutchie | confirmed | |
| 10 | Hii NYC Bay Ridge | Bay Ridge | RETL | hiinyc.com | https://hiinyc.com/stores/hii-bay-ridge | Dutchie | inferred | Same operator as #9 |
| 11 | Chronic Brooklyn | Gowanus | CAURD | chronicbrooklyn.com | https://chronicbrooklyn.com/store/ | Carrot | confirmed | Footer: "Dispensary Website Powered by Carrot" |
| 12 | Bedford Club | Bed-Stuy | CAURD | bedfordclub.com | https://shop.bedfordclub.com/rec/menu | Dutchie | confirmed | |
| 13 | The Plug | Crown Heights | CAURD | theplugny.com | https://theplug-brooklyn.dispensary.shop/rec/search | Dutchie | confirmed | dispensary.shop is Dutchie white-label |
| 14 | Herbology | Bed-Stuy | CAURD | herbologynyc.com | https://herbologynyc.com/shop/ | Dutchie | inferred | WP age-gated; JointCommerce listing confirms Dutchie |
| 15 | Beleaf BK | Prospect Heights | CAURD | beleafny.com | https://beleafny.com/brooklyn/menu/ | Custom / AlpineIQ | inferred | Multi-location operator |
| 16 | Brooklyn Bourne | Flatbush | CAURD | brooklynbourne.com | https://www.brooklynbourne.com/store.html | Custom + own app | confirmed | Static HTML; primary ordering via Bourne Insiders 2.0 app + Springbig loyalty |
| 17 | Fireleaf | Canarsie | CAURD | fireleaf.com | https://fireleaf.com/shop/ | Dutchie | confirmed | fireleafny.com 302s to fireleaf.com; `dtche` params confirmed |
| 18 | Twisted Vibration | Williamsburg | CAURD | twistedvibration.com | https://twistedvibration.com/shop-menu/ | Dutchie | confirmed | `dtche` params in static HTML; page is JS-rendered, bot-blocks fetches |
| 19 | Happy Munkey Brooklyn | Downtown BK | CAURD | happymunkey.com | https://happymunkey.com/shop/fulton/ | Tymber/BLAZE | confirmed | "by BLAZE ™" + tymber-blaze-products.imgix.net |
| 20 | By Any Other Name | Clinton Hill | CAURD | byanyothernamebk.com | https://byanyothernamebk.com/shop/ | Dutchie | inferred | WP lazy-load; JointCommerce /dispensaries/9316 |
| 21 | The Flowery Brooklyn | Williamsburg | CAURD | thefloweryny.com | https://www.thefloweryny.com/shop | Custom (in-house) | inferred | Multi-location operator with first-party shop routes |
| 22 | Puro Vita | Clinton Hill | CAURD | purovita.com | https://purovita.com/stores/puro-vita-retail | Custom (Range Marketing) | inferred | "Designed by Range Marketing" |
| 23 | StashMaster NYC | Bushwick | CAURD | stashmasternyc.com | https://stashmasternyc.com/shop/ | Dutchie | confirmed | `dtche` params confirmed |
| 24 | Kushmart | Midwood | CAURD | kushmart.com | https://kushmart.com/location/brooklyn-ny/shop | Unknown | low | No CDN/footer signals; needs JS network inspection |
| 25 | Kaya Bliss Dispensary | Bay Ridge | CAURD | kayablissnyc.com | https://kayablissnyc.com/location/brooklyn-ny/shop/ | Dutchie | confirmed | `dtche` params |
| 26 | The Spot Dispensary | Clinton Hill | CAURD | thespotdispensary.com | https://thespotdispensary.com/menu | Tymber/BLAZE | confirmed | tymber-blaze-products.imgix.net |
| 27 | Caffiend: The Bushwick Dispensary | Bushwick | CAURD | thebushwicknyc.com | https://caffiend-the-bushwick-dispensary.wm.store/discover | Weedmaps WM Store | confirmed | wm.store subdomain |
| 28 | RNR Dispensary | Bushwick | CAURD | rnrdispensary.com | https://store.rnrdispensary.com/stores/rnr-dispensary | Dutchie | confirmed | store. subdomain |
| 29 | Easy Times | Sheepshead Bay | RETL | easytimesny.com | https://menus.dispenseapp.com/ebc5c94b7fa54813/menu | Dispense | confirmed | |
| 30 | Animo Caribe | Flatbush | CAURD | animocaribe.com | https://animocaribe.com/store/ | Custom WP + own app | inferred | WP + Elementor + Aeropay; own iOS app |
| 31 | Jungle Kingdom Flower | Bed-Stuy | CAURD | junglekingdomflower.com | https://junglekingdomflower.com/order | Dispense | confirmed | dispense-images.imgix.net CDN |
| 32 | OC Dispensary | Crown Heights | CAURD | ocdispensary.co | https://dutchie.com/dispensary/oc-dispensary | Dutchie | inferred | Listed on dutchie.com |
| 33 | Coney Island Cannabis | Coney Island | CAURD | coneyislandcannabis.nyc | https://shop.coneyislandcannabis.nyc/location/coney-island-cannabis/shop | Dutchie | confirmed | images.dutchie.com CDN |
| 34 | Q Dispensary | Flatbush | CAURD | qiscannabis.com | https://www.qiscannabis.com/pages/shop-now | Shopify | confirmed | "Powered by Shopify" footer |
| 35 | Yerba Buena | Cobble Hill | CAURD | yerbabuena.nyc | https://yerbabuena.nyc/shop/cobblehill/ | Dispense | confirmed | dispense-images.imgix.net CDN |
| 36 | Soulmate | Fort Greene | CAURD | soulmatebk.com | https://soulmatebk.com/shop/ | Dutchie | confirmed | `dtche` params |
| 37 | Quality Roots | Bed-Stuy | CAURD | qualityroots.nyc | https://getqualityroots.com/categories/ | Custom (in-house) | inferred | Proprietary CDN |
| 38 | All Good Dispensary | Flatbush | CAURD | stayallgood.com | https://stayallgood.com/shop | Tymber/BLAZE | inferred | URL pattern matches BLAZE convention |
| 39 | Green Apple | Greenpoint | RETL | greenapple.nyc | https://greenapple.nyc/shop/ | SparkMenus | confirmed | Footer "Powered by SparkMenus" |
| 40 | Ignyte Red Hook | Red Hook | RETL | ignyteny.com | https://shop.ignyteny.com/whitestone/categories/flower | Tymber/BLAZE | confirmed | tymber-blaze-products.imgix.net; `/whitestone/` location slug |
| 41 | Quality Control Dispensary | Brighton Beach | RETL | qualitycontroldispensary.com | https://qualitycontroldispensary.com/shop-brooklyn | Dutchie | confirmed | 403 on fetch = Dutchie bot-block signature |
| 42 | Chrome Flowers | Greenpoint | CAURD | chromeflwrs.com | https://menus.dispenseapp.com/3d218a90fcb2edb0/menu/ | Dispense | confirmed | chromeflwrs.com is brochure-ware; menu is external Dispense link |
| 43 | Rustik Smokes | Fort Greene | CAURD | rustiksmokes.com | https://rustiksmokes.com/product-category/shop/flower/ | WooCommerce | inferred | `/product-category/` URL pattern |
| 44 | Hand in Bush | Bed-Stuy | CAURD | handinbush.com | https://handinbush.com/store/category/{cat}?locId=1 | Carrot | confirmed | carrot-static CDN + `?locId=1` params; `/menu/` is 404, real route is `/store/` |
| 45 | Milligrams | Greenpoint | RETL | milligrams.co | https://milligrams.co/stores/brooklyn-greenpoint-ny | Dutchie | confirmed | dutchie.com listing |
| 46 | Hold Up Roll Up | Prospect Heights | CAURD | holduprollup.com | https://holduprollup.com/menu/ | Tymber/BLAZE | confirmed | tymber-blaze-products.imgix.net CDN |
| 47 | Sunflower Cannabis | Williamsburg | CAURD | sunflowerbk.com | — | Unknown | low | Repeated fetch timeouts; possibly in-store only |
| 48 | Brooklyn Urban Dispensary | Greenpoint | RETL | — | — | — | n/a | Opening soon — no web presence yet |
| 49 | The Garden Club | Carroll Gardens | RETL | thegardenclubbk.com | https://thegardenclubbk.com/menu/ | Dutchie | inferred | dutchie.com/dispensary/dizzpensary listing |
| 50 | The Gallery at Dumbo | Dumbo | RETL | thegalleryny.com | https://thegalleryny.com/menu/ | Custom (Prismic-backed) | confirmed | images.prismic.io CDN; no third-party menu vendor |
| 51 | Superbness | Williamsburg | RETL | superbness.com | https://superbness.com/collections/all | Shopify | confirmed | "Powered by Shopify"; `/cdn/shop/files/` asset path |
| 52 | The HiBrary Club | Park Slope | CAURD | — | — | Unknown | low | License OCM-CAURD-25-000321; no standalone website found |
| 53 | Weedly NYC | Flatbush | RETL | weedlynyc.com | https://weedlynyc.com/store/ | Carrot | confirmed | Footer "Powered by Carrot" + carrot-static CDN |
| 54 | High Dankery | Bay Ridge | CAURD | highdankery.com | https://highdankery.com/store/ | Carrot | confirmed | Footer "Powered by Carrot" + `?locId=1` pattern |
| 55 | Budega NYC | Park Slope | CAURD | budega.nyc | https://budega.nyc/shop | Dispense | confirmed | dispense-images.imgix.net CDN |
| 56 | Twenty8Gramz | Sheepshead Bay | CAURD | twenty8gramz.com | https://weedmaps.com/dispensaries/twenty8gramz-1 | Weedmaps-only | confirmed | Own site is brochure-ware; menu only on Weedmaps |
| 57 | Elevated | Midwood | RETL | — | — | Unknown | low | Sparse web presence; verify via OCM |
| 58 | Flower Daddy | Williamsburg | RETL | flowerdaddy.nyc | https://shop.flowerdaddy.nyc/newyork | Sweedpos | confirmed | media-prime.sweedpos.com + static.sweedpos.com CDNs |
| 59 | Happy Buds Brooklyn | Bed-Stuy | CAURD | happybudsbk.com | https://happybudsbk.com/collections/all | Shopify (hemp) | confirmed | Site sells hemp-derived Delta-8/9 (<0.3% THC), not OCM adult-use cannabis — may be separate entity from OCM listing |
| 60 | Grams Cannabis | Williamsburg | RETL | gramsbk.com | https://gramsbk.com/menu | Wix | confirmed | static.wixstatic.com CDN |
| 61 | Pacha | Bushwick | CAURD | — | — | Telegram-only | confirmed | Menu distributed via Telegram referral; no public web menu |
| 62 | Take N' Toke | Prospect Heights | RETL | takentoke.com | https://takentoke.com/menu | Bud Authority | confirmed | Footer "Powered by Bud Authority" |
| 63 | Forever 420 | East New York | CAURD | forever420ny.com | https://forever420ny.com/shop | Custom (Prismic-backed) | confirmed | images.prismic.io CDN |
| 64 | Dagmar Cannabis Williamsburg | Williamsburg | RETL | dagmarcannabis.com | https://dutchie.com/dispensary/dagmar-cannabis-williamsburg | Dutchie | confirmed | Direct dutchie.com/dispensary/ listing |
| 65 | Erudito Cannabis Boutique | Columbia Waterfront | RETL | erudito.nyc | https://erudito.nyc/shop | Custom | inferred | No CDN signals; small standalone store |
| 66 | Cannalicious | Park Slope | RETL | cannaliciousnyc.com | https://cannaliciousnyc.com/menu | Carrot | confirmed | Footer "Powered by Carrot" + carrot-static CDN |
| 67 | Greene Street | Sheepshead Bay | RETL | gstnydispensary.com | https://dutchie.com/dispensary/green-street-brooklyn | Dutchie | confirmed | gstnydispensary.com is brochure-ware; menu is direct Dutchie listing |
| 68 | Society House | Marine Park | CAURD | societyhousebk.com | https://societyhousebk.com/shop/brooklyn | Tymber/BLAZE | inferred | URL pattern matches BLAZE convention |

## Platform Summary

| Platform | Count | Notes |
|---|---|---|
| Dutchie | ~20 | Dominant platform; many WP-embed installs with `dtche` URL params; direct fetches mostly 403 |
| Carrot | 5 | Fingerprint: `?locId=1` param + `carrot-static.ams3.cdn.digitaloceanspaces.com` CDN |
| Tymber/BLAZE | 5–6 | Fingerprint: `tymber-blaze-products.imgix.net` CDN |
| Dispense | 5 | Fingerprint: `dispense-images.imgix.net` or `menus.dispenseapp.com` |
| Alleaves | 1 | Brooklyn Organic Buds — reference instance |
| Sweedpos | 2 | Matawana, Flower Daddy — `media-prime.sweedpos.com` CDN |
| Shopify | 2 | Q Dispensary, Superbness |
| Weedmaps WM Store | 1 | Caffiend |
| Weedmaps-only | 1 | Twenty8Gramz (no own-domain menu) |
| SparkMenus | 1 | Green Apple |
| Bud Authority | 1 | Take N' Toke |
| Wix | 1 | Grams Cannabis |
| Custom (Leaflogix) | 1 | The Travel Agency |
| Custom (Range Marketing) | 1 | Puro Vita |
| Custom (Prismic) | 2 | The Gallery at Dumbo, Forever 420 |
| Custom (in-house) | 3–4 | The Flowery, Quality Roots, Beleaf, Brooklyn Bourne |
| WooCommerce | 1 | Rustik Smokes (inferred) |
| No online menu | 4 | Brooklyn Urban Dispensary (not open), Pacha (Telegram), Twenty8Gramz (Weedmaps only), Tiki Leaves (offline) |
| Unknown | 5 | Kushmart, Sunflower Cannabis, Elevated, The HiBrary Club, Erudito |

## Scraper Priority Order

1. **Dutchie** (~20 stores) — largest unit count; two patterns: `dutchie.com/dispensary/{slug}` or `shop.{brand}.com`
2. **Tymber/BLAZE** (~6) — predictable URL structure; `tymber-blaze-products.imgix.net` fingerprint
3. **Carrot** (5) — `?locId=1` + `carrot-static` CDN; consistent across all installs
4. **Dispense** (5) — `dispense-images.imgix.net` or external `menus.dispenseapp.com` links
5. **Sweedpos** (2) — Matawana + Flower Daddy
6. **Shopify** (2) — standard `/collections/all` pattern
7. **Per-platform singletons** — Alleaves (existing), Weedmaps WM Store, SparkMenus, Bud Authority, Wix
8. **Custom builds** — each needs a bespoke scraper

## Unresolved / Needs Follow-up

- **Kushmart** — no platform signals; needs headless browser network inspection
- **Sunflower Cannabis** — repeated timeouts; may be in-store only or site down
- **Happy Buds Brooklyn** — Dutchie listing at `dutchie.com/dispensary/happy-buds-brooklyn-dispensary` reported by user (bot-blocked, confirm in browser); current site `happybudsbk.com` sells hemp only
- **Elevated** — sparse web presence; verify license status with OCM
- **The HiBrary Club** — license confirmed (OCM-CAURD-25-000321) but no website found
