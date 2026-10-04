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
    ])
    def test_parse(self, texts, cat, expect):
        assert sizes.parse(*texts, category=cat) == expect

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
