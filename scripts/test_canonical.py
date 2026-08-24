import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from canonical import canonicalize, canonical_strain, find_product_line
from scraper_common import normalize_variant


# ---------------------------------------------------------------------------
# Dose-vs-weight variants — regression for tincture doses stored as weights
# (Haiku answered "1000mg" and normalize_variant rewrote it to "1g").
# ---------------------------------------------------------------------------

class TestDoseVariants:
    def test_tincture_1000mg_stays_mg(self):
        assert normalize_variant("1000mg", "tinctures") == "1000mg"

    def test_edible_500mg_stays_mg(self):
        assert normalize_variant("500mg", "edible") == "500mg"

    def test_beverage_oz_not_converted_to_grams(self):
        assert normalize_variant("12oz", "edible") == "12oz"

    def test_weight_categories_still_convert(self):
        assert normalize_variant("1000mg", "flower") == "1g"
        assert normalize_variant("1/8oz", "flower") == "3.5g"

    def test_no_category_keeps_legacy_behavior(self):
        assert normalize_variant("1000mg") == "1g"
        assert normalize_variant("12oz") == "336g"


# ---------------------------------------------------------------------------
# Product lines
# ---------------------------------------------------------------------------

class TestProductLines:
    def test_line_found_in_name(self):
        assert find_product_line("Claybourne Co.", "Claybourne Co. - Banana OG | Flyers Infused 1.5G Blunt") == "Flyers"

    def test_line_absent_returns_none(self):
        assert find_product_line("Claybourne Co.", "Claybourne Co. - Blue Dream | 3.5g Flower") is None

    def test_ampersand_brand_matches_and_spelling(self):
        assert find_product_line("Papa and Barkley", "Papa & Barkley - Sleep Releaf Tincture | 30ml") == "Releaf"

    def test_brand_suffix_drift_matches(self):
        assert find_product_line("Timeless Vapes", "Timeless T2 - Jungle Punch | 2G") == "T2"
        assert find_product_line("Eaton", "Eaton Botanicals Little Pandas - Tropical Cooler") == "Little Pandas"

    def test_short_line_respects_word_boundaries(self):
        assert find_product_line("Ayrloom", "Ayrloom UP (12oz) Beverage - Lemonade") == "UP"
        for name in ("Ayrloom Syrup Blend", "Ayrloom Upside Cake", "Ayrloom - Pineapple Express"):
            assert find_product_line("Ayrloom", name) is None, name

    def test_unknown_brand_returns_none(self):
        assert find_product_line("Nobody", "Nobody - Flyers Something") is None

    def test_longest_match_wins(self):
        assert find_product_line("Claybourne Co.", "Claybourne Co. - Gas Plant | Classic Cuts 3.5g") == "Classic Cuts"


# ---------------------------------------------------------------------------
# Strain aliases
# ---------------------------------------------------------------------------

class TestStrainAliases:
    def test_alias_collapses_spelling_drift(self):
        assert canonical_strain("Kickfly's", "Black Scotti") == "Blackscotti"

    def test_alias_is_case_insensitive(self):
        assert canonical_strain("Alchemy Pure", "marrakesh") == "Marakesh"

    def test_unmapped_strain_untouched(self):
        assert canonical_strain("Kickfly's", "Blue Dream") is None

    def test_empty_strain_untouched(self):
        assert canonical_strain("Kickfly's", "") is None


# ---------------------------------------------------------------------------
# canonicalize() over rows
# ---------------------------------------------------------------------------

class TestCanonicalize:
    def test_sets_line_and_aliases_strain(self):
        rows = [
            {"brand": "Claybourne Co.", "name": "Claybourne Co. - Banana OG | Flyers Infused 1.5G Blunt",
             "strain": "Banana OG", "product_line": None},
            {"brand": "Kickfly's", "name": "Kickfly's - Blackscotti | 14G Flower",
             "strain": "Black Scotti", "product_line": None},
        ]
        stats = canonicalize(rows)
        assert rows[0]["product_line"] == "Flyers"
        assert rows[1]["strain"] == "Blackscotti"
        assert stats["product_line_set"] == 1 and stats["strain_aliased"] == 1

    def test_model_line_kept_when_brand_uncurated(self):
        rows = [{"brand": "Camino", "name": "Camino - Sleep | Midnight Blueberry",
                 "strain": "Midnight Blueberry", "product_line": "Sleep"}]
        canonicalize(rows)
        assert rows[0]["product_line"] == "Sleep"

    def test_line_stripped_out_of_strain(self):
        rows = [{"brand": "Ayrloom", "name": "Ayrloom UP (12oz) Beverage - Lemonade",
                 "strain": "UP Lemonade", "product_line": None}]
        stats = canonicalize(rows)
        assert rows[0]["strain"] == "Lemonade"
        assert rows[0]["product_line"] == "UP"
        assert stats["strain_delined"] == 1

    def test_strain_not_emptied_by_stripping(self):
        rows = [{"brand": "Ayrloom", "name": "Ayrloom UP (12oz)", "strain": "UP", "product_line": None}]
        canonicalize(rows)
        assert rows[0]["strain"] == "UP"

    def test_db_field_names_supported(self):
        rows = [{"scraped_brand": "Claybourne Co.",
                 "scraped_name": "Claybourne Co. - Banana OG | Flyers Infused 1.5G Blunt",
                 "strain": "Banana OG", "product_line": None}]
        canonicalize(rows)
        assert rows[0]["product_line"] == "Flyers"

    def test_no_changes_is_all_zero(self):
        rows = [{"brand": "Nobody", "name": "Nobody - Blue Dream 3.5g", "strain": "Blue Dream", "product_line": None}]
        assert not any(canonicalize(rows).values())
