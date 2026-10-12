"""The pack convention (sizes.PACK_SIGN): a size with no count is one unit, a pack is
"N × unit" and is kept as written, a store's total still fits it."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_match  # noqa: E402
import catalog_grid  # noqa: E402
import sizes  # noqa: E402
import storefront  # noqa: E402

P = "preroll"


def test_a_pack_label_reads_as_count_unit_and_total():
    s = sizes.parse("2 × 0.5g", category="vaporizers")
    assert (s.pack, s.unit_g, s.grams) == (2, 0.5, 1.0)
    assert sizes.parse("4×.75g", category=P).grams == 3.0


def test_a_count_in_words_is_a_pack():
    assert sizes.parse("Candy Rain Live Resin 510 Cart Two-Fer", "1g", category="vaporizers").pack == 2
    assert sizes.parse("Hash Burger Pre-Roll Four Pack 3g", category=P).pack == 4
    assert sizes.parse("Hash Burger Pre-Roll 3g", category=P).pack is None


def test_only_the_multiplication_sign_is_kept_as_a_label():
    assert sizes.pack_label("2×.5g") == "2 × 0.5g"
    assert sizes.pack_label("1 × 1g") == "1g"
    assert sizes.pack_label("2 x 0.5g") is None and sizes.pack_label("1g") is None
    # Older recipes ("2 x 0.5g") and labels ("10pk 100mg") are stored as before.
    assert sizes.entry_variant("2 x 0.5g", sizes.parse("2 x 0.5g", category=P), P) == "1g"
    assert sizes.entry_variant("4 × 0.75g", sizes.parse("4 × 0.75g", category=P), P) == "4 × 0.75g"
    assert sizes.entry_variant("10pk 100mg", sizes.parse("10pk 100mg", category="edible"), "edible") == "10pk 100mg"


def test_two_variants_differ_by_count_only_under_the_convention():
    assert not sizes.same_variant("1g", "2 × 0.5g", P)
    assert sizes.same_variant("2 × 0.5g", "2 × 0.5g", P)
    assert sizes.same_variant("3g", "3g", P)
    # Without a pack label, totals decide as before.
    assert sizes.same_variant("2pk 1g", "1g", P)
    # A store's total fits the pack.
    assert sizes.same_size(sizes.parse("3g", category=P), sizes.parse("4 × 0.75g", category=P))


def _e(i, variant):
    return {"id": i, "variant": variant, "source": "storefront_html"}


def test_the_count_decides_between_a_single_and_a_pack_of_one_total():
    entries = [_e("single", "1g"), _e("pack", "2 × 0.5g"), _e("half", "0.5g")]
    want = lambda *t: sizes.parse(*t, category="vaporizers")
    assert catalog_match.fitting_entry(entries, want("1g"), "vaporizers")["id"] == "single"
    assert catalog_match.fitting_entry(entries, want("1g", "Oishii Cartridge 2pk"), "vaporizers")["id"] == "pack"
    assert catalog_match.fitting_entry(entries, want("1g", "Hash Burger (Two-fer)"), "vaporizers")["id"] == "pack"
    # A total with no single of it is the pack (Classics Chemdog sells no 1g single).
    only = [_e("pack", "2 × 0.5g"), _e("half", "0.5g")]
    assert catalog_match.fitting_entry(only, want("1g"), "vaporizers")["id"] == "pack"


def test_line_fill_keeps_pack_labels_beside_the_single_of_their_total():
    def e(key, strain, variant):
        return {"id": f"{key}{variant}", "product_key": key, "name": strain, "strain": strain,
                "product_line": "Live Resin Infused", "category": P, "subtype": None,
                "variant": variant, "source": "storefront_html"}
    cat = {"id": "c", "brand_name": "Some Brand", "entries": [
        e("hb", "Hash Burger", "1g"), e("hb", "Hash Burger", "2 × 0.5g"), e("cr", "Candy Rain", "4 × 0.75g")]}
    got = sorted((r["strain"], r["variant"]) for r in catalog_grid.wanted(cat).values())
    assert got == [("Candy Rain", "1g"), ("Candy Rain", "2 × 0.5g"), ("Hash Burger", "4 × 0.75g")]


def test_store_totals_are_written_as_the_lines_packs():
    lri = "Live Resin Infused"
    doc = {"brand_name": "Some Brand", "entries": [
        {"category": P, "product_line": lri, "variant": "4 × 0.75g"},
        {"category": P, "product_line": lri, "variant": "0.75g"},
        {"category": P, "product_line": lri, "variant": "1g"}]}

    def store(variant):
        return {"category": P, "product_line": lri, "product_key": "k", "variant": variant,
                "external_id": f"k:{storefront.squash(variant)}"}
    out = storefront.pack_store_sizes([store("3g"), store("2.25g"), store("1g"), store("0.75g")], doc)
    assert [(p["variant"], p["external_id"]) for p in out] == [
        ("4 × 0.75g", "k:4075g"), ("3 × 0.75g", "k:3075g"), ("1g", "k:1g"), ("0.75g", "k:075g")]
    # A brand that writes no pack label is untouched.
    plain = {"brand_name": "Other", "entries": [{"category": P, "product_line": lri, "variant": "3g"}]}
    assert storefront.pack_store_sizes([store("2.25g")], plain)[0]["variant"] == "2.25g"
