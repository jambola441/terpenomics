"""Offline tests for catalog_reading.py and the matcher's review queue — Jev is faked."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_match as cm  # noqa: E402
import catalog_reading as cr  # noqa: E402
import jev  # noqa: E402

CAMINO = {"brand_name": "Camino", "brand_slug": "camino", "entries": [
    {"id": f"e{i}", "product_key": pk, "is_active": True, "name": pk, "category": "edible",
     "subtype": sub, "product_line": line, "strain": strain, "variant": size}
    for i, (pk, sub, line, strain, size) in enumerate([
        ("wc", "gummy", "Gummies", "Wild Cherry Excite", "10pk 100mg"),
        ("wc", "gummy", "Gummies", "Wild Cherry Excite", "20pk 100mg"),
        ("pp", "gummy", "Gummies", "Pineapple Habanero", "10pk 100mg"),
        ("sp", "beverage", "Social", "Sparkling Pear", "1pk 5mg"),
    ])]}


def fake(answers):
    """answers: question key -> (option text prefix or "none", p). Records what was asked."""
    asked = []

    def ask_many(jobs, workers=8, usage=None, model=None, on_error=None):
        out = []
        for state, questions in jobs:
            [(key, q)] = questions.items()
            assert list(q.criteria)[0] == cr.NONE, "the abstain option comes first"
            asked.append((key, state, dict(q.criteria)))
            want, p = answers[key]
            label = cr.NONE if want == "none" else next(
                k for k, v in q.criteria.items() if k != cr.NONE and v.startswith(want))
            out.append(jev.Result({key: {"type": "choice", "choice": label,
                                         "probabilities": {label: p}}}, "fake", 1, 0.0, 0.0))
        return out
    return ask_many, asked


class NoCache:
    def get(self, key): return None
    def put(self, key, value): pass
    def save(self): pass


LISTING = {"id": "1", "name": "Camino Wild Cherry Excite Gummies 100mg", "variant": "100mg",
           "category": "edible", "description": "<p>Uplifting <b>chews</b></p>"}


def test_each_step_offers_only_the_values_left_and_size_only_the_products_sizes(monkeypatch):
    ask, asked = fake({"category": ("edible", 0.99), "subtype": ("gummy", 0.97),
                       "line": ("Gummies", 0.95), "strain": ("Wild Cherry Excite", 0.98),
                       "size": ("10pk 100mg", 0.93)})
    monkeypatch.setattr(jev, "ask_many", ask)
    got = cr.read(CAMINO, [LISTING], cache=NoCache())["1"]
    assert (got["category"], got["subtype"], got["product_line"], got["strain"], got["size"]) == \
        ("edible", "gummy", "Gummies", "Wild Cherry Excite", "10pk 100mg")
    assert got["by"] == "catalog" and got["p"]["size"] == 0.93
    opts = {k: [v for o, v in c.items() if o != cr.NONE] for k, _, c in asked}
    assert opts["subtype"][1].startswith("gummy: Gummies, chews")           # with its definition
    assert opts["strain"] == ["Pineapple Habanero", "Wild Cherry Excite"]    # the gummies alone
    assert opts["size"] == ["10pk 100mg: 10 pieces, 100mg THC in the whole package (THC only)",
                            "20pk 100mg: 20 pieces, 100mg THC in the whole package (THC only)"]
    size_state = next(s for k, s, _ in asked if k == "size")
    assert size_state["product"] == "Wild Cherry Excite"
    assert size_state["description"] == "Uplifting chews"


def test_an_unsure_line_is_left_blank_and_narrows_nothing(monkeypatch):
    ask, asked = fake({"category": ("edible", 0.99), "subtype": ("gummy", 0.6),
                       "line": ("Social", 0.7), "strain": ("Wild Cherry Excite", 0.98),
                       "size": ("10pk 100mg", 0.93)})
    monkeypatch.setattr(jev, "ask_many", ask)
    got = cr.read(CAMINO, [LISTING], cache=NoCache())["1"]
    assert got["subtype"] is None and got["product_line"] is None
    strain_opts = next(c for k, _, c in asked if k == "strain")
    assert len(strain_opts) == 4                                        # none + every strain
    assert cm.CatalogIndex(CAMINO).join(got)[0] == "wc"                 # the join still settles it


def test_a_line_option_names_its_strains_when_it_has_few(monkeypatch):
    ask, asked = fake({"category": ("edible", 0.99), "subtype": ("gummy", 0.97),
                       "line": ("Gummies", 0.95), "strain": ("Wild Cherry Excite", 0.98),
                       "size": ("10pk 100mg", 0.93)})
    monkeypatch.setattr(jev, "ask_many", ask)
    cr.read(CAMINO, [LISTING], cache=NoCache())
    line_opts = [v for o, v in next(c for k, _, c in asked if k == "line").items() if o != cr.NONE]
    assert line_opts == ["Gummies (its products: Pineapple Habanero, Wild Cherry Excite)"]
    monkeypatch.setattr(cr, "LINE_STRAINS_SHOWN", 1)
    assert cr.line_strains("Gummies", CAMINO["entries"]) == ""           # too many to list


def test_no_strain_ends_the_reading(monkeypatch):
    ask, asked = fake({"category": ("edible", 0.99), "subtype": ("gummy", 0.97),
                       "line": ("Gummies", 0.95), "strain": ("none", 0.9)})
    monkeypatch.setattr(jev, "ask_many", ask)
    got = cr.read(CAMINO, [LISTING], cache=NoCache())["1"]
    assert got["strain"] is None and "size" not in got["p"]
    assert [k for k, _, _ in asked] == ["category", "subtype", "line", "strain"]


def test_a_failed_call_leaves_the_listing_out(monkeypatch):
    monkeypatch.setattr(jev, "ask_many", lambda jobs, **kw: [None] * len(jobs))
    assert cr.read(CAMINO, [LISTING], cache=NoCache()) == {}


def test_answers_are_cached_per_question(monkeypatch, tmp_path):
    monkeypatch.setattr(cm, "CACHE_DIR", tmp_path)
    ask, asked = fake({"category": ("edible", 0.99), "subtype": ("gummy", 0.97),
                       "line": ("Gummies", 0.95), "strain": ("Wild Cherry Excite", 0.98),
                       "size": ("10pk 100mg", 0.93)})
    monkeypatch.setattr(jev, "ask_many", ask)
    first = cr.read(CAMINO, [LISTING])
    n = len(asked)
    assert cr.read(CAMINO, [LISTING]) == first and len(asked) == n


def reading(**kw):
    r = {"category": "edible", "subtype": "gummy", "product_line": "Gummies",
         "strain": "Wild Cherry Excite", "size": "10pk 100mg", "by": "catalog",
         "p": {"category": 0.99, "subtype": 0.97, "line": 0.95, "strain": 0.98, "size": 0.93}}
    p = kw.pop("p", {})
    r.update(kw)
    r["p"] = dict(r["p"], **p)
    return r


def resolve(r):
    [d] = cm.resolve(CAMINO, [{"id": 1, "name": "x", "category": "edible", "reading": r}], use_jev=False)
    return d


def test_a_sure_join_is_trusted_and_an_unsure_one_goes_to_review():
    assert resolve(reading()).method == "attributes"
    d = resolve(reading(p={"strain": 0.83}))
    assert (d.method, d.product_key, d.confidence) == ("review_unsure", "wc", 0.83)
    # An unsure size goes to review even when the store's size field names that size.
    [d] = cm.resolve(CAMINO, [{"id": 1, "name": "x", "variant": "10pk 100mg", "category": "edible",
                               "reading": reading(p={"size": 0.8})}], use_jev=False)
    assert d.method == "review_unsure"
    # Enrichment's reading carries no probabilities and is not held to the bar.
    plain = {k: v for k, v in reading().items() if k not in ("p", "by")}
    assert resolve(plain).method == "attributes"


def test_the_review_queue_says_why():
    assert resolve(reading(strain=None)).method == "review_missing"              # catalog lacks it
    assert resolve(reading(size="5pk 50mg", p={"size": 0.95})).method == "review_near"   # one attribute off
    assert resolve(reading(size=None, p={"size": 0.4})).method == "review_unsure"
    assert resolve(reading(category="flower", strain="Gelato", size="3.5g")).method == "none"


def test_the_strain_is_asked_again_from_the_name_and_a_disagreement_is_not_trusted(monkeypatch):
    calls = {"n": 0}
    ask, asked = fake({"category": ("edible", 0.99), "subtype": ("gummy", 0.97),
                       "line": ("Gummies", 0.95), "strain": ("Wild Cherry Excite", 0.98),
                       "size": ("10pk 100mg", 0.93)})

    def ask_many(jobs, **kw):
        # The name-only question (no description in its state) reads another strain.
        out = ask(jobs, **kw)
        for (state, q), r in zip(jobs, out):
            if "strain" in q and "description" not in state:
                calls["n"] += 1
                label = next(k for k, v in q["strain"].criteria.items() if v == "Pineapple Habanero")
                r.answers["strain"] = {"type": "choice", "choice": label, "probabilities": {label: 0.9}}
        return out
    monkeypatch.setattr(jev, "ask_many", ask_many)
    got = cr.read(CAMINO, [LISTING], cache=NoCache())["1"]
    assert calls["n"] == 1 and got["strain_from_name"] == "Pineapple Habanero"
    assert not cr.trusted(got)
    assert "strain_from_name" in cr.unsure_steps(got)
    assert resolve(dict(got)).method == "review_unsure"
    assert cr.trusted(dict(got, strain_from_name="Wild Cherry Excite"))


def test_category_is_not_held_to_a_bar():
    assert resolve(reading(p={"category": 0.5})).method == "attributes"


def test_the_stores_own_category_filing_is_in_the_state(monkeypatch):
    ask, asked = fake({"category": ("edible", 0.99), "subtype": ("gummy", 0.97),
                       "line": ("Gummies", 0.95), "strain": ("Wild Cherry Excite", 0.98),
                       "size": ("10pk 100mg", 0.93)})
    monkeypatch.setattr(jev, "ask_many", ask)
    got = cr.read(CAMINO, [dict(LISTING, store_category="Edibles")], cache=NoCache())["1"]
    assert all(state.get("store_category") == "Edibles" for _, state, _ in asked)
    assert got["store_category"] == "Edibles"


EXAMPLES = {"camino": [
    {"listing": "Camino WC Excite 10ct", "entry": {"strain": "Wild Cherry Excite", "size": "10pk 100mg"}},
    {"listing": "Camino Wild Cherry 20 count", "size_field": "100mg",
     "entry": {"strain": "Wild Cherry Excite", "size": "20pk 100mg"}},
    {"listing": "Camino Pineapple Hab chews", "entry": {"strain": "Pineapple Habanero"}},
    {"listing": "Pineapple again", "entry": {"strain": "Pineapple Habanero"}},          # a second for that entry
    {"listing": "Social Pear can", "entry": {"strain": "Sparkling Pear"}},
    {"listing": "Wild Cherry anything", "entry": {"strain": "Wild Cherry Excite"}},     # names two entries
    {"listing": "nowhere", "entry": {"strain": "Nope"}}]}                               # names none


def asked_instructions(monkeypatch):
    ask, _ = fake({"category": ("edible", 0.99), "subtype": ("gummy", 0.97),
                   "line": ("Gummies", 0.95), "strain": ("Wild Cherry Excite", 0.98),
                   "size": ("10pk 100mg", 0.93)})
    seen = []

    def ask_many(jobs, **kw):
        seen.extend((k, q.instructions) for _, qs in jobs for k, q in qs.items())
        return ask(jobs, **kw)
    monkeypatch.setattr(jev, "ask_many", ask_many)
    return seen


def test_one_listing_per_catalog_entry(monkeypatch):
    monkeypatch.setattr(cr, "_examples", lambda: EXAMPLES)
    got = [ex["listing"] for ex, _ in cr.brand_examples("camino", CAMINO["entries"])]
    assert got == ["Camino WC Excite 10ct", "Camino Wild Cherry 20 count", "Camino Pineapple Hab chews",
                   "Social Pear can"]


def test_a_couple_of_examples_from_entries_like_the_product_nearest_first(monkeypatch):
    monkeypatch.setattr(cr, "_examples", lambda: EXAMPLES)
    seen = asked_instructions(monkeypatch)
    cr.read(CAMINO, [LISTING], cache=NoCache())
    q = {k: i for k, i in seen}
    strain = [i for k, i in seen if k == "strain"]
    assert len(strain) == 2 and strain[0] == strain[1]                # the name-only check shows the same
    # Gummies only (the subtype and line read so far), nearest the listing's name first.
    assert strain[0].endswith("'Camino Wild Cherry 20 count' is 'Wild Cherry Excite'; 'Camino WC Excite 10ct' "
                              "is 'Wild Cherry Excite'; 'Camino Pineapple Hab chews' is 'Pineapple Habanero'.")
    # A sibling's size teaches too; the store's size field is shown for size only.
    assert "'Camino Wild Cherry 20 count' (size field 100mg) is '20pk 100mg'" in q["size"]
    assert "'Camino Pineapple Hab chews' is '10pk 100mg'" in q["size"]
    assert "size field" not in strain[0]
    assert "'Camino WC Excite 10ct' is 'Gummies'" in q["line"]
    for gone in ("Pineapple again", "anything", "nowhere"):
        assert all(gone not in i for _, i in seen)
    # Subtype is asked with examples too (another subtype's entry could be one); category not.
    assert all("Social Pear" not in i for k, i in seen if k != "subtype")
    assert "'Camino Wild Cherry 20 count' is 'gummy'" in q["subtype"]
    assert all("Examples" not in i for k, i in seen if k == "category")


def test_a_subtype_example_tells_a_pen_from_a_cart(monkeypatch):
    vapes = {"brand_name": "MFNY", "brand_slug": "mfny", "entries": [
        {"id": f"v{i}", "product_key": f"{sub}-{strain}", "is_active": True, "name": strain,
         "category": "vaporizers", "subtype": sub, "product_line": "Live Resin", "strain": strain,
         "variant": "0.5g"}
        for i, (sub, strain) in enumerate([("cart", "Skunk"), ("all-in-one", "Skunk"),
                                           ("cart", "Hash Burger"), ("all-in-one", "Hash Burger")])]}
    monkeypatch.setattr(cr, "_examples", lambda: {"mfny": [
        {"listing": "Hash Burger Live Resin 510 Cart | .5g",
         "entry": {"subtype": "cart", "strain": "Hash Burger"}},
        {"listing": "Hash Burger Live Resin Vape Pen | .5g",
         "entry": {"subtype": "all-in-one", "strain": "Hash Burger"}}]})
    ask, _ = fake({"category": ("vaporizers", 0.99), "subtype": ("all-in-one", 0.97),
                   "line": ("Live Resin", 0.95), "strain": ("Skunk", 0.98), "size": ("0.5g", 0.93)})
    seen = []

    def ask_many(jobs, **kw):
        seen.extend((k, q.instructions) for _, qs in jobs for k, q in qs.items())
        return ask(jobs, **kw)
    monkeypatch.setattr(jev, "ask_many", ask_many)
    pen = {"id": "p", "name": "MFNY Skunk Live Resin Vape Pen | .5g", "variant": "0.5g",
           "description": "The MFNY live resin vape cart has a terpene-rich profile"}
    cr.read(vapes, [pen], cache=NoCache())
    sub = next(i for k, i in seen if k == "subtype")
    assert sub.endswith("Examples from this brand's listings: 'Hash Burger Live Resin Vape Pen | .5g' is "
                        "'all-in-one'; 'Hash Burger Live Resin 510 Cart | .5g' is 'cart'.")


def test_examples_are_capped_and_brand_scoped(monkeypatch):
    monkeypatch.setattr(cr, "_examples", lambda: EXAMPLES)
    monkeypatch.setattr(cr, "EXAMPLES_SHOWN", 2)
    seen = asked_instructions(monkeypatch)
    cr.read(CAMINO, [LISTING], cache=NoCache())
    strain = next(i for k, i in seen if k == "strain")
    assert "Wild Cherry 20 count" in strain and "WC Excite 10ct" in strain and "Pineapple" not in strain
    seen.clear()
    cr.read(dict(CAMINO, brand_slug="other"), [LISTING], cache=NoCache())
    assert seen and all("Examples" not in i for _, i in seen)


def test_one_size_offered_and_picked_needs_only_to_beat_none(monkeypatch):
    assert cr.ONE_SIZE_AT == cr.TRUST_AT        # off until the owner picks the bar
    monkeypatch.setattr(cr, "ONE_SIZE_AT", 0.5)
    one = reading(size_options=1, p={"size": 0.55})
    assert cr.trusted(one) and "size" not in cr.unsure_steps(one)
    assert not cr.trusted(reading(size_options=1, size=None, p={"size": 0.6}))   # "none" picked
    assert not cr.trusted(reading(size_options=2, p={"size": 0.55}))
    assert not cr.trusted(reading(size_options=1, p={"size": 0.45}))


def test_a_volume_size_is_spelled_as_a_bottle_that_any_mg_fits():
    label = cr.spell_size("15mL", "tinctures")
    assert label.startswith("15mL: a 15mL bottle") and "any mg figure" in label
