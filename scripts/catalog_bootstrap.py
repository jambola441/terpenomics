#!/usr/bin/env python3
"""
catalog_bootstrap.py — Propose a catalog for any brand from what stores already sell.

Storefront catalogs (brand_catalog.py) cover the brands that run a Shopify shop.
Most do not — Jaunty and Ruby Farms, 940 listings between them, have no reachable
site at all — and a catalog that exists for 1 brand of 719 cannot be the source of
identity. This builds one for every brand from the cross-store signal we already
hold: 266 brands are carried by 3+ stores, and they account for 88% of active
listings (measured 2026-10-04).

The idea is consensus, not extraction. One store's listing is one opinion about what
a product is; the same product listed by five stores is five independent opinions,
written five different ways. Grouping those and taking the consensus gives a product
list that no single store's text — and no single model answer — defines:

  Jetpacks "Afghani FJ-Mini Infused Pre-roll | 0.6G"          (greene-street)
           "Jetpacks - FJ Mini Afghani Infused Preroll - .6g"  (kaya-bliss)
           "Infused Pre-Rolls | Jetpacks - FJ Mini | Afghani"  (oc-dispensary)
           ... seven stores, line recorded as "FJ-Mini", "FJ Mini" or blank
     ->    one entry: "FJ-Mini Afghani", preroll, line FJ-Mini, 0.6g, support 7

How a group is formed
---------------------
  key        (category, strain, product line, size) — strain and line compared
             squashed ("FJ Mini" == "FJ-Mini" == "fj-mini"), size compared as numbers
             (sizes.py: "5pk x 0.6g" == "3g").
  line fix   a group with no line folds into the one group that has the same
             category, strain and size *with* a line — the product_line split that is
             12% of the products view, removed by construction.
  support    distinct stores. Groups seen at fewer than --min-stores (default 2) are
             left out: they are either products only one store carries, or a split
             the next match run will absorb — and either way one store's opinion is
             not a consensus.

What it writes
--------------
`data/catalogs/<brand>.json` in the export shape, source_method "listings_bootstrap",
each entry carrying `support` and the normalised store names it was built from as
`match_terms` — so those stores' listings resolve exactly (no model call) next time.
`--push` also upserts it into Postgres (needs DATABASE_URL), where the admin catalog
page reviews and edits it like any other catalog. Entries have stable synthetic
external ids, so a re-run updates in place. Pushes are additive (brand_catalog.push):
new products are added, curated fields are never overwritten, and bootstrap entries
are never retired automatically — one quiet week at the stores is not a
discontinuation. Take a product out in the admin when it really is gone.

Bootstrap catalogs are matched at a higher Jev threshold (catalog_match.AUTO_BOOTSTRAP)
because a missing product is exactly when near-miss picks happen.

Usage
-----
  python scripts/catalog_bootstrap.py --brand Jetpacks              # propose, print the effect
  python scripts/catalog_bootstrap.py --brand Jetpacks --write      # write data/catalogs/jetpacks.json
  python scripts/catalog_bootstrap.py --top 50 --write              # top brands without a catalog
  python scripts/catalog_bootstrap.py --top 50 --write --push       # ...and into Postgres
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_store  # noqa: E402
import sizes  # noqa: E402
from brand_catalog import strip_brand  # noqa: E402
from scraper_common import slugify  # noqa: E402

import taxonomy  # noqa: E402

# Categories brand catalogs do not model (scripts/taxonomy.py): merch identity is fully
# determined by name tokens already, and "other" is not a product.
SKIP_CATEGORIES = set(taxonomy.SPECS) - taxonomy.catalogable()
MAX_MATCH_TERMS = 12


def squash(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _mode(values, default=None):
    vals = [v for v in values if v]
    return Counter(vals).most_common(1)[0][0] if vals else default


@dataclass
class Group:
    category: str
    subtype: str
    strain_key: str
    line_key: str
    size_key: str
    listings: list[dict] = field(default_factory=list)

    @property
    def stores(self) -> int:
        return len({l["dispensary_id"] for l in self.listings})


def propose(brand: str, listings: list[dict], min_stores: int = 2) -> dict:
    """A catalog document for `brand` built from its listings, plus a report."""
    # Copies: de-lining below edits strain/product_line, and the caller's rows must
    # stay what the database says.
    rows = [dict(l) for l in listings if (l.get("category") or "") not in SKIP_CATEGORIES
            and (l.get("strain") or "").strip()]

    # Line spelling by consensus across the brand: "FJ-Mini" over "FJ Mini" when more
    # stores write it that way.
    line_spelling: dict[str, str] = {}
    by_line = defaultdict(list)
    for l in rows:
        if l.get("product_line"):
            by_line[squash(l["product_line"])].append(l["product_line"])
    for key, spellings in by_line.items():
        line_spelling[key] = Counter(spellings).most_common(1)[0][0]

    # A line the model folded into the strain at some stores ("Championship Cake
    # Powdered Donuts" beside line "Powdered Donuts" elsewhere). De-lined only against
    # the brand's consensus vocabulary, and only for lines of two or more words that
    # two or more stores recorded as a line — never against one listing's own guess,
    # which is how "Blue Dream" with a model line of "Dream" would become "Blue".
    stores_per_line = defaultdict(set)
    for l in rows:
        if l.get("product_line"):
            stores_per_line[squash(l["product_line"])].add(l["dispensary_id"])
    vocab = {k: line_spelling[k] for k, st in stores_per_line.items()
             if len(st) >= 2 and len(line_spelling[k].split()) >= 2}
    delined = 0
    for l in rows:
        if l.get("product_line"):
            continue
        for key, line in vocab.items():
            pattern = re.compile(r"(?<![A-Za-z0-9])" + r"[\s\-_]*".join(
                re.escape(w) for w in line.split()) + r"(?![A-Za-z0-9])", re.I)
            if pattern.search(l["strain"]):
                rest = re.sub(r"\s{2,}", " ", pattern.sub(" ", l["strain"])).strip(" -|,x")
                if rest:
                    l["strain"], l["product_line"] = rest, line
                    delined += 1
                break

    # Grouped on the package total only. Stores mention the pack count inconsistently
    # ("100mg" at one, "100mg 10pk" at the next), and keying on the full label split
    # Wyld's 27 product rows into 42. The entry's displayed size is the group's most
    # common full label.
    #
    # Subtype is part of the key, as it is of a product's identity (taxonomy.py): a
    # strain's cart, pod and all-in-one are three products. Without it they merged and
    # the most common format won: on 2026-10-04's scrapes, 16 vapes whose names say
    # Cart, AIO, Pod or Starter Kit took another format from their catalog entry. A
    # format word in the name beats the model's subtype here, as it does wherever a
    # catalog is applied (catalog_match.matched_subtype).
    groups: dict[tuple, Group] = {}
    for l in rows:
        size = sizes.parse(l.get("variant"), l.get("name"), category=l.get("category"))
        l["_size_label"] = size.label()
        total = (f"{size.grams:g}g" if size.grams is not None
                 else f"{size.mg:g}mg" if size.mg is not None else "")
        subtype = taxonomy.token_subtype(l["category"], l.get("name")) or l.get("subtype") or ""
        key = (l["category"], subtype, squash(l["strain"]), squash(l.get("product_line")), total)
        groups.setdefault(key, Group(*key)).listings.append(l)

    # The product_line split: fold a line-less group into the single lined group that
    # matches it on everything else. Two candidate lines means it is ambiguous which
    # product the store meant, so it is left alone.
    lined: dict[tuple, list[tuple]] = defaultdict(list)
    for key in groups:
        if key[3]:
            lined[(key[0], key[1], key[2], key[4])].append(key)
    folded = 0
    for key in list(groups):
        if key[3]:
            continue
        targets = lined.get((key[0], key[1], key[2], key[4]), [])
        if len(targets) == 1:
            groups[targets[0]].listings.extend(groups.pop(key).listings)
            folded += 1

    entries = []
    kept_listings = 0
    for key, g in sorted(groups.items()):
        if g.stores < min_stores:
            continue
        kept_listings += len(g.listings)
        strain = _mode([l["strain"].strip() for l in g.listings])
        line = line_spelling.get(g.line_key) if g.line_key else None
        product_key = f"lb:{g.category}:{g.subtype}:{g.line_key}:{g.strain_key}"
        terms = Counter(strip_brand(l["name"], brand) for l in g.listings)
        entries.append({
            "external_id": f"{product_key}:{g.size_key or 'nosize'}",
            "product_key": product_key,
            "name": " ".join(x for x in (line, strain) if x),
            "product_line": line,
            "category": g.category,
            "subtype": g.subtype or None,
            "strain": strain,
            "variant": _mode([l["_size_label"] for l in g.listings]) or _mode([l.get("variant") for l in g.listings]),
            "attributes": None,
            "match_terms": [t for t, _ in terms.most_common(MAX_MATCH_TERMS) if t],
            "source": "listings_bootstrap",
            "support": g.stores,
        })

    before = len({(l.get("category"), l.get("subtype"), l.get("product_line"), l.get("strain"),
                   l.get("variant")) for l in rows})
    covered = {id(l) for g in groups.values() if g.stores >= min_stores for l in g.listings}
    after = len(entries) + len({(l.get("category"), l.get("subtype"), l.get("product_line"),
                                 l.get("strain"), l.get("variant"))
                                for l in rows if id(l) not in covered})
    report = {
        "brand": brand, "listings": len(listings), "eligible": len(rows),
        "groups": len(groups), "line_splits_folded": folded, "strains_delined": delined,
        "entries": len(entries), "listings_covered": kept_listings,
        "product_rows_before": before, "product_rows_after": after,
    }
    doc = {
        "brand_slug": slugify(brand),
        "brand_name": brand,
        "source_url": None,
        "source_method": "listings_bootstrap",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "product_count": len({e["product_key"] for e in entries}),
        "entries": entries,
    }
    return {"catalog": doc, "report": report}


def fetch_listings() -> list[dict]:
    import db_http
    rows = db_http.select_all(
        "listings",
        "select=id,dispensary_id,scraped_name,scraped_brand,scraped_category,subtype,strain,"
        "product_line,variant&is_active=is.true&order=id")
    return [{"id": r["id"], "dispensary_id": r["dispensary_id"], "name": r.get("scraped_name") or "",
             "brand": r.get("scraped_brand"), "category": r.get("scraped_category"),
             "subtype": r.get("subtype"), "strain": r.get("strain"),
             "product_line": r.get("product_line"), "variant": r.get("variant")} for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description="Propose brand catalogs from cross-store listings")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand", help="One brand, as written in listings")
    g.add_argument("--top", type=int, help="The N largest brands that have no catalog yet")
    ap.add_argument("--min-stores", type=int, default=2,
                    help="Keep products carried by at least this many stores (default 2)")
    ap.add_argument("--write", action="store_true", help="Write data/catalogs/<brand>.json")
    ap.add_argument("--push", action="store_true",
                    help="Write the file and upsert into Postgres (DATABASE_URL)")
    ap.add_argument("--show", type=int, default=0, help="Print N proposed entries per brand")
    args = ap.parse_args()

    catalogs = catalog_store.load_all()
    listings = fetch_listings()
    by_brand: dict[str, list[dict]] = defaultdict(list)
    spelled: dict[str, Counter] = defaultdict(Counter)
    for l in listings:
        key = catalog_store.brand_key(l.get("brand"))
        if key:
            by_brand[key].append(l)
            spelled[key][l["brand"]] += 1

    if args.brand:
        keys = [catalog_store.brand_key(args.brand)]
    else:
        keys = [k for k, _ in sorted(by_brand.items(), key=lambda kv: -len(kv[1]))
                if k not in catalogs][:args.top]

    totals = Counter()
    for key in keys:
        if key in catalogs and catalogs[key].get("source_method") != "listings_bootstrap":
            print(f"{catalogs[key]['brand_name']}: has a {catalogs[key]['source_method']} "
                  f"catalog — not overwriting it with a bootstrap")
            continue
        brand = spelled[key].most_common(1)[0][0] if spelled.get(key) else args.brand
        out = propose(brand, by_brand.get(key, []), args.min_stores)
        r = out["report"]
        totals.update({k: v for k, v in r.items() if isinstance(v, int)})
        print(f"{brand:28} {r['listings']:>5} listings  {r['entries']:>4} entries "
              f"(support>={args.min_stores})  covers {r['listings_covered']:>5}  "
              f"product rows {r['product_rows_before']:>4} -> {r['product_rows_after']:>4}  "
              f"line splits folded {r['line_splits_folded']}")
        for e in out["catalog"]["entries"][:args.show]:
            print(f"    [{e['support']}] {e['category']:10} {e['name'][:40]:40} {e['variant'] or '':10} "
                  f"line={e['product_line']!r}")
        if args.write or args.push:
            import brand_catalog
            path = brand_catalog.save(out["catalog"])
            if args.push:
                brand_catalog.push(out["catalog"])
            print(f"    wrote {path.relative_to(brand_catalog.ROOT)}{' and pushed' if args.push else ''}")

    if len(keys) > 1:
        print(f"\n{len(keys)} brands: {totals['listings']} listings, {totals['entries']} entries, "
              f"covering {totals['listings_covered']} listings; product rows "
              f"{totals['product_rows_before']} -> {totals['product_rows_after']}")


if __name__ == "__main__":
    main()
