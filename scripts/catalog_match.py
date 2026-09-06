#!/usr/bin/env python3
"""
catalog_match.py — Resolve a listing to an entry in its brand's catalog.

Enrichment extracts fields from a name; this matches the name to a product the brand
says it makes. When it resolves, the entry's fields are authoritative and every store
carrying that product lands on the same values — which is what collapses the
product_line split, where one product appears twice because the line was extracted on
some stores and not others.

Tiers run cheapest first and the one that fired is recorded, so a match can be judged
by how it was made rather than taken on trust:

  exact     normalised listing name == normalised catalog name
  substring catalog name appears in the listing name on token boundaries
  token     token-set coverage above THRESHOLD
  model     constrained pick from that brand's catalog, or none  (not implemented)

**"No match" is a first-class outcome.** With a catalog a wrong answer stops being a
wrong string and becomes a specific wrong SKU, which reads as more authoritative and
travels further. So ambiguity never resolves to a guess: if two different products
match equally well, the answer is None and the listing falls through to extraction.

Usage
-----
  python scripts/catalog_match.py --brand Ayrloom            # measure against the DB
  python scripts/catalog_match.py --brand Ayrloom --misses   # list what did not match
"""

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand_catalog  # noqa: E402
from brand_catalog import norm_name  # noqa: E402

# Token coverage a candidate must reach before tier 3 will take it. Set from the
# Ayrloom miss list: 'rescue 1:1 topical' -> 'rescue balm' shares one of two catalog
# tokens (0.5) and is correct, but 0.5 also admits unrelated single-word overlaps, so
# the threshold sits above it and that case is left to the model tier rather than
# bought at the cost of false positives elsewhere.
THRESHOLD = 0.66

# Tokens that carry no identity — they appear in most names and inflate overlap.
STOPWORDS = {"the", "a", "an", "and", "of", "with", "pack", "pk", "mg", "g",
             "thc", "cbd", "cbn", "each", "size", "count", "ct"}


def _tokens(s: str) -> set[str]:
    return {t for t in norm_name(s).split() if t and t not in STOPWORDS}


def _substring_on_boundary(needle: str, haystack: str) -> bool:
    """Whole-token containment, so 'up' does not match inside 'syrup'."""
    if not needle:
        return False
    n, h = needle.split(), haystack.split()
    return any(h[i:i + len(n)] == n for i in range(len(h) - len(n) + 1))


class CatalogIndex:
    """One brand's catalog, grouped by product so variants resolve inside a product."""

    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.brand_name = catalog["brand_name"]
        # Variants grouped by the source's product id, never by title: 'lychee dream'
        # is both a vape and a pre-roll, and merging them by name lets a pre-roll
        # 5-pack resolve to the vape's '1g'. Names then index the products that carry
        # them, so one title can legitimately offer several candidates.
        groups: dict[str, list[dict]] = defaultdict(list)
        for e in catalog["entries"]:
            groups[e.get("product_external_id") or f"name:{norm_name(e['name'])}"].append(e)
        self.products: dict[str, list[dict]] = dict(groups)
        self.by_name: dict[str, list[str]] = defaultdict(list)
        for pid, entries in self.products.items():
            self.by_name[norm_name(entries[0]["name"])].append(pid)
        self.names = sorted(self.by_name, key=len, reverse=True)

    # -- variant selection within a matched product ------------------------------
    def _pick_variant(self, entries: list[dict], listing_variant: str | None) -> dict:
        """Prefer the entry whose variant matches; otherwise the product's first.

        Catalog variants are '1g', '10mg / 12 pack'; ours are '1g', '0.5g'. A listing
        with no variant, or one that matches nothing, still resolves to the product —
        the fields that matter for the split (product_line, category) are the same
        across a product's variants.
        """
        if listing_variant:
            lv = norm_name(listing_variant)
            for e in entries:
                if e.get("variant") and norm_name(e["variant"]) == lv:
                    return e
            for e in entries:
                if e.get("variant") and _substring_on_boundary(lv, norm_name(e["variant"])):
                    return e
        return entries[0]

    def _disambiguate(self, pids: list[str], category: str | None) -> str | None:
        """Several catalog products matched. Resolve only when it is genuinely safe.

        Catalog titles repeat across categories — Ayrloom sells 'honeycrisp' as a
        vape, a beverage and a canned drink, and also a 'PrideBites honeycrisp plush
        can dog toy'. Category is what separates them. With no category agreement and
        more than one candidate, this returns None rather than guessing.
        """
        if len(pids) == 1:
            return pids[0]
        if category:
            on_cat = [p for p in pids
                      if any(e.get("category") == category for e in self.products[p])]
            if len(on_cat) == 1:
                return on_cat[0]
            if on_cat:
                pids = on_cat
        # A longer title is strictly more specific; accept it only when it is the
        # unique longest, so ties stay unresolved.
        def title(p): return norm_name(self.products[p][0]["name"])
        longest = max(len(title(p)) for p in pids)
        top = [p for p in pids if len(title(p)) == longest]
        if len(top) == 1:
            return top[0]
        # Same title, different products, and category could not separate them (an
        # untagged duplicate shadowing a tagged one). Prefer the one that carries a
        # category at all; a tie beyond that is a genuine ambiguity.
        titled = [p for p in top if any(e.get("category") for e in self.products[p])]
        return titled[0] if len(titled) == 1 else None

    # -- the tiers ---------------------------------------------------------------
    def match(self, name: str, category: str | None = None,
              variant: str | None = None) -> tuple[dict | None, float, str]:
        """Return (entry, confidence, method). entry is None when nothing is safe."""
        ln = norm_name(name)
        if not ln:
            return None, 0.0, "none"

        if ln in self.by_name:
            chosen = self._disambiguate(self.by_name[ln], category)
            if chosen is None:
                return None, 0.0, "ambiguous"
            return self._pick_variant(self.products[chosen], variant), 1.0, "exact"

        hits = [p for n in self.names if _substring_on_boundary(n, ln)
                for p in self.by_name[n]]
        if hits:
            chosen = self._disambiguate(hits, category)
            if chosen is None:
                return None, 0.0, "ambiguous"
            # Longer catalog titles are more of the listing name, so they are more
            # likely to be the actual product rather than a word that co-occurs.
            conf = 0.80 + 0.15 * min(
                1.0, len(norm_name(self.products[chosen][0]["name"]).split()) / 4)
            return self._pick_variant(self.products[chosen], variant), conf, "substring"

        lt = _tokens(name)
        if lt:
            scored = []
            for n in self.names:
                ct = _tokens(n)
                if not ct:
                    continue
                cov = len(ct & lt) / len(ct)
                if cov >= THRESHOLD:
                    scored.extend((cov, p) for p in self.by_name[n])
            if scored:
                best = max(c for c, _ in scored)
                pids = [p for c, p in scored if c == best]
                chosen = self._disambiguate(pids, category)
                if chosen is None:
                    return None, 0.0, "ambiguous"
                return self._pick_variant(self.products[chosen], variant), \
                    round(0.5 + 0.3 * best, 3), "token"

        return None, 0.0, "none"


def load_index(brand: str) -> CatalogIndex:
    from scraper_common import slugify
    return CatalogIndex(brand_catalog.load(slugify(brand)))


# ---------------------------------------------------------------------------
# Measurement CLI — runs the matcher over live listings without writing anything
# ---------------------------------------------------------------------------

def _connect():
    import psycopg2
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.path.join(root, ".env")
    if os.path.isfile(env):
        for line in open(env):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    return psycopg2.connect(url)


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure catalog matching against listings")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--misses", action="store_true", help="Print unmatched listing names")
    ap.add_argument("--sample", type=int, default=0, help="Print N matches for hand-checking")
    ap.add_argument("--write", action="store_true",
                    help="Persist catalog_entry_id/confidence/method onto listings. "
                         "Does NOT touch product_line, strain or any enrichment field.")
    args = ap.parse_args()

    idx = load_index(args.brand)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, scraped_name, scraped_category, variant, product_line, strain
        FROM listings WHERE is_active AND scraped_brand = %s
        """, (args.brand,))
    rows = cur.fetchall()

    # external_id -> the catalog entry's DB id, so a match can be persisted as a real
    # foreign key rather than a name. Only needed when writing.
    entry_ids: dict[str, str] = {}
    if args.write:
        cur.execute(
            """
            SELECT e.external_id, e.id FROM brand_catalog_entries e
            JOIN brand_catalogs c ON c.id = e.catalog_id
            WHERE c.brand_name = %s
            """, (args.brand,))
        entry_ids = {ext: str(eid) for ext, eid in cur.fetchall()}
        if not entry_ids:
            sys.exit(f"No catalog rows for {args.brand} — run `brand_catalog.py push` first.")

    by_method: dict[str, int] = defaultdict(int)
    matched, misses, samples, updates = 0, [], [], []
    for lid, name, cat, variant, pl, strain in rows:
        entry, conf, method = idx.match(name, cat, variant)
        by_method[method] += 1
        if entry:
            matched += 1
            samples.append((name, cat, entry["name"], entry.get("product_line"),
                            entry.get("variant"), round(conf, 3), method))
        else:
            misses.append((name, cat, method))
        if args.write:
            eid = entry_ids.get(entry["external_id"]) if entry else None
            updates.append((eid, round(conf, 3) if entry else None, method, str(lid)))

    if args.write:
        import psycopg2.extras
        psycopg2.extras.execute_values(
            cur,
            """
            UPDATE listings AS l SET
                catalog_entry_id         = v.entry_id::uuid,
                catalog_match_confidence = v.conf::real,
                catalog_match_method     = v.method
            FROM (VALUES %s) AS v(entry_id, conf, method, listing_id)
            WHERE l.id = v.listing_id::uuid
            """,
            updates,
        )
        conn.commit()
        print(f"wrote match columns on {len(updates)} listings "
              f"({matched} with an entry)\n")
    conn.close()

    total = len(rows)
    print(f"{args.brand}: {total} active listings, catalog has "
          f"{len(idx.catalog['entries'])} entries\n")
    print(f"  {'tier':12} {'listings':>9} {'share':>8}")
    print("  " + "-" * 31)
    for m in ("exact", "substring", "token", "ambiguous", "none"):
        n = by_method.get(m, 0)
        print(f"  {m:12} {n:>9} {n / total:>7.1%}")
    print("  " + "-" * 31)
    print(f"  {'MATCHED':12} {matched:>9} {matched / total:>7.1%}")

    if args.sample:
        print(f"\n--- {min(args.sample, len(samples))} matches for hand-checking ---")
        step = max(1, len(samples) // args.sample)
        for s in samples[::step][:args.sample]:
            print(f"  [{s[6]} {s[5]}] {s[1]:11} {s[0][:52]}")
            print(f"      -> {s[2]!r} line={s[3]!r} variant={s[4]!r}")

    if args.misses:
        print(f"\n--- {len(misses)} unmatched ---")
        for n, c, m in misses:
            print(f"  [{m:9}] {c or '?':11} {n[:70]}")


if __name__ == "__main__":
    main()
