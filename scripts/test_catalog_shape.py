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
