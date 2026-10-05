#!/usr/bin/env python3
"""
catalog_shape.py — A brand catalog laid out by product line, for a person or an agent
to read.

A brand sells product lines — "Live Resin Infused" pre-rolls, "Sours" gummies — and
each line comes in several strains or flavours, usually three or more. A catalog
built right has that shape. One that does not (a line with a single strain, a line
named like a strain, a product with no line beside a line of the same strain, two
spellings of one strain) is usually showing a name that something upstream misread:
a storefront recipe rule, or the store consensus in catalog_bootstrap.py.

This prints the shape and the places it looks unlike a brand's ("leads"). Deciding
which leads are real takes judgment and evidence — how stores write the names, what
the brand's site says — so the procedure lives in .claude/skills/catalog-audit/SKILL.md
and this script only does the reading.

Usage:
    python3 scripts/catalog_shape.py triage                        # every catalog, most leads first
    python3 scripts/catalog_shape.py show "Florist Farms"          # by category and line, then leads
    python3 scripts/catalog_shape.py show "Camino" --category edible
    python3 scripts/catalog_shape.py entries "Camino" "(?i)spritz"  # matching entries, every field
    python3 scripts/catalog_shape.py listings "Camino" "(?i)spritz" # how stores write those names
    python3 scripts/catalog_shape.py listings "Camino" --unmatched  # store products the catalog lacks

Read-only, over Supabase's REST API (scripts/db_http.py), so it runs from a sandbox.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sizes  # noqa: E402
import taxonomy  # noqa: E402
from catalog_bootstrap import squash, strain_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / "data" / "storefronts"
BOOTSTRAP = "listings_bootstrap"
THIN = 2              # a line with this many strains or fewer is worth a look
SIMILAR = 0.88        # strain spellings at least this alike (same digits) may be one strain

# Words that make a product line a strain type, a format, or a size rather than a
# brand's named line. Extraction words (live resin, rosin, distillate, hash) are not
# here: many brands do name lines that way.
TYPE_WORDS = {"indica", "sativa", "hybrid", "cbd", "thc", "cbn", "cbg", "balanced"}
FORMAT_WORDS = {
    word for spec in taxonomy.SPECS.values() if spec.catalogable for st in spec.subtypes
    for word in st.split("-")
} | {
    "gummies", "chocolates", "cartridge", "cartridges", "carts", "vape", "vapes",
    "disposable", "disposables", "aio", "preroll", "prerolls", "pre", "roll", "rolls",
    "joint", "joints", "blunt", "blunts", "eighth", "eighths", "ounce", "quarter", "pk",
    "pack", "packs", "singles", "edible", "edibles", "concentrate", "concentrates",
    "tinctures", "topicals", "drink", "drinks", "tablets", "mints", "chews", "gram", "grams",
}
FORMAT_WORDS -= {"other", "in", "one"}   # from "all-in-one"; "other" is not a word a line uses
SIZE_TOKEN = re.compile(r"^\d+(\.\d+)?(g|mg|pk|ct|oz)?$")
# Inside a strain, only words no strain or flavour name uses: "Hash Burger", "Chocolate
# Mint" and "Cinnamon Roll" are names, "Blue Dream Cart" and "Gelato 3.5g" are not.
STRAIN_NOISE = re.compile(
    r"(?<![a-z0-9])(?:carts?|cartridges?|pods?|aio|disposables?|vapes?|gumm(?:y|ies)|"
    r"pre[\s-]?rolls?|joints?|infused|indica|sativa|hybrid|thc|cbd|edibles?|tinctures?|"
    r"eighths?|\d+(?:\.\d+)?\s*(?:g|mg|pk|ct|oz)|\d+\s*pack)(?![a-z0-9])", re.I)
SUBTYPE_DECIDES = {"vaporizers", "edible"}    # as in storefront.py: a cart is not a pod

# Sizes outside these are almost always a misread variant, not a product.
PLAUSIBLE = {  # category: (unit, low, high)
    "flower": ("grams", 0.5, 28), "preroll": ("grams", 0.25, 14),
    "vaporizers": ("grams", 0.1, 2.5), "concentrate": ("grams", 0.25, 28),
    "edible": ("mg", 2, 1000), "tinctures": ("mg", 5, 3000), "topical": ("mg", 5, 3000),
}


# --------------------------------------------------------------------------- shape

@dataclass
class Product:
    """Entries that differ only by size: one strain or flavour of one line."""
    category: str
    subtype: str
    line: str
    strain: str
    entries: list[dict] = field(default_factory=list)
    listings: int = 0
    stores: int = 0

    @property
    def label(self) -> str:
        return self.strain or self.entries[0]["name"]

    @property
    def name(self) -> str:
        return " ".join(p for p in (self.line, self.strain) if p) or self.entries[0]["name"]

    @property
    def sizes(self) -> list[str]:
        return sorted({e["variant"] or "?" for e in self.entries}, key=_size_order)

    @property
    def store_only(self) -> bool:
        """In a storefront catalog: kept from the stores' consensus, not on the site."""
        return all(e.get("source") == BOOTSTRAP for e in self.entries)

    @property
    def support(self) -> int:
        return max((e.get("support") or 0) for e in self.entries)

    @property
    def store_names(self) -> list[str]:
        return sorted({t for e in self.entries for t in (e.get("match_terms") or [])})


def _size_order(v: str):
    s = sizes.parse(v)
    return (s.grams if s.grams is not None else s.mg if s.mg is not None else 1e9, s.pack or 0, v)


def products(entries: list[dict], listings: list[dict] | None = None) -> list[Product]:
    by_key: dict[tuple, Product] = {}
    for e in entries:
        key = (e.get("category") or "?", e.get("subtype") or "", e.get("product_line") or "",
               e.get("strain") or "")
        p = by_key.setdefault(key, Product(*key))
        p.entries.append(e)
    if listings:
        owner = {e["id"]: p for p in by_key.values() for e in p.entries}
        stores: dict[int, set] = defaultdict(set)
        for l in listings:
            p = owner.get(l.get("catalog_entry_id"))
            if p:
                p.listings += 1
                stores[id(p)].add(l.get("dispensary_id"))
        for p in by_key.values():
            p.stores = len(stores.get(id(p), ()))
    return sorted(by_key.values(), key=lambda p: (p.category, p.line.lower(), p.label.lower()))


def lines_of(prods: list[Product]) -> dict[str, dict[str, list[Product]]]:
    """category -> line ("" for none) -> products."""
    out: dict[str, dict[str, list[Product]]] = defaultdict(lambda: defaultdict(list))
    for p in prods:
        out[p.category][p.line].append(p)
    return out


# --------------------------------------------------------------------------- leads

@dataclass
class Lead:
    kind: str
    category: str
    text: str
    weight: int = 1


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9.]+", s.lower())


def _is_format_line(line: str) -> bool:
    words = _words(line)
    return bool(words) and all(w in TYPE_WORDS or w in FORMAT_WORDS or SIZE_TOKEN.match(w)
                               for w in words)


def _noise_in(strain: str) -> list[str]:
    """Format, type or size words inside a strain: "Blue Dream Cart", "Gelato 3.5g"."""
    return [m.group(0) for m in STRAIN_NOISE.finditer(strain)]


def _contains(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])", text.lower()))


def _alike(a: str, b: str) -> bool:
    """Two spellings of one name: equal strain keys, a plural, or close with the same
    digits. Resin and rosin are different products, not a typo."""
    ka, kb = strain_key(a), strain_key(b)
    if ka == kb or ka.rstrip("s") == kb.rstrip("s"):
        return True
    if re.findall(r"\d+", a) != re.findall(r"\d+", b) or min(len(ka), len(kb)) < 6:
        return False
    if ({"resin", "rosin"} & set(_words(a))) != ({"resin", "rosin"} & set(_words(b))):
        return False
    return difflib.SequenceMatcher(None, ka, kb).ratio() >= SIMILAR


def _plausible(category: str, variant: str | None) -> bool | None:
    rule = PLAUSIBLE.get(category)
    if not rule or not variant:
        return None
    unit, lo, hi = rule
    value = getattr(sizes.parse(variant, category=category), unit)
    return None if value is None else lo <= value <= hi


def _tagged(ps: list[Product]) -> str:
    """Product labels, each once, with the subtype where one strain has several."""
    count = Counter(p.label for p in ps)
    return ", ".join(sorted({p.label + (f" [{p.subtype}]" if count[p.label] > 1 and p.subtype else "")
                             for p in ps}))


def leads(prods: list[Product], strain_vocab: dict[str, int] | None = None,
          storefront: bool = False) -> list[Lead]:
    """Where the catalog's shape looks unlike a brand's. Leads, not verdicts.

    strain_vocab: strain_key -> how many other brands' catalogs use it as a strain,
    so a line named like a common strain stands out.
    """
    out: list[Lead] = []
    vocab = strain_vocab or {}
    shape = lines_of(prods)
    strains_at = defaultdict(list)                      # strain_key -> products using it
    for p in prods:
        if p.strain:
            strains_at[strain_key(p.strain)].append(p)

    for cat, lines in sorted(shape.items()):
        named = {l: ps for l, ps in lines.items() if l}
        lineless = lines.get("", [])
        everything = lineless + [p for ps in named.values() for p in ps]

        # A big unnamed group beside named lines: brands name their lines, so the line
        # is usually there in the product names and something dropped it.
        if named and len(lineless) >= 3 and len(lineless) >= 0.3 * len(everything):
            out.append(Lead("mixed-lines", cat, f"{len(lineless)} of {len(everything)} products have "
                            f"no line, beside named lines {', '.join(sorted(named))}", 3))

        thin = {l: ps for l, ps in named.items() if len({p.label for p in ps}) <= THIN}
        if thin:
            if len(thin) >= 3 and len(thin) * 2 >= len(named):
                out.append(Lead("thin-lines", cat, f"{len(thin)} of {len(named)} lines have 1-2 "
                                "strains; the names used as lines may be strains, flavours or "
                                "effects, or the lines' other strains were filed elsewhere", 3))
            out.append(Lead("thin-line", cat, "; ".join(
                f'{l} ({_tagged(ps)})' + (
                    f" +{n} in other categories" if (n := sum(1 for p in prods if p.line == l
                                                              and p.category != cat)) else "")
                for l, ps in sorted(thin.items()))))

        for line, ps in sorted(named.items()):
            k = strain_key(line)
            own = [p for p in strains_at.get(k, []) if p.line != line]
            if own:
                out.append(Lead("line-is-strain", cat, f'line "{line}" ({_tagged(ps)}) is the strain '
                                f'of {", ".join(sorted({f"{p.name} ({p.category})" for p in own}))}', 3))
            elif vocab.get(k):
                out.append(Lead("line-is-strain", cat, f'line "{line}" ({_tagged(ps)}) is a strain in '
                                f"{vocab[k]} other brands' catalogs", 2))
            if _is_format_line(line):
                out.append(Lead("line-word", cat, f'line "{line}" is a strain type, format or size, '
                                f"not a named line ({_tagged(ps)})", 2))
            for other in named:
                if other > line and _alike(line, other):
                    out.append(Lead("similar-lines", cat, f'lines "{line}" and "{other}" may be one line', 2))

        # Products with no line that look like a line's: the same strain is under it,
        # their store names say it, or the strain carries it ("Calm Peach").
        twins, said = defaultdict(list), defaultdict(list)
        repeated = Counter(p.label for p in lineless)
        for p in lineless:
            tag = p.label + (f" [{p.subtype}]" if repeated[p.label] > 1 and p.subtype else "")
            for line, ps in named.items():
                if p.strain and any(strain_key(q.strain) == strain_key(p.strain) for q in ps):
                    twins[line].append(p)
                names = p.store_names
                hits = sum(1 for n in names if _contains(n, line))
                if names and hits * 2 >= len(names) and not _contains(p.label, line):
                    said[line].append(f"{tag} {hits}/{len(names)}")
            for line in {q.line for q in prods if q.line}:
                if p.strain and _contains(p.strain, line) and squash(p.strain) != squash(line):
                    out.append(Lead("line-in-strain", cat, f'"{p.label}" has no line but its strain '
                                    f'contains line "{line}"', 3))
        for line, ps in sorted(twins.items()):
            out.append(Lead("stray", cat, f'no line, same strain as a product in "{line}": {_tagged(ps)}', 2))
        for line, labels in sorted(said.items()):
            out.append(Lead("stray", cat, f'no line, but most of their store names say "{line}": '
                            + ", ".join(sorted(set(labels))), 2))

        for p in everything:
            if p.line and p.strain and _contains(p.strain, p.line):
                out.append(Lead("line-in-strain", cat, f'"{p.name}": the strain repeats its line', 2))
            noise = _noise_in(p.strain)
            if noise:
                out.append(Lead("strain-word", cat, f'"{p.name}": strain carries {", ".join(noise)}'))
            for v in p.sizes:
                ok = _plausible(cat, None if v == "?" else v)
                if v == "?" or ok is False:
                    out.append(Lead("size", cat, f'"{p.name}": size {v!r} '
                                    + ("missing" if v == "?" else "is implausible for " + cat), 2))

        # Two spellings of one strain in one line (and subtype, where that decides).
        groups = defaultdict(list)
        for p in everything:
            groups[(p.line, p.subtype if p.category in SUBTYPE_DECIDES else "")].append(p)
        for ps in groups.values():
            for i, a in enumerate(ps):
                for b in ps[i + 1:]:
                    if a.strain and b.strain and a.strain != b.strain and _alike(a.strain, b.strain):
                        out.append(Lead("near-dup", cat, f'"{a.name}" and "{b.name}" may be one product', 2))

        # Dose sizes written two ways in one line: "100mg" beside "10pk 100mg".
        if PLAUSIBLE.get(cat, ("",))[0] == "mg":
            for line, ps in named.items():
                forms = Counter("pack" in v or "pk" in v for p in ps for v in p.sizes if v != "?")
                if len(forms) == 2:
                    bare = sorted({p.label for p in ps if any("pk" not in v for v in p.sizes)})
                    out.append(Lead("size", cat, f'line "{line}" writes sizes with and without a pack '
                                    f"count; without: {', '.join(bare)}"))

        if storefront:
            site = [p for p in everything if not p.store_only]
            for p in [p for p in everything if p.store_only]:
                for s in site:
                    if p.category in SUBTYPE_DECIDES and p.subtype != s.subtype:
                        continue
                    same = (strain_key(p.strain) and strain_key(p.strain) == strain_key(s.strain)) or \
                        _alike(p.name, s.name) or squash(p.name) in (squash(s.line), squash(s.strain)) or \
                        (p.strain and s.line and strain_key(p.strain) == strain_key(s.line))
                    if same:
                        out.append(Lead("store-copy", cat, f'store-only "{p.name}" {" ".join(p.sizes)} '
                                        f'({p.support} stores) may be site product "{s.name}" '
                                        f'{" ".join(s.sizes)}', 2))
                        break
    return out


# --------------------------------------------------------------------------- render

def render_show(catalog: dict, entries: list[dict], listings: list[dict],
                strain_vocab: dict[str, int], category: str | None = None) -> str:
    storefront = catalog["source_method"] != BOOTSTRAP
    active = [e for e in entries if e["is_active"]]
    prods = products(active, listings)
    out = [f'{catalog["brand_name"]} · {"storefront" if storefront else "bootstrap"} '
           f'({catalog["source_method"]}) · fetched {(catalog.get("fetched_at") or "?")[:16]}']
    recipe = RECIPES / f'{catalog["brand_slug"]}.json'
    if storefront:
        out.append(f'  site: {catalog.get("source_url") or "?"} · recipe: '
                   + (str(recipe.relative_to(ROOT)) if recipe.exists() else "none (fetched another way)"))
    site = sum(1 for p in prods if not p.store_only)
    out.append(f"  {len(active)} active entries = {len(prods)} products"
               + (f" ({site} from the site, {len(prods) - site} store-only)" if storefront else "")
               + f" · {len(entries) - len(active)} inactive"
               + f" · {sum(1 for e in active if e.get('verified_fields'))} verified")
    matched = sum(1 for l in listings if l.get("catalog_entry_id") in {e["id"] for e in active})
    out.append(f"  store listings: {len(listings)} active at {len({l['dispensary_id'] for l in listings})} "
               f"stores, {matched} matched to this catalog"
               + (f" ({matched * 100 // len(listings)}%)" if listings else ""))
    out.append("  per product: sizes · listings matched / stores · [store-only n] = kept from stores, "
               "not on the site")

    shape = lines_of(prods)
    for cat in sorted(shape):
        if category and cat != category:
            continue
        lines = shape[cat]
        n_lines = sum(1 for l in lines if l)
        out.append(f"\n{cat.upper()} · {sum(len(v) for v in lines.values())} products in {n_lines} "
                   f"line(s)" + (f" + {len(lines[''])} without a line" if lines.get("") else ""))
        multi_sub = len({p.subtype for ps in lines.values() for p in ps}) > 1
        for line, ps in sorted(lines.items(), key=lambda kv: (kv[0] == "", -len(kv[1]), kv[0].lower())):
            sizes_seen = Counter(v for p in ps for v in p.sizes)
            subs = sorted({p.subtype for p in ps if p.subtype})
            out.append(f"  {line or '(no line)'} — {len(ps)} strain(s)"
                       + (f" · {'/'.join(subs)}" if subs else "")
                       + " · sizes " + ", ".join(f"{v} ×{n}" for v, n in
                                                 sorted(sizes_seen.items(), key=lambda kv: _size_order(kv[0]))))
            for p in ps:
                tag = f" [{p.subtype}]" if multi_sub and p.subtype else ""
                extra = f"  [store-only {p.support}]" if storefront and p.store_only else ""
                out.append(f"      {p.label + tag:<40} {' '.join(p.sizes):<22} {p.listings}/{p.stores}{extra}")

    found = [l for l in leads(prods, strain_vocab, storefront) if not category or l.category == category]
    out.append(f"\nLEADS · {len(found)} · places the shape looks unlike a brand's. Check each "
               "against store names (listings) and the brand's site before calling it wrong.")
    for l in sorted(found, key=lambda l: (-l.weight, l.category, l.kind, l.text)):
        out.append(f"  [{l.kind}] {l.category}: {l.text}")
    return "\n".join(out)


def render_entries(entries: list[dict], listings: list[dict], pattern: str | None) -> str:
    rx = re.compile(pattern) if pattern else None
    counts = Counter(l.get("catalog_entry_id") for l in listings)
    rows = [e for e in entries
            if not rx or any(rx.search(e.get(f) or "") for f in ("name", "strain", "product_line"))]
    out = [f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}" + (f" matching /{pattern}/" if rx else "")]
    for e in sorted(rows, key=lambda e: (not e["is_active"], e.get("category") or "", e["name"], e.get("variant") or "")):
        out.append(f"\n  {e['name']} · {e.get('variant') or '?'}" + ("" if e["is_active"] else "  (INACTIVE)"))
        out.append(f"    line={e.get('product_line')!r} strain={e.get('strain')!r} "
                   f"category={e.get('category')} subtype={e.get('subtype')}")
        out.append(f"    source={e.get('source')} support={e.get('support')} listings={counts.get(e['id'], 0)} "
                   f"verified={'yes' if e.get('verified_fields') else 'no'}")
        out.append(f"    id={e['id']} external_id={e.get('external_id')}")
        terms = e.get("match_terms") or []
        if terms:
            out.append(f"    store names ({len(terms)}): " + " | ".join(terms[:6])
                       + (" | ..." if len(terms) > 6 else ""))
    return "\n".join(out)


def render_listings(listings: list[dict], entries: list[dict], pattern: str | None,
                    unmatched: bool = False) -> str:
    rx = re.compile(pattern) if pattern else None
    names = {e["id"]: e["name"] + (f" {e['variant']}" if e.get("variant") else "") for e in entries}
    rows = [l for l in listings if (not rx or rx.search(l.get("scraped_name") or ""))
            and (not unmatched or l.get("catalog_entry_id") not in names)]
    groups: dict[tuple, set] = defaultdict(set)
    for l in rows:
        key = (" ".join((l.get("scraped_name") or "").split()), l.get("scraped_category") or "",
               l.get("variant") or "", f"{l.get('product_line') or '-'} / {l.get('strain') or '-'}",
               names.get(l.get("catalog_entry_id"), "-"), l.get("catalog_match_method") or "")
        groups[key].add(l["dispensary_id"])
    out = [f"{len(rows)} listings at {len({l['dispensary_id'] for l in rows})} stores"
           + (f" matching /{pattern}/" if rx else "") + (", not matched to the catalog" if unmatched else ""),
           "  stores · name as the store writes it · category · variant · line / strain as enrichment "
           "read them → catalog entry (match method)"]
    for (name, cat, variant, read, entry, method), stores in sorted(
            groups.items(), key=lambda kv: (kv[0][0].lower(), kv[0][2])):
        out.append(f"  {len(stores):>3}  {name}  · {cat} · {variant or '?'} · {read} → {entry}"
                   + (f" ({method})" if method else ""))
    return "\n".join(out)


def render_triage(catalogs: list[dict], entries: list[dict], strain_vocab_by: dict[str, set]) -> str:
    by_catalog = defaultdict(list)
    for e in entries:
        by_catalog[e["catalog_id"]].append(e)
    rows = []
    for c in catalogs:
        prods = products(by_catalog.get(c["id"], []))
        if not prods:
            continue
        vocab = {k: len(ids - {c["id"]}) for k, ids in strain_vocab_by.items()}
        found = leads(prods, vocab, c["source_method"] != BOOTSTRAP)
        kinds = Counter(l.kind for l in found)
        rows.append((sum(l.weight for l in found), c, prods, kinds))
    out = ["score  brand                          source       products lines no-line  leads by kind"]
    for score, c, prods, kinds in sorted(rows, key=lambda r: (-r[0], r[1]["brand_name"])):
        n_lines = len({(p.category, p.line) for p in prods if p.line})
        out.append(f"{score:>5}  {c['brand_name'][:30]:<30} "
                   f"{'bootstrap' if c['source_method'] == BOOTSTRAP else 'storefront':<12} "
                   f"{len(prods):>8} {n_lines:>5} {sum(1 for p in prods if not p.line):>7}  "
                   + ", ".join(f"{k} {n}" for k, n in kinds.most_common()))
    return "\n".join(out)


# --------------------------------------------------------------------------- reads

ENTRY_COLS = ("id,catalog_id,name,product_line,category,subtype,strain,variant,source,support,"
              "is_active,external_id,verified_fields,match_terms")
LISTING_COLS = ("id,dispensary_id,scraped_name,scraped_category,variant,product_line,strain,"
                "catalog_entry_id,catalog_match_method")


def _db():
    import db_http
    return db_http


def find_catalog(brand: str) -> dict:
    catalogs = _db().select_all("brand_catalogs", "select=*&order=brand_name")
    want = brand.strip().lower()
    for c in catalogs:
        if want in (c["brand_name"].lower(), c["brand_slug"].lower()):
            return c
    close = difflib.get_close_matches(brand, [c["brand_name"] for c in catalogs], n=5, cutoff=0.5)
    sys.exit(f"no catalog for {brand!r}" + (f"; did you mean: {', '.join(close)}?" if close else ""))


def catalog_entries(catalog_id: str) -> list[dict]:
    return _db().select_all("brand_catalog_entries",
                            f"select={ENTRY_COLS}&catalog_id=eq.{catalog_id}&order=id")


def brand_listings(brand: str) -> list[dict]:
    import urllib.parse
    return _db().select_all("listings", f"select={LISTING_COLS}&is_active=is.true"
                                        f"&scraped_brand=eq.{urllib.parse.quote(brand)}&order=id")


def strain_vocabulary() -> dict[str, set]:
    """strain_key -> ids of the catalogs that use it as a strain (active entries)."""
    out: dict[str, set] = defaultdict(set)
    for e in _db().select_all("brand_catalog_entries",
                              "select=catalog_id,strain&is_active=is.true&strain=not.is.null&order=id"):
        k = strain_key(e["strain"])
        if len(k) >= 4:
            out[k].add(e["catalog_id"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("triage", help="every catalog, most leads first")
    show = sub.add_parser("show", help="one catalog by category and line, then its leads")
    show.add_argument("brand")
    show.add_argument("--category", choices=sorted(PLAUSIBLE))
    ent = sub.add_parser("entries", help="entries whose name, strain or line matches, every field")
    ent.add_argument("brand")
    ent.add_argument("pattern", nargs="?")
    lst = sub.add_parser("listings", help="store listings of the brand, grouped by name")
    lst.add_argument("brand")
    lst.add_argument("pattern", nargs="?")
    lst.add_argument("--unmatched", action="store_true", help="only listings no catalog entry matched")
    args = ap.parse_args()

    if args.command == "triage":
        catalogs = _db().select_all("brand_catalogs", "select=*&order=brand_name")
        entries = _db().select_all("brand_catalog_entries",
                                   f"select={ENTRY_COLS}&is_active=is.true&order=id")
        print(render_triage(catalogs, entries, strain_vocabulary()))
        return

    catalog = find_catalog(args.brand)
    entries = catalog_entries(catalog["id"])
    listings = brand_listings(catalog["brand_name"])
    if args.command == "show":
        vocab = {k: len(ids - {catalog["id"]}) for k, ids in strain_vocabulary().items()}
        print(render_show(catalog, entries, listings, vocab, args.category))
    elif args.command == "entries":
        print(render_entries(entries, listings, args.pattern))
    else:
        print(render_listings(listings, entries, args.pattern, args.unmatched))


if __name__ == "__main__":
    main()
