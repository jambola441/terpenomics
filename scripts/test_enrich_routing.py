"""Which rows reach which model in enrich.py — offline, with Jev and the LLM faked.

Two routes skip work the LLM used to do:
  - catalog first: a listing that names a catalog product takes the catalog's answer
    and reaches no model at all (enrich.catalog_answer)
  - Jev classifies: category and subtype come from Jev (jev_classify.py), the LLM
    writes strain, product line and size in one call, and rows Jev is unsure of take
    the old two-call path
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_match  # noqa: E402
import catalog_store  # noqa: E402
import enrich  # noqa: E402
import jev_classify  # noqa: E402
from brand_catalog import strip_brand  # noqa: E402


# --- catalog first -----------------------------------------------------------

STORE_NAMES = {
    "fj3": "Jetpacks FJ-3 Afghani 5pk - Infused Pre-Rolls",
    "gummy": "Jetpacks Blue Razz Gummies 10pk",
    "masked": "Jetpacks Alaskan Thunder Fuck Pre-Roll",
    "nosub": "Jetpacks Mystery Thing",
}


def entry(key, name, category, subtype, strain, variant, line=None):
    return {"id": f"id-{key}", "product_key": key, "name": name, "category": category,
            "subtype": subtype, "strain": strain, "variant": variant, "product_line": line,
            "is_active": True, "match_terms": [strip_brand(STORE_NAMES[key], "Jetpacks")]}


CATALOG = {"brand_name": "Jetpacks", "entries": [
    entry("fj3", "FJ-3 Afghani", "preroll", "infused", "Afghani", "5pk 3g", "FJ-3"),
    entry("gummy", "Blue Razz Gummies", "edible", "gummy", "Blue Razz", "100mg"),
    entry("masked", "Alaskan Thunder Fu*k", "preroll", "single", "Alaskan Thunder Fu*k", "1g"),
    entry("nosub", "Mystery Thing", "edible", None, "Mystery", "100mg"),
]}
INDEXES = {catalog_store.brand_key("Jetpacks"): catalog_match.CatalogIndex(CATALOG)}


def row(key, variant, category="preroll", brand="Jetpacks", **kw):
    return {"name": STORE_NAMES.get(key, key), "brand": brand, "category": category,
            "variant": variant, "sku": key, "dispensary_slug": "test-store", **kw}


def test_a_listing_that_names_a_catalog_product_takes_its_identity():
    hit = enrich.catalog_answer(row("fj3", "5pk x 0.6g"), INDEXES)
    assert hit == {"category": "preroll", "subtype": "infused", "strain": "Afghani",
                   "product_line": "FJ-3", "variant": "3g"}


def test_the_size_written_is_the_listings_total_in_pass_a_form():
    # 10 pieces of a lone 10mg dose is 100mg (NY caps an edible package at 100mg).
    hit = enrich.catalog_answer(row("gummy", "10mg", category="edible"), INDEXES)
    assert hit["variant"] == "100mg" and hit["subtype"] == "gummy"


@pytest.mark.parametrize("listing", [
    row("fj3", "1g"),                              # size disagrees with the entry
    row("fj3", "0.6g"),       # "5pk" is in the name only: 0.6g is the store's figure
    row("fj3", ""),                                # no size to check — the name has none
    row("masked", "1g"),                           # a self-censored strain is never copied
    row("nosub", "100mg", category="edible"),      # an incomplete entry settles nothing
    row("fj3", "5pk x 0.6g", brand="Someone Else"),  # brand without a catalog
    row("Jetpacks Something New 1g", "1g"),        # not a recorded name: that is for Jev
])
def test_anything_short_of_a_full_answer_goes_to_the_model(listing):
    assert enrich.catalog_answer(listing, INDEXES) is None


def test_catalog_rows_never_reach_a_model(monkeypatch):
    seen = []
    monkeypatch.setattr(enrich, "_catalog_indexes", lambda: INDEXES)
    monkeypatch.setattr(enrich, "_load_cache", lambda slug: {})

    def fake_run(pending, cache, slug, categories, subtypes, strains, lines, variants, *a):
        seen.extend(r["name"] for _, r in pending)
        for oi, _ in pending:
            categories[oi], subtypes[oi], strains[oi], variants[oi] = "preroll", "single", "X", "1g"
        return dict(enrich._ZERO_USAGE)

    monkeypatch.setattr(enrich, "_run_enrich", fake_run)
    rows = [row("fj3", "5pk x 0.6g"), row("Jetpacks Something New 1g", "1g")]
    usage = enrich.enrich(rows, model="haiku-or", brand_examples={}, catalog_first=True)
    assert seen == ["Jetpacks Something New 1g"]
    assert usage["from_catalog"] == 1
    assert (rows[0]["strain"], rows[0]["product_line"], rows[0]["variant"]) == ("Afghani", "FJ-3", "3g")


def test_catalog_first_off_sends_everything_on(monkeypatch):
    monkeypatch.setattr(enrich, "_catalog_indexes", lambda: pytest.fail("catalogs read"))
    monkeypatch.setattr(enrich, "_load_cache", lambda slug: {})
    monkeypatch.setattr(enrich, "_run_enrich", lambda pending, *a: dict(enrich._ZERO_USAGE))
    usage = enrich.enrich([row("fj3", "5pk x 0.6g")], model="haiku-or", brand_examples={},
                          catalog_first=False)
    assert usage["from_catalog"] == 0


# --- Jev classifies, the LLM writes text --------------------------------------

def gummy(name, sku):
    return {"name": name, "brand": "Testbrand", "category": "edible", "variant": "10mg",
            "sku": sku, "dispensary_slug": "test-store", "description": ""}


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """A fake LLM that records what each prompt was asked, and a temp cache dir."""
    calls = {"classify": [], "extract": [], "extract_sized": []}

    def fake_llm(client, provider, api_model, system_prompt, payload, *rest):
        if system_prompt in (enrich._CLASSIFY_PROMPT_HINTED, enrich._CLASSIFY_PROMPT_FRESH):
            calls["classify"] += payload
            out = {p["id"]: {"category": "edible", "subtype": "gummy", "variant": "50mg"}
                   for p in payload}
        elif system_prompt == enrich._EXTRACT_PROMPT_SIZED:
            calls["extract_sized"] += payload
            out = {p["id"]: {"strain": "Sized", "product_line": None, "variant": "100mg"}
                   for p in payload}
        else:
            assert system_prompt == enrich._EXTRACT_PROMPT
            calls["extract"] += payload
            out = {p["id"]: {"strain": "Plain", "product_line": None} for p in payload}
        return out, dict(enrich._ZERO_USAGE)

    monkeypatch.setattr(enrich, "_call_llm", fake_llm)
    monkeypatch.setattr(enrich, "_make_client", lambda cfg: object())
    monkeypatch.setattr(enrich, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(enrich.jev, "available", lambda: True)
    return calls


def jev_answers(*specs):
    def fake_classify(items, **kw):
        assert len(items) == len(specs)
        return [None if s is None else
                jev_classify.Answer("edible", s[0], {"edible": ("gummy", s[1])}) for s in specs]
    return fake_classify


def test_confident_jev_rows_skip_pass_a_and_code_or_pass_b_writes_the_size(fakes, monkeypatch):
    monkeypatch.setenv("ENRICH_CLASSIFIER", "jev")
    monkeypatch.setattr(enrich.jev_classify, "classify",
                        jev_answers((0.97, 0.93), (0.97, 0.93), (0.97, 0.55), None))
    rows = [gummy("Sure Gummies 10pk", "a"),                  # code reads 10 x 10mg = 100mg
            dict(gummy("Sure Gummies 5mg THC 2.5mg CBN", "d"), variant=""),  # two doses
            gummy("Unsure Gummies 10pk", "b"), gummy("Failed Gummies 10pk", "c")]
    usage = enrich.enrich(rows, model="haiku-or", brand_examples={}, catalog_first=False)

    assert [p["name"] for p in fakes["classify"]] == ["Unsure Gummies 10pk", "Failed Gummies 10pk"]
    assert [p["name"] for p in fakes["extract_sized"]] == ["Sure Gummies 5mg THC 2.5mg CBN"]
    assert fakes["extract_sized"][0]["hint_variant"] == ""
    assert sorted(p["name"] for p in fakes["extract"]) == [
        "Failed Gummies 10pk", "Sure Gummies 10pk", "Unsure Gummies 10pk"]
    assert [(r["strain"], r["variant"]) for r in rows] == [
        ("Plain", "100mg"), ("Sized", "100mg"), ("Plain", "50mg"), ("Plain", "50mg")]
    assert (usage["jev_classified"], usage["sized_by_code"]) == (2, 1)

    cache = json.loads((enrich._CACHE_DIR / "test-store.haiku-or.json").read_text())
    assert cache["a|10mg"]["jq"] == jev_classify.QUESTION_VERSION
    assert "jq" not in cache["b|10mg"]


@pytest.mark.parametrize("name,variant,category,want", [
    ("Blue Dream 1/8", "3.5g", "flower", "3.5g"),
    ("GMO | Pre-Roll Pack | 2pk", "0.8g", "preroll", "0.8g"),     # the store's figure
    ("Runtz - 28G Flower", "1/8 oz", "flower", None),              # name and field disagree
    ("Gummies 10pk", "10mg", "edible", "100mg"),                   # pack math, NY cap
    ("Gummies 20MG x 2PK", "", "edible", "40mg"),
    ("Drops | 150MG THC : 450MG CBD", ".15g", "tinctures", None),  # two doses: model reads it
    ("Tea Sachets", "50.0 milligrams", "edible", "50mg"),
    ("Mystery", "", "edible", None),
])
def test_stated_size(name, variant, category, want):
    assert enrich.stated_size({"name": name, "variant": variant}, category) == want


def test_a_cached_answer_from_an_older_jev_question_is_asked_again(fakes, monkeypatch):
    monkeypatch.setenv("ENRICH_CLASSIFIER", "jev")
    monkeypatch.setattr(enrich.jev_classify, "classify", jev_answers((0.97, 0.93)))
    stale = {"v": enrich._ENRICH_VERSION, "category": "edible", "subtype": "chocolate",
             "strain": "Old", "product_line": None, "variant": "10mg",
             "jq": jev_classify.QUESTION_VERSION - 1}
    (enrich._CACHE_DIR / "test-store.haiku-or.json").write_text(json.dumps({"a|10mg": stale}))
    rows = [gummy("Sure Gummies 10pk", "a")]
    enrich.enrich(rows, model="haiku-or", brand_examples={}, catalog_first=False)
    assert rows[0]["subtype"] == "gummy" and rows[0]["strain"] == "Plain"


def test_llm_classifier_never_asks_jev(fakes, monkeypatch):
    monkeypatch.setenv("ENRICH_CLASSIFIER", "llm")
    monkeypatch.setattr(enrich.jev_classify, "classify",
                        lambda *a, **k: pytest.fail("Jev asked under ENRICH_CLASSIFIER=llm"))
    rows = [gummy("Sure Gummies 10pk", "a")]
    usage = enrich.enrich(rows, model="haiku-or", brand_examples={}, catalog_first=False)
    assert len(fakes["classify"]) == 1 and not fakes["extract_sized"]
    assert rows[0]["variant"] == "50mg" and "jev_classified" not in usage


def test_jev_questions_put_the_hints_first():
    qs = jev_classify.questions("vaporizers", "pod")
    assert next(iter(qs["category"].criteria)) == "vaporizers"
    assert next(iter(qs["subtype.vaporizers"].criteria)) == "pod"
    assert next(iter(qs["subtype.flower"].criteria)) == "flower"     # its default
    assert "subtype.merch" not in qs                                 # tokens decide merch
