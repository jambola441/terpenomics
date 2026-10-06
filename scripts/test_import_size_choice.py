"""Tests for import_listings.choose_sizes: a trusted match's size chosen among its own
readings and its product's catalog sizes."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import import_listings  # noqa: E402
import size_choice  # noqa: E402


def entry(eid, variant, key, category):
    return {"id": eid, "variant": variant, "product_key": key, "category": category, "is_active": True}


def record(name, variant, entry_id, category, brand="Brand", price_cents=None, description=None):
    return {"scraped_name": name, "variant": variant, "scraped_category": category, "scraped_brand": brand,
            "price_cents": price_cents, "description": description, "catalog_entry_id": entry_id,
            "catalog_match_method": "exact"}


def sized(records, catalogs, prices=None, **kw):
    import_listings.assign_sizes(records, catalogs)
    return import_listings.choose_sizes(records, catalogs, prices or size_choice.PriceBook(), **kw)


def jev_says(monkeypatch, value, p=0.9):
    monkeypatch.setattr(size_choice, "choose",
                        lambda items, prices=None, **kw: [size_choice.Pick(value, "jev", p) for _ in items])


def test_the_price_moves_a_pack_to_its_entry():
    """Hold Up Roll Up's $150 "Sour Diesel - 32PK 1G Prerolls" was matched to Herb's 1g.
    At $150 a gram is 15 times Herb's usual; 32g is half of it."""
    catalogs = {"herb": {"brand_name": "Herb", "entries": [entry("e1", "1g", "sd", "preroll"),
                                                           entry("e32", "32g", "sd", "preroll")]}}
    prices = size_choice.PriceBook(brand_per_g={"herb|preroll": {"median": 1000, "n": 5}})
    rec = record("Sour Diesel - 32PK 1G Prerolls", "1g", "e1", "preroll", brand="Herb", price_cents=15000)
    stats = sized([rec], catalogs, prices, use_jev=False)
    assert (rec["catalog_entry_id"], rec["size"]) == ("e32", "32g")
    assert stats["entry"] == 1


def test_jev_does_not_move_a_listing_off_its_entry(monkeypatch):
    """Measured on the live listings, Jev doubled Runtz's 2-packs (1.5g) to 3g."""
    catalogs = {"runtz": {"brand_name": "Runtz", "entries": [entry("e15", "1.5g", "lcr", "preroll")]}}
    jev_says(monkeypatch, 3.0, p=0.72)
    rec = record("Pre-Rolls | Runtz | Lemon Candy Runtz - 2pk", "1.5g", "e15", "preroll", brand="Runtz",
                 price_cents=1750)
    assert sized([rec], catalogs) == {"entry": 0, "size": 0, "asked": 1}
    assert (rec["catalog_entry_id"], rec["size"]) == ("e15", "1.5g")


def test_jev_agreeing_with_the_entry_sets_the_size_the_catalog_writes(monkeypatch):
    catalogs = {"mfny": {"brand_name": "MFNY", "entries": [entry("e1", "10pk 100mg", "cc", "edible")]}}
    jev_says(monkeypatch, 100.0)
    rec = record("MFNY - Cherry x Candy Rain | Mellow MF-er Live Rosin Gummies", "104mg", "e1", "edible")
    sized([rec], catalogs)
    assert rec["size"] == "100mg"
    catalogs = {"ruby": {"brand_name": "Ruby Farms", "entries": [entry("e5", "5g", "lc", "preroll")]}}
    jev_says(monkeypatch, 4.9)                  # 7 x 0.7g: the catalog's 5g, written as the catalog has it
    rec = record("7pk Classics Prerolls Limoncello (H)", "3.5g", "e5", "preroll")
    sized([rec], catalogs)
    assert (rec["catalog_entry_id"], rec["size"]) == ("e5", "5g")


def test_code_sizes_a_listing_whose_entry_has_no_size():
    catalogs = {"ayrloom": {"brand_name": "Ayrloom", "entries": [entry("e1", None, "rev", "topical")]}}
    rec = record("ayrloom | Revive 1:1 Topical | 1000MG THC : 1000MG CBD", "2000mg", "e1", "topical")
    sized([rec], catalogs, use_jev=False)
    assert (rec["catalog_entry_id"], rec["size"]) == ("e1", "1000mg")


def test_only_a_trusted_match_is_sized_and_the_switch_turns_it_off(monkeypatch):
    catalogs = {"herb": {"brand_name": "Herb", "entries": [entry("e1", "1g", "sd", "preroll"),
                                                           entry("e32", "32g", "sd", "preroll")]}}
    prices = size_choice.PriceBook(brand_per_g={"herb|preroll": {"median": 1000, "n": 5}})
    rec = {**record("Sour Diesel - 32PK 1G Prerolls", "1g", "e1", "preroll", brand="Herb", price_cents=15000),
           "catalog_match_method": "jev_review"}
    sized([rec], catalogs, prices, use_jev=False)
    assert (rec["catalog_entry_id"], rec["size"]) == ("e1", "1g")
    assert import_listings.size_choice_on()
    monkeypatch.setenv("IMPORT_SIZE_CHOICE", "0")
    assert not import_listings.size_choice_on()
