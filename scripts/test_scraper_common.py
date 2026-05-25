import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper_common import normalize_variant, canonical_brands


# ---------------------------------------------------------------------------
# normalize_variant
# ---------------------------------------------------------------------------

class TestNormalizeVariant:
    def test_500mg_to_half_gram(self):
        assert normalize_variant("500mg") == "0.5g"

    def test_1000mg_to_1g(self):
        assert normalize_variant("1000mg") == "1g"

    def test_small_mg_unchanged(self):
        assert normalize_variant("100mg") == "100mg"

    def test_200mg_unchanged(self):
        assert normalize_variant("200mg") == "200mg"

    def test_gram_string_unchanged(self):
        assert normalize_variant("3.5g") == "3.5g"

    def test_non_variant_string_unchanged(self):
        assert normalize_variant("Hybrid") == "Hybrid"

    def test_case_insensitive(self):
        assert normalize_variant("500MG") == "0.5g"

    def test_strips_whitespace(self):
        assert normalize_variant(" 500mg ") == "0.5g"


# ---------------------------------------------------------------------------
# canonical_brands
# ---------------------------------------------------------------------------

class TestCanonicalBrands:
    def test_collapses_case_variants(self):
        result = canonical_brands({"grassroots", "Grassroots", "GRASSROOTS"})
        assert len(set(result.values())) == 1

    def test_picks_title_case_as_canonical(self):
        result = canonical_brands({"grassroots", "Grassroots"})
        assert result["grassroots"] == "Grassroots"

    def test_distinct_brands_stay_distinct(self):
        result = canonical_brands({"Grassroots", "Florist Farms"})
        assert result["Grassroots"] == "Grassroots"
        assert result["Florist Farms"] == "Florist Farms"

    def test_empty_set(self):
        assert canonical_brands(set()) == {}
