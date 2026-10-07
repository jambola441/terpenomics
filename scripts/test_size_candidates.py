"""Tests for size_candidates.py: the readings a listing's size could have, and when they disagree."""

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import size_candidates as sc  # noqa: E402

EVAL = Path(__file__).resolve().parent.parent / "evals" / "sizes" / "run_eval.py"


def listing(name, variant=None, category="preroll", description=None):
    return {"scraped_name": name, "variant": variant, "scraped_category": category,
            "description": description}


def test_a_packs_lone_weight_reads_both_as_the_pack_and_as_each_unit():
    """Hold Up Roll Up's $150 "Sour Diesel - 32PK 1G Prerolls" went under the 1g product."""
    a = sc.assess(listing("Sour Diesel - 32PK 1G Prerolls", "1g"))
    assert a.status == "conflict"
    assert a.values == [1.0, 32.0]
    assert {(c.label(), c.reading) for c in a.candidates if c.source == "name"} == {
        ("1g", "as the pack total"), ("32g", "as 32 x 1g")}


def test_a_count_in_the_name_times_the_size_in_the_field():
    a = sc.assess(listing("Infused Pre-Rolls | MFNY | Honey Banana x Honey Banana - 2pk", "1g"))
    assert a.status == "conflict"
    assert [(c.label(), c.source) for c in a.candidates] == [("1g", "field"), ("2g", "name+field")]


def test_a_stated_unit_size_settles_the_pack():
    assert sc.assess(listing("Lychee Dream", "5 Pack | 0.6g each")).values == [3.0]
    assert sc.assess(listing("Lychee Dream 5 Pack | .6g | 3g")).values == [3.0]
    assert sc.assess(listing("Lychee Dream", "5 x 0.6g")).values == [3.0]
    assert sc.assess(listing("Mini Dogs 5-pack",
                             description="five 0.35g mini joints, 0.35g each")).values == [1.75]
    a = sc.assess(listing("Be Bright | Infused | 6pk", "4.5g", description="6 .75g Infused Pre Rolls | Sativa"))
    assert (a.status, a.values) == ("settled", [4.5])


def test_a_reading_implying_a_unit_that_does_not_exist_is_an_option_not_a_disagreement():
    a = sc.assess(listing("X| Wana | Peach Belini | Gummies | 10pc", "100mg", category="edible"))
    assert (a.status, a.values) == ("settled", [100.0])          # 10 x 100mg is over the cap
    assert a.options() == [100.0, 1000.0]
    assert sc.assess(listing("Bliss Drops 2pk - 10mg", category="edible")).values == [10.0, 20.0]
    a = sc.assess(listing("5pk 2.5g | Gelato"))
    assert (a.status, a.values) == ("settled", [2.5])            # 2.5g pre-rolls do not exist


def test_an_edible_figure_over_the_package_cap_does_not_count_against_one_under_it():
    a = sc.assess(listing("Level | Protab Max Indica Tablets 98.1 mg | 2pk", "196.2mg", category="edible"))
    assert (a.status, a.values) == ("settled", [98.1])
    a = sc.assess(listing("Drops | Blueberry Lullaby 20pc | 20mg", "400mg", category="edible"))
    assert (a.status, a.values) == ("settled", [20.0])


def test_when_every_reading_is_unlikely_they_all_count():
    """1906's pills come 30 to a pack at 5mg each: 150mg, over the edible cap, or 5mg
    for the pack, 0.17mg a pill. Neither unit exists, so both are asked about, and a
    store field stating 150mg is over the cap as well."""
    a = sc.assess(listing("1906 | Genius | 5MG THC , 5MG CBD , 5MG CBG | 30 pk", category="edible"))
    assert (a.status, a.values) == ("conflict", [5.0, 150.0])
    a = sc.assess(listing("1906 | Genius | 5MG THC , 5MG CBD , 5MG CBG | 30 pk", "150mg", category="edible"))
    assert a.status == "conflict" and {5.0, 150.0} <= set(a.values)


def test_a_number_in_a_strain_is_not_a_count():
    assert sc.assess(listing("Gelato 33 Pre-Roll 1g", "1g")).status == "settled"
    a = sc.assess(listing("5 Pre-Rolls | Gelato | 0.5g"))
    assert (a.values, a.options()) == ([2.5], [0.5, 2.5])       # five 0.1g pre-rolls do not exist


def test_a_dose_reading_is_thc_unless_nothing_else_is_stated():
    a = sc.assess(listing("Wana Fast Asleep Gummies 20mg THC 100mg CBD", category="edible"))
    assert a.values == [20.0]
    assert sc.assess(listing("Calm Balm 500mg CBD", category="topical")).values == [500.0]


def test_a_size_field_holding_thc_plus_other_cannabinoids_is_not_the_thc():
    a = sc.assess(listing("Ayrloom | Low Dose Everyday Drops | 1:3 | 150MG THC : 450MG CBD", "600mg",
                          category="tinctures"))
    assert (a.status, a.values) == ("settled", [150.0])
    assert a.options() == [150.0, 600.0]
    a = sc.assess(listing("ayrloom | Restore 1:1 Topical | 1000MG THC : 1000MG CBD", "2000mg", category="topical"))
    assert (a.status, a.values) == ("settled", [1000.0])
    a = sc.assess(listing("X| Drops | Black Currant | THC 100mg | CBD 100mg | CBN 100mg | 20pc", "300mg",
                          category="edible"))
    assert 300.0 not in a.values
    a = sc.assess(listing('Ayrloom | "Pillow Talk" | 1:1 | 5MG THC : 5MG CBN 10 Pack', "10mg", category="edible"))
    assert a.values == [5.0, 50.0]                               # not 10 x the 10mg sum


def test_a_figure_stated_beside_the_cannabinoids_it_adds_up_is_not_the_thc():
    """Ayrloom's Pillow Talk drops: "1800mg per package/300mg THC per serving/1500mg CBN
    per serving". A pack's total that only happens to equal one piece's sum stays: a
    2-pack of "10mg THC + 10mg CBN/gummy" holds 20mg of THC."""
    a = sc.assess(listing("Pillow Talk Sleep Drops - 300MG THC:1500MG CBN", category="tinctures",
                          description="1:5 THC:CBN. 1800mg per package/300mg THC per serving/1500mg CBN per serving."))
    assert (a.status, a.values) == ("settled", [300.0])
    a = sc.assess(listing("Dreamberry | Hash-Infused Gummies | 20mg | 2pk", "20mg", category="edible",
                          description="Sweet dreams, Jaunty. 10mg THC + 10mg CBN/gummy"))
    assert 20.0 in a.values


def test_a_cart_stated_in_mg_reads_in_grams():
    assert sc.assess(listing("Jetty Alien OG Cart", "1000mg", category="vaporizers")).values == [1.0]


def test_the_matched_products_sizes_are_options_not_evidence():
    entries = [{"variant": "3.5g", "category": "flower"}, {"variant": "7g", "category": "flower"}]
    a = sc.assess(listing("Blue Dream 1g", "1g", category="flower"), entries)
    assert (a.status, a.values, a.catalog) == ("off_catalog", [1.0], [3.5, 7.0])
    assert a.options() == [1.0, 3.5, 7.0]
    a = sc.assess(listing("Blue Dream", category="flower"), entries)
    assert (a.status, a.options()) == ("silent", [3.5, 7.0])
    assert sc.assess(listing("Blue Dream 3.5g", category="flower"), entries).status == "settled"


def test_an_ounce_word_is_a_reading_even_in_a_name():
    """Major's "Quarter Water" is a strain; read as a quarter ounce it is 7g. The
    generator lists it and the conflict goes to the chooser, not to a rule."""
    a = sc.assess(listing("Major | Quarter Water | 2g", "2g", category="vaporizers"))
    assert (a.status, a.values) == ("conflict", [2.0, 7.0])


def test_an_ounce_compound_hyphenated_or_run_together():
    """"Half-Ounce" was read as its last word, an ounce (28g)."""
    for name in ("Gelato Half-Ounce Bag", "Gelato Half Ounce", "Gelato HalfOunce", "Gelato Half-Oz"):
        assert sc.assess(listing(name, category="flower")).values == [14.0], name
    assert sc.assess(listing("Gelato Quarter-Ounce", category="flower")).values == [7.0]
    assert sc.assess(listing("Gelato Eighth-Oz", category="flower")).values == [3.5]
    assert sc.assess(listing("Gelato 1/8-oz", category="flower")).values == [3.5]
    assert sc.assess(listing("Gelato Ounce", category="flower")).values == [28.0]


def test_counts_and_figures_stores_write_loosely():
    assert sc.assess(listing("Runtz - Lemon Candy Runtz | .75g Pre-Roll 2 - Pack")).values == [0.75, 1.5]
    assert sc.assess(listing("2x Baked | Sugar Cookie | 10mg | 10 Bite size Cookies",
                             category="edible")).values == [10.0, 100.0]
    assert sc.assess(listing("Hashtag Honey - 3,5g Flower - Gorilla Glue OG", category="flower")).values == [3.5]
    assert sc.assess(listing("Head and Heal Lotion 1,000mg", category="topical")).values == [1000.0]
    assert sc.assess(listing("OFF HOURS Gummies - Mellow - 10 pcs - 10mgTHc/2mgCBd",
                             category="edible")).values == [10.0, 100.0]
    assert sc.assess(listing("X| Flamer | Hehe Haha | 3.5", category="flower")).values == [3.5]
    assert sc.assess(listing("Torrwood Farm Prerolled Flower 28pk Lilac Diesel 1oz")).values == [28.0]
    assert sc.assess(listing("Black Maple (IH) 3.5g - 1/8oz - Flower", category="flower")).values == [3.5]
    assert sc.assess(listing("Off Hours | Overglow Sour Rope | 100THC:40CBG", category="edible")).values == [100.0]
    assert sc.assess(listing("Papa & Barkley THC1000 Releaf Tincture 30ml", "30", category="tinctures")).values == [1000.0]


def test_a_count_in_one_text_times_a_unit_in_another():
    """Edie Parker's Blossoms: "7 Pack" in the name, "Five 0.5g pre-rolls" in a description
    written for the 5-pack. 7 x 0.5g is the 3.5g the store sells."""
    a = sc.assess(listing("Edie Parker | Nightcap Ice Cream Mintz | Blossoms | 7 Pack", "3.5g",
                          description="Indica Blossoms Five 0.5g pre-rolls Effects: relaxing"))
    assert a.status == "conflict"
    assert 3.5 in a.values and 2.5 in a.values
    assert any(c.source == "name+description" and c.value == 3.5 for c in a.candidates)


def test_a_blind_reader_s_size_is_among_the_options_and_rarely_overruled():
    """evals/sizes: a model read 1,000 listings' names and descriptions without seeing
    this code, the store's size field or the catalog. The size it believes must be among
    the options a chooser would get, and the code must almost never settle on its own
    on a different one. The gate is what was measured on 2026-10-06 (597/598, 2/598)."""
    spec = importlib.util.spec_from_file_location("size_eval", EVAL)
    size_eval = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(size_eval)
    s = size_eval.score(size_eval.load_cases())
    assert s["judged"] == 598
    assert s["best_in_options"] / s["judged"] >= 0.995
    assert s["false_agreement"] / s["judged"] <= 0.005
