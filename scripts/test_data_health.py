"""The daily audit's detectors, on small made-up data; the memory tables on a test DB."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_health as dh  # noqa: E402

NOW = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc)


def catalog(brand, *entries, method="listings_bootstrap"):
    slug = brand.lower().replace(" ", "-")
    return {"id": f"c-{slug}", "brand_name": brand, "brand_slug": slug, "source_method": method,
            "entries": [{"id": e.pop("id", f"{slug}-{i}"), "catalog_id": f"c-{slug}", "is_active": True,
                         "product_key": e.pop("pk", f"{slug}:{e['name']}"), "match_terms": [], **e}
                        for i, e in enumerate(entries)]}


def listing(i, store, name, entry=None, method=None, variant=None, brand="STIIIZY", category="preroll",
            seen=NOW - timedelta(hours=1), **extra):
    return {"id": f"l{i}", "dispensary_id": store, "scraped_name": name, "scraped_brand": brand,
            "scraped_category": category, "variant": variant, "size": None, "description": None,
            "catalog_entry_id": entry, "catalog_match_method": method, "catalog_match_confidence": None,
            "last_seen_at": seen.isoformat(), **extra}


def data(listings, *catalogs, aliases=None):
    return dh.Data(listings, {c["brand_slug"]: c for c in catalogs},
                   {s: {"id": s, "name": f"Store {s}", "slug": f"store-{s}"} for s in "ABCDE"},
                   aliases or {}, NOW)


def keys(findings):
    return sorted(f.key for f in findings)


STIIIZY = catalog("STIIIZY",
                  {"id": "os1", "pk": "os", "name": "40's Orange Sunset", "category": "preroll",
                   "product_line": "40's", "strain": "Orange Sunset", "variant": "1g"})


def test_a_store_the_run_missed_is_flagged():
    ls = [listing(1, "A", "x"), listing(2, "B", "y", seen=NOW - timedelta(days=3)),
          listing(3, "B", "z", seen=NOW - timedelta(days=3))]
    found = dh.stale_stores(data(ls))
    assert keys(found) == ["stale-store:store-B"]
    assert found[0].evidence == 2


def test_a_missing_size_needs_two_stores():
    ls = [listing(1, "A", "40's Orange Sunset 5pk - 2.5g", "os1", "jev_review", "2.5g"),
          listing(2, "B", "STIIIZY 40s Orange Sunset 2.5g", "os1", "jev", "2.5g"),
          listing(3, "C", "Orange Sunset 5 x 0.9g", "os1", "jev", "4.5g"),      # one store only
          listing(4, "D", "40's Orange Sunset 1g", "os1", "exact", "1g")]      # fits
    found = dh.missing_sizes(data(ls, STIIIZY))
    assert keys(found) == ["missing-size:stiiizy:os:2.5g"]
    assert "comes in 1g; 2 listing(s) at 2 store(s) say 2.5g" in found[0].text


def test_a_dose_typo_the_product_page_corrects_is_not_a_missing_size():
    camino = catalog("Camino", {"id": "yl", "name": "Balance Yuzu Lemon", "category": "edible",
                                "variant": "20pk 100mg"})
    ls = [listing(i, s, "Balance | Yuzu Lemon | 1:1 | 20pk", "yl", "exact", "50mg", brand="Camino",
                  category="edible", description="5mg THC : 5mg CBD per piece - 100mg THC per package")
          for i, s in enumerate("AB")]
    assert dh.missing_sizes(data(ls, camino)) == []


def test_a_review_cluster_needs_two_stores_and_a_size_that_fits():
    ls = [listing(1, "A", "Orange Sunset Infused 1g", "os1", "jev_review", "1g"),
          listing(2, "B", "Stiiizy Orange Sunset Single", "os1", "jev_review", "1g"),
          listing(3, "C", "Orange Sunset pack", "os1", "jev_review", "2.5g")]   # a size it lacks
    found = dh.review_clusters(data(ls, STIIIZY))
    assert keys(found) == ["review-cluster:stiiizy:os"]
    assert found[0].evidence == 2


def test_a_brandless_listing_named_after_a_catalog_brand():
    ls = [listing(1, "A", "STIIIZY - ORG PODS - ORANGE SUNSET - 0.5G", brand=None),
          listing(2, "A", "Stiiizy 40's Biscotti 1g", brand=None),
          listing(3, "A", "Stii Sour Diesel", brand=None),          # an alias spelling
          listing(4, "A", "RAW Classic Cones", brand=None),         # no catalog brand
          listing(5, "A", "STIIIZY Pod", brand="STIIIZY")]          # has its brand
    found = dh.brandless(data(ls, STIIIZY, aliases={"stii": "STIIIZY"}))
    assert keys(found) == ["brandless:stiiizy"]
    assert found[0].evidence == 3


def test_size_sync_reports_what_the_last_import_left_behind():
    camino = catalog("Camino", {"id": "yl", "name": "Balance Yuzu Lemon", "category": "edible",
                                "variant": "20pk 100mg"})
    typo = listing(1, "A", "Balance | Yuzu Lemon | 1:1 | 20pk", "yl", "exact", "50mg", brand="Camino",
                   category="edible", description="100mg THC per package")
    assert [f.evidence for f in dh.size_sync(data([typo], camino))] == [1]
    assert dh.size_sync(data([{**typo, "size": "100mg"}], camino)) == []


def test_a_dismissed_finding_stays_hidden_until_its_evidence_grows():
    found = [dh.Finding("missing-size:x:p:4.5g", "missing-size", "t", 2),
             dh.Finding("brandless:x", "brandless", "t", 9)]
    shown, hidden = dh.visible(found, {"missing-size:x:p:4.5g": {"evidence": 2},
                                       "brandless:x": {"evidence": 5}})
    assert [f.key for f in hidden] == ["missing-size:x:p:4.5g"]
    assert [f.key for f in shown] == ["brandless:x"]          # 9 > 5: back in the report


def test_the_report_marks_new_findings_and_moves_in_the_numbers():
    found = [dh.Finding("brandless:x", "brandless", "87 listing(s) with no brand", 87, "look here", (87,)),
             dh.Finding("brandless:y", "brandless", "3 listing(s) with no brand", 3, "", (3,))]
    m = {"active_listings": 22050, "stores": 28, "catalog_brand_listings": 14870, "trusted": 10620,
         "trusted_share": 71.4, "review_only": 740, "no_brand": 590}
    prev = {"taken_at": "2026-10-05T18:40:00+00:00", "findings": {"brandless:y": 3},
            "metrics": {**m, "active_listings": 22038, "trusted_share": 71.2, "review_only": 744}}
    text = dh.render(m, found, {}, prev, NOW)
    assert "active listings 22,050 (+12)" in text
    assert "= 71.4% (+0.2)" in text and "review-only 740 (-4)" in text
    assert "- [NEW] 87 listing(s) with no brand" in text
    assert "- 3 listing(s) with no brand" in text             # seen yesterday: not new


def test_snapshots_and_dismissals_round_trip(fresh_db, via_rest):
    via_rest(fresh_db)
    assert dh.previous_snapshot() is None
    dh.save_snapshot({"trusted_share": 71.4}, [dh.Finding("brandless:x", "brandless", "t", 87)])
    snap = dh.previous_snapshot()
    assert snap["metrics"] == {"trusted_share": 71.4} and snap["findings"] == {"brandless:x": 87}

    import db_http
    db_http.upsert("data_health_dismissals", {"finding_key": "shared-name:x:vape cartridge",
                                              "reason": "generic", "evidence": 5}, on_conflict="finding_key")
    assert dh.load_dismissals()["shared-name:x:vape cartridge"]["evidence"] == 5
    assert dh.main(["undismiss", "shared-name:x:vape cartridge"]) == 0
    assert dh.load_dismissals() == {}


def test_a_curated_product_nothing_matched_for_30_days_is_flagged():
    def curated(id, strain, made_days_ago, pk=None):
        return {"id": id, "name": strain, "pk": pk or f"lb:flower:flower::{strain.lower()}", "category": "flower",
                "strain": strain, "variant": "3.5g", "source": "curated",
                "first_seen_at": (NOW - timedelta(days=made_days_ago)).isoformat()}
    find = catalog("Find.", curated("z", "Zangria", 45), curated("t", "Tierz", 45),
                   curated("o", "Out Of Office", 5),                         # too new to judge
                   {"id": "b", "name": "Gas Lit", "category": "flower", "variant": "3.5g",
                    "source": "listings_bootstrap", "first_seen_at": (NOW - timedelta(days=90)).isoformat()})
    ls = [listing(1, "A", "Tierz 3.5g", "t", "exact", "3.5g", brand="Find.", category="flower",
                  seen=NOW - timedelta(days=2))]                              # still selling
    found = dh.stale_curated(data(ls, find))
    assert [f.key for f in found] == ["stale-curated:find.:lb:flower:flower::zangria"]
    assert "never matched" in found[0].text and found[0].look.endswith("z")


def test_enrichment_answers_jev_was_unsure_of_are_grouped_by_brand_and_field():
    ls = [dict(listing(1, "A", "Jaunty Sugar Cookie 1g"), sku="s1", variant="1g", scraped_brand="Jaunty"),
          dict(listing(2, "A", "Jaunty Lemon 1g"), sku="s2", variant="1g", scraped_brand="Jaunty"),
          dict(listing(3, "B", "Other Thing"), sku="s3", variant="", scraped_brand="Other")]
    sure = {"category": 0.99, "subtype": 0.9, "strain": 0.95, "product_line": 0.9, "size": 1.0}
    answers = [
        {"slug": "store-A", "cache_key": "s1|1g", "entry": {"src": "jev", "strain": "Sugar",
                                                           "p": {**sure, "strain": 0.31}, "size_by": "code"}},
        {"slug": "store-A", "cache_key": "s2|1g", "entry": {"src": "jev", "strain": "Lemon",
                                                           "p": {**sure, "strain": 0.45}, "size_by": "code"}},
        {"slug": "store-B", "cache_key": "s3|", "entry": {"src": "jev", "p": sure, "size_by": "field"}},
        {"slug": "store-B", "cache_key": "gone|", "entry": {"src": "jev", "p": {**sure, "strain": 0.1}}},
    ]
    d = data(ls)
    d.answers = answers
    found = dh.unsure_answers(d)
    assert keys(found) == ["unsure:size:other", "unsure:strain:jaunty"]
    assert next(f for f in found if f.key == "unsure:strain:jaunty").evidence == 2


def test_a_format_the_catalog_lacks_is_a_near_miss_at_two_stores():
    eureka = catalog("Eureka", {"id": "dp", "pk": "dp", "name": "RELOAD Durban Poison", "category": "vaporizers",
                                "subtype": "cart", "product_line": "RELOAD", "strain": "Durban Poison",
                                "variant": "1g"})
    aio = {"category": "vaporizers", "subtype": "all-in-one", "strain": "Durban Poison",
           "product_line": "RELOAD", "size": "1g"}
    ls = [listing(1, "A", "Durban Poison Reload AIO 1g", brand="Eureka", category="vaporizers", reading=aio),
          listing(2, "B", "Eureka RELOAD AIO Durban Poison", brand="Eureka", category="vaporizers", reading=aio),
          listing(3, "C", "Durban Poison Reload Cart 1g", brand="Eureka", category="vaporizers",
                  reading=dict(aio, subtype="cart"))]                      # joins: no finding
    found = dh.near_misses(data(ls, eureka))
    assert keys(found) == ["near-miss:eureka:dp:subtype:allinone"]
    assert "subtype is 'cart' in the catalog; 2 listing(s) at 2 store(s) read 'all-in-one'" in found[0].text


def test_a_strain_near_miss_needs_one_product_inside_the_stores_spelling():
    camino = catalog("Camino", *[{"id": k, "pk": k, "name": f"Gummies {s}", "category": "edible",
                                  "subtype": "gummy", "product_line": "Gummies", "strain": s,
                                  "variant": "20pk 100mg"}
                                 for k, s in (("sp", "Social Sparkling Pear"), ("wb", "Chill Wild Berry"))])
    pear = {"category": "edible", "subtype": "gummy", "strain": "Sparkling Pear", "size": "100mg"}
    ls = [listing(i, s, "Camino Sparkling Pear Gummies 20ct", brand="Camino", category="edible", reading=pear)
          for i, s in ((1, "A"), (2, "B"))]
    found = dh.near_misses(data(ls, camino))
    assert keys(found) == ["near-miss:camino:sp:strain:sparklingpear"]
