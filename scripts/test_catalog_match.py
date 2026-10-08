"""Offline tests for catalog_match.py and sizes.py — Jev is faked."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_match as cm  # noqa: E402
import jev  # noqa: E402
import sizes  # noqa: E402


def catalog(*entries):
    return {"brand_name": "Ayrloom", "brand_slug": "ayrloom", "entries": [
        {"id": f"e{i}", "product_key": e.get("pk", e["name"] + "|" + (e.get("category") or "")),
         "is_active": True, **e} for i, e in enumerate(entries)]}


AYRLOOM = catalog(
    {"name": "island time", "category": "edible", "subtype": "gummy", "strain": "Island Time",
     "variant": "100mg"},
    {"name": "pineapple mango", "category": "edible", "subtype": "beverage",
     "strain": "Pineapple Mango", "variant": "10mg"},
    {"name": "honeycrisp", "category": "vaporizers", "variant": "1g", "pk": "hc-vape"},
    {"name": "honeycrisp", "category": "edible", "subtype": "beverage", "variant": "10mg", "pk": "hc-bev"},
    {"name": "mood: bliss", "category": "vaporizers", "product_line": "Mood", "strain": "Bliss",
     "variant": "1g"},
    {"name": "lychee dream", "category": "preroll", "variant": "5 Pack | 0.6g each", "pk": "ld-5"},
    {"name": "lychee dream", "category": "preroll", "variant": "1g", "pk": "ld-1"},
)


def test_a_store_name_matches_with_or_without_the_brand():
    """Recorded store names are kept brand-less (catalog_bootstrap); most stores put
    the brand in. Both are the store's own name for the product."""
    idx = cm.CatalogIndex(catalog({"name": "mood: bliss", "category": "vaporizers",
                                   "product_line": "Mood", "strain": "Bliss", "variant": "1g",
                                   "match_terms": ["mood bliss 1g all in one"]}))
    for name in ("Mood Bliss 1g All-In-One", "Ayrloom | Mood Bliss 1g All-In-One",
                 "AYRLOOM - Mood: Bliss 1g All in One"):
        assert idx.exact(name, "vaporizers")[1] == "exact", name
    assert idx.exact("Ayrloom Mood Bliss 1g All-In-One Rechargeable", "vaporizers")[1] == "none"


class TestSizes:
    @pytest.mark.parametrize("texts,cat,expect", [
        (("0.6g", "FJ-Mini Infused Pre-roll | 0.6G"), "preroll", sizes.Size(grams=0.6)),
        (("", "Jetpacks | FJ-3 | .6g | 5 Pack | 3g | THC 37.83%"), "preroll", sizes.Size(grams=3.0, pack=5)),
        (("", "Blueberry Pancakes 5pk x 0.6g - 3.0g"), "preroll", sizes.Size(grams=3.0, pack=5, unit_g=0.6)),
        (("10mg / 10 pack",), "edible", sizes.Size(mg=100.0, pack=10)),
        (("", "Wyld Gummies 100mg 10pk"), "edible", sizes.Size(mg=100.0, pack=10)),
        (("", "Kiva 20MG x 2PK"), "edible", sizes.Size(mg=40.0, pack=2)),
        (("1/8oz",), "flower", sizes.Size(grams=3.5)),
        (("", "Half Ounce Smalls"), "flower", sizes.Size(grams=14.0)),
        (("", "Blue Dream 1/8 Ounce"), "flower", sizes.Size(grams=3.5)),
        (("", "Eighth Ounce Flower"), "flower", sizes.Size(grams=3.5)),
        (("", "Quarter Ounce"), "flower", sizes.Size(grams=7.0)),
        (("500mg",), "vaporizers", sizes.Size(grams=0.5)),
        (("", "Sweet Plum 1:3 | 100MG"), "edible", sizes.Size(mg=100.0)),
        (("", "Black Scotti | 1/2 Gram Pre-Rolls | 7pk"), "preroll", sizes.Size(grams=3.5, pack=7)),
        (("", "King Sherb | Half Gram Pre-Rolls | 5pk"), "preroll", sizes.Size(grams=2.5, pack=5)),
        (("", "Green Crack | Kief Coated | Half Gram Pre-Rolls | Single"), "preroll",
         sizes.Size(grams=0.5)),
        (("0.5g", "STIIIZY - Half Gram Premium Pod - 0.5g"), "vaporizers", sizes.Size(grams=0.5)),
        (("", "Iced Sangria | 1/2g Joints | 7pk"), "preroll", sizes.Size(grams=3.5, pack=7)),
        (("", "Doobies 0.6g | 0.6g | 5pk"), "preroll", sizes.Size(grams=3.0, pack=5)),
    ])
    def test_parse(self, texts, cat, expect):
        assert sizes.parse(*texts, category=cat) == expect

    @pytest.mark.parametrize("size,cat", [
        (sizes.Size(mg=40.0, pack=2), "edible"),
        (sizes.Size(mg=20.0, pack=2), "edible"),
        (sizes.Size(mg=100.0, pack=10), "edible"),
        (sizes.Size(grams=3.0, pack=5), "preroll"),
        (sizes.Size(grams=0.5, pack=5), "preroll"),
    ])
    def test_a_label_reads_back_as_written(self, size, cat):
        assert sizes.parse(size.label(), category=cat) == size

    def test_a_bare_total_is_the_same_package_as_its_label(self):
        # Catalog entries write "2pk 40mg"; stores write "40mg" for the same package.
        assert sizes.same_size(sizes.parse("40mg", category="edible"),
                               sizes.parse("2pk 40mg", category="edible")) is True
        # Store text is still read as store text: a dose beside a pack is per piece
        # while the package stays under the cap.
        assert sizes.parse("Dreamberry | 20mg | 2pk", category="edible") == sizes.Size(mg=40.0, pack=2)

    def test_a_lone_dose_beside_a_pack_may_be_either_reading(self):
        per_piece = sizes.parse("10mg", "1906 - Bliss Drops 2pk - 10mg", category="edible")
        in_all = sizes.parse("20mg", "Bliss Drops 2-pack", category="edible")
        label = sizes.parse("2pk 20mg", category="edible")
        assert sizes.same_size(per_piece, label) is True
        assert sizes.same_size(in_all, label) is True
        # Only against the same pack count: ten pieces are not a single.
        assert sizes.same_size(sizes.parse("Gummies 10pk 10mg", category="edible"),
                               sizes.parse("10mg", category="edible")) is False
        # An explicit per-piece form is not a guess.
        assert sizes.parse("Kiva 2pk x 20mg", category="edible").alt_mg is None

    def test_the_first_reading_picks_the_entry_when_both_fit(self):
        idx = cm.CatalogIndex(catalog(
            {"name": "dreamberry", "category": "edible", "variant": "2pk 20mg", "pk": "db"},
            {"name": "dreamberry", "category": "edible", "variant": "2pk 40mg", "pk": "db"}))
        assert idx.pick_entry("db", "", "edible", "Dreamberry | 20mg | 2pk")["variant"] == "2pk 40mg"
        assert idx.pick_entry("db", "20mg", "edible", "Dreamberry")["variant"] == "2pk 20mg"

    def test_same_size(self):
        assert sizes.same_size(sizes.parse("5pk x 0.6g", category="preroll"),
                               sizes.parse("3g", category="preroll"))
        assert sizes.same_size(sizes.Size(grams=0.6), sizes.Size(grams=1.0)) is False
        assert sizes.same_size(sizes.Size(), sizes.Size(grams=1.0)) is None


class TestShortlist:
    def test_category_separates_same_title(self):
        idx = cm.CatalogIndex(AYRLOOM)
        assert idx.shortlist("Ayrloom Honeycrisp Disposable Vape 1g", "vaporizers", "1g") == ["hc-vape"]
        assert idx.shortlist("Honeycrisp Cider 12oz Can", "edible", "10mg") == ["hc-bev"]

    def test_size_filters_when_a_candidate_fits(self):
        idx = cm.CatalogIndex(AYRLOOM)
        assert idx.shortlist("Lychee Dream Infused Pre-Roll | 5 Pack | 3g", "preroll", "3g") == ["ld-5"]
        assert idx.shortlist("Lychee Dream Pre-Roll", "preroll", "1g") == ["ld-1"]

    def test_size_never_empties_the_shortlist(self):
        idx = cm.CatalogIndex(AYRLOOM)
        got = idx.shortlist("Lychee Dream Pre-Roll 2g", "preroll", "2g")
        assert set(got) == {"ld-5", "ld-1"}   # a new pack size is still the product

    def test_subtype_prunes_a_drink_of_the_same_flavour(self):
        idx = cm.CatalogIndex(AYRLOOM)
        name = "Island Time Pineapple Mango 2:1 Gummies"
        assert set(idx.shortlist(name, "edible", "")) == {"island time|edible", "pineapple mango|edible"}
        assert idx.shortlist(name, "edible", "", subtype="gummy") == ["island time|edible"]
        # soft on its own: never prunes to nothing
        assert idx.shortlist("Pineapple Mango Chocolate", "edible", "", subtype="chocolate") == \
            ["pineapple mango|edible"]

    def test_subtype_and_size_conflict_together_is_a_veto(self):
        idx = cm.CatalogIndex(AYRLOOM)
        # a 100mg gummy is never the 10mg pineapple mango can, even as the last candidate
        assert idx.shortlist("Pineapple Mango Gummies 10pk 100mg", "edible", "100mg",
                             subtype="gummy", exclude="island time|edible") == []
        # one conflict alone is not enough
        assert idx.shortlist("Pineapple Mango Gummies 10mg", "edible", "10mg",
                             subtype="gummy", exclude="island time|edible") == ["pineapple mango|edible"]

    def test_no_shared_tokens_no_candidates(self):
        assert cm.CatalogIndex(AYRLOOM).shortlist("Rose Dry Cider", "edible", "10mg") == []


class TestDeterministic:
    def test_substring_can_be_confidently_wrong(self):
        """The case that justifies the Jev tier: both titles are substrings and share
        a category, so the lexical tiers pick the beverage for a gummy."""
        idx = cm.CatalogIndex(AYRLOOM)
        key, _, method = idx.deterministic("Island Time Pineapple Mango 2:1 Gummies 100mg", "edible")
        assert method == "substring"

    def test_exact_requires_whole_name(self):
        idx = cm.CatalogIndex(AYRLOOM)
        assert idx.exact("Mood: Bliss", "vaporizers") == ("mood: bliss|vaporizers", "exact")
        assert idx.exact("Mood Bliss AIO", "vaporizers")[0] is None

    def test_a_store_name_on_unrelated_products_goes_to_the_one_it_names(self):
        """A store slip recorded Wyld's Raspberry name on Boysenberry too; the longer
        title must not take it."""
        def gummy(name, *terms):
            return {"name": name, "category": "edible", "variant": "10pk 100mg",
                    "match_terms": list(terms)}
        idx = cm.CatalogIndex(catalog(
            gummy("Raspberry", "raspberry sativa enhanced gummies"),
            gummy("Boysenberry", "raspberry sativa enhanced gummies", "vape cartridge"),
            gummy("Grapefruit", "vape cartridge"),
            gummy("Blue Lobster", "hash infused blue lobster"),
            gummy("Hash Infused Blue Lobster", "hash infused blue lobster")))
        assert idx.exact("Raspberry Sativa Enhanced Gummies", "edible") == ("Raspberry|edible", "exact")
        assert idx.exact("Vape Cartridge", "edible") == (None, "ambiguous")     # names neither
        # One product's title read short and long: the longest still wins.
        assert idx.exact("Hash Infused Blue Lobster", "edible")[0] == "Hash Infused Blue Lobster|edible"


def fake_ask_many(answer_for):
    """answer_for(state, options) -> (label, p)"""
    def ask_many(jobs, workers=8, usage=None, model=None, on_error=None):
        out = []
        for state, questions in jobs:
            options = list(questions["product"].criteria)
            assert options[0] == cm.NONE, "the abstain option must come first"
            label, p = answer_for(state, options)
            probs = {o: 0.0 for o in options}
            probs[label] = p
            probs[cm.NONE] = probs.get(cm.NONE, 0.0) + (1 - p if label != cm.NONE else 0)
            out.append(jev.Result({"product": {"type": "choice", "choice": label, "probabilities": probs}},
                                  "fake", 1, 0.0, 0.0))
        return out
    return ask_many


class TestResolve:
    def test_gate_thresholds(self):
        assert cm.gate("x", cm.AUTO) == "jev"
        assert cm.gate("x", cm.AUTO - 0.01) == "jev_review"
        assert cm.gate("x", cm.REVIEW - 0.01) == "none"
        assert cm.gate(cm.NONE, 0.99) == "none"

    def test_bootstrap_catalogs_need_more_confidence(self):
        assert cm.auto_threshold({"source_method": "listings_bootstrap"}) == cm.AUTO_BOOTSTRAP
        assert cm.auto_threshold({"source_method": "shopify_products_json"}) == cm.AUTO
        assert cm.gate("x", 0.87, cm.AUTO_BOOTSTRAP) == "jev_review"

    def test_jev_overrides_a_wrong_substring_pick(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(jev, "ask_many", fake_ask_many(
            lambda state, options: ("island time", 0.97)))
        [d] = cm.resolve(AYRLOOM, [{"id": "1", "name": "Island Time Pineapple Mango Gummies 100mg",
                                    "category": "edible", "variant": "100mg"}], use_jev=True)
        assert (d.method, d.product_key) == ("jev", "island time|edible")

    def test_abstain_and_review(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(jev, "ask_many", fake_ask_many(
            lambda state, options: (cm.NONE, 0.9) if "Rest" in state["listing_name"] else (options[1], 0.6)))
        ds = cm.resolve(AYRLOOM, [
            {"id": "1", "name": "Ayrloom Mood Rest AIO 1g", "category": "vaporizers", "variant": "1g"},
            {"id": "2", "name": "Bliss AIO 1g", "category": "vaporizers", "variant": "1g"}], use_jev=True)
        assert [d.method for d in ds] == ["none", "jev_review"]
        assert ds[0].entry is None and ds[1].entry is not None

    def test_failed_call_is_no_match_and_not_cached(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(jev, "ask_many", lambda jobs, **kw: [None] * len(jobs))
        cache = cm.AnswerCache("ayrloom")
        [d] = cm.resolve(AYRLOOM, [{"id": "1", "name": "Bliss AIO", "category": "vaporizers",
                                    "variant": "1g"}], use_jev=True, cache=cache)
        assert d.method == "error" and d.entry is None and cache.data == {}

    def test_cache_is_keyed_by_candidates(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        calls = {"n": 0}

        def counting(jobs, **kw):
            calls["n"] += len(jobs)
            return fake_ask_many(lambda s, o: (o[1], 0.95))(jobs)

        monkeypatch.setattr(jev, "ask_many", counting)
        listing = [{"id": "1", "name": "Bliss AIO 1g", "category": "vaporizers", "variant": "1g"}]
        cm.resolve(AYRLOOM, listing, use_jev=True, cache=cm.AnswerCache("ayrloom"))
        cm.resolve(AYRLOOM, listing, use_jev=True, cache=cm.AnswerCache("ayrloom"))
        assert calls["n"] == 1                       # second run served from cache
        grown = catalog(*AYRLOOM["entries"], {"name": "bliss", "category": "vaporizers", "variant": "1g"})
        cm.resolve(grown, listing, use_jev=True, cache=cm.AnswerCache("ayrloom"))
        assert calls["n"] == 2                       # a new candidate means a new question

    def test_holdout_removes_the_true_product(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        seen = {}

        def capture(jobs, **kw):
            seen["options"] = list(jobs[0][1]["product"].criteria)
            return fake_ask_many(lambda s, o: (cm.NONE, 0.9))(jobs)

        monkeypatch.setattr(jev, "ask_many", capture)
        cm.resolve(AYRLOOM, [{"id": "1", "name": "Lychee Dream Pre-Roll", "category": "preroll",
                              "variant": "1g"}], use_jev=True, exclude={"1": "ld-1"})
        # The true 1g product is gone, so the 3g five-pack is no longer filtered out by
        # size — exactly what a catalog missing the 1g would look like.
        assert "lychee dream" in seen["options"]
        assert len(seen["options"]) == 2             # none + the one remaining product




class TestDescribedLine:
    """A store that leaves the line out of the name often has it in the description
    (Hold Up Roll Up's "King Louis XIII - 1G Infused Prerolls", 2026-10-05). Only lines
    curated with a category count — data/product_lines.json's STIIIZY entries here."""

    STIIIZY = {"brand_name": "STIIIZY", "brand_slug": "stiiizy", "entries": [
        {"id": "e0", "product_key": "40-klx", "name": "40's King Louis XIII", "category": "preroll",
         "product_line": "40's", "strain": "King Louis XIII", "variant": "1g", "is_active": True},
        {"id": "e1", "product_key": "og-klx", "name": "Original King Louis XIII", "category": "vaporizers",
         "product_line": "Original", "strain": "King Louis XIII", "variant": "1g", "is_active": True},
        {"id": "e2", "product_key": "lil-bd", "name": "LIIIL Blue Dream", "category": "vaporizers",
         "product_line": "LIIIL", "strain": "Blue Dream", "variant": "0.5g", "is_active": True}]}
    KLX = {"id": "1", "name": "King Louis XIII - 1G Infused Prerolls", "category": "preroll",
           "variant": "1g", "description": "<p>Elevate your game. Stiiizy 40\u2019s pre-rolls are setting the standard</p>"}

    def line(self, listing, catalog=None):
        return cm.described_line(listing, cm.CatalogIndex(catalog or self.STIIIZY))

    def test_the_one_line_the_description_names(self):
        assert self.line(self.KLX) == "40's"      # curly apostrophe and HTML don't matter

    def test_not_when_the_name_names_a_line(self):
        assert self.line({**self.KLX, "name": "40s King Louis XIII 1g"}) is None
        assert self.line({**self.KLX, "name": "Original King Louis XIII 1g"}) is None

    def test_only_lines_of_the_listings_category_and_only_one(self):
        vape = {"id": "2", "name": "Blue Dream 0.5g", "category": "vaporizers", "variant": "0.5g"}
        assert self.line({**vape, "description": "A LIIIL disposable"}) == "LIIIL"
        assert self.line({**vape, "description": "For fans of 40's pre-rolls"}) is None
        assert self.line({**vape, "description": "Like our Liquid Diamonds pods, LIIIL is..."}) is None
        assert self.line({**vape, "description": None}) is None

    def test_uncurated_lines_never_count(self):
        palms = {"brand_name": "Jaunty", "entries": [
            {"id": "p0", "product_key": "palms-cb", "name": "Palms Cake Batter", "category": "vaporizers",
             "product_line": "Palms", "variant": "1.5g", "is_active": True}]}
        listing = {"id": "3", "name": "Cake Batter - 1.5G AIO Vape", "category": "vaporizers",
                   "description": "Jaunty Palms all-in-one"}
        assert self.line(listing, palms) is None

    def test_it_goes_into_the_question_and_its_cache_key(self):
        idx = cm.CatalogIndex(self.STIIIZY)
        cands = idx.shortlist(self.KLX["name"], "preroll", "1g")
        state, _, _ = cm.jev_question("STIIIZY", self.KLX, idx, cands)
        assert state["product_line_in_description"] == "40's"
        plain = {**self.KLX, "description": "Elevate your game."}
        assert "product_line_in_description" not in cm.jev_question("STIIIZY", plain, idx, cands)[0]
        # A listing without a hint keeps the key it had before hints existed, so its
        # cached answer is still found; one with a hint is a new question.
        assert cm._cache_key(plain, cands, idx) == cm._cache_key({**self.KLX, "description": None}, cands, idx)
        assert cm._cache_key(self.KLX, cands, idx) != cm._cache_key(plain, cands, idx)


class TestCatalogSize:
    """A store's size is its own field; for a dose product it is often the CBD figure,
    a cannabinoid sum or a per-piece dose. Product pages take the catalog's then."""

    def entries(self, *variants, category="edible"):
        return [{"category": category, "variant": v} for v in variants]

    def test_a_mistyped_dose_takes_the_catalog_size(self):
        camino = self.entries("20pk 100mg")
        assert cm.catalog_size("50mg", "Balance | Yuzu Lemon | 1:1 | 20pk", camino[0], camino,
                               "5mg THC : 5mg CBD per piece - 100mg THC : 100mg CBD per package") == "100mg"
        ayrloom = self.entries("150mg", category="tinctures")
        assert cm.catalog_size("600mg", "Ayrloom Tincture Drops (150mg THC: 450mg CBD)",
                               ayrloom[0], ayrloom) == "150mg"
        wyld = self.entries("10pk 100mg")
        assert cm.catalog_size("10mg", "Wyld Raspberry Gummies", wyld[0], wyld) == "100mg"   # per piece

    def test_the_listing_has_to_back_the_catalog(self):
        camino = self.entries("20pk 100mg")
        assert cm.catalog_size("50mg", "Balance | Yuzu Lemon | 1:1 | 20pk", camino[0], camino) is None
        level = self.entries("5pk 100mg")       # Level may sell a 50mg 5-pack the catalog lacks
        assert cm.catalog_size("50mg", "Level - Protab THC Infused Pills - 5pk", level[0], level) is None
        eaton = self.entries("5mg")             # a per-piece dose recorded as the size
        assert cm.catalog_size("100mg", "Daily Elevation | Peach 5mg", eaton[0], eaton) is None
        wana = self.entries("10pk 100mg")       # the catalog took the CBD total
        assert cm.catalog_size("20mg", "Optimals Fast Asleep Gummies [10 pack] | 20mg", wana[0], wana,
                               "Per Package: 100mg CBD, 20mg CBN, 20mg CBG, 20mg THC") is None
        grön = self.entries("10pk 25mg")        # "OF" between the figure and the cannabinoid
        assert cm.catalog_size("10mg", "10:1 Tart Cherry - CBN/THC - Nightly", grön[0], grön,
                               "25MG OF CBN PER PEARL | 2.5MG OF THC PER PEARL") is None
        assert cm.catalog_size("10mg", "10:1 Tart Cherry - CBN/THC - Nightly", grön[0], grön,
                               "25MG OF THC PER PACKAGE | 250MG OF CBN PER PACKAGE") == "25mg"

    def test_the_stores_size_stands_otherwise(self):
        camino = self.entries("20pk 100mg")
        assert cm.catalog_size("100mg", "Yuzu Lemon Gummies 20pk", camino[0], camino) is None   # it fits
        assert cm.catalog_size(None, "Yuzu Lemon Gummies", camino[0], camino) is None          # states none
        level = self.entries("5pk 100mg")
        assert cm.catalog_size("352mg", "Level Protab 2pk", level[0], level) is None           # another pack
        two = self.entries("10pk 100mg", "20pk 200mg")
        assert cm.catalog_size("50mg", "Gummies 100mg", two[0], two) is None                   # two sizes left
        flower = self.entries("3.5g", category="flower")
        assert cm.catalog_size("14g", "Gelato Half Ounce", flower[0], flower) is None           # a real size


def test_infused_flower_never_matches_the_plain_flower_of_its_strain():
    """Grassroots sells Atomic Breath as plain and as diamond-infused flower at 3.5g; with
    only the plain one in the catalog, the infused listing must find no product rather
    than the plain one. Infused pre-ground is its own subtype and is left alone."""
    cat = catalog({"name": "Atomic Breath", "category": "flower", "subtype": "flower", "strain": "Atomic Breath",
                   "variant": "3.5g", "match_terms": ["atomic breath 3 5g diamond infused flower"]},
                  {"name": "Golden Goat", "category": "flower", "subtype": "preground", "strain": "Golden Goat",
                   "variant": "14g"})
    idx = cm.CatalogIndex(cat)
    infused = "Atomic Breath | 3.5g Diamond Infused (Flower)"
    assert idx.shortlist(infused, "flower", "3.5g") == []
    assert idx.shortlist("Atomic Breath | 3.5g (Flower)", "flower", "3.5g") == ["Atomic Breath|flower"]
    assert idx.shortlist("Pre Ground Infused Flower | Golden Goat | 14g", "flower", "14g") == ["Golden Goat|flower"]
    # A store name recorded on the plain product does not carry an infused listing to it.
    [d] = cm.resolve(cat, [{"id": 1, "name": "Atomic Breath 3.5g Diamond Infused Flower", "category": "flower",
                            "variant": "3.5g"}], use_jev=True)
    assert d.product_key is None


def test_a_description_that_states_infused_flower_vetoes_plain_flower():
    """Stores sell Grassroots' infused Atomic Breath as "Atomic Breath Whole Flower 3.5g"
    and say so only in the description. Figurative uses do not count."""
    cat = catalog({"name": "Atomic Breath", "category": "flower", "subtype": "flower", "strain": "Atomic Breath",
                   "variant": "3.5g"})
    idx = cm.CatalogIndex(cat)
    name = "Atomic Breath Whole Flower 3.5g"
    for desc in ["Brace yourself for the explosive potency of the Infused Atomic Breath.",
                 "<p>This premium flower is diamond-infused for an extra punch.</p>",
                 "Premium flower infused with 4 grams of kief per bag.",
                 "Infused with both bubble hash and diamonds."]:
        assert idx.shortlist(name, "flower", "3.5g", description=desc) == [], desc
    for desc in [None, "A 3.5g hybrid infused with the irresistible taste of maraschino cherries.",
                 "A smooth, gas-infused cherry finish.", "Drenched in rosin and infused with a terpene blend."]:
        assert idx.shortlist(name, "flower", "3.5g", description=desc) == ["Atomic Breath|flower"], desc
    [d] = cm.resolve(cat, [{"id": 1, "name": name, "category": "flower", "variant": "3.5g",
                            "description": "the Infused Atomic Breath"}], use_jev=True)
    assert d.product_key is None
