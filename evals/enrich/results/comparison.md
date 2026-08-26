# Enrich model comparison

Models: deepseek-pro-0813


## gold_dispensary — gold_coney_island.json

_Hand-labeled gold set: all 56 unique listings from Coney Island Cannabis (Dutchie GraphQL). Every description is EMPTY, so the model must work from the name alone — no pack counts or per-piece doses to read. The scraped variant column is actively wrong for edibles ('.1g', '0.001g' for a 100mg gummy), so a correct answer means overriding the hint rather than trusting it. Its 'other' bucket holds PRE-ROLLS — a third meaning of 'other' across the three stores. Also covers version suffixes ('Gorilla Glue #4'), a strain containing a format word that must survive ('Chocolate Haze'), and a source typo to preserve ('Dirty Sherley')._

| case | expected | deepseek-pro-0813 |
|---|---|---|
| coney-000-ayrloom-cran-haze-aio-1g | category=vaporizers, subtype=all-in-one, strain=Cran Haze, variant=1g | ✓ |
| coney-001-ayrloom-honeycrisp-aio-1g | category=vaporizers, subtype=all-in-one, strain=Honeycrisp, variant=1g | ✓ |
| coney-002-ayrloom-lime-haze-aio-1g | category=vaporizers, subtype=all-in-one, strain=Lime Haze, variant=1g | ✓ |
| coney-003-ayrloom-mood-energy-aio-1g-thc-thcv-cbg | category=vaporizers, subtype=all-in-one, variant=1g | ✓ |
| coney-004-camino-sours-balance-orchard-peach-gummi | category=edible, subtype=gummy, strain=Orchard Peach, product_line=Balance, variant=100mg | ✗ product_line: None→want 'Balance' |
| coney-005-camino-midnight-blueberry-5-1-sleep-gumm | category=edible, subtype=gummy, strain=Midnight Blueberry, product_line=Sleep | ✗ product_line: None→want 'Sleep' |
| coney-006-camino-pineapple-habanero-gummies-100mg- | category=edible, subtype=gummy, strain=Pineapple Habanero, variant=100mg | ✓ |
| coney-007-camino-watermelon-lemonade-bliss-gummies | category=edible, subtype=gummy, strain=Watermelon Lemonade, product_line=Bliss | ✗ product_line: None→want 'Bliss' |
| coney-008-camino-wild-berry-chill-gummies-20pk | category=edible, subtype=gummy, strain=Wild Berry, product_line=Chill | ✗ product_line: None→want 'Chill' |
| coney-009-camino-wild-cherry-excite-gummies-20pk | category=edible, subtype=gummy, strain=Wild Cherry, product_line=Excite | ✗ product_line: None→want 'Excite' |
| coney-010-chicken-n-waffle-flower-mixed-buds | category=flower, strain=Chicken N Waffle, variant=7g | ✓ |
| coney-011-dr-jekyll-and-mr-high-chem-dog | category=flower, subtype=flower, strain=Chem Dog, variant=3.5g | ✓ |
| coney-012-dr-jekyll-and-mr-high-do-si-do-flower | category=flower, subtype=flower, strain=Do-Si-Do, variant=3.5g | ✓ |
| coney-013-dr-jekyll-and-mr-high-gelato | category=flower, subtype=flower, strain=Gelato, variant=3.5g | ✓ |
| coney-014-dr-jekyll-and-mr-high-girl-scout-cookies | category=flower, subtype=flower, strain=Girl Scout Cookies, variant=3.5g | ✓ |
| coney-015-dr-jekyll-and-mr-high-mango-kush | category=flower, subtype=flower, strain=Mango Kush, variant=3.5g | ✓ |
| coney-016-dr-jekyll-and-mr-high-white-widow | category=flower, subtype=flower, strain=White Widow, variant=3.5g | ✓ |
| coney-017-fernway-berry-haze-510-cart | category=vaporizers, subtype=cart, strain=Berry Haze, variant=1g | ✓ |
| coney-018-herb-chocolate-haze-flower | category=flower, subtype=flower, strain=Chocolate Haze, variant=3.5g | ✓ |
| coney-019-herb-runtz-flower | category=flower, subtype=flower, strain=Runtz, variant=14g | ✓ |
| coney-020-herb-sour-og-flower | category=flower, subtype=flower, strain=Sour OG, variant=3.5g | ✓ |
| coney-021-maui-mac-nut-infused-pre-roll | category=preroll, subtype=infused, strain=Maui Mac Nut, variant=1g | ✓ |
| coney-022-moods-banana-diesel-aio | category=vaporizers, subtype=all-in-one, strain=Banana Diesel, variant=1g | ✓ |
| coney-023-moods-cream-cheese-zushi-aio | category=vaporizers, subtype=all-in-one, strain=Cream Cheese Zushi, variant=1g | ✓ |
| coney-024-moods-ny-minute-mini-aio | category=vaporizers, subtype=all-in-one, variant=1g | ✓ |
| coney-025-moods-wedding-cake-aio | category=vaporizers, subtype=all-in-one, strain=Wedding Cake, variant=1g | ✓ |
| coney-026-moony-s-zooties-biscotti-pre-roll-2pk | category=preroll, subtype=pack, strain=Biscotti, variant=1g | ✓ |
| coney-027-moony-s-zooties-vanilla-frosting-pre-rol | category=preroll, subtype=infused, strain=Vanilla Frosting, variant=0.5g | ✓ |
| coney-028-nanticoke-mac-nilla-infused-pre-roll | category=preroll, subtype=infused, strain=Mac Nilla, variant=1g | ✓ |
| coney-029-preload-starter-kit-1g-fusion-sour-apple | category=vaporizers, strain=Sour Appleicious, variant=1g | ✓ |
| coney-030-rec-roots-super-candy | category=flower, subtype=flower, strain=Super Candy, variant=3.5g | ✓ |
| coney-031-rezziano | category=flower, subtype=flower, strain=Rezziano, variant=14g | ✓ |
| coney-032-smartbud-motorhead-flower | category=flower, subtype=flower, strain=Motorhead, variant=3.5g | ✓ |
| coney-033-smoakland-durban-poison-flower | category=flower, subtype=flower, strain=Durban Poison, variant=28g | ✓ |
| coney-034-smoothie-bar-lava-cake-x-sour-diesel-dua | category=vaporizers, subtype=all-in-one, strain=Lava Cake x Sour Diesel, variant=2g | ✓ |
| coney-035-smoothie-bar-mimosa-x-dirty-sherley-dual | category=vaporizers, subtype=all-in-one, strain=Mimosa x Dirty Sherley, variant=2g | ✓ |
| coney-036-smoothie-bar-papaya-x-lemonade-dual-cham | category=vaporizers, subtype=all-in-one, strain=Papaya x Lemonade, variant=2g | ✓ |
| coney-037-smoothie-bar-sour-lemon-og-x-pineapple-j | category=vaporizers, subtype=all-in-one, strain=Sour Lemon OG x Pineapple Jack, variant=2g | ✓ |
| coney-038-toke-blueberry-glue-pre-roll | category=preroll, subtype=single, strain=Blueberry Glue, variant=0.5g | ✓ |
| coney-039-toke-quatro-killa-pre-roll | category=preroll, subtype=single, strain=Quatro Killa, variant=0.5g | ✓ |
| coney-040-vacation-blue-raspberry-aio | category=vaporizers, subtype=all-in-one, strain=Blue Raspberry, variant=1g | ✓ |
| coney-041-vacation-blue-raspberry-hash-rosin-gummi | category=edible, subtype=gummy, strain=Blue Raspberry, variant=100mg | ✓ |
| coney-042-vacation-gorilla-glue-4-flower | category=flower, subtype=flower, strain=Gorilla Glue #4, variant=3.5g | ✓ |
| coney-043-vacation-gorilla-glue-4-pre-roll-10pk | category=preroll, subtype=pack, strain=Gorilla Glue #4, variant=3.5g | ✓ |
| coney-044-vacation-memory-loss-og-flower | category=flower, subtype=flower, strain=Memory Loss OG, variant=3.5g | ✓ |
| coney-045-vacation-memory-loss-og-pre-roll-10pk | category=preroll, subtype=pack, strain=Memory Loss OG, variant=3.5g | ✓ |
| coney-046-vacation-peach-rings-hash-rosin-gummies- | category=edible, subtype=gummy, strain=Peach Rings, variant=100mg | ✓ |
| coney-047-vacation-pineapple-coconut-aio | category=vaporizers, subtype=all-in-one, strain=Pineapple Coconut, variant=1g | ✓ |
| coney-048-vacation-pineapple-coconut-hash-rosin-gu | category=edible, subtype=gummy, strain=Pineapple Coconut, variant=100mg | ✓ |
| coney-049-vacation-sour-fuel-flower | category=flower, subtype=flower, strain=Sour Fuel, variant=3.5g | ✓ |
| coney-050-vacation-sour-fuel-pre-roll-10pk | category=preroll, subtype=pack, strain=Sour Fuel, variant=3.5g | ✓ |
| coney-051-vacation-tiki-fruit-punch-aio | category=vaporizers, subtype=all-in-one, strain=Tiki Fruit Punch, variant=1g | ✓ |
| coney-052-vacation-tiki-fruit-punch-hash-rosin-gum | category=edible, subtype=gummy, strain=Tiki Fruit Punch, variant=100mg | ✓ |
| coney-053-ayrloom-low-dose-everyday-drops-150mg-th | category=tinctures, subtype=tincture, variant=150mg | ✓ |
| coney-054-ayrloom-rescue-1-1-topical-1000mg-thc-10 | category=topical, subtype=topical, strain=Rescue, variant=1000mg | ✗ variant: '1g'→want '1000mg' |
| coney-055-ayrloom-revive-1-1-topical-1000mg-thc-10 | category=topical, subtype=topical, strain=Revive, variant=1000mg | ✗ variant: '1g'→want '1000mg' |

## identity_cluster — gold_cross_dispensary.json

_CROSS-DISPENSARY identity clusters built from real rows in six store snapshots. Each case is the SAME physical product as listed by different stores, whose naming conventions disagree on everything: brand first vs last vs absent, lineage and THC% inline, shelf codes appended, and three different meanings of the 'other' category. Enrichment must land every member on one identity tuple — this is the products view's 'same product -> same key' contract, and the only test here that measures what a wrong answer actually costs: a split product group. x-ayrloom-honeycrisp-beverage and x-ayrloom-honeycrisp-vape are a matched pair: the same brand and strain in two formats, which must converge WITHIN each cluster without merging ACROSS them. Clusters carry a partial `canonical` where the sources genuinely disagree on the right value (dose vs volume), so they score convergence without asserting a spelling the data does not settle._

| group | canonical | deepseek-pro-0813 |
|---|---|---|
| x-ayrloom-revive-balm | category=topical, subtype=topical, strain=Revive | ✗ split: strain=[|Revive] |
| x-camino-watermelon-lemonade-bliss | category=edible, subtype=gummy, strain=Watermelon Lemonade, variant=100mg | ✗ split: variant=[100mg|72mg] |
| x-jaunty-mango-haze-aio | category=vaporizers, subtype=all-in-one, strain=Mango Haze, variant=1.5g | ~ converged, off-canonical (strain) |
| x-ayrloom-honeycrisp-beverage | category=edible, subtype=beverage | ✓ converged + canonical |
| x-ayrloom-honeycrisp-vape | category=vaporizers, subtype=all-in-one, strain=Honeycrisp, variant=1g | ~ converged, off-canonical (strain) |
| x-papa-barkley-releaf-balm | category=topical, subtype=topical | ✓ converged + canonical |

## gold_dispensary — gold_hold_up_roll_up.json

_Hand-labeled gold set: 48 real listings from Hold Up Roll Up (Tymber). The hardest naming convention of the three: the brand NEVER appears in the product name (names are bare "Strain - Size Format"), so brand-anchored reasoning has nothing to grip. 64% of its menu maps to 'other', holding flower, pre-rolls, vapes and pods all at once, so almost every case is a category-override test. Includes a name/variant-field conflict ("Runtz - 28G Flower" whose variant column says 1/8 oz), a source spelling to preserve ("Chem Dawg"), and null-strain merch whose name carries a flavor ("Peaches N Cream ... Rolling Papers")._

| case | expected | deepseek-pro-0813 |
|---|---|---|
| holdup-000-cereal-milk-x-banana-mochi-1-5g-2pk-full | category=preroll, strain=Cereal Milk x Banana Mochi, variant=1.5g | ✓ |
| holdup-001-blue-razz-lemonade-1g-botanica-blend-pod | category=vaporizers, subtype=pod, strain=Blue Razz Lemonade, variant=1g | ✓ |
| holdup-002-runtz-28g-flower | category=flower, subtype=flower, strain=Runtz, variant=28g | ✓ |
| holdup-003-nyc-vapor-3-5g-flower | category=flower, subtype=flower, strain=NYC Vapor, variant=3.5g | ✓ |
| holdup-004-bubba-kush-14g-infused-pre-ground-flower | category=flower, strain=Bubba Kush, variant=14g | ✓ |
| holdup-005-watermelon-og-1g-live-resin-aio-disposab | category=vaporizers, subtype=all-in-one, strain=Watermelon OG, variant=1g | ✓ |
| holdup-006-blackberry-kush-2g-starter-kit | category=vaporizers, strain=Blackberry Kush, variant=2g | ✓ |
| holdup-007-blue-oreos-1g-ice-water-hash-pre-roll | category=preroll, subtype=infused, strain=Blue Oreos, variant=1g | ✓ |
| holdup-008-gorilla-glue-1g-aio-vape | category=vaporizers, subtype=all-in-one, strain=Gorilla Glue, variant=1g | ✓ |
| holdup-009-heir-heads-1g-live-resin-510-vape | category=vaporizers, subtype=cart, strain=Heir Heads, variant=1g | ✓ |
| holdup-010-blue-dream-4g-aio-vape | category=vaporizers, subtype=all-in-one, strain=Blue Dream, variant=4g | ✓ |
| holdup-011-moonbeam-gelato-7g-flower-smalls | category=flower, subtype=smalls, strain=Moonbeam Gelato, variant=7g | ✓ |
| holdup-012-sour-apple-glue-1g-ice-water-hash-pre-ro | category=preroll, subtype=infused, strain=Sour Apple Glue, variant=1g | ✗ strain: ''→want 'Sour Apple Glue' |
| holdup-013-king-louis-xiii-0-5g-pod | category=vaporizers, subtype=pod, strain=King Louis XIII, variant=0.5g | ✗ strain: ''→want 'King Louis XIII' |
| holdup-014-northern-lights-10pk-live-resin-infused- | category=preroll, strain=Northern Lights, variant=3.5g | ✗ strain: ''→want 'Northern Lights' |
| holdup-015-northern-lights-2g-infused-preroll | category=preroll, subtype=infused, strain=Northern Lights, variant=2g | ✗ strain: ''→want 'Northern Lights' |
| holdup-016-lemon-lavender-serenity-50mg-gummies | category=edible, subtype=gummy, strain=Lemon Lavender, variant=50mg | ✗ strain: ''→want 'Lemon Lavender' |
| holdup-017-blue-razzleberry-mega-100mg-gummy | category=edible, subtype=gummy, strain=Blue Razzleberry Mega, variant=100mg | ✗ strain: ''→want 'Blue Razzleberry Mega' |
| holdup-018-nordic-blueberry-100mg-gummies | category=edible, subtype=gummy, strain=Nordic Blueberry, variant=100mg | ✗ strain: ''→want 'Nordic Blueberry' |
| holdup-019-cookies-n-cream-cones-100mg-ice-cream-co | category=edible, strain=Cookies N Cream, variant=100mg | ✗ strain: ''→want 'Cookies N Cream' |
| holdup-020-pineapple-float-100mg-20pk-gummies | category=edible, subtype=gummy, strain=Pineapple Float, variant=100mg | ✗ strain: ''→want 'Pineapple Float' |
| holdup-021-black-cherry-sparkling-water-5mg | category=edible, subtype=beverage, strain=Black Cherry, variant=5mg | ✗ strain: ''→want 'Black Cherry' |
| holdup-022-sour-blue-raspberry-lemonade-100mg-multi | category=edible, subtype=gummy, strain=Sour Blue Raspberry Lemonade, variant=100mg | ✗ strain: ''→want 'Sour Blue Raspberry Lemonade' |
| holdup-023-wake-and-bake-yaupon-and-mint-10mg-tea-s | category=edible, subtype=beverage, variant=50mg | ✗ variant: '10mg'→want '50mg' |
| holdup-024-mega-dose-cherry-rings-100mg-gummy | category=edible, subtype=gummy, variant=100mg | ✓ |
| holdup-025-midnight-mango-1-1-1-thc-cbd-cbn-20pk-sl | category=edible, subtype=gummy, strain=Midnight Mango | ✗ strain: ''→want 'Midnight Mango' |
| holdup-026-donny-burger-1g-preroll | category=preroll, subtype=single, strain=Donny Burger, variant=1g | ✗ strain: ''→want 'Donny Burger' |
| holdup-027-platinum-life-breath-1g-preroll | category=preroll, subtype=single, strain=Platinum Life Breath, variant=1g | ✗ strain: ''→want 'Platinum Life Breath' |
| holdup-028-shock-bloom-x-pinnacle-3-3-5g-7pk-prerol | category=preroll, subtype=pack, strain=Shock Bloom x Pinnacle 3, variant=3.5g | ✗ strain: ''→want 'Shock Bloom x Pinnacle 3' |
| holdup-029-lilac-diesel-8pk-preroll | category=preroll, subtype=pack, strain=Lilac Diesel, variant=4g | ✗ strain: ''→want 'Lilac Diesel' |
| holdup-030-blue-lobster-1g-pre-roll | category=preroll, subtype=single, strain=Blue Lobster, variant=1g | ✗ strain: ''→want 'Blue Lobster' |
| holdup-031-animal-face-5pk-pre-rolls | category=preroll, subtype=pack, strain=Animal Face, variant=1.75g | ✗ strain: ''→want 'Animal Face' |
| holdup-032-citronella-1g-preroll | category=preroll, subtype=single, strain=Citronella, variant=1g | ✗ strain: ''→want 'Citronella' |
| holdup-033-empire-state-cake-0-5g-6pk-perolls | category=preroll, subtype=pack, strain=Empire State Cake, variant=3g | ✗ strain: ''→want 'Empire State Cake' |
| holdup-034-silly-nice-bubble-hash-1g | category=concentrate, subtype=hash, strain=None, variant=1g | ✓ |
| holdup-035-chem-dawg-1g-cured-resin-crumble | category=concentrate, subtype=resin, strain=Chem Dawg, variant=1g | ✗ strain: ''→want 'Chem Dawg' |
| holdup-036-burnout-cookies-1g-crumble | category=concentrate, strain=Burnout Cookies, variant=1g | ✗ strain: ''→want 'Burnout Cookies' |
| holdup-037-biscotti-1g-cured-resin-budder | category=concentrate, subtype=resin, strain=Biscotti, variant=1g | ✗ strain: ''→want 'Biscotti' |
| holdup-038-blue-cookies-1g-badder | category=concentrate, strain=Blue Cookies, variant=1g | ✗ strain: ''→want 'Blue Cookies' |
| holdup-039-mk-lighter-cultivate-series-jet-pocket-l | category=merch, subtype=merch, strain=None | ✓ |
| holdup-040-peaches-n-cream-juicy-jay-s-flavored-rol | category=merch, subtype=merch, strain=None | ✓ |
| holdup-041-black-510-thread-stick-battery | category=merch, subtype=merch, strain=None | ✗ category: 'vaporizers'→want 'merch'; subtype: 'battery'→want 'merch' |
| holdup-042-dab-tool | category=merch, subtype=merch, strain=None | ✓ |
| holdup-043-organic-medium-dog-cbd-oil-600mg-tinctur | category=tinctures, subtype=tincture, strain=None, variant=600mg | ✓ |
| holdup-044-pillow-talk-sleep-drops-300mg-thc-1500mg | category=tinctures, subtype=tincture, strain=Pillow Talk, variant=300mg | ✗ strain: ''→want 'Pillow Talk'; variant: '1800mg'→want '300mg' |
| holdup-045-unflavored-beverage-enhancer-300mg-thc-t | category=tinctures, subtype=tincture, variant=300mg | ✓ |
| holdup-046-unscented-cbd-lotion-300mg | category=topical, subtype=topical, strain=None, variant=300mg | ✓ |
| holdup-047-on-heat-relief-muscle-spray-300mg | category=topical, subtype=topical, variant=300mg | ✓ |

## gold_dispensary — gold_the_plug.json

_Hand-labeled gold set: 108 real listings from The Plug (Crown Heights), stratified across categories, incl. the 'other' bucket the scraper's CATEGORY_MAP missed (mostly vapes — tests hint override), pack-math edibles, typo strains that must be kept verbatim (Red Zprite, Marakesh), product lines (UP, Flyers, Noir, Quicks, Releaf), and null-strain merch/topicals. Ambiguous fields are omitted from expect on purpose. Rulings: beverages are dosed in mg not volume; topical scent names ARE strains; version suffixes (2.0) are kept; concentrate 'diamonds' is its own subtype._

| case | expected | deepseek-pro-0813 |
|---|---|---|
| gold-000-off-hours-razz-lemonade-live-resin-rope | category=edible, subtype=gummy, strain=Razz Lemonade | ✗ strain: ''→want 'Razz Lemonade' |
| gold-001-ayrloom-up-12oz-beverage-honeycrisp-5mg-1-1- | category=edible, subtype=beverage, strain=Honeycrisp, variant=5mg, product_line=UP | ✗ strain: ''→want 'Honeycrisp' |
| gold-002-ayrloom-up-12oz-beverage-lemonade | category=edible, subtype=beverage, strain=Lemonade, product_line=UP | ✗ strain: ''→want 'Lemonade' |
| gold-003-old-pal-x-babish-thc-infused-sugar-100mg | category=edible, subtype=other, variant=100mg, strain=None | ✓ |
| gold-004-wyld-kiwi-1-1-thc-thcv | category=edible, subtype=gummy, strain=Kiwi | ✗ strain: ''→want 'Kiwi' |
| gold-005-florist-farms-peach-gummies-20mg-x-2pk-1-1-t | category=edible, subtype=gummy, strain=Peach, variant=40mg | ✗ strain: ''→want 'Peach' |
| gold-006-camino-sleep-midnight-blueberry-5-1-cbn-20pk | category=edible, subtype=gummy, strain=Midnight Blueberry, variant=100mg | ✗ strain: ''→want 'Midnight Blueberry' |
| gold-007-foy-strawberry-nighttime-1-1-1-chews | category=edible, subtype=gummy | ✓ |
| gold-008-myhi-boisterous-berry-3-x-10mg-thc-stir-stik | category=edible, subtype=beverage, strain=Boisterous Berry, variant=30mg | ✗ strain: ''→want 'Boisterous Berry' |
| gold-009-mfny-live-resin-gummies-creamsicle-x-rainbow | category=edible, subtype=gummy, strain=Creamsicle x Rainbow Beltz 2.0 | ✗ strain: ''→want 'Creamsicle x Rainbow Beltz 2.0' |
| gold-010-revert-grape-100mg-scored-gummy | category=edible, subtype=gummy, strain=Grape, variant=100mg | ✗ strain: ''→want 'Grape' |
| gold-011-myhi-simply-flavorless-3-x-10mg-thc-stir-sti | category=edible, subtype=beverage, strain=Simply Flavorless, variant=30mg | ✗ strain: ''→want 'Simply Flavorless' |
| gold-012-kushy-punch-blue-raspberry-gummies-100mg | category=edible, subtype=gummy, strain=Blue Raspberry | ✗ strain: ''→want 'Blue Raspberry' |
| gold-013-gr-n-baja-blaze-mega | category=edible, subtype=gummy, strain=Baja Blaze Mega | ✗ strain: ''→want 'Baja Blaze Mega' |
| gold-014-wana-fast-asleep-5-1-1-1-dream-berry | category=edible, subtype=gummy, strain=Dream Berry | ✗ strain: ''→want 'Dream Berry' |
| gold-015-eaton-botanicals-apple-a-day-apple-2-5mg-gum | category=edible, subtype=gummy, strain=Apple-A-Day | ✗ strain: ''→want 'Apple-A-Day' |
| gold-016-gr-n-milk-chocolate-mini-bar-daytime-sativa- | category=edible, subtype=chocolate, variant=100mg | ✗ variant: '7g'→want '100mg' |
| gold-017-ayrloom-up-12oz-beverage-pineapple-mango | category=edible, subtype=beverage, strain=Pineapple Mango, product_line=UP | ✗ strain: ''→want 'Pineapple Mango' |
| gold-018-camino-balance-yuzu-lemon-100mg-20pk | category=edible, subtype=gummy, strain=Yuzu Lemon, variant=100mg | ✗ strain: ''→want 'Yuzu Lemon' |
| gold-019-ayrloom-10-mg-thc-5mg-thcv-gummies-sol-burst | category=edible, subtype=gummy, strain=Sol Burst | ✗ strain: ''→want 'Sol Burst' |
| gold-020-camino-recover-freshly-squeezed-1-2-cbg-20pk | category=edible, subtype=gummy, strain=Freshly Squeezed, variant=100mg | ✗ strain: ''→want 'Freshly Squeezed' |
| gold-021-camino-chews-pineapple-paradise-1-1-thc-cbc- | category=edible, subtype=gummy, strain=Pineapple Paradise, variant=100mg | ✗ strain: ''→want 'Pineapple Paradise'; variant: '46g'→want '100mg' |
| gold-022-gr-n-milk-chocolate-full-bar-sativa | category=edible, subtype=chocolate, strain=Sativa | ✗ strain: ''→want 'Sativa' |
| gold-023-hashtag-honey-tropical-punch-live-resin-gumm | category=edible, subtype=gummy, strain=Tropical Punch, variant=100mg | ✗ strain: ''→want 'Tropical Punch'; variant: '50.2g'→want '100mg' |
| gold-024-purple-punch-infused-5pk-0-5g-pre-rolls | category=preroll, strain=Purple Punch, variant=2.5g | ✗ strain: ''→want 'Purple Punch' |
| gold-025-aphrodite-vanilla-gelato-foam-tip-pre-roll-5 | category=preroll, subtype=pack, strain=Vanilla Gelato, variant=2.5g | ✗ strain: ''→want 'Vanilla Gelato' |
| gold-026-jaunty-stay-puft-x-strawberry-meltz-1g-hash- | category=preroll, subtype=infused, strain=Stay Puft x Strawberry Meltz, variant=1g | ✗ strain: ''→want 'Stay Puft x Strawberry Meltz' |
| gold-027-budd-lemon-cherry-gelato-1g-pre-roll | category=preroll, subtype=single, strain=Lemon Cherry Gelato, variant=1g | ✗ strain: ''→want 'Lemon Cherry Gelato' |
| gold-028-claybourne-co-strawberry-cough-flyers-infuse | category=preroll, subtype=infused, strain=Strawberry Cough, product_line=Flyers, variant=1.5g | ✗ strain: ''→want 'Strawberry Cough' |
| gold-029-claybourne-co-king-louis-og-diamond-frosted- | category=preroll, strain=King Louis OG, variant=2.5g | ✗ strain: ''→want 'King Louis OG' |
| gold-030-the-plug-pack-tequila-sunrise-1g-preroll | category=preroll, subtype=single, strain=Tequila Sunrise, variant=1g | ✗ subtype: 'pack'→want 'single'; strain: ''→want 'Tequila Sunrise' |
| gold-031-nanticoke-coconut-cream-1g-infused-pre-roll | category=preroll, subtype=infused, strain=Coconut Cream, variant=1g | ✗ strain: ''→want 'Coconut Cream' |
| gold-032-lowell-smokes-quicks-afternoon-delight-0-35g | category=preroll, subtype=pack, strain=Afternoon Delight, product_line=Quicks, variant=3.5g | ✗ strain: ''→want 'Afternoon Delight' |
| gold-033-claybourne-co-banana-og-flyers-infused-1-5g- | category=preroll, subtype=infused, strain=Banana OG, product_line=Flyers, variant=1.5g | ✗ strain: ''→want 'Banana OG' |
| gold-034-ruby-farms-classics-7pk-pre-rolls-trop-cherr | category=preroll, subtype=pack, strain=Trop Cherry, variant=5g | ✗ strain: ''→want 'Trop Cherry' |
| gold-035-boutiq-snack-pack-cherry-lime-x-rz-11-5-x-05 | category=preroll, strain=Cherry Lime x RZ-11, variant=2.5g | ✗ strain: ''→want 'Cherry Lime x RZ-11' |
| gold-036-ruby-farms-hash-infused-blueberry-dj-cut-2pk | category=preroll, subtype=infused, strain=Blueberry DJ Cut, variant=1g | ✗ strain: ''→want 'Blueberry DJ Cut' |
| gold-037-florist-farms-mule-fuel-1g-live-resin-infuse | category=preroll, subtype=infused, strain=Mule Fuel, variant=1g | ✗ strain: ''→want 'Mule Fuel' |
| gold-038-claybourne-co-fast-lane-sativa-flyers-blends | category=preroll, variant=3.5g | ✓ |
| gold-039-alibi-dream-star-cherry-diesel-4g-variety-pr | category=preroll, subtype=pack, variant=4g | ✓ |
| gold-040-eaton-botanicals-little-pandas-tropical-cool | category=preroll, subtype=pack, variant=1.75g, product_line=Little Pandas | ✓ |
| gold-041-jetpacks-fj-mini-0-6g-infused-preroll-strawb | category=preroll, subtype=infused, strain=Strawberry Sour Diesel, variant=0.6g | ✗ strain: ''→want 'Strawberry Sour Diesel' |
| gold-042-smoke-wrld-mochi-runtz-3-5g-flower | category=flower, subtype=flower, strain=Mochi Runtz, variant=3.5g | ✗ strain: ''→want 'Mochi Runtz' |
| gold-043-the-plug-pack-sapphire-haze-28g-flower | category=flower, subtype=flower, strain=Sapphire Haze, variant=28g | ✗ strain: ''→want 'Sapphire Haze' |
| gold-044-umamii-ice-cream-cake-3-5g-flower | category=flower, subtype=flower, strain=Ice Cream Cake, variant=3.5g | ✗ strain: ''→want 'Ice Cream Cake' |
| gold-045-revert-crumble-cake-3-5g-flower | category=flower, subtype=flower, strain=Crumble Cake, variant=3.5g | ✗ strain: ''→want 'Crumble Cake' |
| gold-046-alchemy-pure-space-panda-0-7g-flower-bag | category=flower, subtype=flower, strain=Space Panda, variant=0.7g | ✗ strain: ''→want 'Space Panda' |
| gold-047-ttm-essentials-northern-lights-3-5g-flower-b | category=flower, subtype=flower, strain=Northern Lights, variant=3.5g | ✗ strain: ''→want 'Northern Lights' |
| gold-048-smoke-wrld-red-zprite-3-5g | category=flower, subtype=flower, strain=Red Zprite, variant=3.5g | ✗ strain: ''→want 'Red Zprite' |
| gold-049-budd-lemon-cherry-gelato-3-5g-premium-smalls | category=flower, subtype=smalls, strain=Lemon Cherry Gelato, variant=3.5g | ✗ strain: ''→want 'Lemon Cherry Gelato' |
| gold-050-kickfly-s-blackscotti-14g-flower | category=flower, subtype=flower, strain=Blackscotti, variant=14g | ✗ strain: ''→want 'Blackscotti' |
| gold-051-leal-chronic-tonic-3-5g | category=flower, subtype=flower, strain=Chronic Tonic, variant=3.5g | ✗ strain: ''→want 'Chronic Tonic' |
| gold-052-the-botanist-gsc-3-5g-flower | category=flower, subtype=flower, strain=GSC, variant=3.5g | ✗ strain: ''→want 'GSC' |
| gold-053-untitled-sour-diesel-7g | category=flower, subtype=flower, strain=Sour Diesel, variant=7g | ✗ strain: ''→want 'Sour Diesel' |
| gold-054-revert-golden-pineapple-14g-flower | category=flower, subtype=flower, strain=Golden Pineapple, variant=14g | ✓ |
| gold-055-noizey-ny-super-glue-4g-flower | category=flower, subtype=flower, strain=NY Super Glue, variant=4g | ✓ |
| gold-056-smoakland-tropical-haze-28g-flower | category=flower, subtype=flower, strain=Tropical Haze, variant=28g | ✓ |
| gold-057-matter-grape-gas-3-5g-flower | category=flower, subtype=flower, strain=Grape Gas, variant=3.5g | ✓ |
| gold-058-gypsy-weed-kombucha-oreo-28g | category=flower, subtype=flower, strain=Kombucha Oreo, variant=28g | ✓ |
| gold-059-munchkins-trop-cherry-3-5g-small-buds | category=flower, subtype=smalls, strain=Trop Cherry, variant=3.5g | ✓ |
| gold-060-blends-by-basin-fruity-pebbles-1g-cart | category=vaporizers, subtype=cart, strain=Fruity Pebbles, variant=1g | ✓ |
| gold-061-select-flavor-series-grape-ape-1g-briq-v2 | category=vaporizers, strain=Grape Ape, variant=1g | ✓ |
| gold-062-timeless-t2-blue-dream-chill-2g-rechargeable | category=vaporizers, strain=Blue Dream, variant=2g | ✓ |
| gold-063-florist-farms-durban-poison-1g-cart | category=vaporizers, subtype=cart, strain=Durban Poison, variant=1g | ✓ |
| gold-064-select-ace-terpologist-durban-fizz-1g-cart | category=vaporizers, subtype=cart, strain=Durban Fizz, variant=1g | ✓ |
| gold-065-jetty-el-chiveoz-1g-solventless-live-rosin-a | category=vaporizers, subtype=all-in-one, strain=El Chiveoz, variant=1g | ✓ |
| gold-066-jaunty-mango-haze-1-5g-aio | category=vaporizers, subtype=all-in-one, strain=Mango Haze, variant=1.5g | ✓ |
| gold-067-timeless-t1-new-york-sour-diesel-1g-recharga | category=vaporizers, strain=New York Sour Diesel, variant=1g | ✓ |
| gold-068-toast-royal-rntz-7g-infused-pre-ground-hybri | category=flower, strain=Royal Rntz, variant=7g | ✓ |
| gold-069-jaunty-sugar-cookie-1-5g-all-in-one-palm | category=vaporizers, subtype=all-in-one, strain=Sugar Cookie, variant=1.5g | ✓ |
| gold-070-timeless-noir-707-headband-live-resin-1g-vap | category=vaporizers, subtype=cart, strain=707 Headband, product_line=Noir, variant=1g | ✓ |
| gold-071-the-plug-pack-lemon-berry-kush-28g-infused-p | category=flower, strain=Lemon Berry Kush, variant=28g | ✓ |
| gold-072-ayrloom-0-5g-disposable-lychee-dream | category=vaporizers, subtype=all-in-one, strain=Lychee Dream, variant=0.5g | ✓ |
| gold-073-ayrloom-0-5g-disposable-blue-widow | category=vaporizers, subtype=all-in-one, strain=Blue Widow, variant=0.5g | ✓ |
| gold-074-timeless-noir-panamango-live-resin-1g-vape-c | category=vaporizers, subtype=cart, strain=Panamango, product_line=Noir, variant=1g | ✓ |
| gold-075-mfny-0-5g-live-resin-dispo-gelonade | category=vaporizers, subtype=all-in-one, strain=Gelonade, variant=0.5g | ✓ |
| gold-076-kushy-punch-pineapple-jealousy-1g-510-thread | category=vaporizers, subtype=cart, strain=Pineapple Jealousy, variant=1g | ✓ |
| gold-077-doja-zoap-1g-aio-live-resin | category=vaporizers, subtype=all-in-one, strain=Zoap, variant=1g | ✓ |
| gold-078-jaunty-strawnana-1-5g-aio | category=vaporizers, subtype=all-in-one, strain=Strawnana, variant=1.5g | ✓ |
| gold-079-mfny-0-5g-live-resin-dispo-honey-banana | category=vaporizers, subtype=all-in-one, strain=Honey Banana, variant=0.5g | ✓ |
| gold-080-ayrloom-rest-1g-disposable | category=vaporizers, subtype=all-in-one, variant=1g | ✓ |
| gold-081-revert-galactic-jack-14g-kief-infused-ground | category=flower, strain=Galactic Jack, variant=14g | ✓ |
| gold-082-stiiizy-blue-burst-1g-disposable | category=vaporizers, subtype=all-in-one, strain=Blue Burst, variant=1g | ✓ |
| gold-083-stiiizy-premium-jack-5g-pod | category=vaporizers, subtype=pod, strain=Premium Jack, variant=0.5g | ✓ |
| gold-084-jetpacks-donny-burger-1g-indica-diamonds | category=concentrate, subtype=diamonds, strain=Donny Burger, variant=1g | ✗ strain: ''→want 'Donny Burger' |
| gold-085-jetty-gdp-1g-concentrate-dablicator | category=concentrate, strain=GDP, variant=1g | ✗ strain: ''→want 'GDP' |
| gold-086-jetpacks-panama-punch-1g-sativa-diamonds | category=concentrate, subtype=diamonds, strain=Panama Punch, variant=1g | ✗ strain: ''→want 'Panama Punch' |
| gold-087-blotter-runtz-mintz-1g-live-resin-sugar | category=concentrate, subtype=resin, strain=Runtz Mintz, variant=1g | ✗ strain: ''→want 'Runtz Mintz' |
| gold-088-mfny-chemdog-2g-live-resin-badder | category=concentrate, subtype=resin, strain=Chemdog, variant=2g | ✗ strain: ''→want 'Chemdog' |
| gold-089-jetpacks-cherry-limeade-1g-sativa-badder | category=concentrate, strain=Cherry Limeade, variant=1g | ✗ strain: ''→want 'Cherry Limeade' |
| gold-090-alchemy-pure-marakesh-1g-live-rosin | category=concentrate, subtype=rosin, strain=Marakesh, variant=1g | ✗ strain: ''→want 'Marakesh' |
| gold-091-mind-melters-permanent-marker-1g-cold-cure-l | category=concentrate, subtype=rosin, strain=Permanent Marker, variant=1g | ✗ strain: ''→want 'Permanent Marker' |
| gold-092-hashtag-honey-chocolate-diesel-1g-live-sugar | category=concentrate, strain=Chocolate Diesel, variant=1g | ✗ strain: ''→want 'Chocolate Diesel' |
| gold-093-jetty-alien-og-1g-concentrate-dablicator | category=concentrate, strain=Alien OG, variant=1g | ✗ strain: ''→want 'Alien OG' |
| gold-094-timeless-combo-510-battery-and-case-black-ye | category=merch, subtype=merch, strain=None, variant= | ✗ category: 'vaporizers'→want 'merch'; subtype: 'battery'→want 'merch' |
| gold-095-raw-classic-cones-1-1-4-6-pack | category=merch, subtype=merch, strain=None, variant= | ✓ |
| gold-096-stiiizy-lite-battery-promo | category=merch, subtype=merch, strain=None, variant= | ✗ category: 'vaporizers'→want 'merch'; subtype: 'battery'→want 'merch' |
| gold-097-human-grade-5-recycler-1a-dab-rig-smoke | category=merch, subtype=merch, strain=None | ✓ |
| gold-098-mushroom-holder-dab-tool | category=merch, subtype=merch, strain=None | ✓ |
| gold-099-stiiizy-pro-xl-battery-red | category=merch, subtype=merch, strain=None | ✗ category: 'vaporizers'→want 'merch'; subtype: 'battery'→want 'merch' |
| gold-100-papa-barkley-thc1000-releaf-tincture-30ml | category=tinctures, subtype=tincture, variant=1000mg, product_line=Releaf | ✓ |
| gold-101-mfny-yellow-beltz-live-resin-tincture | category=tinctures, subtype=tincture, strain=Yellow Beltz | ✗ strain: ''→want 'Yellow Beltz' |
| gold-102-ayrloom-beverage-enhancer-tincture-300mg | category=tinctures, subtype=tincture, variant=300mg | ✓ |
| gold-103-mfny-rainbow-driver | category=tinctures, subtype=tincture, strain=Rainbow Driver | ✗ strain: ''→want 'Rainbow Driver' |
| gold-104-ayrloom-tincture-1000mg-thc-high-dose | category=tinctures, subtype=tincture, variant=1000mg | ✓ |
| gold-105-papa-barkley-1-3-releaf-balm-50ml | category=topical, subtype=topical, strain=None, product_line=Releaf | ✓ |
| gold-106-ayrloom-balm-1000mg-thc-1000mg-cbd-revive-bc | category=topical, subtype=topical, strain=Revive | ✗ strain: ''→want 'Revive' |
| gold-107-ayrloom-balm-1000mg-thc-1000mg-cbd-restore-l | category=topical, subtype=topical, strain=Restore | ✗ strain: ''→want 'Restore' |

## gold_dispensary — gold_the_spot_bk.json

_Hand-labeled gold set: 50 real listings from The Spot BK (Tymber). A deliberately different naming convention from The Plug: brand comes LAST, lineage and THC% are inline ("-Hybrid- 24.00% THC"), and every name carries a trailing shelf code ("-ii8", "-p4 middle") that must not leak into the strain. Its 'other' bucket is FLOWER, not vapes, so it tests the hint override in the opposite direction. Ambiguous fields are omitted from expect on purpose._

| case | expected | deepseek-pro-0813 |
|---|---|---|
| spot-000-tropicana-cookies-hybrid-48-7-5pk-2-5g-t | category=preroll, strain=Tropicana Cookies, variant=2.5g | ✗ strain: ''→want 'Tropicana Cookies' |
| spot-001-dream-star-31-thc-cherry-diesel-34-thc-s | category=preroll, subtype=pack, variant=4g | ✓ |
| spot-002-big-bad-wolf-hybrid-21-67-thc-1g-pre-rol | category=preroll, subtype=single, strain=Big Bad Wolf, variant=1g | ✗ strain: ''→want 'Big Bad Wolf' |
| spot-003-kosher-kush-indica-29-thc-7-x-0-7g-5g-pr | category=preroll, subtype=pack, strain=Kosher Kush, variant=5g | ✗ strain: ''→want 'Kosher Kush' |
| spot-004-super-lemon-haze-hybrid-30-thc-5g-pre-ro | category=preroll, subtype=single, strain=Super Lemon Haze, variant=0.5g | ✗ strain: ''→want 'Super Lemon Haze' |
| spot-005-lemon-candy-runtz-hybrid-28-2-thc-2pk-pr | category=preroll, subtype=pack, strain=Lemon Candy Runtz, variant=1.5g | ✗ strain: ''→want 'Lemon Candy Runtz' |
| spot-006-purple-punch-indica-23-75-thc-1g-pre-rol | category=preroll, subtype=single, strain=Purple Punch, variant=1g | ✓ |
| spot-007-pink-cookies-indica-36-40-thc-presidenti | category=preroll, subtype=infused, strain=Pink Cookies, variant=1g | ✓ |
| spot-008-sugar-runtz-hybrid-18-35-thc-2g-hash-inf | category=preroll, subtype=infused, strain=Sugar Runtz, variant=2g | ✓ |
| spot-009-alaskan-thunder-fuck-sativa-90-00-thc-2g | category=vaporizers, subtype=all-in-one, strain=Alaskan Thunder Fuck, variant=2g | ✓ |
| spot-010-blueberry-jam-indica-1ml-live-resin-rech | category=vaporizers, subtype=all-in-one, strain=Blueberry Jam, variant=1g | ✓ |
| spot-011-sour-z-sativa-85-95-thc-1g-vape-cartridg | category=vaporizers, subtype=cart, strain=Sour Z, variant=1g, product_line=None | ✓ |
| spot-012-maui-wowie-sativa-90-thc-510-vape-cartri | category=vaporizers, subtype=cart, strain=Maui Wowie, variant=1g | ✓ |
| spot-013-granddaddy-purp-indica-97-thc-melted-dia | category=vaporizers, subtype=all-in-one, strain=Granddaddy Purp, variant=1g | ✓ |
| spot-014-apricot-punch-indica-85-45-thc-0-5g-clas | category=vaporizers, subtype=all-in-one, strain=Apricot Punch, variant=0.5g | ✓ |
| spot-015-super-jack-sativa-80-thc-1g-aio-vape-pen | category=vaporizers, subtype=all-in-one, strain=Super Jack, variant=1g | ✓ |
| spot-016-big-apple-hybrid-79-thc-1g-aio-vape-pen- | category=vaporizers, subtype=all-in-one, strain=Big Apple, variant=1g | ✓ |
| spot-017-strawberry-diesel-hybrid-88-5-thc-1g-aio | category=vaporizers, subtype=all-in-one, strain=Strawberry Diesel, variant=1g | ✓ |
| spot-018-trainwreck-sativa-19-00-thc-sun-soil-gro | category=flower, subtype=flower, strain=Trainwreck, variant=28g | ✓ |
| spot-019-lilac-diesel-hybrid-24-00-thc-3-5g-jar-f | category=flower, subtype=flower, strain=Lilac Diesel, variant=3.5g | ✓ |
| spot-020-jelly-cake-indica-23-5-thc-28g-flower-ma | category=flower, subtype=flower, strain=Jelly Cake, variant=28g | ✓ |
| spot-021-lemon-skunk-sativa-26-65-thc-28g-jar-flo | category=flower, subtype=flower, strain=Lemon Skunk, variant=28g | ✗ strain: ''→want 'Lemon Skunk' |
| spot-022-sativa-29-thc-7g-pre-ground-flower-in-my | category=flower, subtype=preground, strain=Sativa, variant=7g | ✗ strain: ''→want 'Sativa' |
| spot-023-lemon-skunk-og-sativa-dominant-hybrid-31 | category=flower, subtype=flower, strain=Lemon Skunk OG, variant=3.5g | ✗ strain: ''→want 'Lemon Skunk OG' |
| spot-024-purple-sunset-indica-21-53-thc-14g-flowe | category=flower, subtype=flower, strain=Purple Sunset, variant=14g | ✗ strain: ''→want 'Purple Sunset' |
| spot-025-frank-rizzo-hybrid-24-90-thc-3-5g-flower | category=flower, subtype=flower, strain=Frank Rizzo, variant=3.5g | ✗ strain: ''→want 'Frank Rizzo' |
| spot-026-reserve-hybrid-16-45-thc-1-1-thc-cbd-7g- | category=flower, variant=7g | ✓ |
| spot-027-permanent-marker-indica-28-thc-dime-bag- | category=flower, subtype=flower, strain=Permanent Marker, variant=0.7g | ✗ strain: ''→want 'Permanent Marker' |
| spot-028-sour-grape-indica-100mg-10-pcs-live-resi | category=edible, subtype=gummy, strain=Sour Grape, variant=100mg | ✗ strain: ''→want 'Sour Grape' |
| spot-029-strawberry-sativa-100mg-thc-10-pcs-live- | category=edible, subtype=gummy, strain=Strawberry, variant=100mg | ✗ strain: ''→want 'Strawberry' |
| spot-030-camino-sour-orchard-peach-balance-hybrid | category=edible, subtype=gummy, strain=Sour Orchard Peach, product_line=Balance, variant=100mg | ✗ strain: ''→want 'Sour Orchard Peach'; product_line: None→want 'Balance' |
| spot-031-cali-melon-sativa-100mg-thc-10pcs-live-r | category=edible, subtype=gummy, strain=Cali Melon, variant=100mg | ✗ strain: ''→want 'Cali Melon' |
| spot-032-permanent-marker-hybrid-100mg-10-pack-ne | category=edible, subtype=gummy, variant=100mg | ✓ |
| spot-033-watermelon-lemonade-bliss-gummies-100-mg | category=edible, subtype=gummy, strain=Watermelon Lemonade, product_line=Bliss, variant=100mg | ✗ strain: ''→want 'Watermelon Lemonade'; product_line: None→want 'Bliss' |
| spot-034-grape-honey-indica-10-20-thc-cbn-100mg-1 | category=edible, strain=Grape & Honey, variant=100mg | ✗ strain: ''→want 'Grape & Honey' |
| spot-035-tropical-burst-energy-sativa-10mg-2-1-th | category=edible, subtype=gummy, strain=Tropical Burst, product_line=Energy, variant=100mg | ✗ strain: ''→want 'Tropical Burst'; product_line: None→want 'Energy' |
| spot-036-mendo-breath-indica-65-56-thc-all-in-one | category=vaporizers, subtype=all-in-one, strain=Mendo Breath, variant=0.5g | ✗ strain: ''→want 'Mendo Breath' |
| spot-037-10-honey-banana-sativa-70-93-thc-1g-live | category=concentrate, subtype=resin, strain=Honey Banana, variant=1g | ✗ strain: ''→want 'Honey Banana' |
| spot-038-papaya-juice-sativa-79-95-thc-1g-wax-sug | category=concentrate, strain=Papaya Juice, variant=1g | ✗ strain: ''→want 'Papaya Juice' |
| spot-039-tropical-punch-hybrid-65-56-thc-all-in-o | category=vaporizers, subtype=all-in-one, strain=Tropical Punch, variant=0.5g | ✗ strain: ''→want 'Tropical Punch' |
| spot-040-12-candy-rain-hybrid-68-50-thc-live-resi | category=concentrate, subtype=resin, strain=Candy Rain, variant=1g | ✗ strain: ''→want 'Candy Rain' |
| spot-041-pink-certz-hybrid-81-37-thc-1g-badder-co | category=concentrate, strain=Pink Certz, variant=1g | ✗ strain: ''→want 'Pink Certz' |
| spot-042-watermelon-drip-x-2pk-hemp-wraps-billion | category=merch, subtype=merch, strain=None | ✓ |
| spot-043-bambu-x-classic-natural | category=merch, subtype=merch, strain=None | ✓ |
| spot-044-matte-black-3-2v-auto-start-510-vape-car | category=merch, subtype=merch, strain=None | ✗ category: 'vaporizers'→want 'merch'; subtype: 'battery'→want 'merch' |
| spot-045-zzz-s-rolling-tray-with-magnetic-cover-d | category=merch, subtype=merch, strain=None | ✓ |
| spot-046-turbo-blueberry-indica-73-38-thc-15ml-ti | category=tinctures, subtype=tincture, strain=Turbo Blueberry | ✗ strain: ''→want 'Turbo Blueberry' |
| spot-047-focus-tincture-13-40-thc-864mg-tac-thc-c | category=tinctures, subtype=tincture | ✓ |
| spot-048-restore-1000-00mg-thc-balm-2-3oz-tin-a11 | category=topical, subtype=topical, strain=Restore, variant=1000mg | ✗ strain: ''→want 'Restore'; variant: '1g'→want '1000mg' |
| spot-049-relief-balm-130mg-cbd-40mg-thc-3-1-15ml- | category=topical, subtype=topical | ✓ |
