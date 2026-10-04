"""taxonomy.py is the single definition of category attributes. These tests pin that
moving the definitions there changed nothing the model reads, and that every
consumer agrees with it."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import taxonomy  # noqa: E402

GOLDEN = json.loads((Path(__file__).parent / "testdata" / "prompt_golden.json").read_text())


def test_enrichment_prompts_are_byte_identical_to_before_the_refactor():
    """A rail edit is a prompt edit, and prompt edits moved the gold suite every time
    one was made (README.md). The refactor must not be one."""
    import enrich
    assert enrich._CLASSIFY_PROMPT_HINTED == GOLDEN["CLASSIFY_PROMPT_HINTED"]
    assert enrich._CLASSIFY_PROMPT_FRESH == GOLDEN["CLASSIFY_PROMPT_FRESH"]
    assert enrich._EXTRACT_PROMPT == GOLDEN["EXTRACT_PROMPT"]


def test_rails_defaults_and_categories_unchanged():
    import enrich
    assert enrich.CATEGORIES == GOLDEN["CATEGORIES"]
    assert enrich.SUBTYPES == GOLDEN["SUBTYPES"]
    assert list(enrich.SUBTYPES) == list(GOLDEN["SUBTYPES"])   # order is the prompt's
    assert enrich._CATEGORY_DEFAULTS == GOLDEN["CATEGORY_DEFAULTS"]


def test_brand_prompt_rules_and_strain_bearing_unchanged():
    import brand_catalog
    import brand_prompt
    assert brand_prompt.CATEGORY_RULES == GOLDEN["BRAND_CATEGORY_RULES"]
    assert list(brand_prompt.CATEGORY_RULES) == list(GOLDEN["BRAND_CATEGORY_RULES"])
    assert sorted(brand_catalog.STRAIN_BEARING) == GOLDEN["STRAIN_BEARING"]


def test_every_default_is_on_its_rail():
    for name, s in taxonomy.SPECS.items():
        assert s.default_subtype is None or s.default_subtype in s.subtypes, name


def test_merch_tokens_only_produce_rail_values():
    import enrichers
    merch = enrichers.for_category("merch")
    assert merch.subtypes == taxonomy.MERCH_SUBTYPES
    for subtype, _ in merch.tokens:
        assert subtype in taxonomy.MERCH_SUBTYPES, subtype


def test_one_answer_to_dose_versus_weight():
    import scraper_common
    import sizes
    dose = taxonomy.categories_measured_by("dose")
    weight = taxonomy.categories_measured_by("weight")
    assert dose == {"edible", "tinctures", "topical"}
    assert weight == {"flower", "preroll", "vaporizers", "concentrate"}
    assert scraper_common._DOSE_CATEGORIES == sizes.DOSE_CATEGORIES == dose
    assert scraper_common._WEIGHT_CATEGORIES == sizes.WEIGHT_CATEGORIES == weight


def test_catalogs_cover_every_product_category():
    assert taxonomy.catalogable() == set(taxonomy.SPECS) - {"merch", "other"}
