"""Tests for storefront.py — offline: a recipe run over canned site payloads."""

import json
import os
import re
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import storefront  # noqa: E402

FLORIST = storefront.load_recipe("Florist Farms")


def product(pid, title, product_type="", variants=("Default Title",), tags=()):
    return {"id": pid, "title": title, "product_type": product_type, "tags": list(tags),
            "vendor": "Florist Farms", "handle": f"p{pid}", "body_html": "<p>About</p>",
            "variants": [{"id": pid * 10 + i, "title": v} for i, v in enumerate(variants)]}


SITE = [
    product(1, "Calm | Peach Gummies | 10pk", "Gummies"),
    product(2, "Blueberry Lemonade | Live Resin Gummies | 10-Pack", "Gummies"),
    # Typed Flower on the site; the title says pre-roll, and the title decides.
    product(3, "Witches Brew | Live Resin Infused | 1/2 Gram Pre-Rolls | 5pk", "Flower"),
    product(4, "Mule Fuel | Eighth Ounce"),
    product(5, "Mule Fuel | Quarter Ounce", "Flower"),
    product(6, "Jealousy | Live Resin | All-In-One Vape | 1G", "Vapes"),
    product(7, "Northern Lights |  Vape Cartridge | 1 g"),
    product(8, "Green Crack | Kief Coated | Half Gram Pre-Rolls | Single", "Joint"),
    product(9, "Barn Quilt Crewneck", variants=("DARK GREEN / S", "DARK GREEN / M")),
    product(10, "Mystery | Gummies | 20pk", "Gummies"),
    product(11, "Mandarine Dog | Live Resin Infused | Half Gram Pre-Rolls | 5pk", "Joint"),
    product(12, "Strawberries and Cream | 1/2 Gram Pre-Rolls | 7pk", "Flower"),
]


def fake_get(pages):
    calls = []

    def get(url):
        calls.append(url)
        page = int(dict(p.split("=") for p in url.split("?")[1].split("&"))["page"])
        return pages[page - 1] if page <= len(pages) else {"products": []}
    get.calls = calls
    return get


def build(site=SITE):
    items = storefront.shopify(FLORIST["source"], get=fake_get([{"products": site}]))
    return storefront.build(FLORIST, items)


def by_title(doc, report=None):
    return {e["match_terms"][-1]: e for e in doc["entries"]}


def entry(doc, name, variant=None):
    hits = [e for e in doc["entries"] if e["name"] == name and (variant is None or e["variant"] == variant)]
    assert len(hits) == 1, (name, variant, [(e["name"], e["variant"]) for e in doc["entries"]])
    return hits[0]


def test_the_florist_farms_recipe_reads_its_title_shapes():
    doc, report = build()
    calm = entry(doc, "Calm Peach")
    assert (calm["product_line"], calm["strain"], calm["category"], calm["subtype"], calm["variant"]) == \
        ("Calm", "Peach", "edible", "gummy", "10pk 100mg")
    lr = entry(doc, "Live Resin Blueberry Lemonade")
    assert (lr["product_line"], lr["strain"], lr["variant"]) == ("Live Resin", "Blueberry Lemonade", "10pk 100mg")
    wb = entry(doc, "Live Resin Infused Witches Brew")
    assert (wb["category"], wb["subtype"], wb["variant"]) == ("preroll", None, "2.5g")
    assert entry(doc, "Kief Coated Green Crack")["variant"] == "0.5g"
    assert entry(doc, "Strawberries and Cream")["variant"] == "3.5g"
    aio = entry(doc, "Live Resin Jealousy")
    assert (aio["category"], aio["subtype"], aio["variant"]) == ("vaporizers", "all-in-one", "1g")
    cart = entry(doc, "Northern Lights")
    assert (cart["subtype"], cart["variant"]) == ("cart", "1g")
    eighth, quarter = entry(doc, "Mule Fuel", "3.5g"), entry(doc, "Mule Fuel", "7g")
    assert eighth["category"] == "flower" and eighth["subtype"] == "flower"
    # Sizes of one product are one product, so the matcher picks the size inside it.
    assert eighth["product_key"] == quarter["product_key"] == "sf:flower:flower::mulefuel"
    assert eighth["external_id"] == "sf:flower:flower::mulefuel:35g:40"
    assert report["skipped"] == {"apparel": 2}
    assert [u["title"] for u in report["unparsed"]] == ["Mystery | Gummies | 20pk"]
    assert doc["source_method"] == "shopify_products_json" and doc["brand_slug"] == "florist-farms"


def test_shopify_pages_until_a_short_page():
    get = fake_get([{"products": [product(i, f"S{i} | Eighth Ounce", "Flower") for i in range(250)]},
                    {"products": [product(999, "Last | Eighth Ounce", "Flower")]}])
    items = storefront.shopify({"url": "https://shop.example/products.json"}, get=get)
    assert len(items) == 251 and len(get.calls) == 2
    assert "limit=250" in get.calls[0] and "page=2" in get.calls[1]


def test_woocommerce_items_per_variation():
    pages = [[{"id": 1, "name": "Holiday &amp; Co H-Bar", "categories": [{"name": "Vapes"}],
               "tags": [], "permalink": "https://x/h-bar", "short_description": "", "description": "",
               "variations": [{"id": 11, "attributes": [{"name": "size", "value": "0.5g"}]},
                              {"id": 12, "attributes": [{"name": "size", "value": "1g"}]}]},
              {"id": 2, "name": "Plain", "categories": [], "tags": [], "variations": []}]]
    items = storefront.woocommerce({"url": "https://x/wp-json/wc/store/v1/products"},
                                   get=lambda url: pages[0] if "page=1" in url else [])
    assert [(i.id, i.title, i.variant) for i in items] == \
        [("11", "Holiday & Co H-Bar", "0.5g"), ("12", "Holiday & Co H-Bar", "1g"), ("2", "Plain", None)]
    assert items[0].fields["product_type"] == "Vapes"


@pytest.mark.parametrize("change,message", [
    ({"source": {"kind": "ftp", "url": "x"}}, "source.kind"),
    ({"category": [{"when": {"colour": "x"}, "set": {"category": "flower"}}]}, "unknown field"),
    ({"category": [{"when": {"title": "("}, "set": {"category": "flower"}}]}, "category[0].when.title"),
    ({"category": [{"set": {"category": "flowers"}}]}, "is not one of"),
    ({"title": [{"match": "(?P<brand>x)"}]}, "groups other than"),
    ({"skip": [{"when": {"category": "x"}}]}, "unknown field"),
])
def test_a_bad_recipe_fails_on_load_naming_the_rule(change, message):
    with pytest.raises(SystemExit, match=re.escape(message)):
        storefront.validate({**FLORIST, **change})


def listing(store, name, strain, category, variant, line=None, subtype=None):
    return {"id": str(uuid.uuid4()), "dispensary_id": store, "name": name, "brand": "Florist Farms",
            "category": category, "subtype": subtype, "strain": strain, "product_line": line,
            "variant": variant}


def test_stores_fill_in_only_what_the_site_lacks():
    doc, _ = build()
    stores = [
        # The site's "Mandarine Dog" and "Strawberries and Cream", spelled the stores' way.
        *[listing(s, "Mandarin Dog LRI 5pk", "Mandarin Dog", "preroll", "2.5g") for s in ("a", "b")],
        *[listing(s, "Strawberries & Cream 7pk", "Strawberries & Cream", "preroll", "3.5g") for s in ("a", "b")],
        # Not on the site at all.
        *[listing(s, "Gorilla Glue AIO 1g", "Gorilla Glue", "vaporizers", "1g", subtype="all-in-one")
          for s in ("a", "b", "c")],
        # A longer strain name is a different product, not a spelling.
        *[listing(s, "Jealousy Haze AIO 1g", "Jealousy Haze", "vaporizers", "1g", "Live Resin",
                  "all-in-one") for s in ("a", "b")],
        # Same name, a size the site does not list.
        *[listing(s, "Mule Fuel 14g", "Mule Fuel", "flower", "14g", subtype="flower") for s in ("a", "b")],
    ]
    found, only_stores, terms = storefront.split_store_products(doc, stores)
    assert sorted(e["name"] for e in found) == ["Mandarin Dog", "Strawberries & Cream"]
    assert sorted((e["name"], e["variant"]) for e in only_stores) == \
        [("Gorilla Glue", "1g"), ("Live Resin Jealousy Haze", "1g"), ("Mule Fuel", "14g")]
    pushed = storefront.with_store_products(doc, only_stores, terms)
    assert len(pushed["entries"]) == len(doc["entries"]) + 3
    assert {e["source"] for e in pushed["entries"]} == {"shopify_products_json", "listings_bootstrap"}
    # The stores' names for a site product travel with it, so those listings stay exact.
    dog = next(e for e in pushed["entries"] if e["strain"] == "Mandarine Dog")
    assert "mandarin dog lri 5pk" in dog["match_terms"]


def test_a_store_product_matching_two_site_products_brings_no_names():
    doc, _ = build(SITE + [product(20, "Mule Fuel | 1 Gram Pre-Roll | Single", "Joint"),
                           product(21, "Mule Fuel | Live Resin Infused | 1 Gram Pre-Roll | Single", "Joint")])
    stores = [listing(s, "Mule Fuel Preroll 1g", "Mule Fuel", "preroll", "1g") for s in ("a", "b")]
    found, only_stores, terms = storefront.split_store_products(doc, stores)
    assert [e["name"] for e in found] == ["Mule Fuel"] and not only_stores and terms == {}


def test_a_push_is_refused_when_the_site_changed_shape():
    doc, report = build()
    assert storefront.refusal(report) is None                       # 1 of 10 handled items
    broken = [product(100 + i, f"New Layout {i}", "Joint") for i in range(5)]
    _, report = build(SITE + broken)
    assert "no rule handled" in storefront.refusal(report)
    _, report = build([product(9, "Barn Quilt Crewneck")])
    assert storefront.refusal(report) == "no entries"


def test_every_recipe_in_the_repo_loads():
    recipes = storefront.all_recipes()
    assert recipes and all(r["brand"] for r in recipes)
    assert {storefront.recipe_path(r["brand"]).name for r in recipes} == \
        {p.name for p in storefront.RECIPE_DIR.glob("*.json")}
    json.dumps(recipes)                                              # plain data throughout
