import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper_common import strip_noinfo, normalize_variant, canonical_brands


# ---------------------------------------------------------------------------
# strip_noinfo
# ---------------------------------------------------------------------------

class TestStripNoinfo:
    # --- pre-roll format descriptors ---

    def test_removes_pre_roll_segment(self):
        assert strip_noinfo("Delta Diamonds x Runtz | Pre Roll") == "Delta Diamonds x Runtz"

    def test_removes_pre_rolls_plural(self):
        assert strip_noinfo("OG Kush | Pre Rolls") == "OG Kush"

    def test_removes_pre_roll_hyphenated(self):
        assert strip_noinfo("Mint Kush | 2pk | Pre-Roll") == "Mint Kush"

    def test_removes_pre_roll_leading(self):
        assert strip_noinfo("Pre Roll | Jet Fuel") == "Jet Fuel"

    def test_removes_pre_roll_pack(self):
        assert strip_noinfo("OG Kush | Pre-Roll Pack") == "OG Kush"

    def test_removes_pre_roll_pack_in_segment(self):
        assert strip_noinfo("Gelato | Live Resin Infused Pre-Roll Pack | 5pk") == "Gelato | Live Resin Infused"

    def test_removes_single(self):
        assert strip_noinfo("Apples & Bananas | Single") == "Apples & Bananas"

    def test_removes_singles(self):
        assert strip_noinfo("Blue Dream | Singles") == "Blue Dream"

    def test_removes_single_pre_roll(self):
        assert strip_noinfo("Gelonade x Gelonade | Infused Single Pre-Roll") == "Gelonade x Gelonade | Infused"

    def test_removes_single_pre_roll_as_only_segment(self):
        assert strip_noinfo("Single Pre-Roll") == ""

    def test_removes_premium_flower(self):
        assert strip_noinfo("Blue Dream | Premium Flower") == "Blue Dream"

    # --- weight segments ---

    def test_removes_1_gram_joint(self):
        assert strip_noinfo("Bermuda Triangle | 1 Gram Joint | Single") == "Bermuda Triangle"

    def test_removes_half_gram_joints(self):
        assert strip_noinfo("Black Scotti | 1/2 Gram Joints | 7pk") == "Black Scotti"

    def test_removes_gram_segment_only(self):
        assert strip_noinfo("Live Resin Infused & Kief Coated | 1/2 Gram | 2pk | Pineapple Express") == "Live Resin Infused & Kief Coated | Pineapple Express"

    # --- pack / count ---

    def test_removes_10pk(self):
        assert strip_noinfo("Blue Dream | 10pk") == "Blue Dream"

    def test_removes_7pk(self):
        assert strip_noinfo("Live Rosin | Blue Dream | 7pk") == "Live Rosin | Blue Dream"

    def test_removes_5pk(self):
        assert strip_noinfo("Bermuda Triangle | Cones | 5pk") == "Bermuda Triangle"

    def test_removes_10ct(self):
        assert strip_noinfo("Gummies | 10ct") == "Gummies"

    def test_removes_pk_with_space(self):
        assert strip_noinfo("OG Kush | 10 pk") == "OG Kush"

    # --- sample inventory ---

    def test_removes_sample_segment(self):
        assert strip_noinfo("Sample | Hybrid | Alien OG") == "Hybrid | Alien OG"

    def test_removes_samples_allcaps(self):
        assert strip_noinfo("SAMPLES | Indica | Granddaddy Purple") == "Indica | Granddaddy Purple"

    # --- vape / vessel descriptors ---

    def test_removes_510_cart(self):
        assert strip_noinfo("Pineapple Express | 510 Cart") == "Pineapple Express"

    def test_removes_disposable_vape_pen(self):
        assert strip_noinfo("OG Kush | Disposable Vape Pen | Sativa") == "OG Kush | Sativa"

    def test_removes_all_in_one_vape_pen(self):
        assert strip_noinfo("Gelato | All-In-One Vape Pen") == "Gelato"

    def test_removes_cart(self):
        assert strip_noinfo("Sour Diesel | Cart") == "Sour Diesel"

    def test_removes_aio(self):
        assert strip_noinfo("Jet Fuel | AIO | Sativa") == "Jet Fuel | Sativa"

    def test_removes_pod(self):
        assert strip_noinfo("Wedding Cake | Pod") == "Wedding Cake"

    def test_removes_flower_jar(self):
        assert strip_noinfo("Wedding Cake | Flower Jar") == "Wedding Cake"

    def test_removes_cones(self):
        assert strip_noinfo("OG Kush | Cones") == "OG Kush"

    # --- preserves meaningful content ---

    def test_preserves_live_resin_infused(self):
        assert strip_noinfo("Gelato | Live Resin Infused | 5pk") == "Gelato | Live Resin Infused"

    def test_preserves_classification(self):
        assert strip_noinfo("Blue Dream | Hybrid") == "Blue Dream | Hybrid"

    def test_preserves_plain_name(self):
        assert strip_noinfo("Sour Diesel") == "Sour Diesel"

    def test_preserves_multi_segment_name(self):
        assert strip_noinfo("Live Resin Infused | Candy Jack | 5pk") == "Live Resin Infused | Candy Jack"

    def test_empty_string(self):
        assert strip_noinfo("") == ""


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
