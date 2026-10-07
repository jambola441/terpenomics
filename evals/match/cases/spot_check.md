# Matcher test set: spot check

For each, is the label right? The matcher's last decision is shown for comparison only.

1. **Camino**: Edible Gummies | Camino | Sparkling Pear - (3:1 CBD:THC) | 100MG (size field '100mg', $30.00; oc-dispensary-bk)
   - label (entry, likely): Gummies Social Sparkling Pear [20pk 40mg]: Sparkling Pear 3:1 CBD:THC is the catalog's Gummies Social Sparkling Pear (the effect is left out, so the catalog's wording wins). The store's 100MG conflicts with the product, which is 2mg THC and 6mg CBD per gummy in a 20pk, 40mg THC, as nine other stores list it; only the-spot-bk also shows a 100mg template figure.
   - matcher: None None: —
   - case 5f5b5311-408c-45fc-a3dd-ce479cf33348

2. **MFNY**: #13 Shiskaberry  -Indica 73.53% THC | 1g Live Resin Badder (Concentrate) | MFNY  -TF2 (size field '1g', $65.00; the-spot-bk)
   - label (entry, likely): Shishkaberry [1g]: 1g Live Resin Badder Shishkaberry (the #13 and TF2 are store codes and Shiskaberry is a misspelling) is the catalog's only Shishkaberry concentrate, resin 1g ($58.50), and other stores list the same 1g live resin badder; the catalog entry carries no Live Resin line, which is the small doubt.
   - matcher: None None: —
   - case a5db9d51-e3de-44ed-90eb-f2d5aaa0de1a

3. **Presidential**: Infused Blunts | Presidential - Moon Rocks | Presidential (size field '1.5g', $34.00; oc-dispensary-bk)
   - label (entry, likely): Presidential OG [1.5g]: The strain slot reads Presidential, which is the catalog's Presidential OG (the brand's flagship Moon Rock blunt, listed elsewhere as Presidential (OG) Classic); the blunt's 1.5g field gives the 1.5g entry (typical $35, listing $34). Doubt: the store may have shortened the name, and its own page is blocked (403).
   - matcher: None None: —
   - case 9de85fe9-abe6-4ed5-ac29-9cdcce3e2a84

4. **Hashtag Honey**: HH Unicorn Piss 1G PREROLL (size field '1g', $12.00; brooklyn-organic-buds)
   - label (product, sure): Unicorn Piss [2.5g]: The catalog has Unicorn Piss pre-roll only as 2.5g; this listing is a single 1g pre-roll (store field and name both say 1g), so same product in a size the catalog lacks.
   - matcher: jev_review 0.76: Unicorn Piss [2.5g]
   - case 807472b8-a547-450a-a6a2-8237fe23e7b1

5. **Ayrloom**: Ayrloom - Beverage 12oz Single Can (1:1)  - Rose (size field '5mg', $5.00; grow-together-bk)
   - label (entry, likely): rosé [10mg]: Rose (1:1) single can is the Rosé beverage; its own page states THC 10.0mg and every other store lists Rosé 1:1 as 10mg THC : 10mg CBC, so the 5mg size field looks wrong. The catalog has only the 10mg Rosé entry.
   - matcher: None None: —
   - case a62032b5-48f4-4016-8a0a-c8622e5f67c0

6. **Jaunty**: AIO Vape 1.5g | Ghost Train (S) (size field '1.5g', $55.00; hii-nyc-williamsburg)
   - label (entry, sure): Palms Ghost Train [1.5g]: AIO Vape 1.5g Ghost Train (sativa) matches the only Ghost Train all-in-one in the catalog, Palms Ghost Train at 1.5g and $55; other stores list it as Ghost Train | AIO Palm | Sativa | 1.5g at $55, though this name omits the Palm line.
   - matcher: None None: —
   - case 4c31f873-0fb7-4370-aeeb-5d33c2621646

7. **STIIIZY**: STIIIZY - 2PK 1G Pods -Watermelon Z- Indica (size field '2g', $69.91; grow-together-bk)
   - label (product, likely): Original Watermelon Z [1g]: 2PK of 1g pods is a 2g package (size field 2g, name 2 x 1g, page price $79 matches a typical 2g vape at $80); the catalog has the Original Watermelon Z pod only at 1g and has no 2g entry.
   - matcher: jev 0.92: —
   - case e2903708-6720-486f-ac43-32fc276011c4

8. **Jaunty**: Mango Haze | AIO Palm | Sativa | 1.5g (size field '1.5g', $54.87; herbology-bed-stuy)
   - label (entry, sure): Palms Mango Haze [1.5g]: Name Mango Haze | AIO Palm | Sativa | 1.5g and the Palms description match the catalog's Palms Mango Haze all-in-one at 1.5g; another store lists the identical name at $55.
   - matcher: None None: —
   - case 9a597559-23de-4d77-a10e-9c6add592684

9. **Presidential**: Infused Pre-Rolls | Presidential - Moon Rocks | Pineapple (size field '1g', $22.00; oc-dispensary-bk)
   - label (entry, likely): Pineapple [1g]: Pineapple at 1g (field, readings settled; price $22 equals the usual 1g price) is the catalog's Pineapple 1g entry. Moon Rocks here is the store's generic product name for Presidential's infused pre-rolls, not a Pineapple-specific line, and the catalog has no Moon Rocks Pineapple entry.
   - matcher: None None: —
   - case d8fe4d72-ba88-4f0c-b658-ffb38d80ad44

10. **Ruby Farms**: Ruby Farms Rose Petals Hash Infused | Strawberry Fields | 1.5G Pack | Hybrid (size field '1.5g', $33.90; the-plug-crown-heights)
   - label (entry, likely): Doobies Strawberry Fields [1.5g]: Hash-infused rose petal 1.5g single in Strawberry Fields; the only Strawberry Fields entry at 1.5g, and every store lists 1.5g Strawberry Fields as the Rose Petal single at $30 (the entry's typical price). Doubt: the entry's line is Doobies, which come only as 2pk 1g and 7pk 3.5g, so it is filed under the wrong line (fix proposed).
   - matcher: None None: —
   - case e4da219b-872b-419c-9445-61af05b6a247

11. **Grön**: Gron - Dark Chocolate Mini Bar 1:1 CBN:THC 10pk - 100mg (size field '100mg', $14.00; kaya-bliss-brooklyn-heights)
   - label (entry, sure): Mini Bar 1:1 Dark Chocolate [10pk 100mg]: A 1:1 CBN:THC Dark Chocolate Mini Bar, 10 servings, 100mg THC per package; other stores list it as '1:1 Dark Chocolate Mini Bar - CBN/THC - Sleepy Indica', the catalog's Mini Bar 1:1 Dark Chocolate.
   - matcher: jev 0.95: Mini Bar 1:1 Dark Chocolate [10pk 100mg]
   - case f152622f-e0a0-41fa-923b-a92790d76315

12. **Florist Farms**: Live Resin Infused & Kief Coated | 1/2 Gram Joints | 2pk | Super Sour Diesel (size field '1g', $16.00; brooklyn-organic-buds)
   - label (none, sure): —: Live Resin Infused 2pk of half-gram joints (1g, $16) in Super Sour Diesel; the catalog has Super Sour Diesel only as vapes and a plain Sour Diesel 7pk 3.5g pre-roll, with no infused pre-roll of that strain, so the product is missing.
   - matcher: None None: —
   - case 71e80c45-f625-4dff-8870-6ca66221f614

13. **Grön**: 3:1 Blueberry Lemonade Pearls 2-Pack - CBG/THC - Daytime Sativa (size field '100mg', $22.00; milligrams-greenpoint)
   - label (product, likely): Pearls Blueberry Lemonade [10pk 100mg]: Same 3:1 CBG:THC daytime-sativa Blueberry Lemonade Pearl as the catalog's Pearls entry, but the name and description say a 2-pack of 10mg-THC pearls (20mg total, Grön's 'Fun Size'), a size the catalog lacks (it has only 10pk 100mg). The store's 100mg size field and $22 price look like the 10pk's, so a little doubt.
   - matcher: jev 0.99: Pearls Blueberry Lemonade [10pk 100mg]
   - case cb909398-1d4e-42a7-99d0-7efe8bbc0cf0

14. **BLOOM**: Cherry Pie -Hybrid- 85.51% THC | 0.5g Live All-in-One (Vape) | Bloom  -ttt5 BACK (size field '0.5g', $32.00; the-spot-bk)
   - label (entry, likely): Cherry Pie [0.5g]: Cherry Pie AIO at 0.5g is the catalog's only 0.5g Cherry Pie entry, but that entry has no product line while the listing says Live (Live Cherry Pie exists only at 1g); Cherry Pie is a Live-collection strain and $32 is the Live 0.5g price, so it reads as the same product with its Live line missing.
   - matcher: jev 0.95: Cherry Pie [0.5g]
   - case 494d3e83-4f49-495e-a63b-cb19b774caec

15. **Fernway**: Vape AIO | Fernway | Banana Bread - Traveler Pro (size field '2g', $90.00; oc-dispensary-bk)
   - label (none, sure): —: I listed the whole catalog: no Banana Bread in any size or spelling. The product is real (Stashmaster 'Banana Bread | Flavor Line | All-In-One Traveler PRO | 2.0g' $86, Kaya Bliss 2g $86), so the catalog lacks it.
   - matcher: None None: —
   - case d96957b9-8121-476b-a425-ceaf9e9b84f0

16. **MFNY**: MFNY | Badder | Live Resin | Chemdog | 1g | Indica | THC 70.29% (size field '1g', $73.00; quality-control-brighton-beach)
   - label (product, likely): Chemdog [2g]: Chemdog live resin badder at 1g: the catalog has Chemdog live resin concentrate only as a 2g entry, and its 1g Chemdog entry is rosin, a different subtype; the listing says Live Resin and its price (about $73 at this store) fits resin rather than the $75 rosin.
   - matcher: None None: —
   - case 615c3a29-8170-4839-b9d7-43cd2bc81b95

17. **Presidential**: Presidential | Gorilla Goo - Moon Rock Infused Pre-Roll (size field '1g', $17.00; rnr-dispensary-bk)
   - label (entry, sure): Gorilla Goo [1g]: Gorilla Goo Moon Rock Infused Pre-Roll (not a blunt) with size field 1g and the store page also showing 1g at $17, so the catalog's Gorilla Goo 1g entry rather than the 1.5g one.
   - matcher: jev_review 0.73: Gorilla Goo [1g]
   - case ecf2ff68-0475-4d1a-9d8f-028c6b42a37f

18. **PAX**: Pax - Era Go Battery - Pink Crush (size field None, $5.00; kaya-bliss-bay-ridge)
   - label (none, sure): —: Era Go battery in Pink Crush is a hardware accessory with no size; the full catalog has no battery entries, and other stores list Era Go batteries at $5 to $20, so the $5 price does not change the reading.
   - matcher: None None: —
   - case 6fb437d8-c38c-46c7-912f-c1f7fa792f32

19. **MFNY**: MFNY | Chemdog Live Resin Vape Cart (size field '1g', $58.00; milligrams-greenpoint)
   - label (product, likely): Classics Live Resin Chemdog [0.5g]: A single 1g Chemdog live resin cart (name, field and the $58 price match other stores' 1g Chemdog live resin carts); the catalog's Classics Live Resin Chemdog cart exists only at 0.5g, and its 1g Chemdog entry is the Classics Two-Fer 2-pack, a different product.
   - matcher: jev_review 0.55: Classics Two-Fer Chemdog [1g]
   - case 0b75f951-5aa0-467f-81b0-7e24350b4bfc

20. **MFNY**: .5g Live Resin Vape Cart- The Belafonte (size field '0.5g', $38.00; hii-nyc-williamsburg)
   - label (entry, sure): Live Resin The "Belafonte" [0.5g]: A .5g Live Resin 510 Vape Cart of The Belafonte (field and name both 0.5g, $38) is the catalog's Live Resin The Belafonte cart at 0.5g ($38.00); the other Belafonte cart entry is 1g.
   - matcher: jev 1: Live Resin The "Belafonte" [0.5g]
   - case ae3c19a5-6341-4cc3-a4fc-de3ca6b3307c

21. **Grön**: Gron Pearls | Star Spell | Sativa | 100MG Hash Rosin (size field '100mg', $24.86; emerald-dispensary-bk)
   - label (none, sure): —: Name is Star Spell Pearls, sativa, 100mg hash rosin: the same product as listing 9b507f1f (also listed by fireleaf-canarsie), and the catalog has no Star Spell entry.
   - matcher: None None: —
   - case 30c314db-9852-4427-8c01-302b4b3006d7

22. **STIIIZY**: White Raspberry - 0.5G Pod (size field '0.5g', $25.00; hold-up-roll-up)
   - label (product, likely): Original White Raspberry [1g]: A 0.5g White Raspberry pod (size settled at 0.5g, $25 is the usual 0.5g vape price); the catalog has the Original White Raspberry pod only at 1g, while the LIIIL White Raspberry is a different format (all-in-one).
   - matcher: None None: —
   - case 06ec6a87-2ebf-407a-a3cf-1e9c2ffe0dfb

23. **PUFF**: Lemon Wreck | Pre Rolls (size field '2.5g', $35.00; brooklyn-organic-buds)
   - label (entry, sure): Lemon Wreck [2.5g]: Plain Lemon Wreck pre-rolls sold as the 2.5g pack (store size 2.5g, URL says 2-5g; size_readings settle on 2.5g); the $35 price fits the 2.5g entry's typical $32.76, not the 1g or 7g entries.
   - matcher: jev 1: Lemon Wreck [2.5g]
   - case 7b62b360-245d-4c16-bb60-e71e93cde503

24. **Hashtag Honey**: Hashtag Honey 2g Vape- Durban Poison (size field '2g', $60.00; grow-together-bk)
   - label (none, sure): —: No Durban Poison in the catalog (searched durban and poison); quality-control-brighton-beach lists it as a 2g AIO, so it is a real Hashtag Honey product the catalog lacks.
   - matcher: None None: —
   - case 85e79e35-e390-410c-8c4d-6c434f2526c3

25. **Grassroots**: Grassroots - Fuzzy Navel - 14g (size field '14g', $132.00; stashmaster-nyc)
   - label (product, sure): Fuzzy Navel [3.5g]: The catalog has Fuzzy Navel (flower, no line) only at 3.5g; this listing is 14g (field and name agree) with no smalls or other format wording, so it is the same product in a size the catalog lacks.
   - matcher: jev_review 0.86: Fuzzy Navel [3.5g]
   - case 2b6d96df-d51d-41c0-9b7b-76c34894cfdb

26. **Revert**: Revert | Strawberry Amnesia (S) | Pre-Rolls | .5g (size field '0.5g', $7.91; fireleaf-canarsie)
   - label (entry, sure): Strawberry Amnesia [0.5g]: Catalog has Strawberry Amnesia pre-roll 0.5g with typical price $7.91, the listing's exact price; name, store category and size field all say 0.5g pre-roll and size_readings settled at 0.5g.
   - matcher: exact 1: Strawberry Amnesia [0.5g]
   - case fc8df3bc-235f-400c-95f2-c1736b8f2f8d

27. **STIIIZY**: Stiiizy - Lite Battery - Black (size field None, $5.00; kaya-bliss-bay-ridge)
   - label (none, sure): —: This is the STIIIZY Lite battery in black (merch, battery); the catalog holds no battery or merch entries at all (searches for battery, lite and merch find nothing).
   - matcher: None None: —
   - case 0c0837fa-6332-4165-bc1b-e8b680763d42

28. **1906**: CHILL DROPS - 2PK (size field '20mg', $5.00; hii-nyc-williamsburg)
   - label (product, likely): Drops Chill [2pk 20mg]: Chill 2-pack whose description says each drop is 5mg THC (25mg CBD), so 10mg THC; the 20mg field is not the THC-only total, and the catalog's Chill entries are 2pk 20mg (a mis-sized pouch, see proposed fix) and 20pk 100mg, so the product is there but not this size.
   - matcher: jev_review 0.82: Drops Chill [2pk 20mg]
   - case 1061bd0b-747a-4ee9-ab71-8bfb486b17aa

29. **Fernway**: Fernway | Americano Vape Cart (size field '1g', $50.00; milligrams-greenpoint)
   - label (entry, sure): Flavor Line Americano [1g]: An Americano 'Vape Cart' at 1g, $50: the catalog's only Americano is the 1g cart (Flavor Line), and the other stores list Americano only as a 1g 510 cartridge at $50.
   - matcher: jev 0.92: Flavor Line Americano [1g]
   - case f63e0c45-a13f-47ba-b890-02912dc14985

30. **Ruby Farms**: Turkey Tail Mushroom | Balm (size field '100mg', $50.00; travel-agency-ny)
   - label (none, sure): —: A 2.0oz Turkey Tail Mushroom balm (page says 1000mg THC : 1000mg CBD, so 1000mg THC; the 100mg size field looks like a typo). The Ruby Farms catalog holds no topical entries at all: searches for topical, balm, turkey and mushroom return nothing.
   - matcher: None None: —
   - case 45740f2a-27a3-4213-a0ff-c98813cf906b
