"""What a listing is called on screen.

Every raw name below is a real one, lifted from the hand-labelled gold sets in
`evals/enrich/cases/`. The point of the module is that a shopper never reads a
store's catalogue string, so the assertions are about what they do read.
"""
import pytest

from services.display_name import clean, compose


# ---------------------------
# The composed path: enrichment already found the identity
# ---------------------------

def test_strain_is_the_name():
    assert compose(
        scraped_name="Apricot Punch -Indica- 85.45% THC | 0.5g Classic Surf All-In-One (Vape) | Bloom -sss11 front",
        brand="BLOOM",
        strain="Apricot Punch",
        category="vaporizers",
    ) == "Apricot Punch"


def test_product_line_leads_the_strain():
    assert compose(product_line="Flyers", strain="Fast Lane", category="preroll") == "Flyers Fast Lane"


def test_product_line_is_not_repeated_when_the_strain_already_says_it():
    # 'Little Pandas' + 'Little Pandas Tropical' would stutter on the card.
    assert compose(product_line="Little Pandas", strain="Little Pandas Tropical") == "Little Pandas Tropical"


def test_falls_back_through_line_then_subtype_then_category():
    assert compose(product_line="Releaf", category="topical") == "Releaf"
    assert compose(subtype="gummy", category="edible") == "Gummy"
    assert compose(category="merch") == "Merch"


def test_never_returns_blank():
    assert compose() == "—"
    assert compose(scraped_name="   ", brand="") == "—"


# ---------------------------
# The cleaned path: no strain, so the raw name is all there is
# ---------------------------

@pytest.mark.parametrize("raw,brand,expected", [
    # The brand, repeated from the column next to it.
    ("Silly Nice | Bubble Hash | 1G", "Silly Nice", "Bubble Hash"),
    ("MK Lighter Cultivate Series Jet Pocket Lighter", "MK Lighter", "Cultivate Series Jet Pocket Lighter"),
    ("STIIIZY Pro XL Battery - Red", "STIIIZY", "Pro XL Battery · Red"),
    # Brand at the end rather than the start.
    ("Watermelon Drip x 2pk Hemp Wraps | Billionaire", "Billionaire", "Watermelon Drip Hemp Wraps"),
    # Brand written differently in the name than in the brand column.
    ("Focus Tincture 13.40% THC | 864mg TAC THC:CBG 150mg:600mg | Head and Heal -ii12 back",
     "Head & Heal", "Focus Tincture"),

    # Potency, ratios and doses.
    ("Unscented CBD lotion - 300mg", "Head & Heal", "Unscented CBD lotion"),
    ("ayrloom | Low Dose Everyday Drops | 150MG THC : 450MG CBD", "ayrloom", "Low Dose Everyday Drops"),
    ("Ayrloom | Mood Energy | AIO | 1g | THC : THCV : CBG", "Ayrloom", "Mood Energy"),
    ("Foy - Strawberry Nighttime | 1:1:1 Chews", "foy", "Strawberry Nighttime · Chews"),

    # Sizes and pack counts.
    ("RAW Classic Cones - 1 1/4 6 Pack", "", "RAW Classic Cones"),
    ("Mega Dose Cherry Rings  - 100mg Gummy", "Flav", "Mega Dose Cherry Rings"),
    ("Papa & Barkley - 1:3 Releaf Balm - | 50ml", "Papa & Barkley", "Releaf Balm"),

    # Scraper debris pinned to the end.
    ("Relief Balm - 130mg CBD | 40mg THC | 3:1 | 15ml (Topical) Papa & Barkley      -yyy7 front",
     "Papa & Barkley", "Relief Balm"),

    # Classification the card shows in its own slot.
    ("Grön- Milk Chocolate Mini Bar- Daytime Sativa (100mg)", "Grön", "Milk Chocolate Mini Bar · Daytime"),

    # Nothing to strip.
    ("Mushroom Holder Dab Tool", "Human Grade", "Mushroom Holder Dab Tool"),
])
def test_clean_strips_what_the_card_already_shows(raw, brand, expected):
    assert clean(raw, brand) == expected


def test_a_format_word_inside_a_name_is_the_noun_not_noise():
    # 'Hash' and 'Battery' are what the product *is*; only a segment made
    # entirely of format words gets dropped.
    assert clean("Silly Nice | Bubble Hash | 1G", "Silly Nice") == "Bubble Hash"
    assert clean("Black - 510 Thread Stick Battery", "Bonanza") == "Black · 510 Thread Stick Battery"


def test_a_cannabinoid_in_the_product_name_survives():
    # Dropping any segment mentioning CBD would leave this listing nameless.
    assert clean("Organic Medium Dog CBD Oil - 600mg Tincture", "Head & Heal") == "Organic Medium Dog CBD Oil · Tincture"


def test_slashed_words_are_not_rewritten():
    assert clean("Timeless - Combo 510 Battery and Case | Black/Yellow", "Timeless") \
        == "Combo 510 Battery and Case · Black/Yellow"


def test_shouted_names_are_calmed_down():
    assert clean("BLACKBERRY KUSH DISPOSABLE", "Eureka") == "Blackberry Kush Disposable"


def test_at_most_two_segments_are_kept():
    # Past two, a name is restating the catalogue row rather than naming a product.
    assert clean("Alpha | Beta | Gamma | Delta", "") == "Alpha · Beta"


def test_a_name_that_is_only_the_brand_yields_nothing():
    assert clean("Ayrloom", "ayrloom") is None
    assert clean("| 1g |", "Whoever") is None
    assert clean("", "Whoever") is None
    assert clean(None) is None


def test_the_brand_survives_when_it_is_all_the_name_has():
    # Dropping it would leave the card blank, so compose falls through instead.
    assert compose(scraped_name="Ayrloom", brand="ayrloom", category="tinctures") == "Tinctures"


def test_cleaning_is_stable_when_applied_twice():
    # The output is shown, stored in order snapshots, and can be re-cleaned by a
    # later caller; a second pass must not keep eating the name.
    for raw, brand in [
        ("Silly Nice | Bubble Hash | 1G", "Silly Nice"),
        ("STIIIZY Pro XL Battery - Red", "STIIIZY"),
        ("Grön- Milk Chocolate Mini Bar- Daytime Sativa (100mg)", "Grön"),
    ]:
        once = clean(raw, brand)
        assert clean(once, brand) == once
