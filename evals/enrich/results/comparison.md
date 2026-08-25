# Enrich model comparison

Models: haiku, deepseek


## gold_dispensary — gold_the_plug.json

_Hand-labeled gold set: 108 real listings from The Plug (Crown Heights), stratified across categories, incl. the 'other' bucket the scraper's CATEGORY_MAP missed (mostly vapes — tests hint override), pack-math edibles, typo strains that must be kept verbatim (Red Zprite, Marakesh), product lines (UP, Flyers, Noir, Quicks, Releaf), and null-strain merch/topicals. Ambiguous fields are omitted from expect on purpose. Rulings: beverages are dosed in mg not volume; topical scent names ARE strains; version suffixes (2.0) are kept; concentrate 'diamonds' is its own subtype._

| case | expected | haiku | deepseek |
|---|---|---|---|
| gold-000-off-hours-razz-lemonade-live-resin-rope | category=edible, subtype=gummy, strain=Razz Lemonade | ✓ | ✗ strain: ''→want 'Razz Lemonade' |
| gold-001-ayrloom-up-12oz-beverage-honeycrisp-5mg-1-1- | category=edible, subtype=beverage, strain=Honeycrisp, variant=5mg, product_line=UP | ✓ | ✗ strain: ''→want 'Honeycrisp'; variant: '12fl oz'→want '5mg' |
| gold-002-ayrloom-up-12oz-beverage-lemonade | category=edible, subtype=beverage, strain=Lemonade, product_line=UP | ✓ | ✗ strain: ''→want 'Lemonade' |
| gold-003-old-pal-x-babish-thc-infused-sugar-100mg | category=edible, subtype=other, variant=100mg, strain=None | ✓ | ✗ variant: ''→want '100mg' |
| gold-004-wyld-kiwi-1-1-thc-thcv | category=edible, subtype=gummy, strain=Kiwi | ✓ | ✗ subtype: 'other'→want 'gummy'; strain: ''→want 'Kiwi' |
| gold-005-florist-farms-peach-gummies-20mg-x-2pk-1-1-t | category=edible, subtype=gummy, strain=Peach, variant=40mg | ✓ | ✗ strain: ''→want 'Peach'; variant: ''→want '40mg' |
| gold-006-camino-sleep-midnight-blueberry-5-1-cbn-20pk | category=edible, subtype=gummy, strain=Midnight Blueberry, variant=100mg | ✓ | ✗ subtype: 'other'→want 'gummy'; strain: ''→want 'Midnight Blueberry'; variant: '72g'→want '100mg' |
| gold-007-foy-strawberry-nighttime-1-1-1-chews | category=edible, subtype=gummy | ✓ | ✓ |
| gold-008-myhi-boisterous-berry-3-x-10mg-thc-stir-stik | category=edible, subtype=beverage, strain=Boisterous Berry, variant=30mg | ✓ | ✗ subtype: 'other'→want 'beverage'; strain: ''→want 'Boisterous Berry'; variant: '2.1g'→want '30mg' |
| gold-009-mfny-live-resin-gummies-creamsicle-x-rainbow | category=edible, subtype=gummy, strain=Creamsicle x Rainbow Beltz 2.0 | ✓ | ✗ strain: ''→want 'Creamsicle x Rainbow Beltz 2.0' |
| gold-010-revert-grape-100mg-scored-gummy | category=edible, subtype=gummy, strain=Grape, variant=100mg | ✓ | ✗ strain: ''→want 'Grape'; variant: ''→want '100mg' |
| gold-011-myhi-simply-flavorless-3-x-10mg-thc-stir-sti | category=edible, subtype=beverage, strain=Simply Flavorless, variant=30mg | ✓ | ✗ subtype: 'other'→want 'beverage'; strain: ''→want 'Simply Flavorless'; variant: '2.1g'→want '30mg' |
| gold-012-kushy-punch-blue-raspberry-gummies-100mg | category=edible, subtype=gummy, strain=Blue Raspberry | ✓ | ✗ strain: ''→want 'Blue Raspberry' |
| gold-013-gr-n-baja-blaze-mega | category=edible, subtype=gummy, strain=Baja Blaze Mega | ✗ subtype: 'beverage'→want 'gummy' | ✗ subtype: 'other'→want 'gummy'; strain: ''→want 'Baja Blaze Mega' |
| gold-014-wana-fast-asleep-5-1-1-1-dream-berry | category=edible, subtype=gummy, strain=Dream Berry | ✓ | ✗ subtype: 'other'→want 'gummy'; strain: ''→want 'Dream Berry' |
| gold-015-eaton-botanicals-apple-a-day-apple-2-5mg-gum | category=edible, subtype=gummy, strain=Apple-A-Day | ✓ | ✗ strain: ''→want 'Apple-A-Day' |
| gold-016-gr-n-milk-chocolate-mini-bar-daytime-sativa- | category=edible, subtype=chocolate, variant=100mg | ✓ | ✗ variant: '7g'→want '100mg' |
| gold-017-ayrloom-up-12oz-beverage-pineapple-mango | category=edible, subtype=beverage, strain=Pineapple Mango, product_line=UP | ✓ | ✗ strain: ''→want 'Pineapple Mango' |
| gold-018-camino-balance-yuzu-lemon-100mg-20pk | category=edible, subtype=gummy, strain=Yuzu Lemon, variant=100mg | ✓ | ✗ subtype: 'other'→want 'gummy'; strain: ''→want 'Yuzu Lemon'; variant: '72g'→want '100mg' |
| gold-019-ayrloom-10-mg-thc-5mg-thcv-gummies-sol-burst | category=edible, subtype=gummy, strain=Sol Burst | ✓ | ✗ strain: ''→want 'Sol Burst' |
| gold-020-camino-recover-freshly-squeezed-1-2-cbg-20pk | category=edible, subtype=gummy, strain=Freshly Squeezed, variant=100mg | ✓ | ✗ subtype: 'other'→want 'gummy'; strain: ''→want 'Freshly Squeezed'; variant: '72g'→want '100mg' |
| gold-021-camino-chews-pineapple-paradise-1-1-thc-cbc- | category=edible, subtype=gummy, strain=Pineapple Paradise, variant=100mg | ✓ | ✗ strain: ''→want 'Pineapple Paradise'; variant: '46g'→want '100mg' |
| gold-022-gr-n-milk-chocolate-full-bar-sativa | category=edible, subtype=chocolate, strain=Sativa | ✗ strain: 'Milk Chocolate'→want 'Sativa' | ✗ strain: ''→want 'Sativa' |
| gold-023-hashtag-honey-tropical-punch-live-resin-gumm | category=edible, subtype=gummy, strain=Tropical Punch, variant=100mg | ✓ | ✗ strain: ''→want 'Tropical Punch'; variant: '50.2g'→want '100mg' |
| gold-024-purple-punch-infused-5pk-0-5g-pre-rolls | category=preroll, strain=Purple Punch, variant=2.5g | ✓ | ✗ strain: ''→want 'Purple Punch' |
| gold-025-aphrodite-vanilla-gelato-foam-tip-pre-roll-5 | category=preroll, subtype=pack, strain=Vanilla Gelato, variant=2.5g | ✓ | ✗ strain: ''→want 'Vanilla Gelato' |
| gold-026-jaunty-stay-puft-x-strawberry-meltz-1g-hash- | category=preroll, subtype=infused, strain=Stay Puft x Strawberry Meltz, variant=1g | ✓ | ✗ strain: ''→want 'Stay Puft x Strawberry Meltz' |
| gold-027-budd-lemon-cherry-gelato-1g-pre-roll | category=preroll, subtype=single, strain=Lemon Cherry Gelato, variant=1g | ✓ | ✗ strain: ''→want 'Lemon Cherry Gelato' |
| gold-028-claybourne-co-strawberry-cough-flyers-infuse | category=preroll, subtype=infused, strain=Strawberry Cough, product_line=Flyers, variant=1.5g | ✓ | ✗ strain: ''→want 'Strawberry Cough' |
| gold-029-claybourne-co-king-louis-og-diamond-frosted- | category=preroll, strain=King Louis OG, variant=2.5g | ✓ | ✗ strain: ''→want 'King Louis OG' |
| gold-030-the-plug-pack-tequila-sunrise-1g-preroll | category=preroll, subtype=single, strain=Tequila Sunrise, variant=1g | ✓ | ✗ subtype: 'pack'→want 'single'; strain: ''→want 'Tequila Sunrise' |
| gold-031-nanticoke-coconut-cream-1g-infused-pre-roll | category=preroll, subtype=infused, strain=Coconut Cream, variant=1g | ✓ | ✗ strain: ''→want 'Coconut Cream' |
| gold-032-lowell-smokes-quicks-afternoon-delight-0-35g | category=preroll, subtype=pack, strain=Afternoon Delight, product_line=Quicks, variant=3.5g | ✓ | ✗ strain: ''→want 'Afternoon Delight' |
| gold-033-claybourne-co-banana-og-flyers-infused-1-5g- | category=preroll, subtype=infused, strain=Banana OG, product_line=Flyers, variant=1.5g | ✓ | ✗ strain: ''→want 'Banana OG' |
| gold-034-ruby-farms-classics-7pk-pre-rolls-trop-cherr | category=preroll, subtype=pack, strain=Trop Cherry, variant=5g | ✓ | ✗ strain: ''→want 'Trop Cherry' |
| gold-035-boutiq-snack-pack-cherry-lime-x-rz-11-5-x-05 | category=preroll, strain=Cherry Lime x RZ-11, variant=2.5g | ✗ variant: '250mg'→want '2.5g' | ✗ strain: ''→want 'Cherry Lime x RZ-11' |
| gold-036-ruby-farms-hash-infused-blueberry-dj-cut-2pk | category=preroll, subtype=infused, strain=Blueberry DJ Cut, variant=1g | ✓ | ✗ strain: ''→want 'Blueberry DJ Cut' |
| gold-037-florist-farms-mule-fuel-1g-live-resin-infuse | category=preroll, subtype=infused, strain=Mule Fuel, variant=1g | ✓ | ✗ strain: ''→want 'Mule Fuel' |
| gold-038-claybourne-co-fast-lane-sativa-flyers-blends | category=preroll, variant=3.5g | ✓ | ✓ |
| gold-039-alibi-dream-star-cherry-diesel-4g-variety-pr | category=preroll, subtype=pack, variant=4g | ✓ | ✓ |
| gold-040-eaton-botanicals-little-pandas-tropical-cool | category=preroll, subtype=pack, variant=1.75g, product_line=Little Pandas | ✓ | ✓ |
| gold-041-jetpacks-fj-mini-0-6g-infused-preroll-strawb | category=preroll, subtype=infused, strain=Strawberry Sour Diesel, variant=0.6g | ✓ | ✗ strain: ''→want 'Strawberry Sour Diesel' |
| gold-042-smoke-wrld-mochi-runtz-3-5g-flower | category=flower, subtype=flower, strain=Mochi Runtz, variant=3.5g | ✓ | ✗ strain: ''→want 'Mochi Runtz' |
| gold-043-the-plug-pack-sapphire-haze-28g-flower | category=flower, subtype=flower, strain=Sapphire Haze, variant=28g | ✓ | ✗ strain: ''→want 'Sapphire Haze' |
| gold-044-umamii-ice-cream-cake-3-5g-flower | category=flower, subtype=flower, strain=Ice Cream Cake, variant=3.5g | ✓ | ✗ strain: ''→want 'Ice Cream Cake' |
| gold-045-revert-crumble-cake-3-5g-flower | category=flower, subtype=flower, strain=Crumble Cake, variant=3.5g | ✓ | ✗ strain: ''→want 'Crumble Cake' |
| gold-046-alchemy-pure-space-panda-0-7g-flower-bag | category=flower, subtype=flower, strain=Space Panda, variant=0.7g | ✓ | ✗ strain: ''→want 'Space Panda' |
| gold-047-ttm-essentials-northern-lights-3-5g-flower-b | category=flower, subtype=flower, strain=Northern Lights, variant=3.5g | ✓ | ✗ strain: ''→want 'Northern Lights' |
| gold-048-smoke-wrld-red-zprite-3-5g | category=flower, subtype=flower, strain=Red Zprite, variant=3.5g | ✓ | ✗ strain: ''→want 'Red Zprite' |
| gold-049-budd-lemon-cherry-gelato-3-5g-premium-smalls | category=flower, subtype=smalls, strain=Lemon Cherry Gelato, variant=3.5g | ✓ | ✗ strain: ''→want 'Lemon Cherry Gelato' |
| gold-050-kickfly-s-blackscotti-14g-flower | category=flower, subtype=flower, strain=Blackscotti, variant=14g | ✓ | ✗ strain: ''→want 'Blackscotti' |
| gold-051-leal-chronic-tonic-3-5g | category=flower, subtype=flower, strain=Chronic Tonic, variant=3.5g | ✓ | ✗ strain: ''→want 'Chronic Tonic' |
| gold-052-the-botanist-gsc-3-5g-flower | category=flower, subtype=flower, strain=GSC, variant=3.5g | ✓ | ✗ strain: ''→want 'GSC' |
| gold-053-untitled-sour-diesel-7g | category=flower, subtype=flower, strain=Sour Diesel, variant=7g | ✓ | ✗ strain: ''→want 'Sour Diesel' |
| gold-054-revert-golden-pineapple-14g-flower | category=flower, subtype=flower, strain=Golden Pineapple, variant=14g | ✓ | ✗ strain: ''→want 'Golden Pineapple' |
| gold-055-noizey-ny-super-glue-4g-flower | category=flower, subtype=flower, strain=NY Super Glue, variant=4g | ✓ | ✗ strain: ''→want 'NY Super Glue' |
| gold-056-smoakland-tropical-haze-28g-flower | category=flower, subtype=flower, strain=Tropical Haze, variant=28g | ✓ | ✗ strain: ''→want 'Tropical Haze' |
| gold-057-matter-grape-gas-3-5g-flower | category=flower, subtype=flower, strain=Grape Gas, variant=3.5g | ✓ | ✗ strain: ''→want 'Grape Gas' |
| gold-058-gypsy-weed-kombucha-oreo-28g | category=flower, subtype=flower, strain=Kombucha Oreo, variant=28g | ✓ | ✗ strain: ''→want 'Kombucha Oreo' |
| gold-059-munchkins-trop-cherry-3-5g-small-buds | category=flower, subtype=smalls, strain=Trop Cherry, variant=3.5g | ✓ | ✗ strain: ''→want 'Trop Cherry' |
| gold-060-blends-by-basin-fruity-pebbles-1g-cart | category=vaporizers, subtype=cart, strain=Fruity Pebbles, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'cart'; strain: ''→want 'Fruity Pebbles' |
| gold-061-select-flavor-series-grape-ape-1g-briq-v2 | category=vaporizers, strain=Grape Ape, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; strain: ''→want 'Grape Ape' |
| gold-062-timeless-t2-blue-dream-chill-2g-rechargeable | category=vaporizers, strain=Blue Dream, variant=2g | ✓ | ✗ category: 'other'→want 'vaporizers'; strain: ''→want 'Blue Dream' |
| gold-063-florist-farms-durban-poison-1g-cart | category=vaporizers, subtype=cart, strain=Durban Poison, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'cart'; strain: ''→want 'Durban Poison' |
| gold-064-select-ace-terpologist-durban-fizz-1g-cart | category=vaporizers, subtype=cart, strain=Durban Fizz, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'cart'; strain: ''→want 'Durban Fizz' |
| gold-065-jetty-el-chiveoz-1g-solventless-live-rosin-a | category=vaporizers, subtype=all-in-one, strain=El Chiveoz, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'El Chiveoz' |
| gold-066-jaunty-mango-haze-1-5g-aio | category=vaporizers, subtype=all-in-one, strain=Mango Haze, variant=1.5g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Mango Haze' |
| gold-067-timeless-t1-new-york-sour-diesel-1g-recharga | category=vaporizers, strain=New York Sour Diesel, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; strain: ''→want 'New York Sour Diesel' |
| gold-068-toast-royal-rntz-7g-infused-pre-ground-hybri | category=flower, strain=Royal Rntz, variant=7g | ✓ | ✗ category: 'other'→want 'flower'; strain: ''→want 'Royal Rntz' |
| gold-069-jaunty-sugar-cookie-1-5g-all-in-one-palm | category=vaporizers, subtype=all-in-one, strain=Sugar Cookie, variant=1.5g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Sugar Cookie' |
| gold-070-timeless-noir-707-headband-live-resin-1g-vap | category=vaporizers, subtype=cart, strain=707 Headband, product_line=Noir, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'cart'; strain: ''→want '707 Headband' |
| gold-071-the-plug-pack-lemon-berry-kush-28g-infused-p | category=flower, strain=Lemon Berry Kush, variant=28g | ✓ | ✗ category: 'other'→want 'flower'; strain: ''→want 'Lemon Berry Kush' |
| gold-072-ayrloom-0-5g-disposable-lychee-dream | category=vaporizers, subtype=all-in-one, strain=Lychee Dream, variant=0.5g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Lychee Dream' |
| gold-073-ayrloom-0-5g-disposable-blue-widow | category=vaporizers, subtype=all-in-one, strain=Blue Widow, variant=0.5g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Blue Widow' |
| gold-074-timeless-noir-panamango-live-resin-1g-vape-c | category=vaporizers, subtype=cart, strain=Panamango, product_line=Noir, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'cart'; strain: ''→want 'Panamango' |
| gold-075-mfny-0-5g-live-resin-dispo-gelonade | category=vaporizers, subtype=all-in-one, strain=Gelonade, variant=0.5g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Gelonade' |
| gold-076-kushy-punch-pineapple-jealousy-1g-510-thread | category=vaporizers, subtype=cart, strain=Pineapple Jealousy, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'cart'; strain: ''→want 'Pineapple Jealousy' |
| gold-077-doja-zoap-1g-aio-live-resin | category=vaporizers, subtype=all-in-one, strain=Zoap, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Zoap' |
| gold-078-jaunty-strawnana-1-5g-aio | category=vaporizers, subtype=all-in-one, strain=Strawnana, variant=1.5g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Strawnana' |
| gold-079-mfny-0-5g-live-resin-dispo-honey-banana | category=vaporizers, subtype=all-in-one, strain=Honey Banana, variant=0.5g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Honey Banana' |
| gold-080-ayrloom-rest-1g-disposable | category=vaporizers, subtype=all-in-one, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one' |
| gold-081-revert-galactic-jack-14g-kief-infused-ground | category=flower, strain=Galactic Jack, variant=14g | ✓ | ✗ category: 'other'→want 'flower'; strain: ''→want 'Galactic Jack' |
| gold-082-stiiizy-blue-burst-1g-disposable | category=vaporizers, subtype=all-in-one, strain=Blue Burst, variant=1g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'all-in-one'; strain: ''→want 'Blue Burst' |
| gold-083-stiiizy-premium-jack-5g-pod | category=vaporizers, subtype=pod, strain=Premium Jack, variant=0.5g | ✓ | ✗ category: 'other'→want 'vaporizers'; subtype: 'other'→want 'pod'; strain: ''→want 'Premium Jack' |
| gold-084-jetpacks-donny-burger-1g-indica-diamonds | category=concentrate, subtype=diamonds, strain=Donny Burger, variant=1g | ✓ | ✗ strain: ''→want 'Donny Burger' |
| gold-085-jetty-gdp-1g-concentrate-dablicator | category=concentrate, strain=GDP, variant=1g | ✓ | ✗ strain: ''→want 'GDP' |
| gold-086-jetpacks-panama-punch-1g-sativa-diamonds | category=concentrate, subtype=diamonds, strain=Panama Punch, variant=1g | ✓ | ✗ strain: ''→want 'Panama Punch' |
| gold-087-blotter-runtz-mintz-1g-live-resin-sugar | category=concentrate, subtype=resin, strain=Runtz Mintz, variant=1g | ✓ | ✗ strain: ''→want 'Runtz Mintz' |
| gold-088-mfny-chemdog-2g-live-resin-badder | category=concentrate, subtype=resin, strain=Chemdog, variant=2g | ✓ | ✗ strain: ''→want 'Chemdog' |
| gold-089-jetpacks-cherry-limeade-1g-sativa-badder | category=concentrate, strain=Cherry Limeade, variant=1g | ✓ | ✗ strain: ''→want 'Cherry Limeade' |
| gold-090-alchemy-pure-marakesh-1g-live-rosin | category=concentrate, subtype=rosin, strain=Marakesh, variant=1g | ✓ | ✗ strain: ''→want 'Marakesh' |
| gold-091-mind-melters-permanent-marker-1g-cold-cure-l | category=concentrate, subtype=rosin, strain=Permanent Marker, variant=1g | ✓ | ✗ strain: ''→want 'Permanent Marker' |
| gold-092-hashtag-honey-chocolate-diesel-1g-live-sugar | category=concentrate, strain=Chocolate Diesel, variant=1g | ✓ | ✗ strain: ''→want 'Chocolate Diesel' |
| gold-093-jetty-alien-og-1g-concentrate-dablicator | category=concentrate, strain=Alien OG, variant=1g | ✓ | ✗ strain: ''→want 'Alien OG' |
| gold-094-timeless-combo-510-battery-and-case-black-ye | category=merch, subtype=merch, strain=None, variant= | ✓ | ✓ |
| gold-095-raw-classic-cones-1-1-4-6-pack | category=merch, subtype=merch, strain=None, variant= | ✓ | ✓ |
| gold-096-stiiizy-lite-battery-promo | category=merch, subtype=merch, strain=None, variant= | ✓ | ✓ |
| gold-097-human-grade-5-recycler-1a-dab-rig-smoke | category=merch, subtype=merch, strain=None | ✓ | ✓ |
| gold-098-mushroom-holder-dab-tool | category=merch, subtype=merch, strain=None | ✓ | ✓ |
| gold-099-stiiizy-pro-xl-battery-red | category=merch, subtype=merch, strain=None | ✓ | ✓ |
| gold-100-papa-barkley-thc1000-releaf-tincture-30ml | category=tinctures, subtype=tincture, variant=1000mg, product_line=Releaf | ✓ | ✗ variant: '30'→want '1000mg' |
| gold-101-mfny-yellow-beltz-live-resin-tincture | category=tinctures, subtype=tincture, strain=Yellow Beltz | ✓ | ✗ strain: ''→want 'Yellow Beltz' |
| gold-102-ayrloom-beverage-enhancer-tincture-300mg | category=tinctures, subtype=tincture, variant=300mg | ✓ | ✗ variant: '30'→want '300mg' |
| gold-103-mfny-rainbow-driver | category=tinctures, subtype=tincture, strain=Rainbow Driver | ✓ | ✗ strain: ''→want 'Rainbow Driver' |
| gold-104-ayrloom-tincture-1000mg-thc-high-dose | category=tinctures, subtype=tincture, variant=1000mg | ✓ | ✗ variant: '30'→want '1000mg' |
| gold-105-papa-barkley-1-3-releaf-balm-50ml | category=topical, subtype=topical, strain=None, product_line=Releaf | ✓ | ✓ |
| gold-106-ayrloom-balm-1000mg-thc-1000mg-cbd-revive-bc | category=topical, subtype=topical, strain=Revive | ✓ | ✗ strain: ''→want 'Revive' |
| gold-107-ayrloom-balm-1000mg-thc-1000mg-cbd-restore-l | category=topical, subtype=topical, strain=Restore | ✓ | ✗ strain: ''→want 'Restore' |
