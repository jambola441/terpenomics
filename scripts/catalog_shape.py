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
from datetime import datetime, timedelta, timezone
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sizes  # noqa: E402
import taxonomy  # noqa: E402
from brand_catalog import norm_name  # noqa: E402
from catalog_bootstrap import squash, strain_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / "data" / "storefronts"
BOOTSTRAP = "listings_bootstrap"
THIN = 2              # a line with this many strains or fewer is worth a look
FRESH_DAYS = 21       # a listing not seen for longer is stale: its store stopped scraping
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
# Where strain can only mean a cultivar. A vape's strain may be a flavour or an effect
# ("Energy"), which is no evidence that the word is a strain.
CULTIVAR = {c for c, spec in taxonomy.SPECS.items() if spec.strain_means == "cultivar"}

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
    size_listings: Counter = field(default_factory=Counter)   # size -> listings matched

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
    def store_only_sizes(self) -> set[str]:
        """Sizes no site entry gives: one strain's 7-pack can be on the site while its
        5-pack was kept from the stores."""
        site = {e["variant"] or "?" for e in self.entries if e.get("source") != BOOTSTRAP}
        return {v for v in self.sizes if v not in site}

    def store_names_at(self, size: str) -> list[str]:
        return sorted({t for e in self.entries if (e["variant"] or "?") == size
                       for t in (e.get("match_terms") or [])})

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
        variant = {e["id"]: e["variant"] or "?" for e in entries}
        for l in listings:
            p = owner.get(l.get("catalog_entry_id"))
            if p:
                p.listings += 1
                p.size_listings[variant[l["catalog_entry_id"]]] += 1
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
          storefront: bool = False, other_brands: dict[str, str] | None = None,
          listings_known: bool = False) -> list[Lead]:
    """Where the catalog's shape looks unlike a brand's. Leads, not verdicts.

    strain_vocab: strain_key -> how many other brands' catalogs use it as a strain,
    so a line named like a common strain stands out. other_brands: squash(name) ->
    name of every other brand we keep a catalog for, so a line named like one does.
    listings_known: the products carry their listing counts (show does; triage not).
    """
    out: list[Lead] = []
    vocab = strain_vocab or {}
    shape = lines_of(prods)
    strains_at = defaultdict(list)                      # strain_key -> products using it
    for p in prods:
        if p.strain:
            strains_at[strain_key(p.strain)].append(p)

    # A line belongs to one category: "40's" are pre-rolls, "Sours" are gummies. The
    # same name as a line in two categories is usually not a line at all (an extraction
    # word, a brand-wide name, an effect) or products filed in the wrong category. The
    # lead goes to the category holding fewer of them, the usual suspect.
    spans = defaultdict(lambda: defaultdict(list))      # squash(line) -> category -> products
    for p in prods:
        if p.line:
            spans[squash(p.line)][p.category].append(p)
    for cats in spans.values():
        if len(cats) > 1:
            size = {c: len({q.label for q in ps}) for c, ps in cats.items()}
            least = min(cats, key=lambda c: (size[c], c))
            others = ", ".join(f"{c} ({n})" for c, n in sorted(size.items()) if c != least)
            out.append(Lead("cross-category", least, f'line "{cats[least][0].line}" '
                            f"({_tagged(cats[least])}) is also a line in {others}", 2))

    for cat, lines in sorted(shape.items()):
        named = {l: ps for l, ps in lines.items() if l}
        lineless = lines.get("", [])
        everything = lineless + [p for ps in named.values() for p in ps]

        # A big unnamed group beside named lines: brands name their lines, so the line
        # is usually there in the product names and something dropped it. Bootstrap
        # only: a storefront's unnamed range is the site's own naming.
        if not storefront:
            by_format = defaultdict(list)       # judged per format where the format decides
            for p in everything:
                by_format[p.subtype if cat in SUBTYPE_DECIDES else ""].append(p)
            for sub, ps in sorted(by_format.items()):
                here = sorted({p.line for p in ps if p.line})
                bare = [p for p in ps if not p.line]
                if here and len(bare) >= 3 and len(bare) >= 0.3 * len(ps):
                    out.append(Lead("mixed-lines", cat, f"{len(bare)} of {len(ps)} "
                                    f"{sub + ' ' if sub else ''}products have no line, beside "
                                    f"named lines {', '.join(here)}", 3))

        thin = {l: ps for l, ps in named.items() if len({p.label for p in ps}) <= THIN}
        if thin:
            if len(thin) >= 3 and len(thin) * 2 >= len(named):
                out.append(Lead("thin-lines", cat, f"{len(thin)} of {len(named)} lines have 1-2 "
                                "strains; the names used as lines may be strains, flavours or "
                                "effects, or the lines' other strains were filed elsewhere", 3))
            out.append(Lead("thin-line", cat, "; ".join(
                f"{l} ({_tagged(ps)})" for l, ps in sorted(thin.items()))))

        for line, ps in sorted(named.items()):
            k = strain_key(line)
            own = [p for p in strains_at.get(k, []) if p.line != line]
            if own:
                out.append(Lead("line-is-strain", cat, f'line "{line}" ({_tagged(ps)}) is the strain '
                                f'of {", ".join(sorted({f"{p.name} ({p.category})" for p in own}))}', 3))
            elif vocab.get(k):
                who = vocab[k] if isinstance(vocab[k], int) else (
                    f"{len(vocab[k])} other brands' catalogs ({', '.join(sorted(vocab[k])[:3])}"
                    + (", ..." if len(vocab[k]) > 3 else "") + ")")
                out.append(Lead("line-is-strain", cat, f'line "{line}" ({_tagged(ps)}) is a strain in '
                                + (f"{who} other brands' catalogs" if isinstance(who, int) else who), 2))
            if other_brands and squash(line) in other_brands:
                out.append(Lead("line-is-brand", cat, f'line "{line}" ({_tagged(ps)}) is '
                                f"{other_brands[squash(line)]}, a brand with its own catalog; "
                                "its products may be listed twice", 3))
            if _is_format_line(line):
                out.append(Lead("line-word", cat, f'line "{line}" is a strain type, format or size, '
                                f"not a named line ({_tagged(ps)})", 2))
            for other in named:
                if other > line and _alike(line, other):
                    out.append(Lead("similar-lines", cat, f'lines "{line}" and "{other}" may be one line', 2))

        # Store names that say a line the product lacks. Per size, since one strain's
        # sizes can belong to different lines (a plain 7-pack, an infused 5-pack).
        said = defaultdict(list)
        repeated = Counter(p.label for p in lineless)
        for p in lineless:
            tag = p.label + (f" [{p.subtype}]" if repeated[p.label] > 1 and p.subtype else "")
            for v in p.sizes:
                names = p.store_names_at(v)     # normalised: "40's" is stored as "40 s"
                for line in named:
                    hits = sum(1 for n in names if _contains(norm_name(n), norm_name(line)))
                    if names and hits * 2 >= len(names) and not _contains(norm_name(p.label), norm_name(line)):
                        said[line].append(f"{tag} {v} {hits}/{len(names)}")
        for line, labels in sorted(said.items()):
            out.append(Lead("stray", cat, f'no line, but most of their store names say "{line}": '
                            + ", ".join(sorted(set(labels))), 2))

        # A line of this category inside a strain: "Live Resin Infused Super Bud" with no
        # line, "Calm Peach" next to line "Calm". One lead per product, the longest line.
        flagged = set()
        for p in everything:
            if not p.strain:
                continue
            inside = [l for l in named if l != p.line and _contains(p.strain, l)
                      and squash(p.strain) != squash(l)]
            if inside:
                where = "has no line but its strain" if not p.line else f"(line {p.line}): the strain"
                out.append(Lead("line-in-strain", cat, f'"{p.label}" {where} contains line '
                                f'"{max(inside, key=len)}"', 3))
                flagged.add(id(p))
            elif p.line and _contains(p.strain, p.line):
                out.append(Lead("line-in-strain", cat, f'"{p.name}": the strain repeats its line', 2))
                flagged.add(id(p))

        # A line-less product whose strain is in exactly one line here, in sizes that
        # line lacks: likely the line's other size, split off where the line was missed
        # (STIIIZY: 40's Biscotti 2.5g beside a line-less Biscotti 1g). A strain sold
        # plain and in a line in the same size is two products and is not flagged.
        # Not where the line-less products are a range of their own, with a size 3+ of
        # them share and no line uses (Florist Farms' plain 7-packs): a plain 7-pack beside
        # an infused single is two products.
        def own_range(sub: str) -> bool:
            plain = Counter(v for q in lineless if q.subtype == sub or cat not in SUBTYPE_DECIDES
                            for v in q.sizes)
            lined = {v for q in everything if q.line and (q.subtype == sub or cat not in SUBTYPE_DECIDES)
                     for v in q.sizes}
            return any(n >= 3 and v not in lined for v, n in plain.items())

        for p in lineless:
            homes = [q for q in everything if q.line and p.strain
                     and strain_key(q.strain) == strain_key(p.strain)
                     and (cat not in SUBTYPE_DECIDES or q.subtype == p.subtype)]
            theirs = sorted({v for q in homes for v in q.sizes}, key=_size_order)
            if len({q.line for q in homes}) == 1 and not set(p.sizes) & set(theirs) \
                    and not own_range(p.subtype):
                out.append(Lead("split-size", cat, f"{_shown(p)} {' '.join(p.sizes)} has no line; "
                                f"{_shown(homes[0])} comes only in {' '.join(theirs)}. The line's "
                                "other size?", 2))

        # A format the brand barely uses: three carts beside forty pods is usually a
        # misread format word, not a product line.
        if cat in SUBTYPE_DECIDES and len(everything) >= 10:
            per = Counter(p.subtype for p in everything if p.subtype)
            top = max(per.values(), default=0)
            for sub, n in sorted(per.items()):
                if n <= 3 and top >= 10:
                    who = ", ".join(sorted({p.name for p in everything if p.subtype == sub}))
                    out.append(Lead("rare-format", cat, f"{n} {sub} product(s) beside {top} of the "
                                    f"brand's main format: {who}. Does the brand sell {sub}s?"))

        # Bootstrap entries come from 2+ stores' listings; none matched now means the
        # listings went stale or match elsewhere.
        if listings_known and not storefront:
            idle = sorted({_shown(p) for p in everything if not p.listings})
            if idle:
                out.append(Lead("idle", cat, f"{len(idle)} product(s) no listing matches now: "
                                + ", ".join(idle)))

        for p in everything:
            noise = _noise_in(p.strain)
            if noise and id(p) not in flagged:      # a contained line's words are not noise
                out.append(Lead("strain-word", cat, f'"{p.name}": strain carries {", ".join(noise)}'))
            for v in p.sizes:
                ok = _plausible(cat, None if v == "?" else v)
                if v == "?" or ok is False:
                    out.append(Lead("size", cat, f'"{p.name}": size {v!r} '
                                    + ("missing" if v == "?" else "is implausible for " + cat), 2))

        # A size that belongs to another line: every infused pre-roll is a 5-pack, so a
        # line-less 5-pack is probably an infused one that lost its line.
        held = {l: Counter(v for p in ps for v in p.sizes if v != "?") for l, ps in lines.items()}
        for a, ps in sorted(lines.items()):
            for v, k in sorted(held[a].items()):
                if k > 2 or k >= 0.2 * len(ps):
                    continue
                for b, qs in sorted(named.items()):
                    if b != a and held[b].get(v, 0) >= 3 and held[b][v] * 2 >= len(qs):
                        who = ", ".join(sorted({p.label for p in ps if v in p.sizes}))
                        out.append(Lead("size-of-other-line", cat, f"{who} ({a or 'no line'}) {v}: "
                                        f'the size of "{b}" ({held[b][v]} of {len(qs)}), rare in '
                                        f"{a or 'the line-less group'} ({k} of {len(ps)})", 2))
                        break

        # Two spellings of one strain in one line (and subtype, where that decides).
        groups = defaultdict(list)
        for p in everything:
            groups[(p.line, p.subtype if p.category in SUBTYPE_DECIDES else "")].append(p)
        for ps in groups.values():
            for i, a in enumerate(ps):
                for b in ps[i + 1:]:
                    if a.strain and b.strain and a.strain != b.strain and _alike(a.strain, b.strain):
                        out.append(Lead("near-dup", cat, f"{_shown(a)} and {_shown(b)} may be one product", 2))

        # Format pairs: a range that sells most strains as, say, both a cart and an
        # all-in-one makes a strain with one of the two stand out (the other filed under
        # another name, or sold at too few stores to be catalogued).
        if cat in SUBTYPE_DECIDES:
            for line, ps in sorted(lines.items()):
                formats = defaultdict(set)
                for q in ps:
                    if q.subtype:
                        formats[strain_key(q.label)].add(q.subtype)
                pairs = Counter(frozenset(f) for f in formats.values() if len(f) > 1)
                if not pairs:
                    continue
                pair, n = pairs.most_common(1)[0]
                if n >= 3 and n >= 0.6 * len(formats):
                    lone = sorted({f"{q.label} [{q.subtype}]" for q in ps
                                   if q.subtype in pair and len(formats[strain_key(q.label)] & pair) == 1})
                    if lone:
                        out.append(Lead("missing-pair", cat, f"{line or 'line-less'} range sells {n} of "
                                        f"{len(formats)} strains as {' + '.join(sorted(pair))}; only one "
                                        f"of the pair: {', '.join(lone)}"))

        # Dose sizes written two ways in one line: "100mg" beside "10pk 100mg".
        if PLAUSIBLE.get(cat, ("",))[0] == "mg":
            for line, ps in named.items():
                forms = Counter("pack" in v or "pk" in v for p in ps for v in p.sizes if v != "?")
                if len(forms) == 2:
                    bare = sorted({p.label for p in ps if any("pk" not in v for v in p.sizes)})
                    out.append(Lead("size", cat, f'line "{line}" writes sizes with and without a pack '
                                    f"count; without: {', '.join(bare)}"))

        if storefront:
            out += _store_only_leads(cat, everything)
    return out


def _same_size(category: str, a: str, b: str) -> bool:
    return a == b or sizes.same_size(sizes.parse(a, category=category),
                                     sizes.parse(b, category=category)) is True


def _shown(p: Product) -> str:
    """A product's name, with its format where the format makes it a different product
    (a strain's 1g cart and 1g all-in-one are two products)."""
    return f'"{p.name}"' + (f" [{p.subtype}]" if p.category in SUBTYPE_DECIDES and p.subtype else "")


def _store_only_leads(cat: str, everything: list[Product]) -> list[Lead]:
    """Storefront catalogs: store-only sizes (gap fills) that may be site products under
    the stores' name. Compared size by size — a different size is a real gap fill."""
    out = []
    site = [(s, w) for s in everything for w in s.sizes if w not in s.store_only_sizes]
    for p in everything:
        for v in sorted(p.store_only_sizes, key=_size_order):
            shape = [(s, w) for s, w in site if s is not p and _same_size(cat, v, w)
                     and (cat not in SUBTYPE_DECIDES or s.subtype == p.subtype)]
            for s, w in shape:
                if (strain_key(p.strain) and strain_key(p.strain) == strain_key(s.strain)) or \
                        _alike(p.name, s.name) or squash(p.name) in (squash(s.line), squash(s.strain)) or \
                        (p.strain and s.line and strain_key(p.strain) == strain_key(s.line)):
                    out.append(Lead("store-copy", cat, f"store-only {_shown(p)} {v} ({p.support} stores) "
                                    f"may be site product {_shown(s)} {w}", 2))
                    break
            else:
                # A site product the stores sell under another name has no listings of
                # its own, while the store-only copy beside it has them (GG4, renamed
                # from Gorilla Glue on the site).
                idle = sorted({s.label for s, w in shape if s.line == p.line and not s.size_listings.get(w)})
                if p.size_listings.get(v) and 1 <= len(idle) <= 3:
                    out.append(Lead("orphan-site", cat, f"store-only {_shown(p)} {v} "
                                    f"({p.size_listings[v]} listings) sits beside site products of "
                                    f"its shape that no listing matched: {', '.join(idle)}; renamed "
                                    "on the site?", 2))
    return out


# --------------------------------------------------------------------------- render

def store_sizes(prods: list[Product], listings: list[dict]) -> dict[tuple, list[tuple[str, int, int]]]:
    """(category, line) -> [(size, listings, stores)]: the sizes the stores' own listings
    of the line state, commonest first. The counts are the tell no single row gives:
    STIIIZY's 40's read 1g and 2.5g on dozens of listings and 4.5g on two at one store."""
    owner = {e["id"]: p for p in prods for e in p.entries}
    counts: dict[tuple, Counter] = defaultdict(Counter)
    stores: dict[tuple, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for l in listings:
        p = owner.get(l.get("catalog_entry_id"))
        if not p or not is_fresh(l):
            continue
        size = sizes.parse(l.get("variant"), l.get("scraped_name"), category=p.category).label() or "unstated"
        counts[(p.category, p.line)][size] += 1
        stores[(p.category, p.line)][size].add(l.get("dispensary_id"))
    return {key: [(v, n, len(stores[key][v])) for v, n in c.most_common()] for key, c in counts.items()}


def _states(text: str, label: str, category: str) -> bool:
    """Whether `text` names the package size `label` (its total weight or dose)."""
    want = sizes.parse(label, category=category)
    if want.grams is not None:
        return any(abs(g - want.grams) <= 0.02 for g in sizes.weight_mentions(text))
    if want.mg is not None:
        return any(abs(m - want.mg) <= 0.5 for m in sizes.mg_mentions(text))
    return False


def _unit_sold(size: sizes.Size, line_sizes: list[str], category: str) -> str | None:
    """The line's single size that each unit of a pack is ("2pk 2g" of 1g pods), if any."""
    if not size.pack or size.pack < 2:
        return None
    unit = (sizes.Size(grams=size.grams / size.pack) if size.grams is not None
            else sizes.Size(mg=size.mg / size.pack) if size.mg is not None else None)
    for v in line_sizes:
        single = sizes.parse(v, category=category)
        if unit and not single.pack and sizes.same_size(unit, single):
            return v
    return None


def listing_size_leads(prods: list[Product], listings: list[dict]) -> list[Lead]:
    """Store sizes that no product of the line comes in.

    A listing's size is the store's own field, copied as typed, and product pages group
    on it, so a typo makes a product of its own: The Spot's "5 x 0.9g ... (2.5g Pre-Roll
    Pack)" STIIIZY 40's showed as 4.5g, where 40's come in 1g and 2.5g. When the
    listing's own name or description states a size the line sells, the store mistyped;
    when two stores agree and nothing contradicts them, the catalog may lack the size. A
    pack of a size the line sells ("2PK 1G Pods") is a bundle, and its "1G" proves no
    typo. Sizes the line sells but one product lacks are a coverage gap, not this lead.
    """
    owner = {e["id"]: p for p in prods for e in p.entries}
    sold: dict[tuple, set] = defaultdict(set)            # (category, line) -> sizes
    for p in prods:
        sold[(p.category, p.line)].update(v for v in p.sizes if v != "?")
    groups: dict[tuple, dict] = {}
    for l in listings:
        p = owner.get(l.get("catalog_entry_id"))
        if not p or not is_fresh(l):
            continue
        cat, line_sizes = p.category, sorted(sold[(p.category, p.line)], key=_size_order)
        mine = sizes.parse(l.get("variant"), l.get("scraped_name"), category=cat)
        if mine.is_empty() or not line_sizes or any(
                sizes.same_size(mine, sizes.parse(v, category=cat)) is not False for v in line_sizes):
            continue
        g = groups.setdefault((id(p), mine.label()), {"p": p, "size": mine.label(), "sold": line_sizes,
                                                       "listings": 0, "stores": set(), "said": set(),
                                                       "unit": _unit_sold(mine, line_sizes, cat)})
        g["listings"] += 1
        g["stores"].add(l.get("dispensary_id"))
        text = " | ".join(t for t in (l.get("scraped_name"), _plain(l.get("description"))) if t)
        g["said"].update(v for v in line_sizes if _states(text, v, cat))
    out = []
    for g in groups.values():
        p, n, k = g["p"], g["listings"], len(g["stores"])
        kind = f"{p.line} {p.category}" if p.line else f"line-less {p.category}"
        head = (f'"{p.name}"' + (f" [{p.subtype}]" if p.subtype else "")
                + f': {n} listing{"s" if n > 1 else ""} at {k} store{"s" if k > 1 else ""} '
                + f'say{"" if n > 1 else "s"} {g["size"]}; {kind} products come in {", ".join(g["sold"])}')
        if g["unit"]:
            out.append(Lead("listing-size", p.category, head + f'. A pack of the line\'s {g["unit"]}: '
                            "a bundle the catalog lacks?"))
        elif g["said"]:
            out.append(Lead("listing-size", p.category, head + ". Its own name or description says "
                            + ", ".join(sorted(g["said"], key=_size_order)) + ": a store typo, not a size", 2))
        elif k > 1:
            out.append(Lead("listing-size", p.category, head + ". Stores agree: a size the catalog lacks?"))
        else:
            out.append(Lead("listing-size", p.category, head + ". One store: check its name and photo"))
    return out


def render_show(catalog: dict, entries: list[dict], listings: list[dict],
                strain_vocab: dict[str, int], category: str | None = None,
                other_brands: dict[str, str] | None = None,
                filed_elsewhere: dict[str, int] | None = None) -> str:
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
    ids = {e["id"] for e in active}
    fresh = [l for l in listings if is_fresh(l)]
    matched = sum(1 for l in fresh if l.get("catalog_entry_id") in ids)
    stale = len(listings) - len(fresh)
    out.append(f"  store listings: {len(fresh)} active at {len({l['dispensary_id'] for l in fresh})} "
               f"stores, {matched} matched to this catalog"
               + (f" ({matched * 100 // len(fresh)}%)" if fresh else "")
               + (f"; {stale} more not seen for {FRESH_DAYS}+ days at "
                  f"{len({l['dispensary_id'] for l in listings if not is_fresh(l)})} store(s), left out"
                  if stale else ""))
    out.append("  per product: sizes (* = that size only from stores) · listings matched / stores · "
               "[store-only n] = the whole product kept from n stores, "
               "not on the site")
    out.append("  per line: stores write = the sizes the line's listings state, listings/stores, "
               "commonest first; (no product) = no product of the line comes in it")

    shape = lines_of(prods)
    written = store_sizes(prods, listings)
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
            if written.get((cat, line)):
                out.append("    stores write: " + " · ".join(
                    f"{v} {n}/{k}" + ("" if v == "unstated" or any(_same_size(cat, v, c) for c in sizes_seen)
                                      else " (no product)")
                    for v, n, k in written[(cat, line)]))
            for p in ps:
                tag = f" [{p.subtype}]" if multi_sub and p.subtype else ""
                extra = f"  [store-only {p.support}]" if storefront and p.store_only else ""
                marked = " ".join(v + ("*" if storefront and v in p.store_only_sizes and not p.store_only
                                       else "") for v in p.sizes)
                out.append(f"      {p.label + tag:<40} {marked:<22} {p.listings}/{p.stores}{extra}")

    found = [l for l in leads(prods, strain_vocab, storefront, other_brands, listings_known=True)
             + listing_size_leads(prods, listings)
             if not category or l.category == category]
    for brand, n in sorted((filed_elsewhere or {}).items()):
        found.append(Lead("inside-other-catalog", "*", f'{brand}\'s catalog has a line "{catalog["brand_name"]}" '
                          f"with {n} product(s); the same products may be listed twice", 3))
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


def is_fresh(listing: dict, now: datetime | None = None) -> bool:
    """Seen within FRESH_DAYS. A store that stops scraping leaves its listings active, so
    an old last_seen_at is a dead menu, not a product on sale. Unknown counts as fresh."""
    seen = listing.get("last_seen_at")
    if not seen:
        return True
    when = datetime.fromisoformat(seen.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - when <= timedelta(days=FRESH_DAYS)


def render_lines(listings: list[dict], entries: list[dict], words: list[str]) -> str:
    """Each line word: how many store names carry it, how many of those listings have it
    recorded as their line, and the catalog's products in it. A word stores print far
    more often than enrichment records is a line enrichment misses."""
    fresh = [l for l in listings if is_fresh(l)]
    lines = Counter((e.get("product_line") or "") for e in entries if e["is_active"])
    out = [f"{len(fresh)} fresh listings · word · in store names (listings / stores) · "
           "recorded as the listing's line · catalog products in that line · only in the "
           "description (a store that leaves the line out of the name)"]
    seen = {l.lower(): l for l in words}
    seen.update({l.lower(): l for l in lines if l})       # the catalog's spelling wins
    for word in sorted(seen.values(), key=str.lower):
        w = norm_name(word)
        named = [l for l in fresh if _contains(norm_name(l.get("scraped_name") or ""), w)]
        recorded = sum(1 for l in named if _contains(norm_name(l.get("product_line") or ""), w))
        prods = len({(e.get("category"), e.get("subtype"), e.get("strain")) for e in entries
                     if e["is_active"] and e.get("product_line") == word})
        described = sum(1 for l in fresh if l not in named
                        and _contains(norm_name(_plain(l.get("description"))), w))
        out.append(f"  {word:<26} {len(named):>5} / {len({l['dispensary_id'] for l in named}):<4} "
                   f"{recorded:>6}   {prods:>4}   {described:>5}")
    return "\n".join(out)


def render_preview(catalog: dict, entries: list[dict], listings: list[dict], fresh_only: bool) -> str:
    """What `catalog_bootstrap.py --rebuild` would propose for this brand from today's
    listings, against the active bootstrap entries. Writes nothing."""
    import catalog_bootstrap
    rows = [{"id": l["id"], "dispensary_id": l["dispensary_id"], "name": l.get("scraped_name") or "",
             "brand": l.get("scraped_brand"), "category": l.get("scraped_category"),
             "subtype": l.get("subtype"), "strain": l.get("strain"),
             "product_line": l.get("product_line"), "variant": l.get("variant")}
            for l in listings if not fresh_only or is_fresh(l)]
    proposed = {e["external_id"]: e for e in
                catalog_bootstrap.propose(catalog["brand_name"], rows)["catalog"]["entries"]}
    current = {e["external_id"]: e for e in entries if e["is_active"] and e.get("source") == BOOTSTRAP}
    added = sorted(proposed.keys() - current.keys())
    gone = sorted(current.keys() - proposed.keys())
    out = [f"{catalog['brand_name']}: a rebuild from {len(rows)} {'fresh ' if fresh_only else ''}listings "
           f"proposes {len(proposed)} entries; {len(current)} bootstrap entries are active now. "
           f"+{len(added)} new, -{len(gone)} no longer proposed (a --rebuild --push retires those "
           "unless verified)."]
    for sign, keys, pool in (("+", added, proposed), ("-", gone, current)):
        for k in keys:
            out.append(f"  {sign} {_entry_label(pool[k])}  ({pool[k].get('support')} stores)")
    return "\n".join(out)


def _entry_label(e: dict) -> str:
    sub = f" [{e['subtype']}]" if e.get("category") in SUBTYPE_DECIDES and e.get("subtype") else ""
    return e["name"] + (f" {e['variant']}" if e.get("variant") else "") + sub


def _plain(html_text: str | None) -> str:
    """A description as text: menus send HTML."""
    return " ".join(re.sub(r"<[^>]+>", " ", html_text or "").split())


def render_listings(listings: list[dict], entries: list[dict], pattern: str | None,
                    unmatched: bool = False, photos: bool = False, descriptions: bool = False) -> str:
    rx = re.compile(pattern) if pattern else None
    by_id = {e["id"]: e for e in entries}
    rows = [l for l in listings if (not rx or rx.search(l.get("scraped_name") or ""))
            and (not unmatched or l.get("catalog_entry_id") not in by_id)]
    groups: dict[tuple, set] = defaultdict(set)
    images: dict[tuple, str] = {}
    blurbs: dict[tuple, str] = {}
    for l in rows:
        e = by_id.get(l.get("catalog_entry_id"))
        if e:
            method = l.get("catalog_match_method") or ""
            # The listing's size against its entry's: a 7-pack matched to a single is a
            # wrong match, whatever the name says.
            cat = e.get("category") or l.get("scraped_category")
            if l.get("variant") and e.get("variant") and sizes.same_size(
                    sizes.parse(l["variant"], category=cat), sizes.parse(e["variant"], category=cat)) is False:
                method += ", SIZE DIFFERS"
            target = _entry_label(e)
        else:
            target, method = "-", ("no match" if l.get("catalog_match_method") == "none" else
                                   l.get("catalog_match_method") or "not matched yet")
        key = (" ".join((l.get("scraped_name") or "").split()), l.get("scraped_category") or "",
               l.get("variant") or "", f"{l.get('product_line') or '-'} / {l.get('strain') or '-'}",
               target, method)
        groups[key].add(l["dispensary_id"])
        if l.get("image_url"):
            images.setdefault(key, l["image_url"])
        if l.get("description"):
            blurbs.setdefault(key, _plain(l["description"]))
    out = [f"{len(rows)} listings at {len({l['dispensary_id'] for l in rows})} stores"
           + (f" matching /{pattern}/" if rx else "") + (", not matched to the catalog" if unmatched else ""),
           "  stores · name as the store writes it · category · variant · line / strain on the listing "
           "→ catalog entry (match method)",
           "  (a matched listing's line / strain are copied from its entry; only the store's name is "
           "independent evidence)"]
    for (name, cat, variant, read, entry, method), stores in sorted(
            groups.items(), key=lambda kv: (kv[0][0].lower(), kv[0][2])):
        out.append(f"  {len(stores):>3}  {name}  · {cat} · {variant or '?'} · {read} → {entry}"
                   + (f" ({method})" if method else ""))
        if photos and (name, cat, variant, read, entry, method) in images:
            out.append(f"         photo: {images[(name, cat, variant, read, entry, method)]}")
        if descriptions and (name, cat, variant, read, entry, method) in blurbs:
            text = blurbs[(name, cat, variant, read, entry, method)]
            out.append(f"         description: {text[:220]}{'...' if len(text) > 220 else ''}")
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
        found = leads(prods, vocab, c["source_method"] != BOOTSTRAP, brands_but(catalogs, c))
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
LISTING_COLS = ("id,dispensary_id,scraped_name,scraped_brand,scraped_category,subtype,variant,"
                "product_line,strain,catalog_entry_id,catalog_match_method,last_seen_at,image_url,"
                "description")


def _db():
    import db_http
    return db_http


def brands_but(catalogs: list[dict], catalog: dict) -> dict[str, str]:
    """squash(name) -> name of every brand with a catalog, except this one."""
    return {squash(c["brand_name"]): c["brand_name"] for c in catalogs
            if c["id"] != catalog["id"] and len(squash(c["brand_name"])) >= 4}


def find_catalog(brand: str, catalogs: list[dict]) -> dict:
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


def catalog_index() -> tuple[dict[str, set], dict[str, Counter]]:
    """Over every catalog's active entries: strain_key -> ids of the catalogs that use it
    as a cultivar (only where strain means one: a tincture named "Sleep" is not evidence
    that Sleep is a strain), and squash(line) -> catalog id -> products in that line."""
    strains: dict[str, set] = defaultdict(set)
    lines: dict[str, Counter] = defaultdict(Counter)
    seen = set()
    for e in _db().select_all("brand_catalog_entries", "select=catalog_id,strain,category,product_line,"
                              "subtype&is_active=is.true&order=id"):
        k = strain_key(e.get("strain"))
        if len(k) >= 4 and e.get("category") in CULTIVAR:
            strains[k].add(e["catalog_id"])
        product = (e["catalog_id"], e.get("product_line"), e.get("category"), e.get("subtype"), k)
        if e.get("product_line") and product not in seen:
            seen.add(product)
            lines[squash(e["product_line"])][e["catalog_id"]] += 1
    return strains, lines


def strain_vocabulary() -> dict[str, set]:
    return catalog_index()[0]


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
    lst.add_argument("--photos", action="store_true", help="a package photo URL per row (the pack settles "
                     "dose, pack count and the printed effect)")
    lst.add_argument("--descriptions", action="store_true", help="the store's description per row (it can "
                     "name a line the product name leaves out)")
    lns = sub.add_parser("lines", help="line words in store names against what enrichment recorded")
    lns.add_argument("brand")
    lns.add_argument("--word", action="append", default=[], help="another candidate line word (repeatable)")
    pre = sub.add_parser("preview", help="what a bootstrap rebuild would propose now (writes nothing)")
    pre.add_argument("brand")
    pre.add_argument("--all-listings", action="store_true",
                     help=f"include listings not seen for {FRESH_DAYS}+ days, as the rebuild does today")
    args = ap.parse_args()

    if args.command == "triage":
        catalogs = _db().select_all("brand_catalogs", "select=*&order=brand_name")
        entries = _db().select_all("brand_catalog_entries",
                                   f"select={ENTRY_COLS}&is_active=is.true&order=id")
        print(render_triage(catalogs, entries, catalog_index()[0]))
        return

    catalogs = _db().select_all("brand_catalogs", "select=*&order=brand_name")
    catalog = find_catalog(args.brand, catalogs)
    entries = catalog_entries(catalog["id"])
    listings = brand_listings(catalog["brand_name"])
    if args.command == "show":
        names = {c["id"]: c["brand_name"] for c in catalogs}
        strains, lines = catalog_index()
        vocab = {k: [names[i] for i in ids - {catalog["id"]}] for k, ids in strains.items()}
        elsewhere = {names[i]: n for i, n in lines.get(squash(catalog["brand_name"]), {}).items()
                     if i != catalog["id"]}
        print(render_show(catalog, entries, listings, vocab, args.category,
                          brands_but(catalogs, catalog), elsewhere))
    elif args.command == "entries":
        print(render_entries(entries, listings, args.pattern))
    elif args.command == "lines":
        print(render_lines(listings, entries, args.word))
    elif args.command == "preview":
        print(render_preview(catalog, entries, listings, fresh_only=not args.all_listings))
    else:
        print(render_listings(listings, entries, args.pattern, args.unmatched, args.photos,
                              args.descriptions))


if __name__ == "__main__":
    main()
