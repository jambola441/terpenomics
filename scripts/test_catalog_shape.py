"""Tests for catalog_shape.py — offline: the shape and leads of hand-made catalogs."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_shape as cs  # noqa: E402

_ids = iter(range(10_000))


def entry(line, strain, category="edible", subtype="gummy", variant="10pk 100mg",
          source="listings_bootstrap", support=3, terms=(), active=True):
    name = " ".join(p for p in (line, strain) if p)
    return {"id": f"e{next(_ids)}", "catalog_id": "c1", "name": name, "product_line": line,
            "strain": strain, "category": category, "subtype": subtype, "variant": variant,
            "source": source, "support": support, "is_active": active, "external_id": None,
            "verified_fields": None, "match_terms": list(terms)}


def kinds(found):
    return sorted({l.kind for l in found})


def texts(found, kind):
    return [l.text for l in found if l.kind == kind]


def test_products_merge_sizes_and_count_listings():
    a = entry("Sours", "Peach", variant="10pk 100mg")
    b = entry("Sours", "Peach", variant="20pk 200mg")
    c = entry("Sours", "Lime")
    listings = [{"catalog_entry_id": a["id"], "dispensary_id": "d1"},
                {"catalog_entry_id": b["id"], "dispensary_id": "d1"},
                {"catalog_entry_id": b["id"], "dispensary_id": "d2"}]
    prods = cs.products([a, b, c], listings)
    peach = next(p for p in prods if p.strain == "Peach")
    assert peach.sizes == ["10pk 100mg", "20pk 200mg"]
    assert (peach.listings, peach.stores) == (3, 2)
    assert [p.label for p in prods] == ["Lime", "Peach"]


def test_a_well_shaped_catalog_has_no_leads():
    entries = [entry("Sours", s) for s in ("Peach", "Lime", "Cherry", "Grape")] + \
              [entry("Fruit Chews", s) for s in ("Mango", "Berry", "Apple")]
    assert cs.leads(cs.products(entries)) == []


def test_thin_lines_and_a_line_named_like_a_strain():
    entries = [entry("Calm", "Peach"), entry("Uplift", "Lime"), entry("Rest", "Cherry"),
               entry("Sours", "Calm"), entry("Sours", "Grape"), entry("Sours", "Kiwi")]
    found = cs.leads(cs.products(entries), strain_vocab={"uplift": 2})
    assert "thin-lines" in kinds(found)          # 3 of 4 lines have one strain
    assert texts(found, "thin-line") == ["Calm (Peach); Rest (Cherry); Uplift (Lime)"]
    is_strain = texts(found, "line-is-strain")
    assert any('"Calm"' in t and "Sours Calm" in t for t in is_strain)
    assert any('"Uplift"' in t and "2 other brands" in t for t in is_strain)


def test_lineless_products_beside_lines():
    entries = [entry("Live Resin", s, "vaporizers", "cart", "1g") for s in ("Gelato", "Runtz", "Zkittlez")]
    entries += [entry(None, "Gelato", "vaporizers", "cart", "1g"),
                entry(None, "Mimosa", "vaporizers", "cart", "1g",
                      terms=("mimosa live resin cart 1g", "live resin mimosa 510", "mimosa cart")),
                entry(None, "Live Resin Haze", "vaporizers", "cart", "1g")]
    found = cs.leads(cs.products(entries))
    assert "mixed-lines" in kinds(found)
    # A strain sold plain and in a line is two products, not a stray; store names decide.
    assert texts(found, "stray") == ['no line, but most of their store names say "Live Resin": Mimosa 1g 2/3']
    assert texts(found, "line-in-strain") == ['"Live Resin Haze" has no line but its strain contains '
                                              'line "Live Resin"']
    # A storefront's unnamed range is the site's own naming.
    assert "mixed-lines" not in kinds(cs.leads(cs.products(entries), storefront=True))


def test_line_words_similar_lines_but_not_resin_and_rosin():
    entries = [entry("Indica", s, "flower", "flower", "3.5g") for s in ("A1", "B2", "C3")]
    entries += [entry("Bagel Hole", s, "preroll", None, "1g") for s in ("Kush", "Haze", "Diesel")]
    entries += [entry("BagelHole", s, "preroll", None, "1g") for s in ("Runtz", "Mints", "Gelato")]
    entries += [entry("Live Resin", s, "concentrate", "resin", "1g") for s in ("Kush", "Haze", "Mints")]
    entries += [entry("Live Rosin", s, "concentrate", "rosin", "1g") for s in ("Kush", "Haze", "Mints")]
    found = cs.leads(cs.products(entries))
    assert any('"Indica"' in t for t in texts(found, "line-word"))
    assert texts(found, "similar-lines") == ['lines "Bagel Hole" and "BagelHole" may be one line']


def test_strain_words_spare_real_names():
    entries = [entry("Core", s, "flower", "flower", "3.5g")
               for s in ("Blue Dream Cart", "Gelato 3.5g", "Hash Burger", "Cinnamon Roll",
                         "Blueberry 2.0", "Oishii #4", "Chocolate Mint")]
    noisy = texts(cs.leads(cs.products(entries)), "strain-word")
    assert noisy == ['"Core Blue Dream Cart": strain carries Cart',
                     '"Core Gelato 3.5g": strain carries 3.5g']


def test_near_duplicates_only_within_a_line():
    entries = [entry("Original", s, "vaporizers", "pod", "1g")
               for s in ("Skywalker", "Skywalker OG", "Granddaddy Purple", "Grand Daddy Purple",
                         "Go", "On", "Gelato 33", "Gelato 41")]
    entries += [entry("Live Resin", "Skywalker", "vaporizers", "pod", "1g")]
    dups = texts(cs.leads(cs.products(entries)), "near-dup")
    assert sorted(dups) == [
        '"Original Grand Daddy Purple" [pod] and "Original Granddaddy Purple" [pod] may be one product',
        '"Original Skywalker" [pod] and "Original Skywalker OG" [pod] may be one product']


def test_sizes_missing_implausible_or_written_two_ways():
    entries = [entry("Core", "Kush", "flower", "flower", None),
               entry("Core", "Haze", "flower", "flower", "35g"),
               entry("Core", "Runtz", "flower", "flower", "3.5g"),
               entry("Sours", "Peach", variant="100mg"), entry("Sours", "Lime"),
               entry("Sours", "Kiwi")]
    sized = texts(cs.leads(cs.products(entries)), "size")
    assert '"Core Kush": size \'?\' missing' in sized
    assert any("Core Haze" in t and "implausible" in t for t in sized)
    big = cs.leads(cs.products([entry(None, s, "flower", "flower", "70g") for s in ("Gas Lit", "Slingria")]))
    assert texts(big, "size") == []                       # 2.5 oz bags (Find.), not a misread
    assert any('line "Sours"' in t and "without: Peach" in t for t in sized)


def test_store_only_copies_of_site_products():
    site = [entry("Melt", "Blueberry Pie", variant="100mg", source="storefront_html"),
            entry("Sours", "Peach", source="storefront_html"),
            entry("Sours", "Lime", source="storefront_html"),
            entry("Sours", "Kiwi", source="storefront_html")]
    store = [entry(None, "Melt", variant="100mg", support=2),
             entry(None, "Lime", support=4), entry(None, "Watermelon", support=5)]
    found = cs.leads(cs.products(site + store), storefront=True)
    copies = texts(found, "store-copy")
    assert len(copies) == 2
    assert any('"Melt"' in t and '"Melt Blueberry Pie"' in t for t in copies)
    assert any('"Lime"' in t and '"Sours Lime"' in t for t in copies)
    assert "store-copy" not in kinds(cs.leads(cs.products(site + store)))   # bootstrap catalogs


def test_render_show_lists_lines_then_leads():
    catalog = {"id": "c1", "brand_name": "Acme", "brand_slug": "acme", "source_method": "listings_bootstrap",
               "fetched_at": "2026-10-05T05:00:00Z", "source_url": None}
    entries = [entry("Sours", s) for s in ("Peach", "Lime", "Cherry")] + [entry("Calm", "Peach"),
                                                                         entry(None, "Grape", active=False)]
    listings = [{"id": "l1", "dispensary_id": "d1", "catalog_entry_id": entries[0]["id"]},
                {"id": "l2", "dispensary_id": "d2", "catalog_entry_id": None}]
    text = cs.render_show(catalog, entries, listings, {})
    assert "4 active entries = 4 products · 1 inactive" in text
    assert "2 active at 2 stores, 1 matched to this catalog (50%)" in text
    assert text.index("  Sours — 3 strain(s)") < text.index("  Calm — 1 strain(s)")
    assert "[thin-line] edible: Calm (Peach)" in text


def test_render_listings_groups_by_name_and_filters_unmatched():
    e = entry("Sours", "Peach")
    listings = [
        {"id": "l1", "dispensary_id": "d1", "scraped_name": "Sours  Peach 10pk", "scraped_category": "edible",
         "variant": "100mg", "product_line": "Sours", "strain": "Peach", "catalog_entry_id": e["id"],
         "catalog_match_method": "exact"},
        {"id": "l2", "dispensary_id": "d2", "scraped_name": "Sours Peach 10pk", "scraped_category": "edible",
         "variant": "100mg", "product_line": "Sours", "strain": "Peach", "catalog_entry_id": e["id"],
         "catalog_match_method": "exact"},
        {"id": "l3", "dispensary_id": "d3", "scraped_name": "Peach Rings", "scraped_category": "edible",
         "variant": "100mg", "product_line": None, "strain": "Peach Rings", "catalog_entry_id": None,
         "catalog_match_method": None},
    ]
    text = cs.render_listings(listings, [e], "(?i)peach")
    assert ("    2  Sours Peach 10pk  · edible · 100mg · Sours / Peach → Sours Peach 10pk 100mg [gummy] "
            "(exact)") in text
    unmatched = cs.render_listings(listings, [e], None, unmatched=True)
    assert "Peach Rings" in unmatched and "Sours Peach 10pk" not in unmatched


def test_render_triage_ranks_catalogs_by_leads():
    catalogs = [{"id": "c1", "brand_name": "Tidy", "source_method": "listings_bootstrap"},
                {"id": "c2", "brand_name": "Messy", "source_method": "listings_bootstrap"}]
    tidy = [entry("Sours", s) for s in ("Peach", "Lime", "Cherry")]
    messy = [dict(entry(l, s), catalog_id="c2") for l, s in
             (("Calm", "Peach"), ("Rest", "Lime"), ("Zen", "Kiwi"), (None, "Peach"), (None, "Calm Lime"))]
    text = cs.render_triage(catalogs, tidy + messy, {})
    rows = text.splitlines()[1:]
    assert rows[0].split()[1] == "Messy" and rows[1].split()[1] == "Tidy"
    assert rows[1].split()[0] == "0"


def test_a_line_in_two_categories_is_flagged_where_it_is_smaller():
    entries = [entry("Live Rosin", s) for s in ("Peach", "Lime", "Kiwi", "Plum")]
    entries += [entry("Live Rosin", "Guava", "vaporizers", "all-in-one", "0.5g")]
    entries += [entry("Sours", s) for s in ("Cherry", "Grape", "Mango")]
    found = cs.leads(cs.products(entries))
    crossing = [(l.category, l.text) for l in found if l.kind == "cross-category"]
    assert crossing == [("vaporizers", 'line "Live Rosin" (Guava) is also a line in edible (4)')]


def test_a_line_named_like_another_brand():
    entries = [entry("Camino", s) for s in ("Peach", "Lime", "Kiwi")]
    found = cs.leads(cs.products(entries), other_brands={"camino": "Camino"})
    assert any("Camino, a brand with its own catalog" in t for t in texts(found, "line-is-brand"))
    catalogs = [{"id": "k", "brand_name": "Kiva"}, {"id": "c", "brand_name": "Camino"},
                {"id": "f", "brand_name": "Flav"}]
    assert cs.brands_but(catalogs, catalogs[0]) == {"camino": "Camino", "flav": "Flav"}


def test_a_line_inside_a_strain_is_one_lead_and_not_strain_noise():
    entries = [entry("Live Resin Infused", s, "preroll", None, "2.5g") for s in ("Kush", "Haze", "Runtz")]
    entries += [entry("Live Resin", s, "vaporizers", "cart", "1g") for s in ("Kush", "Haze", "Runtz")]
    entries += [entry(None, "Live Resin Infused Super Bud", "preroll", None, "2.5g")]
    found = cs.leads(cs.products(entries))
    assert texts(found, "line-in-strain") == ['"Live Resin Infused Super Bud" has no line but its strain '
                                              'contains line "Live Resin Infused"']
    assert texts(found, "strain-word") == []


def test_a_size_that_belongs_to_another_line():
    entries = [entry("Live Resin Infused", s, "preroll", None, v)
               for s in ("Kush", "Haze", "Runtz", "Mints") for v in ("1g", "2.5g")]
    entries += [entry(None, s, "preroll", None, v)
                for s in ("Kush", "Haze", "Runtz", "Mints", "Zkittlez", "Gelato", "Diesel", "Cookies",
                          "Mango", "Lemon") for v in ("1g", "3.5g")]
    entries += [entry(None, "Biscotti", "preroll", None, "2.5g")]
    found = texts(cs.leads(cs.products(entries)), "size-of-other-line")
    assert found == ['Biscotti (no line) 2.5g: the size of "Live Resin Infused" (4 of 4), rare in the '
                     'line-less group (1 of 11)']


def test_a_store_only_size_beside_an_idle_site_product_may_be_a_rename():
    site = [entry(None, s, "vaporizers", "cart", "1g", source="shopify_products_json")
            for s in ("GG4", "Blue Dream", "Gelato")]
    store = [entry(None, "Gorilla Glue", "vaporizers", "cart", "1g", support=3)]
    listings = [{"catalog_entry_id": e["id"], "dispensary_id": f"d{i}"}
                for i, e in enumerate([site[1], site[2], store[0], store[0]])]
    found = cs.leads(cs.products(site + store, listings), storefront=True)
    assert texts(found, "orphan-site") == [
        'store-only "Gorilla Glue" [cart] 1g (2 listings) sits beside site products of its shape that '
        'no listing matched: GG4; renamed on the site?']


def test_store_only_sizes_are_marked_in_show():
    catalog = {"id": "c1", "brand_name": "Acme", "brand_slug": "acme", "source_method": "shopify_products_json",
               "fetched_at": "2026-10-05T05:00:00Z", "source_url": "https://acme.example"}
    entries = [entry(None, "Biscotti", "preroll", None, "1g", source="shopify_products_json"),
               entry(None, "Biscotti", "preroll", None, "2.5g")]
    text = cs.render_show(catalog, entries, [], {})
    assert "1g 2.5g*" in text


def test_listings_flag_a_size_that_differs_from_the_entry():
    e = entry("Core", "Kush", "preroll", None, "1g")
    listing = {"id": "l1", "dispensary_id": "d1", "scraped_name": "Kush Pre-Roll Pack 7pk",
               "scraped_category": "preroll", "variant": "3.5g", "product_line": "Core", "strain": "Kush",
               "catalog_entry_id": e["id"], "catalog_match_method": "jev_review"}
    assert "(jev_review, SIZE DIFFERS)" in cs.render_listings([listing], [e], None)


def test_a_strain_with_half_of_a_format_pair():
    # Florist Farms sells each classic vape strain as a 1g cart and a 1g all-in-one.
    entries = [entry(None, st, "vaporizers", sub, "1g")
               for st in ("Blue Dream", "Gelato", "Jack Herer", "Green Crack") for sub in ("cart", "all-in-one")]
    entries += [entry(None, "GG4", "vaporizers", "cart", "1g")]
    found = cs.leads(cs.products(entries))
    assert texts(found, "missing-pair") == [
        "line-less range sells 4 of 5 strains as all-in-one + cart; only one of the pair: GG4 [cart]"]
    assert "near-dup" not in kinds(found) and "store-copy" not in kinds(found)


def test_a_lines_other_size_filed_without_it():
    entries = [entry("40's", s, "preroll", None, v) for s, v in
               (("Biscotti", "2.5g"), ("Gelato", "1g"), ("Gelato", "2.5g"), ("Runtz", "1g"))]
    entries += [entry(None, "Biscotti", "preroll", None, "1g"),     # 40's has only its 2.5g
                entry(None, "Runtz", "preroll", None, "1g")]        # same size as 40's Runtz: two products
    found = texts(cs.leads(cs.products(entries)), "split-size")
    assert found == ['"Biscotti" 1g has no line; "40\'s Biscotti" comes only in 2.5g. The line\'s other size?']


def test_a_product_whose_store_names_say_another_line():
    """Ruby Farms' White Widow 1.5g was filed under Doobies (one store wrote "Doobies");
    its other store names say "Rose Petal Infused", a line of its own. The two spellings
    of that line, one with the brand's name, read as one."""
    entries = [entry("Doobies", s, "preroll", None, "3.5g") for s in ("Blue Dream", "OG #18", "Wedding Cake")]
    entries += [entry("Doobies", "White Widow", "preroll", None, "1.5g",
                      terms=("ruby farms rose petal infused preroll white widow",
                             "white widow 1 5g rose petal infused pre roll",
                             "doobies white widow rose petal rolled hash infused preroll 1 5g")),
                entry("Rose Petals Infused", "Ghost Train Haze", "preroll", None, "1.5g"),
                entry("Ruby Rose Petal", "Ghost Train Haze #2", "preroll", None, "1.5g")]
    found = cs.leads(cs.products(entries), brand="Ruby Farms")
    assert texts(found, "line-disagrees") == [
        'White Widow (Doobies) 1.5g: 3 of 3 store names say "Ruby Rose Petal", 1 say "Doobies"']
    assert 'lines "Rose Petals Infused" and "Ruby Rose Petal" may be one line' in texts(found, "similar-lines")
    # Without the brand's name, "Ruby" is a word of the line and the two differ.
    assert "similar-lines" not in kinds(cs.leads(cs.products(entries[-2:])))


def test_store_names_are_compared_normalised():
    # Match terms are stored normalised: "40's" arrives as "40 s".
    entries = [entry("40's", s, "preroll", None, "1g") for s in ("Gelato", "Runtz", "Zkittlez")]
    entries += [entry(None, "Orange Sunset", "preroll", None, "1g",
                      terms=("orange sunset 40 s infused pre roll 1g", "40 s orange sunset", "orange sunset"))]
    assert texts(cs.leads(cs.products(entries)), "stray") == [
        'no line, but most of their store names say "40\'s": Orange Sunset 1g 2/3']


def test_mixed_lines_per_format_rare_format_and_idle():
    pods = [entry("Original" if i < 2 else None, f"Strain {i}", "vaporizers", "pod", "1g") for i in range(12)]
    carts = [entry(None, "Tahoe OG", "vaporizers", "cart", "1g")]
    prods = cs.products(pods + carts, [{"catalog_entry_id": pods[0]["id"], "dispensary_id": "d1"}])
    found = cs.leads(prods, listings_known=True)
    assert texts(found, "mixed-lines") == ["10 of 12 pod products have no line, beside named lines Original"]
    assert texts(found, "rare-format")[0].startswith("1 cart product(s) beside 12 of the brand's main format")
    assert texts(found, "idle")[0].startswith("12 product(s) no listing matches now")
    assert "idle" not in kinds(cs.leads(prods))           # triage has no listing counts


def test_freshness():
    now = cs.datetime(2026, 10, 5, tzinfo=cs.timezone.utc)
    assert cs.is_fresh({"last_seen_at": "2026-10-01T10:00:00+00:00"}, now)
    assert not cs.is_fresh({"last_seen_at": "2026-08-29T17:54:09+00:00"}, now)
    assert cs.is_fresh({}, now)


def test_render_lines_counts_words_against_recorded_lines():
    entries = [entry("Original", "Gelato", "vaporizers", "pod", "1g")]
    listings = [{"id": "l1", "dispensary_id": "d1", "scraped_name": "Gelato Original THC Pod | 1g",
                 "product_line": None},
                {"id": "l2", "dispensary_id": "d2", "scraped_name": "Gelato Original Pod",
                 "product_line": "Original"},
                {"id": "l3", "dispensary_id": "d2", "scraped_name": "Gelato LIIIL Pen 0.5g", "product_line": None},
                {"id": "l4", "dispensary_id": "d3", "scraped_name": "Gelato - 1g POD", "product_line": None,
                 "description": "<p>STIIIZY <b>Original</b> pods</p>"}]
    text = cs.render_lines(listings, entries, ["liiil", "ORIGINAL"])
    rows = {r.split()[0]: r.split()[1:] for r in text.splitlines()[1:]}
    # word: in names (listings / stores), recorded as the line, catalog products, only in the description
    assert rows == {"Original": ["2", "/", "2", "1", "1", "1"], "liiil": ["1", "/", "1", "0", "0", "0"]}
    assert text.count("riginal") == 1                     # one row per word, the catalog's spelling


def test_render_preview_diffs_a_rebuild_against_the_catalog():
    catalog = {"id": "c1", "brand_name": "Acme", "source_method": "listings_bootstrap"}
    listings = [{"id": f"l{i}", "dispensary_id": f"d{i}", "scraped_name": "Acme Blue Dream 3.5g",
                 "scraped_brand": "Acme", "scraped_category": "flower", "subtype": "flower",
                 "strain": "Blue Dream", "product_line": None, "variant": "3.5g"} for i in range(2)]
    text = cs.render_preview(catalog, [], listings, fresh_only=True)
    assert "proposes 1 entries; 0 bootstrap entries are active now. +1 new, -0" in text
    assert "  + Blue Dream 3.5g  (2 stores)" in text


def test_preview_counts_a_curated_entry_as_held_and_never_as_retired():
    """catalog_fix.py gives curated entries the bootstrap's ids: a rebuild that proposes
    one updates it, and one that does not leaves it alone."""
    catalog = {"id": "c1", "brand_name": "Acme", "source_method": "listings_bootstrap"}
    listings = [{"id": f"l{i}", "dispensary_id": f"d{i}", "scraped_name": "Acme Blue Dream 3.5g",
                 "scraped_brand": "Acme", "scraped_category": "flower", "subtype": "flower",
                 "strain": "Blue Dream", "product_line": None, "variant": "3.5g"} for i in range(2)]
    curated = [{**entry(None, s, "flower", "flower", "3.5g", source="curated"), "external_id": x}
               for s, x in (("Blue Dream", "lb:flower:flower::bluedream:3.5g"),
                            ("Zangria", "lb:flower:flower::zangria:3.5g"))]   # one store: never proposed
    text = cs.render_preview(catalog, curated, listings, fresh_only=True)
    assert "+0 new, -0 no longer proposed" in text


def test_no_split_size_where_the_lineless_products_are_a_range_of_their_own():
    # Florist Farms: plain 7-packs (3.5g, a size no line uses) beside infused singles.
    entries = [entry("Live Resin Infused", s, "preroll", None, v)
               for s in ("Apple Fritter", "Gelato", "Runtz") for v in ("1g",)]
    entries += [entry(None, s, "preroll", None, "3.5g") for s in ("Apple Fritter", "Kush", "Haze", "Mints")]
    assert texts(cs.leads(cs.products(entries)), "split-size") == []


def test_show_prints_the_sizes_stores_write_per_line():
    catalog = {"id": "c1", "brand_name": "Acme", "brand_slug": "acme", "source_method": "listings_bootstrap",
               "fetched_at": "2026-10-05T05:00:00Z", "source_url": None}
    one, pack = entry("40's", "Biscotti", "preroll", None, "1g"), entry("40's", "Biscotti", "preroll", None, "2.5g")
    listings = ([{"id": f"a{i}", "dispensary_id": f"d{i}", "catalog_entry_id": one["id"], "variant": "1g",
                  "scraped_name": "Biscotti 1g"} for i in range(3)]
                + [{"id": f"b{i}", "dispensary_id": f"d{i}", "catalog_entry_id": pack["id"], "variant": "2.5g",
                    "scraped_name": name} for i, name in enumerate(("Biscotti 0.5g 5-pack", "Biscotti Multi-Pack"))]
                + [{"id": f"c{i}", "dispensary_id": "d9", "catalog_entry_id": pack["id"], "variant": v,
                    "scraped_name": name} for i, (v, name) in enumerate((("4.5g", "Biscotti 5 x 0.9g"),
                                                                          ("4.5g", "Biscotti")))])
    text = cs.render_show(catalog, [one, pack], listings, {})
    # One package written two ways is one size: under the catalog's label when it has
    # one, under the first one seen when it has none.
    assert "stores write: 1g 3/3 · 2.5g 2/2 · 5pk 4.5g 2/1 (no product)" in text


def test_no_split_size_where_the_line_is_defined_by_its_size():
    # STIIIZY: LIIIL is the 0.5g all-in-one; the line-less 1g all-in-ones are the plain range.
    entries = [entry("LIIIL", s, "vaporizers", "all-in-one", "0.5g") for s in ("Biscotti", "Gelato", "Runtz")]
    entries += [entry(None, s, "vaporizers", "all-in-one", "1g") for s in ("Biscotti", "Gelato")]
    entries += [entry("Liquid Diamonds", "Tahoe", "vaporizers", "all-in-one", "1g")]
    assert texts(cs.leads(cs.products(entries)), "split-size") == []


def test_inferred_sizes_stay_out_of_the_shape():
    entries = [entry("Original", "OG", "vaporizers", "pod", "1g"),
               {**entry("Original", "OG", "vaporizers", "pod", "0.5g"), "source": "inferred"}]
    [p] = cs.products(entries)
    assert p.sizes == ["1g"]
