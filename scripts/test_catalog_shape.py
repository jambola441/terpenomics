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
    strays = texts(found, "stray")
    assert any('same strain as a product in "Live Resin": Gelato' in t for t in strays)
    assert any('say "Live Resin": Mimosa 2/3' in t for t in strays)
    assert any("Live Resin Haze" in t for t in texts(found, "line-in-strain"))


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
    assert sorted(dups) == ['"Original Grand Daddy Purple" and "Original Granddaddy Purple" may be one product',
                            '"Original Skywalker" and "Original Skywalker OG" may be one product']


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
    assert "    2  Sours Peach 10pk  · edible · 100mg · Sours / Peach → Sours Peach 10pk 100mg (exact)" in text
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
