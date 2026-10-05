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
    # Store names travel with an exact match only: "Mandarin Dog" is a spelling of the
    # site's "Mandarine Dog" — or a different strain; the model decides those listings.
    dog = next(e for e in pushed["entries"] if e["strain"] == "Mandarine Dog")
    assert "mandarin dog lri 5pk" not in dog["match_terms"]
    cream = next(e for e in pushed["entries"] if e["strain"] == "Strawberries and Cream")
    assert "strawberries and cream 7pk" in cream["match_terms"]


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


def test_wordpress_posts_with_embedded_terms():
    page = [{"id": 7, "title": {"rendered": "Mango Haze &#8211; 2G Palm"}, "link": "https://hk.example/p/7",
             "content": {"rendered": "<p>WEIGHT: 2g</p>"}, "excerpt": {"rendered": ""},
             "class_list": ["post-7", "product_cat-palms"], "acf": {"weight": "2g"},
             "_embedded": {"wp:term": [[{"name": "Palms"}], [{"name": "Sativa"}]]}}]
    items = storefront.wordpress({"url": "https://hk.example/wp-json/wp/v2/product"}, get=lambda u: page if "page=1" in u else [])
    [it] = items
    assert it.title == "Mango Haze – 2G Palm" and it.fields["tags"] == "Palms, Sativa"
    assert it.fields["product_type"] == "post-7 product_cat-palms" and json.loads(it.fields["meta"]) == {"weight": "2g"}


def test_html_cards_across_pages_stop_at_the_first_empty_one():
    card = '<div class="card"><a href="/p/{n}"><h3>{t}</h3></a><span class="cat">Pre-Roll</span></div>'
    pages = {"page=1": "".join(card.format(n=i, t=f"Strain {i} | 1g") for i in range(3)),
             "page=2": card.format(n=9, t="Strain 9 | 1g"),
             "page=3": "<p>nothing</p>"}
    src = {"kind": "html", "url": "https://x.example/products", "pages": {"param": "page", "from": 1, "to": 5},
           "item": "div.card", "fields": {"title": "h3", "url": "a@href", "product_type": ".cat"}}
    items = storefront.html_cards(src, get_text=lambda url, post=None: next(
        (t for k, t in pages.items() if k in url), ""))
    assert [i.title for i in items] == ["Strain 0 | 1g", "Strain 1 | 1g", "Strain 2 | 1g", "Strain 9 | 1g"]
    assert items[0].id == "https://x.example/p/0" and items[0].fields["product_type"] == "Pre-Roll"


def test_json_from_a_blob_a_page_embeds_lenient():
    page = '<script>window.catalog = {products: [{name: "Afghani", line: "FJ-Mini", size: "0.6g"},' \
           ' {name: "", line: "x"}]};</script>'
    src = {"kind": "json", "url": "https://j.example/", "extract": r"window\.catalog = (\{.*?\});",
           "lenient": True, "items": "products.*",
           "fields": {"title": "name", "product_type": "line", "variant": "size"}}
    pytest.importorskip("json5")
    [it] = storefront.json_items(src, get_text=lambda url, post=None: page)
    assert (it.title, it.variant, it.fields["product_type"]) == ("Afghani", "0.6g", "FJ-Mini")


def test_extract_reads_a_size_from_the_description():
    recipe = storefront.validate({
        "brand": "Off Hours", "source": {"kind": "shopify_json", "url": "https://oh.example/products.json"},
        "category": [{"set": {"category": "edible", "subtype": "gummy"}}],
        "title": [{"match": "^(?P<line>\\w+) (?P<strain>.+) Gummies$",
                   "extract": {"body": "SIZE:\\s*(?P<size>\\d+\\s*CT)\\s+STRENGTH:\\s*(?P<size2>\\d+\\s*MG)"}}]})
    items = storefront.shopify(recipe["source"], get=fake_get([{"products": [
        dict(product(1, "Offline Grape Punch Gummies"), body_html="<p>SIZE: 10CT STRENGTH: 100MG THC</p>")]}]))
    doc, report = storefront.build(recipe, items)
    [e] = doc["entries"]
    assert (e["product_line"], e["strain"], e["variant"]) == ("Offline", "Grape Punch", "10pk 100mg")


def test_repeats_collapse_and_capitals_can_be_title_cased():
    recipe = storefront.validate({
        "brand": "7 SEAZ", "title_case": True,
        "source": {"kind": "shopify_json", "url": "https://s.example/products.json"},
        "category": [{"set": {"category": "preroll"}}],
        "title": [{"match": "^(?P<line>[A-Z ]+?) - (?P<strain>.+?) (?P<size>[\\d.]+G)"}]})
    lots = [product(1, "TIDAL WAVES - SFV OG 3G Lot 1"), product(2, "TIDAL WAVES - SFV OG 3G Lot 2"),
            product(3, "TIDAL WAVES - SFV OG 1.2G Lot 1")]
    doc, report = storefront.build(recipe, storefront.shopify(recipe["source"], get=fake_get([{"products": lots}])))
    assert sorted((e["name"], e["variant"]) for e in doc["entries"]) == \
        [("Tidal Waves SFV OG", "1.2g"), ("Tidal Waves SFV OG", "3g")]
    assert report["duplicates_collapsed"] == 1
    three = next(e for e in doc["entries"] if e["variant"] == "3g")
    assert {"tidal waves sfv og 3g lot 1", "tidal waves sfv og 3g lot 2"} <= set(three["match_terms"])


def test_title_case_leaves_acronyms_and_codes():
    assert storefront._title_case("KEY LIME PIE") == "Key Lime Pie"
    assert storefront._title_case("SFV OG x MAC 1") == "SFV OG x MAC 1"
    assert storefront._title_case("SF16 FUJI FIG (GMO)") == "SF16 Fuji Fig (GMO)"
    assert storefront._title_case("Blue Dream") == "Blue Dream"


def test_store_aliases_map_a_store_line_and_name_to_the_sites():
    doc, _ = build()
    stores = [*[listing(s, "Calm Peach Gummies 100mg", "Peach", "edible", "10pk 100mg", line="Chill",
                        subtype="gummy") for s in ("a", "b")],
              *[listing(s, "Cauldron Brew 5pk", "Cauldron Brew", "preroll", "2.5g", line="Live Resin Infused")
                for s in ("a", "b")]]
    found, only_stores, _ = storefront.split_store_products(doc, stores)
    assert sorted(e["name"] for e in only_stores) == ["Chill Peach", "Live Resin Infused Cauldron Brew"]
    aliases = {"lines": {"chill": "Calm"}, "names": {"Cauldron Brew": "Witches Brew"}}
    found, only_stores, terms = storefront.split_store_products(doc, stores, aliases)
    assert not only_stores and len(found) == 2
    with pytest.raises(SystemExit, match="only lines and names"):
        storefront.validate({**FLORIST, "store_aliases": {"sizes": {}}})


def test_a_missing_page_costs_its_product_and_most_pages_missing_fails():
    import urllib.error
    pages = {"/p/1": "<h1>A | 1g</h1>", "/p/2": None, "/p/3": "<h1>C | 1g</h1>"}

    def get(url, post=None):
        if url.endswith("sitemap.xml"):
            return "".join(f"<loc>https://s.example{p}</loc>" for p in pages)
        text = pages[url.replace("https://s.example", "")]
        if text is None:
            raise urllib.error.HTTPError(url, 404, "gone", {}, None)
        return text
    src = {"kind": "html", "sitemap": {"url": "https://s.example/sitemap.xml", "match": "/p/"},
           "fields": {"title": "h1"}}
    items = storefront.html_cards(src, get_text=get)
    assert [i.title for i in items] == ["A | 1g", "C | 1g"]
    assert items[0].fields["page"] == "https://s.example/p/1"
    pages["/p/3"] = None
    with pytest.raises(RuntimeError, match="2 of 3 pages failed"):
        storefront.html_cards(src, get_text=get)


def test_a_dropped_connection_is_retried(monkeypatch):
    import io
    import urllib.error
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(req, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.URLError(ConnectionResetError("reset"))
        return Resp(b'{"ok": true}')
    monkeypatch.setattr(storefront.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert storefront._get_json("https://flaky.example/x") == {"ok": True} and len(calls) == 3

    def not_found(req, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 404, "no", {}, None)
    calls.clear()
    monkeypatch.setattr(storefront.urllib.request, "urlopen", not_found)
    with pytest.raises(urllib.error.HTTPError):
        storefront._get_json("https://flaky.example/x")
    assert len(calls) == 1                                           # a 4xx is an answer


def test_store_products_need_the_same_subtype_and_a_repeat_name_is_one():
    doc, _ = build(SITE + [product(30, "Hash Burger x Hash Burger | 1 Gram Pre-Roll | Single", "Joint")])
    stores = [*[listing(s, "Northern Lights AIO 1g", "Northern Lights", "vaporizers", "1g",
                        subtype="all-in-one") for s in ("a", "b")],
              *[listing(s, "Hash Burger 1g", "Hash Burger", "preroll", "1g") for s in ("a", "b")]]
    found, only_stores, terms = storefront.split_store_products(doc, stores)
    assert [e["name"] for e in only_stores] == ["Northern Lights"]     # the site's is a cart
    assert [e["name"] for e in found] == ["Hash Burger"] and len(terms) == 1


def test_paged_sources_stop_at_the_first_missing_page_and_can_post_the_page():
    import urllib.error
    seen = []

    def get(url, post=None):
        seen.append((url, post))
        n = int(post.split("=")[-1])
        if n > 2:
            raise urllib.error.HTTPError(url, 404, "past the end", {}, None)
        return f'<div class="p"><h3>Strain {n} | 1g</h3></div>'
    src = {"kind": "html", "url": "https://r.example/wp-admin/admin-ajax.php",
           "pages": {"param": "page", "from": 1, "to": 9, "in_post": True},
           "post": "action=load_more_products&page={page}", "item": "div.p", "fields": {"title": "h3"}}
    items = storefront.html_cards(src, get_text=get)
    assert [i.title for i in items] == ["Strain 1 | 1g", "Strain 2 | 1g"]
    assert [p for _, p in seen] == [f"action=load_more_products&page={n}" for n in (1, 2, 3)]


def test_discover_reads_the_data_url_off_a_page(monkeypatch):
    pages = {"https://d.example/coa": "<script>DATA = ['/s/1790_master.js'];</script>",
             "https://d.example/s/1790_master.js": '{"rows": [{"name": "GELATO", "size": "3.5 GRAM BAGS"}]}'}
    monkeypatch.setattr(storefront, "_get_text", lambda url, post=None: pages[url])
    recipe = storefront.validate({
        "brand": "Dank", "source": {"kind": "json", "items": "rows.*",
                                    "discover": {"url": "https://d.example/coa", "match": "'(/s/\\d+_master\\.js)'"},
                                    "fields": {"title": "name", "variant": "size"}},
        "category": [{"set": {"category": "flower"}}], "title": [{"match": "^(?P<strain>.+)$"}]})
    [item] = storefront.fetch(recipe)
    assert (item.title, item.variant) == ("GELATO", "3.5 GRAM BAGS")


def test_older_than_rolls_with_the_date():
    from datetime import date
    spec = {"field": "meta", "days": 365}
    today = date(2026, 10, 5)
    assert not storefront._older(spec, {"meta": "tested 2026-01-02"}, today)
    assert storefront._older(spec, {"meta": "2025-10-04"}, today)
    assert storefront._older(spec, {"meta": "no date"}, today)          # undated is hidden too


def test_a_cross_is_the_same_either_way_round_and_gram_packs_read():
    a = storefront._names({"strain": "Napa x Strawberry Lemonade"})
    b = storefront._names({"strain": "Strawberry Lemonade x Napa"})
    assert storefront._name_match(a, b) == "exact"
    import sizes
    assert sizes.parse("5 x 0.5 gram Pre-Rolls", category="preroll") == \
        sizes.Size(grams=2.5, pack=5, unit_g=0.5)


def test_store_listings_leave_out_stale_menus(monkeypatch):
    import db_http
    asked = []
    monkeypatch.setattr(db_http, "select_all", lambda table, query: asked.append(query) or [])
    storefront.store_listings("Florist Farms", via_http=True)
    assert "&or=(last_seen_at.gte." in asked[0]


def test_the_fake_rest_api_models_the_freshness_filter():
    from conftest import RestOverPostgres
    cols, where, args, _ = RestOverPostgres._parse(
        "select=id&is_active=is.true&or=(last_seen_at.gte.2026-09-14T13:00:00Z,last_seen_at.is.null)")
    assert where == " WHERE is_active IS TRUE AND (last_seen_at >= %s OR last_seen_at IS NULL)"
    assert args == ["2026-09-14T13:00:00Z"]


def test_a_draft_recipe_can_be_checked_but_not_pushed(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["storefront.py", "push", "--recipe", "draft.json"])
    with pytest.raises(SystemExit, match="--recipe is for check"):
        storefront.main()


def test_strain2_joins_a_split_product_name():
    recipe = storefront.validate({
        "brand": "Camino", "site": "https://example.com",
        "source": {"kind": "shopify_json", "url": "https://example.com/products.json"},
        "category": [{"when": {"title": "."}, "set": {"category": "edible", "subtype": "gummy"}}],
        "title": [{"when": {"category": "^edible$"},
                   "match": "^10mg\\b[^']*'(?P<strain>[^']+)'\\s*(?P<strain2>.+)$",
                   "set": {"line": "Sours", "size": "10pk 100mg"}}]})
    doc, report = storefront.build(recipe, [storefront.Item("1", "10mg: 10mg CBN 'Deep Sleep' Blackberry Dream",
                                                            "", {"title": "10mg: 10mg CBN 'Deep Sleep' Blackberry Dream"})])
    (e,) = doc["entries"]
    assert (e["product_line"], e["strain"], e["name"]) == ("Sours", "Deep Sleep Blackberry Dream",
                                                            "Sours Deep Sleep Blackberry Dream")


def test_store_listings_leave_a_sub_brand_to_its_own_catalog(monkeypatch):
    import db_http
    rows = [{"id": 1, "dispensary_id": 1, "scraped_name": "KIVA Camino - Chews - Boysenberry", "scraped_brand": "Kiva"},
            {"id": 2, "dispensary_id": 1, "scraped_name": "Kiva Bar - Churro Milk Chocolate", "scraped_brand": "Kiva"}]
    monkeypatch.setattr(db_http, "select_all", lambda table, query: rows)
    assert [l["name"] for l in storefront.store_listings("Kiva", via_http=True)] == ["Kiva Bar - Churro Milk Chocolate"]
