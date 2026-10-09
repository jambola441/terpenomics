"""Hardware and papers in brand catalogs (merch_catalog.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_match as cm  # noqa: E402
import merch_catalog as mc  # noqa: E402


def l(i, store, name, category="merch", subtype=None):
    return {"id": i, "dispensary_id": store, "name": name, "category": category, "subtype": subtype}


def test_a_paper_size_is_width_count_and_tips():
    assert mc.parse_size("king size 32ct") == mc.MerchSize("king size", 32, False)
    assert mc.parse_size("1 1/4 50pk w/tips") == mc.MerchSize("1 1/4", 50, True)
    assert mc.parse_size("1 1/4 50pk w/tips").label() == "1 1/4 50ct w/tips"
    assert mc.same_size(mc.parse_size("king size"), mc.parse_size("king size 32ct"))       # open count
    assert not mc.same_size(mc.parse_size("king size 32ct"), mc.parse_size("1 1/4 32ct"))
    assert not mc.same_size(mc.parse_size("king size 32ct w/tips"), mc.parse_size("king size 32ct"))


def test_the_reading_is_the_rules():
    r = mc.reading("Blazy Susan Pink King Size Papers 32ct", "Blazy Susan", "paper")
    assert (r["subtype"], r["colour"], r["size"]) == ("paper", "Pink", "king size 32ct")
    # A name with no format word takes its line's; a vape-filed device is hardware.
    assert mc.reading("PAX Flow | Onyx", "PAX", "merch")["subtype"] == "battery"
    assert mc.is_merch("vaporizers", "all-in-one", "PAX Plus | Onyx", "PAX")
    assert mc.is_merch("vaporizers", "all-in-one", "Pax - Four Vaporizer - Greenstone", "PAX")
    assert not mc.is_merch("vaporizers", "pod", "PAX | Blue Dream | Live Rosin | Pod", "PAX")


def test_papers_need_two_stores_and_partial_sizes_fold_in():
    rows = [l(1, "A", "RAW Classic King Size Cones 3pk"), l(2, "B", "Raw | Cones | Classic | 3 Pack | King Size"),
            l(3, "C", "RAW - King Size Classic Cones"),                          # partial: folds into 3pk
            l(4, "A", "RAW Classic 1 1/4 Cones 6pk")]                            # one store: out
    es = mc.propose_entries("RAW", rows)
    assert [(e["name"], e["variant"], e["support"]) for e in es] == [("Classic Cones", "king size 3ct", 3)]


def test_hardware_with_a_curated_line_is_admitted_on_one_store():
    es = mc.propose_entries("PAX", [l(1, "A", "Era Go | Battery | Gold"), l(2, "A", "Unbranded Battery Gold")])
    assert [(e["name"], e["attributes"]) for e in es] == [("Era Go Gold Battery", {"colour": "Gold"})]


def test_the_matcher_joins_merch_on_its_attributes():
    entries = mc.propose_entries("PAX", [l(1, "A", "Era Go | Battery | Gold"), l(2, "B", "PAX | Era Go | Rechargeable Battery (Black)")])
    catalog = {"brand_name": "PAX", "entries": [{**e, "id": e["external_id"]} for e in entries]}
    listings = [{"id": 9, "name": "Pax - Era Go Battery - Gold", "category": "merch", "subtype": "battery"},
                {"id": 8, "name": "Pax - Era Go Battery - Sky", "category": "merch", "subtype": "battery"}]
    gold, sky = cm.resolve(catalog, listings, use_jev=False)
    assert (gold.method, gold.entry["name"]) == ("attributes", "Era Go Gold Battery")
    assert sky.method == "none"                                   # no Sky in the catalog


def test_a_brands_unlined_paper_is_its_default_line_and_black_is_a_line():
    r = mc.reading("Raw - King Size Rolling Papers", "RAW", "paper")
    assert (r["product_line"], r["colour"]) == ("Classic", None)
    r = mc.reading("RAW - Black Classic Rolling Paper KS Slim - 32ct", "RAW", "paper")
    assert (r["product_line"], r["colour"], r["size"]) == ("Black", None, "king size 32ct")
    # Connoisseur comes with tips whether or not the name says so.
    assert mc.reading("RAW Classic Connoisseur KS 33ct", "RAW", "paper")["size"] == "king size 33ct w/tips"


def test_a_site_page_gives_its_widths_times_its_retail_counts():
    body = ("RAW Classic 1¼ Cones are available in a 6 Cone Pack, 32 Cone Pack, 500 bulk box, "
            "600 bulk box and 900 Bulk Box.")
    got = mc.site_sizes("RAW Classic 1¼ Cones", "RAWCONE1, RAWCONE500", body, "Classic")
    assert sorted(s.label() for s in got) == ["1 1/4 32ct", "1 1/4 6ct"]
    got = mc.site_sizes("RAW Classic Kingsize", "RAWKSBULK5800, RAWKSWIDE, RAWK-SSLIM",
                        "available in Slim, Wide and in 5800 sheet bulk size.", "Classic")
    assert sorted(s.label() for s in got) == ["king size", "ks wide"]


def test_a_partial_size_a_complete_one_covers_is_folded():
    sizes = [mc.parse_size(x) for x in ("king size 32ct", "32ct", "king size", "20ct")]
    assert sorted(s.label() for s in mc.fold_partial(sizes)) == ["20ct", "king size 32ct"]


def test_a_listing_with_no_size_takes_the_size_less_entry():
    entries = [{"id": i, "product_key": "tips", "category": "merch", "subtype": "filter-tip",
                "product_line": None, "variant": v} for i, v in ((1, "21ct"), (2, None))]
    r = {"subtype": "filter-tip", "product_line": None, "colour": None, "size": None}
    assert mc.join(entries, r)["id"] == 2
    assert mc.join(entries, dict(r, size="21ct"))["id"] == 1


def test_a_brands_retail_counts_pick_each_widths_count():
    # A page naming two widths and two counts is two sizes, not four.
    counts = {"1 1/4": [50], "king size": [32]}
    got = mc.site_sizes("RAW Ethereal", "RAWKSSLIM-ETH, RAW-114-ETH", "50 leaves per pack. 32 leaves per pack.",
                        "Ethereal", counts)
    assert {x.label() for x in got} == {"1 1/4 50ct", "king size 32ct"}
    # A line that differs, and a count the title states, win.
    assert [x.label() for x in mc.site_sizes("RAW Creaseless 1¼", "", "", "Classic Creaseless",
                                             {"1 1/4": [50], "Classic Creaseless 1 1/4": [300]})] == ["1 1/4 300ct"]
    assert [x.label() for x in mc.site_sizes("Unbleached 1¼ Cones 32 Pack", "", "", "Unbleached",
                                             {"1 1/4": [6]})] == ["1 1/4 32ct"]


def test_stores_count_the_cover_leaf():
    assert mc.same_size(mc.parse_size("king size 33ct"), mc.parse_size("king size 32ct"))
    assert not mc.same_size(mc.parse_size("king size 3ct"), mc.parse_size("king size 4ct"))


def test_widths_stores_write():
    for name, size in [("RAW | Classic 1¼ Rolling Papers", "1 1/4"), ("RAW | King Classic Cones", "king size"),
                       ("OCB Bamboo Rolling Papers - Slim", "king size"), ("X-Pert Slim Fit Rolling Papers", "king size"),
                       ("Bamboo Mini Cones", "mini"), ("RAW Lemonade King Wide Papers", "ks wide"),
                       ("King Palm Wraps", None)]:
        assert mc.parse_size(mc._MERCH.variant(name, None)).width == size, name


def test_cone_tips_and_tip_booklets_are_tips_without_a_width():
    for name in ("Pre-Rolled Perfecto Cone Tips", "Raw - Original Tips Booklet - 50ct", "RAW | Slim Pre Rolled Tips"):
        r = mc.reading(name, "RAW", "cone")
        assert r["subtype"] == "filter-tip", name
        assert mc.parse_size(r["size"]).width is None


def test_a_lines_packaging_colour_is_no_colour():
    assert mc.reading("1 1/4 x 6pk Yellow Classic Cones", "RAW", "cone")["colour"] is None
    # The colour word is part of the line's spelling: OCB's "Organic Unbleached Hemp".
    r = mc.reading("OCB - Organic Unbleached Hemp King Size Cones - 3pk", "OCB", "cone")
    assert (r["product_line"], r["colour"]) == ("Organic Hemp", None)


def test_a_stores_size_of_a_site_product_joins_it():
    import storefront as sf
    site = {"brand_name": "RAW", "entries": [{
        "external_id": "sf:merch:paper:classicconnoisseur:::1141450ctwtips:1", "product_key": "sf:merch:paper:classicconnoisseur::",
        "name": "Classic Connoisseur Papers", "product_line": "Classic Connoisseur", "category": "merch",
        "subtype": "paper", "strain": None, "variant": "1 1/4 50ct w/tips", "attributes": None, "match_terms": []}]}
    listings = [l(1, "a", "Raw Classic Connoisseur Papers King Size 32ct"), l(2, "b", "Classic Connoisseur KS Slim Papers 32ct"),
                l(3, "a", "Raw Classic Connoisseur 1 1/4 Papers 50ct"), l(4, "b", "Classic Connoisseur 1 1/4 Papers 50ct")]
    found, only, _ = sf.split_store_products(site, listings)
    assert [e["variant"] for e in found] == ["1 1/4 50ct w/tips"]
    assert [(e["product_key"], e["variant"]) for e in only] == [(site["entries"][0]["product_key"], "king size 32ct w/tips")]
