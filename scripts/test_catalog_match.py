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


class TestSizes:
    @pytest.mark.parametrize("texts,cat,expect", [
        (("0.6g", "FJ-Mini Infused Pre-roll | 0.6G"), "preroll", sizes.Size(grams=0.6)),
        (("", "Jetpacks | FJ-3 | .6g | 5 Pack | 3g | THC 37.83%"), "preroll", sizes.Size(grams=3.0, pack=5)),
        (("", "Blueberry Pancakes 5pk x 0.6g - 3.0g"), "preroll", sizes.Size(grams=3.0, pack=5, unit_g=0.6)),
        (("10mg / 10 pack",), "edible", sizes.Size(mg=10.0, pack=10)),        # ambiguous: as stated
        (("", "Wyld Gummies 100mg 10pk"), "edible", sizes.Size(mg=100.0, pack=10)),
        (("", "Kiva 20MG x 2PK"), "edible", sizes.Size(mg=40.0, pack=2, unit_mg=20.0)),
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
        # A lone dose beside a pack is never multiplied (owner, 2026-10-10): the figure
        # stands, and pack x figure is only the other reading.
        got = sizes.parse("Dreamberry | 20mg | 2pk", category="edible")
        assert got == sizes.Size(mg=20.0, pack=2) and got.alt_mg == 40.0

    def test_a_lone_dose_beside_a_pack_may_be_either_reading(self):
        per_piece = sizes.parse("10mg", "1906 - Bliss Drops 2pk - 10mg", category="edible")
        in_all = sizes.parse("20mg", "Bliss Drops 2-pack", category="edible")
        label = sizes.parse("2pk 20mg", category="edible")
        assert sizes.same_size(per_piece, label) is True
        assert sizes.same_size(in_all, label) is True
        # Only against the same pack count: ten pieces are not a stated single.
        assert sizes.same_size(sizes.parse("Gummies 10pk 10mg", category="edible"),
                               sizes.parse("1pk 10mg", category="edible")) is False
        assert sizes.same_size(sizes.parse("Gummies 10pk 10mg", category="edible"),
                               sizes.parse("10pk 100mg", category="edible")) is True
        # An explicit per-piece form is not a guess.
        assert sizes.parse("Kiva 2pk x 20mg", category="edible").alt_mg is None

    def test_the_first_reading_picks_the_entry_when_both_fit(self):
        idx = cm.CatalogIndex(catalog(
            {"name": "dreamberry", "category": "edible", "variant": "2pk 20mg", "pk": "db"},
            {"name": "dreamberry", "category": "edible", "variant": "2pk 40mg", "pk": "db"}))
        assert idx.pick_entry("db", "", "edible", "Dreamberry | 20mg | 2pk")["variant"] == "2pk 20mg"   # as stated
        assert idx.pick_entry("db", "", "edible", "Dreamberry | 20mg each | 2pk")["variant"] == "2pk 40mg"
        assert idx.pick_entry("db", "20mg", "edible", "Dreamberry")["variant"] == "2pk 20mg"

    def test_a_dose_single_is_not_a_pack_of_the_same_total(self):
        single = sizes.parse("Flav - Strawberry Belts Mega Dosed Gummy 1pk - 100mg", category="edible")
        assert single == sizes.Size(mg=100.0, pack=1) and single.label() == "1pk 100mg"
        assert sizes.parse("1pk 100mg", category="edible") == single          # the label reads back
        assert sizes.same_size(single, sizes.parse("10pk 100mg", category="edible")) is False
        # A count left open still fits either; a weight's "1pk" is no count at all.
        assert sizes.same_size(sizes.parse("100mg", category="edible"), single) is True
        assert sizes.parse("1pk 1g", category="preroll") == sizes.Size(grams=1.0)

    def test_two_stated_counts_that_differ_are_two_packages(self):
        assert sizes.same_size(sizes.parse("5pk 2.5g", category="preroll"),
                               sizes.parse("10pk 2.5g", category="preroll")) is False

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


STIIIZY = {"brand_name": "STIIIZY", "brand_slug": "stiiizy", "entries": [
    {"id": f"s{i}", "product_key": pk, "is_active": True, "name": name, "category": "vaporizers",
     "subtype": sub, "product_line": line, "strain": strain, "variant": v, **extra}
    for i, (pk, name, sub, line, strain, v, extra) in enumerate([
        ("liiil-bisc", "LIIIL Biscotti", "all-in-one", "LIIIL", "Biscotti", "0.5g", {}),
        ("bisc", "Biscotti", "all-in-one", None, "Biscotti", "1g", {}),
        ("og-bisc", "Original Biscotti", "pod", "Original", "Biscotti", "1g", {}),
        ("og-bisc", "Original Biscotti", "pod", "Original", "Biscotti", "0.5g", {"source": "inferred"}),
    ])]}


def reading(strain, size, line=None, subtype="all-in-one", category="vaporizers"):
    return {"category": category, "subtype": subtype, "strain": strain, "product_line": line, "size": size}


class TestJoin:
    """The listing's own reading names exactly one product in a size it comes in."""

    def test_the_size_tells_two_products_of_one_strain_apart(self):
        idx = cm.CatalogIndex(STIIIZY)
        assert idx.join(reading("Biscotti", "0.5g"))[0] == "liiil-bisc"     # no line read: LIIIL is the 0.5g
        assert idx.join(reading("Biscotti", "1g"))[0] == "bisc"

    def test_a_size_no_product_comes_in_does_not_join(self):
        assert cm.CatalogIndex(STIIIZY).join(reading("Biscotti", "2g")) is None   # Jev decides; the audit sees it

    def test_a_line_read_must_agree_and_format_is_compared(self):
        idx = cm.CatalogIndex(STIIIZY)
        assert idx.join(reading("Biscotti", "1g", line="LIIIL")) is None
        assert idx.join(reading("Biscotti", "1g", line="Original", subtype="pod"))[0] == "og-bisc"
        assert idx.join(reading("Biscotti", "1g", subtype="battery")) is None          # a cart would be the pod (FORMAT_SYNONYMS)

    def test_an_inferred_size_counts(self):
        key, entry = cm.CatalogIndex(STIIIZY).join(reading("Biscotti", "0.5g", line="Original", subtype="pod"))
        assert key == "og-bisc" and entry["source"] == "inferred"

    def test_no_join_without_a_strain_or_a_size(self):
        idx = cm.CatalogIndex(STIIIZY)
        assert idx.join(reading("Biscotti", None)) is None and idx.join(reading("", "1g")) is None
        assert idx.join(None) is None

    def test_a_lone_dose_beside_a_pack_joins_either_reading(self):
        # 1906 writes the package total ("2pk - 10mg" is 10mg in all); readings stored
        # before the parser stopped multiplying hold 20mg.
        cat = {"brand_name": "1906", "entries": [
            {"id": "a", "product_key": "chill", "name": "Drops Chill", "product_line": "Drops",
             "category": "edible", "subtype": "tablet", "strain": "Chill", "variant": "2pk 10mg"},
            {"id": "b", "product_key": "chill", "name": "Drops Chill", "product_line": "Drops",
             "category": "edible", "subtype": "tablet", "strain": "Chill", "variant": "20pk 100mg"}]}
        idx = cm.CatalogIndex(cat)
        r = {"category": "edible", "subtype": "tablet", "strain": "Chill", "product_line": "Drops",
             "size": "20mg"}
        assert idx.join(r) is None                                      # the bare figure alone
        assert idx.join(r, "1906 - Chill Drops 2pk - 10mg")[1]["id"] == "a"
        # Only when the name agrees with the reading's figure: otherwise the reading's
        # own figure decides. And the other reading counts only against the same pack
        # count, so a 20-pack name never reaches the 2-pack.
        assert idx.join(dict(r, size="100mg"), "1906 - Chill Drops 2pk - 10mg")[1]["id"] == "b"
        assert idx.join(dict(r, size="100mg"), "1906 - Chill Drops 20pk - 100mg")[1]["id"] == "b"
        assert idx.join(r, "1906 - Chill Drops 20pk - 100mg") is None

    def test_a_count_left_open_does_not_pick_between_a_single_and_a_pack(self):
        cat = {"brand_name": "Flav", "entries": [
            {"id": "one", "product_key": "belts-straw", "name": "Belts Strawberry", "product_line": "Belts",
             "category": "edible", "subtype": "gummy", "strain": "Strawberry", "variant": "1pk 100mg"},
            {"id": "ten", "product_key": "belts-straw", "name": "Belts Strawberry", "product_line": "Belts",
             "category": "edible", "subtype": "gummy", "strain": "Strawberry", "variant": "10pk 100mg"}]}
        idx = cm.CatalogIndex(cat)
        r = {"category": "edible", "subtype": "gummy", "strain": "Strawberry", "size": "100mg"}
        assert idx.join(r, "Strawberry Belts - 100mg") is None                 # single or 10-pack: Jev decides
        assert idx.join(r, "Strawberry Belts Mega Dosed Gummy 1pk - 100mg")[1]["id"] == "one"
        assert idx.join(r, "Flav | 10pk Gummy Belts | 100mg | Strawberry")[1]["id"] == "ten"
        assert idx.join(dict(r, size="10pk 100mg"))[1]["id"] == "ten"

    def test_a_bare_dose_joins_the_pack_it_is_the_per_piece_dose_of(self):
        # A store can print the piece's dose and leave out the count: "Sour Cherry 10mg"
        # is Wyld's 10-pack of 100mg.
        def e(i, key, variant):
            return {"id": i, "product_key": key, "name": key.title(), "category": "edible",
                    "subtype": "gummy", "strain": key.title(), "variant": variant}
        cat = {"brand_name": "Wyld", "entries": [e("sc", "sour cherry", "10pk 100mg")]}
        idx = cm.CatalogIndex(cat)
        r = {"category": "edible", "subtype": "gummy", "strain": "Sour Cherry", "size": "10mg"}
        assert idx.join(r, "Wyld Sour Cherry Gummies 10mg")[1]["id"] == "sc"
        assert idx.join(dict(r, size="20mg")) is None                  # 200mg is no size it sells
        assert idx.join(r, "Wyld Sour Cherry Gummies 1pk 10mg") is None   # a count that differs
        assert idx.join(r, "Wyld | Sour Cherry | Gummies | 1-Pack") is None    # a count, no figure
        # A product that sells the figure itself keeps it; two packs it fits leave Jev to choose.
        idx = cm.CatalogIndex({"brand_name": "Wyld", "entries": [
            e("ten", "sour cherry", "10pk 100mg"), e("one", "sour cherry", "10mg")]})
        assert idx.join(r)[1]["id"] == "one"
        idx = cm.CatalogIndex({"brand_name": "Wyld", "entries": [
            e("ten", "sour cherry", "10pk 100mg"), e("five", "sour cherry", "5pk 50mg")]})
        assert idx.join(r) is None
        # And the near entries Jev is offered count it as no miss.
        p = cm.CatalogIndex(cat).products["sour cherry"]
        assert cm.attribute_misses(r, p, cat["entries"][0]) == []
        assert cm.attribute_misses(dict(r, size="20mg"), p, cat["entries"][0]) == ["size"]

    def test_words_around_a_strain_are_set_aside_only_when_no_product_carries_it(self):
        def e(i, line, strain, size="1g"):
            return {"id": i, "product_key": i, "name": f"{line or ''} {strain}".strip(), "product_line": line,
                    "category": "vaporizers", "subtype": "cart", "strain": strain, "variant": size}
        cat = {"brand_name": "MFNY", "entries": [e("hb", "Live Resin", "Hash Burger"),
                                                  e("bel", "Live Resin", 'The "Belafonte"'),
                                                  e("sd", None, "Sour Diesel"),
                                                  e("psd", None, "Premium Sour Diesel")]}
        idx = cm.CatalogIndex(cat)
        r = {"category": "vaporizers", "subtype": "cart", "size": "1g"}
        assert idx.join(dict(r, strain="Hash Burger Live Resin"))[0] == "hb"      # extraction words
        assert idx.join(dict(r, strain="Belafonte"))[0] == "bel"                 # "The", quotes
        # A product carries the strain as read: no setting aside, no Premium twin.
        assert idx.join(dict(r, strain="Sour Diesel"))[0] == "sd"
        assert idx.join(dict(r, strain="Premium Sour Diesel"))[0] == "psd"

    def test_the_products_own_line_is_set_aside_from_the_strain(self):
        cat = {"brand_name": "Flav", "entries": [
            {"id": "b", "product_key": "b", "name": "Belts Blueberry", "product_line": "Belts",
             "category": "edible", "subtype": "gummy", "strain": "Blueberry", "variant": "10pk 100mg"}]}
        r = {"category": "edible", "subtype": "gummy", "strain": "Blueberry Belts", "size": "10pk 100mg"}
        assert cm.CatalogIndex(cat).join(r)[0] == "b"
        assert cm.strain_core("Live Resin") == "liveresin"                       # nothing else left

    def test_resolve_takes_the_join_and_names_never_decide(self):
        listings = [{"id": 1, "name": "STIIIZY Biscotti 0.5g", "category": "vaporizers",
                     "reading": reading("Biscotti", "0.5g")},
                    {"id": 2, "name": "LIIIL Biscotti", "category": "vaporizers"}]     # no reading
        a, b = cm.resolve(STIIIZY, listings, use_jev=False)
        assert (a.method, a.product_key, a.confidence) == ("attributes", "liiil-bisc", 1.0)
        assert (b.method, b.product_key) == ("none", None)      # its name is a catalog title; still no match


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

    def test_jev_picks_an_entry_one_attribute_away(self, monkeypatch, tmp_path):
        """STIIIZY's 4.5g listing of a strain the catalog has in 1g and 0.5g: Jev chooses
        among those sizes (or none); its pick is the entry, size and all."""
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        seen = {}

        def answer(state, options):
            seen["options"] = options
            return next(o for o in options if o.endswith("— 1g")), 0.95

        monkeypatch.setattr(jev, "ask_many", fake_ask_many(answer))
        [d] = cm.resolve(STIIIZY, [{"id": "1", "name": "Biscotti AIO 4.5g", "category": "vaporizers",
                                    "variant": "4.5g", "reading": reading("Biscotti", "4.5g")}], use_jev=True)
        assert (d.method, d.product_key, d.entry["variant"]) == ("jev", "bisc", "1g")
        # Same strain and format, another size; the LIIIL 0.5g is one attribute away too.
        assert sorted(seen["options"][1:]) == ["Biscotti — 1g", "LIIIL Biscotti — 0.5g"]

    def test_entries_two_attributes_away_are_not_offered(self):
        idx = cm.CatalogIndex(STIIIZY)
        far = {"name": "Gelato Pod 4.5g", "category": "vaporizers", "reading": reading("Gelato", "4.5g", subtype="pod")}
        assert cm.near_entries(idx, far, "STIIIZY") == []
        # A strain the reading lacks is the one miss: every pod of that size is offered.
        blank = {"name": "Original Pod 1g", "category": "vaporizers",
                 "reading": reading(None, "1g", line="Original", subtype="pod")}
        assert [(k, e["variant"]) for k, e, _ in cm.near_entries(idx, blank, "STIIIZY")] == [("og-bisc", "1g")]

    def test_abstain_and_review(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(jev, "ask_many", fake_ask_many(
            lambda state, options: (cm.NONE, 0.9) if "Rest" in state["listing_name"] else (options[1], 0.6)))
        ds = cm.resolve(AYRLOOM, [
            {"id": "1", "name": "Ayrloom Mood Rest AIO 1g", "category": "vaporizers", "variant": "1g",
             "reading": reading("Rest", "1g", line="Mood", subtype=None)},
            {"id": "2", "name": "Bliss AIO 2g", "category": "vaporizers", "variant": "2g",
             "reading": reading("Bliss", "2g", subtype=None)}], use_jev=True)
        assert [d.method for d in ds] == ["none", "jev_review"]
        assert ds[0].entry is None and ds[1].entry is not None

    def test_failed_call_is_no_match_and_not_cached(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(jev, "ask_many", lambda jobs, **kw: [None] * len(jobs))
        cache = cm.AnswerCache("ayrloom")
        [d] = cm.resolve(AYRLOOM, [{"id": "1", "name": "Bliss AIO", "category": "vaporizers", "variant": "2g",
                                    "reading": reading("Bliss", "2g", subtype=None)}], use_jev=True, cache=cache)
        assert d.method == "error" and d.entry is None and cache.data == {}

    def test_cache_is_keyed_by_candidates(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        calls = {"n": 0}

        def counting(jobs, **kw):
            calls["n"] += len(jobs)
            return fake_ask_many(lambda s, o: (o[1], 0.95))(jobs)

        monkeypatch.setattr(jev, "ask_many", counting)
        listing = [{"id": "1", "name": "Bliss AIO 2g", "category": "vaporizers", "variant": "2g",
                    "reading": reading("Bliss", "2g", subtype=None)}]
        cm.resolve(AYRLOOM, listing, use_jev=True, cache=cm.AnswerCache("ayrloom"))
        cm.resolve(AYRLOOM, listing, use_jev=True, cache=cm.AnswerCache("ayrloom"))
        assert calls["n"] == 1                       # second run served from cache
        grown = catalog(*AYRLOOM["entries"], {"name": "mood: bliss", "category": "vaporizers",
                                               "product_line": "Mood", "strain": "Bliss", "variant": "3g"})
        cm.resolve(grown, listing, use_jev=True, cache=cm.AnswerCache("ayrloom"))
        assert calls["n"] == 2                       # a new option means a new question

    def test_holdout_removes_the_true_product(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        seen = {}

        def capture(jobs, **kw):
            seen["options"] = list(jobs[0][1]["product"].criteria) if jobs else []
            return fake_ask_many(lambda s, o: (cm.NONE, 0.9))(jobs)

        monkeypatch.setattr(jev, "ask_many", capture)
        listing = {"id": "1", "name": "Bliss AIO 2g", "category": "vaporizers", "variant": "2g",
                   "reading": reading("Bliss", "2g", line="Mood", subtype=None)}
        cm.resolve(AYRLOOM, [listing], use_jev=True)
        assert any(o.startswith("mood: bliss") for o in seen["options"])
        seen.clear()
        [d] = cm.resolve(AYRLOOM, [listing], use_jev=True, exclude={"1": "mood: bliss|vaporizers"})
        assert d.method == "none" and not any(o.startswith("mood: bliss") for o in seen.get("options", []))

    def test_papers_keep_width_and_tips(self, monkeypatch, tmp_path):
        """OCB's 'Bamboo Rolling Papers KS - 24ct' (24 is the display count): of Bamboo's
        sizes only the king size booklet without tips is offered."""
        monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
        ocb = {"brand_name": "OCB", "brand_slug": "ocb", "entries": [
            {"id": f"b{i}", "product_key": "bamboo", "name": "Bamboo Papers", "product_line": "Bamboo",
             "category": "merch", "subtype": "paper", "variant": v, "is_active": True}
            for i, v in enumerate(["1 1/4 50ct", "1 1/4 50ct w/tips", "king size 32ct", "king size 32ct w/tips"])]}
        seen = {}

        def answer(state, options):
            seen["options"] = options
            return options[1], 0.9

        monkeypatch.setattr(jev, "ask_many", fake_ask_many(answer))
        [d] = cm.resolve(ocb, [{"id": "1", "name": "OCB - Bamboo Rolling Papers KS - 24ct", "category": "merch",
                                "subtype": "paper"}], use_jev=True)
        assert seen["options"][1:] == ["Bamboo Papers — king size 32ct"]
        assert d.entry["variant"] == "king size 32ct"


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
        cands = [("40-klx", idx.products["40-klx"].entries[0], [])]
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


def test_write_over_rest_changes_only_moved_matches_and_never_a_manual_one(fresh_db, via_rest):
    """The sandbox has no 5432 path, so --write --via-http writes through PostgREST: only
    listings whose match changed, and each conditioned on the method it read."""
    import uuid as _uuid
    cur = fresh_db.cursor()
    via_rest(fresh_db)
    store, cat = str(_uuid.uuid4()), str(_uuid.uuid4())
    cur.execute("INSERT INTO dispensaries (id, name, slug, pos_type, created_at, updated_at) "
                "VALUES (%s, 'S', 's', 'none', now(), now())", (store,))
    cur.execute("INSERT INTO brand_catalogs (id, brand_slug, brand_name, source_method) "
                "VALUES (%s, 'b', 'B', 'curated')", (cat,))
    old_e, new_e = str(_uuid.uuid4()), str(_uuid.uuid4())
    for e in (old_e, new_e):
        cur.execute("INSERT INTO brand_catalog_entries (id, catalog_id, name) VALUES (%s, %s, 'x')", (e, cat))
    ids = [str(_uuid.uuid4()) for _ in range(4)]
    stored = [(old_e, 1.0, "exact"), (new_e, 1.0, "exact"), (old_e, 1.0, "manual"), (None, None, None)]
    for i, (e, c, m) in zip(ids, stored):
        cur.execute("INSERT INTO listings (id, dispensary_id, scraped_name, in_stock, is_active, created_at, "
                    "updated_at, catalog_entry_id, catalog_match_confidence, catalog_match_method) "
                    "VALUES (%s, %s, 'n', true, true, now(), now(), %s, %s, %s)", (i, store, e, c, m))

    def dec(i, e, c, m):
        listing = {"id": i, "catalog_entry_id": stored[ids.index(i)][0],
                   "catalog_match_confidence": stored[ids.index(i)][1],
                   "catalog_match_method": stored[ids.index(i)][2]}
        return cm.Decision(listing, "p" if e else None, {"id": e} if e else None, c, m)

    decisions = [dec(ids[0], new_e, 0.97, "jev"),      # moved: written
                 dec(ids[1], new_e, 1.0, "exact"),     # unchanged: not sent
                 dec(ids[2], new_e, 1.0, "exact"),     # a person's match: never touched
                 dec(ids[3], new_e, 1.0, "exact")]     # newly matched: written
    assert cm.write_decisions_http(decisions) == 2
    cur.execute("SELECT id::text, catalog_entry_id::text, catalog_match_method FROM listings")
    got = {i: (e, m) for i, e, m in cur.fetchall()}
    assert got[ids[0]] == (new_e, "jev") and got[ids[3]] == (new_e, "exact")
    assert got[ids[2]] == (old_e, "manual") and got[ids[1]] == (new_e, "exact")


class TestFormatSynonyms:
    """A pod and a cart are one format (the owner's call, 2026-10-09)."""

    PAX = {"brand_name": "PAX", "entries": [
        {"id": "nl-pod", "product_key": "nl-pod", "name": "Live Rosin Northern Lights", "product_line": "Live Rosin",
         "category": "vaporizers", "subtype": "pod", "strain": "Northern Lights", "variant": "1g"},
        {"id": "nl-aio", "product_key": "nl-aio", "name": "Live Rosin Northern Lights", "product_line": "Live Rosin",
         "category": "vaporizers", "subtype": "all-in-one", "strain": "Northern Lights", "variant": "1g"}]}

    def test_a_cart_reading_joins_the_pod(self):
        r = {"category": "vaporizers", "subtype": "cart", "strain": "Northern Lights",
             "product_line": "Live Rosin", "size": "1g"}
        assert cm.CatalogIndex(self.PAX).join(r)[1]["id"] == "nl-pod"
        # An AIO is still another format.
        assert cm.CatalogIndex(self.PAX).join(dict(r, subtype="all-in-one"))[1]["id"] == "nl-aio"

    def test_the_overlay_keeps_the_pod(self):
        pod = self.PAX["entries"][0]
        assert cm.matched_subtype(pod, "Northern Lights | Live Rosin w Diamonds | Cart") == "pod"
        assert cm.matched_subtype(pod, "Northern Lights | AIO") == "all-in-one"

    def test_a_brand_selling_both_keeps_them_apart(self):
        select = {"brand_name": "Select", "entries": [
            {"id": "cliq", "product_key": "cliq", "name": "Cliq Gelato", "product_line": "Cliq",
             "category": "vaporizers", "subtype": "pod", "strain": "Gelato", "variant": "1g"},
            {"id": "elite", "product_key": "elite", "name": "Elite Gelato", "product_line": "Elite",
             "category": "vaporizers", "subtype": "cart", "strain": "Gelato", "variant": "1g"}]}
        idx = cm.CatalogIndex(select)
        assert idx.synonyms is False and cm.CatalogIndex(self.PAX).synonyms is True
        r = {"category": "vaporizers", "subtype": "cart", "strain": "Gelato", "size": "1g"}
        assert idx.join(r)[1]["id"] == "elite"                  # a cart is the cart, not either
        assert idx.join(dict(r, subtype="pod"))[1]["id"] == "cliq"
        assert cm.matched_subtype(select["entries"][0], "Select Gelato Cart", synonyms=False) == "cart"


def test_exact_entries_first_and_too_many_options_trimmed_by_name():
    idx = cm.CatalogIndex(catalog(*[{"name": f"Strain {i}", "category": "flower", "strain": f"Strain {i}",
                                     "variant": "3.5g"} for i in range(30)],
                                  {"name": "Alley Oop", "category": "flower", "strain": "Alley Oop", "variant": "3.5g"}))
    listing = {"name": "Alley - OOP (H) 3.5g Flower", "category": "flower",
               "reading": reading("Alley", "3.5g", subtype=None, category="flower")}
    cands = cm.closest(cm.near_entries(idx, listing, "Ayrloom"), listing["name"], idx)
    assert len(cands) == cm.MAX_OPTIONS and cands[0][0] == "Alley Oop|flower"
    exact = [("a", {}, []), ("b", {}, ["size"])]
    assert cm.closest(exact, "x", idx) == [("a", {}, [])]
