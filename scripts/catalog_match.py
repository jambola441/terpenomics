#!/usr/bin/env python3
"""
catalog_match.py — Resolve listings to entries in their brand's catalog.

Enrichment extracts fields from a name; this matches the name to a product the brand
says it makes. When it resolves, the entry's fields are authoritative and every store
carrying that product lands on the same values — which is what collapses the
product_line split, where one product appears twice because the line was extracted on
some stores and not others (Jetpacks "FJ-Mini Afghani 0.6g" is written seven ways at
seven stores, with the line recorded as "FJ-Mini", "FJ Mini" or nothing).

How a listing is resolved
-------------------------
  attributes  its own reading (enrichment's category, format, strain, line and size,
              saved on the listing before any catalog overlay) names exactly one
              product in a size it comes in. Free, and accepted outright.
  review_*    otherwise, in the pipeline (owner's call, 2026-10-10), no match: the
              listing goes to the review queue with the reason (review_reason):
              review_missing, review_unsure or review_near. A join on a catalog
              reading (catalog_reading) read unsurely is review_unsure with its entry
              as a suggestion. Jev reads the listing against the catalog; it no
              longer picks entries here.
  jev         with --jev only (measurement), Jev chooses among the catalog's entries (one product in one
              size each) that agree with the reading on every attribute but one
              (near_entries; papers by merch_catalog's width and tips), or "none", with
              a probability for every option. Its pick is the entry, so the size comes
              with it: Jev never picks a product without its size (owner, 2026-10-09).
              A reading two attributes from everything gets no question; of more
              than 25 options, those whose titles share most words with the name.
              The probability is the gate:

                p >= AUTO (0.85)     method "jev"          trusted for identity
                p >= REVIEW (0.50)   method "jev_review"   entry recorded, not trusted
                otherwise            method "none"

Names never decide a match. The name tiers (a listing's name equal to, or inside, a
catalog title or a store name recorded on an entry) were removed on 2026-10-08: a store
name recorded on the wrong entry made a trusted wrong match no model ever saw (MFNY's
rosin badders on its resin entries). A misread now gets fixed where it is read, with
a strain alias or a line rule, once for every store. Without --jev only the join
decides.

**"No match" is a first-class outcome.** With a catalog a wrong answer stops being a
wrong string and becomes a specific wrong SKU, which reads as more authoritative and
travels further. The abstain option is offered *first* in every Jev question because
the model leans toward the first option (documented, jev-1.13 jaggedness): that bias
then pushes toward caution rather than toward whichever product ranked highest.

Cost and repeat runs
--------------------
One Jev call per unresolved listing, ~600 input tokens, $0.042/M, output free: about
$0.000025 a listing, so the whole fleet is cents. Answers are cached under
data/enrich_cache/catalog_match/ (the persistent disk on Render), keyed by the listing
name *and the options offered*, so a catalog edit that changes a listing's options
re-asks that listing and nothing else.

Usage
-----
  python scripts/catalog_match.py --brand Ayrloom                  # the attribute join only
  python scripts/catalog_match.py --brand Ayrloom --jev --misses   # with the Jev tier
  python scripts/catalog_match.py --brand Ayrloom --eval           # measure Jev's gating
  python scripts/catalog_match.py --all --write                    # pipeline step (5432)
  python scripts/catalog_match.py --all --write --via-http         # from the sandbox
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brand_catalog import norm_name  # noqa: E402
from catalog_bootstrap import squash, strain_key  # noqa: E402
import canonical  # noqa: E402
import catalog_reading  # noqa: E402
import catalog_store  # noqa: E402
import jev  # noqa: E402
import merch_catalog  # noqa: E402
import sizes  # noqa: E402
import taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# On the persistent disk the Render worker mounts, so repeat runs are free there too.
CACHE_DIR = ROOT / "data" / "enrich_cache" / "catalog_match"
# Bump when the question wording or the option rendering changes: cached answers were
# given to a different question.
QUESTION_VERSION = 4   # 3: options are entries (one product in one size), 2026-10-09
                       # 4: the state carries every size the listing could mean, 2026-10-10

# Set from the Ayrloom holdout (--eval, 2026-10-04): with the true product removed
# from the shortlist, Jev still picked a wrong one at p>=0.80 for 5.7% of listings,
# p>=0.85 for 2.3%, p>=0.90 for 0% — every one a near miss ("Half + Half" lemonade-
# and-tea read as "Lemonade"). Coverage on the same brand: 94.5% / 92.8% / 87.2%.
# 0.85 is the trade; the 0.50-0.85 band goes to review rather than being dropped.
AUTO = float(os.environ.get("CATALOG_MATCH_AUTO", "0.85"))
REVIEW = float(os.environ.get("CATALOG_MATCH_REVIEW", "0.50"))
# A catalog built from our own listings (catalog_bootstrap.py) omits products only
# one store carries, and a missing product is exactly when Jev's near-miss picks
# happen — the holdout's false matches above 0.85 vanish at 0.90.
AUTO_BOOTSTRAP = float(os.environ.get("CATALOG_MATCH_AUTO_BOOTSTRAP", "0.90"))


def auto_threshold(catalog: dict) -> float:
    return AUTO_BOOTSTRAP if catalog.get("source_method") == "listings_bootstrap" else AUTO
SHORTLIST = 25

# Methods counted as resolved in reports.
# "attributes": the listing's own reading joined the catalog (CatalogIndex.join).
# "exact", "substring" and "token" were the name tiers, removed 2026-10-08; listings
# matched by them before keep the method until their next match.
TRUSTED_METHODS = ("attributes", "exact", "substring", "token", "jev", "manual")
# Methods whose entry may overwrite a listing's identity at import. Narrower than the
# above on purpose: a substring hit read a beverage title onto seven gummies on
# Ayrloom ("Pineapple Mango" vs "Island Time Pineapple Mango"), so on its own it only
# nominates candidates.
OVERLAY_METHODS = ("attributes", "exact", "jev", "manual")

# Tokens that carry no identity — they appear in most names and inflate overlap.
STOPWORDS = {"the", "a", "an", "and", "of", "with", "pack", "pk", "mg", "g",
             "thc", "cbd", "cbn", "cbg", "each", "size", "count", "ct", "single",
             "indica", "sativa", "hybrid", "i", "s", "h"}


# Words stores and catalogs add around a strain without changing it: the extraction
# ("Orange Yuzu Rosin", "Hash Burger Live Resin"), the grade or format ("Premium Jack",
# "Indoor Hot Sauce", "Mega Dosed"), "The" ("The Belafonte"). strain_core sets them
# aside, with the brand's name and the product's own line ("Blueberry Belts" against
# Flav's Belts line, "Juicy Fruit Wave Rider" against 7 SEAZ's Wave Rider).
STRAIN_NOISE = {"live", "resin", "rosin", "solventless", "infused", "triple", "indoor", "sungrown",
                "premium", "the", "mega", "dosed", "dose", "gummy", "gummies", "flower", "vape",
                "cart", "pod", "aio", "preroll", "pre", "roll", "rolls", "disposable", "single", "pack"}


def strain_core(strain: str | None, brand: str | None = None, line: str | None = None) -> str:
    """strain_key() of the strain with STRAIN_NOISE, the brand's words and the line's words
    set aside; the whole strain when nothing else is left ("Live Resin" stays itself)."""
    words = [w for w in norm_name(strain or "").split() if w]
    drop = STRAIN_NOISE | set(norm_name(brand or "").split()) | set(norm_name(line or "").split())
    kept = [w for w in words if w not in drop]
    return strain_key(" ".join(kept or words))


def _tokens(s: str) -> set[str]:
    return {t for t in norm_name(s).split() if t and t not in STOPWORDS and not t.isdigit()}


def _contained(needle: str, haystack: str) -> bool:
    """Whole-token containment, so 'up' does not match inside 'syrup'."""
    n, h = needle.split(), haystack.split()
    return bool(n) and any(h[i:i + len(n)] == n for i in range(len(h) - len(n) + 1))


# ---------------------------------------------------------------------------
# The catalog, as products
# ---------------------------------------------------------------------------

@dataclass
class Product:
    key: str
    entries: list[dict]
    title: str = ""
    category: str | None = None
    subtype: str | None = None
    product_line: str | None = None
    strain: str | None = None
    sizes: list[sizes.Size] = field(default_factory=list)
    terms: set[str] = field(default_factory=set)
    tokens: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, key: str, entries: list[dict]) -> "Product":
        first = entries[0]
        p = cls(key=key, entries=entries, title=first.get("name") or "",
                category=first.get("category"), subtype=first.get("subtype"),
                product_line=first.get("product_line"), strain=first.get("strain"))
        for e in entries:
            s = sizes.parse(e.get("variant"), category=p.category)
            # An inferred size (line_fill.py) counts like a stated one: it is a size the
            # product's line comes in (the owner's rule, 2026-10-09), and a shortlist that
            # ignored it dropped the right product (a Live Rosin 0.5g pod read only off the
            # line) for whichever products state 0.5g.
            if not s.is_empty():
                p.sizes.append(s)
            # The catalog's own titles only: they rank the shortlist Jev reads. Store
            # names (match_terms) no longer take part in matching.
            n = norm_name(e.get("name") or "")
            if n:
                p.terms.add(n)
        p.tokens = _tokens(p.title)
        return p

    def size_ok(self, listing_size: sizes.Size) -> bool | None:
        """True if any size this product comes in matches, False if none does, None if
        either side is silent."""
        verdicts = [sizes.same_size(listing_size, s) for s in self.sizes]
        known = [v for v in verdicts if v is not None]
        return None if not known else any(known)

    def describe(self) -> str:
        """The option description Jev reads. Every criterion spelled out, because the
        model reads literally (jev-1.13 jaggedness: 'literal reading')."""
        bits = [self.title]
        kind = "/".join(x for x in (self.category, self.subtype) if x)
        if kind:
            bits.append(kind)
        if self.product_line:
            bits.append(f"product line {self.product_line}")
        if self.strain and norm_name(self.strain) != norm_name(self.title):
            bits.append(f"strain/flavor {self.strain}")
        labels = sorted({e.get("variant") for e in self.entries if e.get("variant")})
        if labels:
            bits.append("sizes " + ", ".join(labels[:6]))
        return " · ".join(bits)


# A flower listing whose name says infused ("3.5g Diamond Infused (Flower)") is never
# the brand's plain flower of the strain, even when the catalog has no infused product:
# Grassroots' "Atomic Breath Diamond Infused 3.5g" went to plain Atomic Breath at p=0.96
# once that product gained a 3.5g. Stores' subtype guesses are too loose to veto with
# (shortlist only prunes by them), but the word in the name is not a guess.
# A description counts only when it states the infusion outright ("the Infused Atomic
# Breath", "diamond infused", "infused with THCa diamonds"): stores also write
# "infused with the taste of cherries" of plain flower.
PLAIN_FLOWER = {"flower", "smalls"}
INFUSED_DESCRIPTION = re.compile(
    r"(?i)\bthe infused\b|\b(?:diamonds?|hash|kief|rosin|resin|distillate)[- ]infused\b"
    r"|\binfused (?:(?:indoor|whole|ground|pre-?ground)\s+)*(?:flower|buds?|nugs?)\b"
    r"|\binfus(?:ed|ing it) with (?:[\w-]+\s+){0,4}?"
    r"(?:diamonds?|resin|rosin|distillate|kief|hash|concentrates?|crystals?)\b")


def infused_veto(product: "Product", name: str | None, category: str | None,
                 description: str | None = None) -> bool:
    """True when the name or description states infused flower and the product is plain flower."""
    if (category or product.category) != "flower" or product.subtype not in PLAIN_FLOWER:
        return False
    if taxonomy.token_subtype("flower", name) == "infused":
        return True
    text = html.unescape(re.sub(r"<[^>]+>", " ", description or ""))
    return bool(INFUSED_DESCRIPTION.search(" ".join(text.split())))


class CatalogIndex:
    """One brand's catalog, grouped by product so sizes resolve inside a product."""

    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.brand_name = catalog.get("brand_name") or ""
        groups: dict[str, list[dict]] = defaultdict(list)
        for e in catalog.get("entries") or []:
            if e.get("is_active", True):
                groups[e.get("product_key") or catalog_store._product_key(e)].append(e)
        self.products = {k: Product.build(k, v) for k, v in groups.items()}
        # Pod and cart are one format here unless the brand sells both (taxonomy).
        self.synonyms = format_synonyms(catalog)

    def pick_entry(self, key: str, listing_variant: str | None, category: str | None,
                   name: str = "") -> dict:
        """The entry for the size this listing sells; the product's first otherwise.

        The fields that decide identity (category, line, strain) are the same across a
        product's entries, so an unmatched size still resolves to the right product.
        """
        product = self.products[key]
        want = sizes.parse(listing_variant, name, category=category or product.category)
        for e in product.entries:
            if sizes.same_size(want, sizes.parse(e.get("variant"), category=product.category)):
                return e
        if listing_variant:
            lv = norm_name(listing_variant)
            for e in product.entries:
                if e.get("variant") and norm_name(e["variant"]) == lv:
                    return e
        return product.entries[0]

    # -- the attribute join ----------------------------------------------------
    def join(self, reading: dict | None, name: str | None = None) -> tuple[str, dict] | None:
        """The one product, in the one size, the listing's own reading names: the same
        category, format and strain, the same line where the reading has one, and an
        entry of the size read. None when no product or several fit, or the reading
        lacks a strain or a size: Jev decides those.

        Exact on purpose (owner's call, 2026-10-08): a size the catalog does not list
        is not joined to the product's other sizes; the listing goes to Jev, and the
        audit shows what is left. On the labelled set this tier decided 168 of 295
        listings, 14 of them against the label, most of those labels stale.

        Inferred sizes (line_fill.py) count: they are the sizes the product's line
        comes in. Format is compared wherever both sides state one; a pre-roll keeps
        none.

        `name` is the listing's own name, read for one thing only: the other reading
        of a lone dose beside a pack (reading_size)."""
        if not reading or not reading.get("strain") or not reading.get("size"):
            return None
        category = reading.get("category")
        want = reading_size(reading, name)
        if want.is_empty():
            return None
        strain, line, subtype = strain_key(reading["strain"]), squash(reading.get("product_line")), \
            reading.get("subtype")
        # The strain as read first. Only when no product of the category carries it are
        # the words around a strain set aside (strain_core), so "Sour Diesel" never
        # reaches "Premium Sour Diesel" while the brand sells a plain Sour Diesel.
        exact = any(p.category == category and strain_key(p.strain) == strain
                    for p in self.products.values())
        hits = []
        for key, p in self.products.items():
            if p.category != category:
                continue
            if exact and strain_key(p.strain) != strain:
                continue
            if not exact and strain_core(p.strain, self.brand_name, p.product_line) != \
                    strain_core(reading["strain"], self.brand_name, p.product_line):
                continue
            if line and squash(p.product_line) != line:
                continue
            if subtype and p.subtype and taxonomy.keeps_subtype(category) \
                    and not taxonomy.same_format(subtype, p.subtype, self.synonyms):
                continue
            entry = fitting_entry(p.entries, want, category)
            if entry is not False:
                hits.append((key, entry))
        return hits[0] if len(hits) == 1 and hits[0][1] is not None else None

    def shortlist(self, name: str, category: str | None, variant: str | None,
                  k: int = SHORTLIST, exclude: str | None = None,
                  subtype: str | None = None, description: str | None = None) -> list[str]:
        """Products worth asking about, best first. Possibly empty.

        Containment of a title or match term scores highest; otherwise token overlap.
        A product in a different known category is dropped (category is 100% on the
        gold suites — it is the one field we can lean on). Size filters only when it
        can: if no candidate states a compatible size, none is dropped for size,
        because a brand launching a new pack size is still the same product.

        Subtype filters the same soft way. It is what separates a gummy from a drink
        of the same flavour: in the Ayrloom holdout every wrong pick above p=0.85 was a
        gummy ("Sunny Days" pink lemonade) answered with the beverage "Lemonade", and
        the substring tier made the same mistake with "Island Time Pineapple Mango".
        Enrichment gets subtype right 97.9% of the time on the gold suites — enough to
        prune with, not enough to exclude with when it is the only thing left.

        `exclude` drops one product before anything else, as if the catalog did not
        contain it — the --eval holdout. Dropping it after the filters would let the
        true product shield its wrong-size siblings and flatter the result.
        """
        ln = norm_name(name)
        lt = _tokens(name)
        scored: list[tuple[float, str]] = []
        for key, p in self.products.items():
            if key == exclude:
                continue
            if category and p.category and p.category != category:
                continue
            if infused_veto(p, name, category, description):
                continue
            best = 0.0
            for t in p.terms:
                if _contained(t, ln):
                    best = max(best, 2.0 + 0.1 * len(t.split()))
            if best == 0.0 and p.tokens and lt:
                overlap = len(p.tokens & lt) / len(p.tokens)
                if overlap > 0:
                    best = overlap
            if best > 0:
                scored.append((best, key))
        if not scored:
            return []
        listing_size = sizes.parse(variant, name, category=category)
        # Hard veto: a product whose subtype AND size both contradict the listing is
        # never it — a 100mg gummy is not a 10mg can — even if that empties the list.
        # In the holdout this was the last wrong pick above p=0.85 ("Sunny Days" pink
        # lemonade gummies -> the "Lemonade" drink, once Sunny Days was removed).
        if subtype and not listing_size.is_empty():
            scored = [(s, key) for s, key in scored
                      if not (self.products[key].subtype
                              and not taxonomy.same_format(self.products[key].subtype, subtype, self.synonyms)
                              and self.products[key].size_ok(listing_size) is False)]
        if subtype:
            same = [(s, key) for s, key in scored
                    if not self.products[key].subtype
                    or taxonomy.same_format(self.products[key].subtype, subtype, self.synonyms)]
            if any(taxonomy.same_format(self.products[key].subtype, subtype, self.synonyms) for _, key in same):
                scored = same
        if not listing_size.is_empty():
            fits = [(s, key) for s, key in scored
                    if self.products[key].size_ok(listing_size) is not False]
            if any(self.products[key].size_ok(listing_size) for _, key in fits):
                scored = fits
        scored.sort(key=lambda sk: (-sk[0], len(self.products[sk[1]].title)))
        return [key for _, key in scored[:k]]


def fitting_entry(entries: list[dict], want: sizes.Size, category: str | None) -> dict | None | bool:
    """The one entry of a product in the size wanted: False when none fits, None when
    two sizes fit and nothing tells them apart.

    A size that leaves its pack count open fits a product's single and its 10-pack of
    the same total alike ("100mg" against Flav's "1pk 100mg" and "10pk 100mg"). The
    entry stating the same count wins; otherwise the product is a match whose size is
    unknown, and the join leaves the listing to Jev rather than take whichever entry
    came first. Two entries of one size (a stated one and an inferred one) are one fit.
    """
    fits = [(e, sizes.parse(e.get("variant"), category=category)) for e in entries]
    fits = [(e, s) for e, s in fits if sizes.same_size(want, s) is True]
    if not fits:
        return False
    if len({s for _, s in fits}) > 1:
        fits = [(e, s) for e, s in fits if s.pack == want.pack] or fits
    if len({s for _, s in fits}) > 1:
        return None
    return next((e for e, _ in fits if e.get("source") != "inferred"), fits[0][0])


def attribute_misses(reading: dict, product: "Product", entry: dict,
                     name: str | None = None, brand: str | None = None,
                     synonyms: bool = True) -> list[str]:
    """The attributes on which one catalog entry disagrees with a listing's reading, in
    the join's own terms (CatalogIndex.join): a line or format the reading leaves blank
    is no disagreement; a strain or size it leaves blank is one, because the join needs
    both. An empty list is a join hit."""
    category = reading.get("category")
    out = []
    if not category or product.category != category:
        out.append("category")
    if not reading.get("strain") or (
            strain_key(product.strain) != strain_key(reading["strain"])
            and strain_core(product.strain, brand, product.product_line)
            != strain_core(reading["strain"], brand, product.product_line)):
        out.append("strain")
    line = squash(reading.get("product_line"))
    if line and squash(product.product_line) != line:
        out.append("line")
    subtype = reading.get("subtype")
    if subtype and product.subtype and taxonomy.keeps_subtype(category or product.category) \
            and not taxonomy.same_format(subtype, product.subtype, synonyms):
        out.append("subtype")
    want = reading_size(reading, name)
    if want.is_empty() or sizes.same_size(
            want, sizes.parse(entry.get("variant"), category=product.category)) is not True:
        out.append("size")
    return out


def reading_size(reading: dict, name: str | None = None) -> sizes.Size:
    """The size the reading names, with the pack count the listing's name states.

    The reading stores one label ("100mg"), which can drop the count the name gives:
    "1pk - 100mg" is Flav's single Mega Belt, not its 10-pack of 100mg (fitting_entry
    tells them apart only when the count is known). So when the reading states no
    count and the name read alone gives the same total with one, the name's Size is
    used. Nothing else is read into it: a size that fits no entry is Jev's to choose
    (near_entries). The name gives a size here, never an identity.
    """
    category = reading.get("category")
    want = sizes.parse(reading.get("size"), category=category)
    if not name or want.pack is not None:
        return want
    own = sizes.parse(name, category=category)
    if own.pack is not None and not own.is_empty() and sizes.same_size(own, want):
        return own
    return want


def format_synonyms(catalog: dict) -> bool:
    """Whether pod and cart (taxonomy.FORMAT_SYNONYMS) are one format in this catalog."""
    return taxonomy.synonyms_hold({e.get("subtype") for e in catalog.get("entries") or []
                                   if e.get("is_active", True) and e.get("subtype")})


def matched_subtype(entry: dict, name: str | None, synonyms: bool = True) -> str | None:
    """The subtype a listing resolved to `entry` takes.

    The entry's — unless a format word in the listing's own name says otherwise
    ("Cart", "AIO", "Starter Kit": taxonomy.SUBTYPE_TOKENS). The name is a fact about
    this listing; the entry's subtype is a claim about the product, and a bootstrap
    built from model answers can get a format wrong. Used wherever a catalog identity
    is applied — enrichment's catalog-first step and the importer's overlay — so the
    two never disagree. None for a category that keeps no subtype (pre-roll).
    """
    if not taxonomy.keeps_subtype(entry.get("category")):
        return None
    said = taxonomy.token_subtype(entry.get("category"), name)
    # A synonym is no disagreement where the brand sells one of the two: a PAX pod a
    # store calls "Cart" stays a pod. Where it sells both, the name's word stands.
    if said and taxonomy.same_format(said, entry.get("subtype"), synonyms):
        return entry.get("subtype")
    return said or entry.get("subtype")


def catalog_size(variant: str | None, name: str | None, entry: dict,
                 product_entries: list[dict], description: str | None = None) -> str | None:
    """The size a mistyped listing really is, from its product's catalog sizes, written
    the way stores write sizes (the package total: "100mg"). None when the store's own
    size stands.

    Only products sold by dose (edible, tincture, topical), where a store's figure is
    often the CBD amount, a cannabinoid sum or a per-piece dose: Camino's 100mg 20-pack
    listed as 50mg, Ayrloom's 150mg drops as 600mg (150mg THC + 450mg CBD). A weight
    that disagrees is more often a real size the catalog lacks (a 14g bag matched to
    its strain's 3.5g), so it stands. So does a size the product comes in, a listing
    that names another pack count (Level's Protab 2-pack beside the catalog's 5-pack),
    and one the product's sizes cannot settle (two sizes left after the pack count).

    The listing has to back the catalog, because the catalog can lack a size too (Level
    may sell a 50mg Protab 5-pack beside the 100mg one): its name or description states
    the catalog's total ("100mg THC : 100mg CBD per package"), or its figure is that
    size's per-piece dose ("10mg" on a 10-pack of 100mg). And a catalog size of 10mg or
    less with no pack count is never the answer to a larger figure: that is usually a
    per-piece dose recorded as the size (Eaton's "Daily Elevation 5mg" gummies).
    """
    category = entry.get("category")
    if category not in sizes.DOSE_CATEGORIES:
        return None
    mine = sizes.parse(variant, name, category=category)
    if mine.mg is None:
        return None
    own = [sizes.parse(e.get("variant"), category=category) for e in (product_entries or [entry])]
    own = [s for s in own if s.mg is not None]
    if not own or any(sizes.same_size(mine, s) is not False for s in own):
        return None
    if mine.pack:
        own = [s for s in own if (s.pack or 1) == mine.pack]
    if len({s.mg for s in own}) != 1:
        return None
    target = own[0]
    if (target.pack or 1) == 1 and target.mg <= 10 < mine.mg:
        return None
    # A figure the text gives for another cannabinoid corroborates nothing: Wana's Fast
    # Asleep is "20mg THC", and its "100mg CBD" must not move it to a 100mg entry.
    stated = any(abs(m - target.mg) <= 0.5 for m in sizes.mg_mentions(name, html.unescape(
        re.sub(r"<[^>]+>", " ", description or "")), non_thc=False))
    per_piece = (target.pack or 1) > 1 and not mine.pack and abs(mine.mg * target.pack - target.mg) <= 0.5
    return f"{target.mg:g}mg" if stated or per_piece else None


# ---------------------------------------------------------------------------
# The Jev question
# ---------------------------------------------------------------------------

NONE = "none"


# Most entries a question may offer; beyond it, those whose product title shares most
# words with the listing's name (closest).
MAX_OPTIONS = 25

# A candidate: (product key, entry, the attributes it misses the reading on — none or one).
Candidate = tuple


def near_entries(index: "CatalogIndex", listing: dict, brand: str,
                 exclude: str | None = None) -> list[Candidate]:
    """Jev's options for a listing the join left: the catalog entries that agree with
    its reading on every attribute but at most one (owner's call, 2026-10-09: Jev never
    picks a product without its size; it chooses among the entries one attribute away,
    or none). STIIIZY's 4.5g Orange Sunset gets the 1g and the 2.5g; a strain the
    reading lacks gets every strain in its line and size. Papers and hardware are read
    by merch_catalog's rules (width, tips, colour), the rest by attribute_misses."""
    name, cat = listing.get("name") or "", listing.get("category")
    if merch_catalog.is_merch(cat, listing.get("subtype"), name, brand):
        r = merch_catalog.reading(name, brand, listing.get("subtype"), cat)
        if r.get("subtype") not in merch_catalog.CATALOGED:
            return []
        out = []
        for e, m in merch_catalog.near_entries(index.catalog.get("entries") or [], r):
            key = e.get("product_key") or catalog_store._product_key(e)
            if key in index.products and key != exclude:
                out.append((key, e, m))
        return out
    reading = listing.get("reading")
    if not reading:
        return []
    out = []
    for key, p in index.products.items():
        if key == exclude or infused_veto(p, name, cat, listing.get("description")):
            continue
        for e in p.entries:
            m = attribute_misses(reading, p, e, name, brand, index.synonyms)
            if len(m) <= 1:
                out.append((key, e, m))
    return out


def closest(candidates: list[Candidate], name: str, index: "CatalogIndex") -> list[Candidate]:
    """The options a question offers: the entries that miss nothing when there are any
    (a reading that fits several products exactly, which the join leaves), else the
    near entries, at most MAX_OPTIONS of them, those whose product's title shares the
    most words with the listing's name first. A strain read short ("Alley" for Alley
    Oop) is one attribute from every flower of its size; the name tells which."""
    exact = [c for c in candidates if not c[2]]
    if exact:
        candidates = exact
    if len(candidates) <= MAX_OPTIONS:
        return candidates
    words = set(norm_name(name).split())
    def overlap(c):
        p = index.products[c[0]]
        title = set(norm_name(" ".join(x for x in (p.title, p.strain, p.product_line) if x)).split())
        return len(words & title) / (len(title) or 1)
    return sorted(candidates, key=overlap, reverse=True)[:MAX_OPTIONS]


def option_text(product: "Product", entry: dict) -> str:
    """What Jev reads for one option: the product, spelled out (Product.describe) but
    with this entry's size alone."""
    bits = [product.title]
    kind = "/".join(x for x in (product.category, product.subtype) if x)
    if kind:
        bits.append(kind)
    if product.product_line:
        bits.append(f"product line {product.product_line}")
    if product.strain and norm_name(product.strain) != norm_name(product.title):
        bits.append(f"strain/flavor {product.strain}")
    colour = (entry.get("attributes") or {}).get("colour")
    if colour:
        bits.append(f"colour {colour}")
    bits.append(f"size {entry.get('variant') or 'not stated'}")
    return " · ".join(bits)


def jev_question(brand: str, listing: dict, index: CatalogIndex,
                 candidates: list[Candidate]) -> tuple[dict, dict, dict[str, Candidate]]:
    """(state, questions, label -> candidate) for one listing.

    The state is the listing and nothing else a decision does not need — of the sales
    copy, only a product line it names (described_line): 'large irrelevant state costs
    accuracy' is the third documented jagged edge.
    """
    state = {
        "brand": brand,
        "listing_name": listing.get("name") or "",
        "listing_category": listing.get("category") or "",
        "listing_subtype": listing.get("subtype") or "",
        "store_size_field": listing.get("variant") or "",
    }
    # Every size the listing could mean, not one the parser settled on: the store's
    # field, and the name and description read as the package total and as count x
    # unit (owner, 2026-10-10: the parser proposes sizes, Jev picks among the catalog's).
    options = size_options(listing)
    if options:
        state["sizes_the_listing_could_mean"] = options
    line = described_line(listing, index)
    if line:
        state["product_line_in_description"] = line
    labels: dict[str, Candidate] = {}
    criteria: dict[str, str] = {
        NONE: ("None of the options below is this listing — its flavor, strain or scent "
               "differs, its product line differs, its size differs, or it is a product "
               "this catalog does not contain."),
    }
    for cand in candidates:
        key, entry, _ = cand
        p = index.products[key]
        label = f"{(p.title or key).strip()} — {entry.get('variant') or 'no size'}"[:70]
        base, n = label, 2
        while label in criteria:
            label = f"{base} ({n})"
            n += 1
        labels[label] = cand
        criteria[label] = option_text(p, entry)
    question = jev.Choice(
        instructions=(
            f"Which {brand} catalog item is this dispensary listing? Each option is one "
            "product in one size. Stores rename products freely: extra words, store codes, "
            "potency, lineage and the brand name itself are noise. The listing's size can be "
            "read more than one way (a figure beside a pack count may be each piece or the "
            "whole pack, and a store's size field can be mistyped); the sizes it could mean "
            "are listed, and the right option is the one in the size this listing most "
            "likely is. Match on what the product "
            "is — the same flavor, strain or scent, the same product line, and the same "
            "size. Answer none when no option is that product in that size."
        ),
        criteria=criteria,
    )
    return state, {"product": question}, labels


def size_options(listing: dict) -> str:
    """The sizes size_candidates reads in a listing, each with where it was read:
    "4.5g (store size field; name, as 5 x 0.9g), 2.5g (name)". Readings that imply a
    unit that does not exist (a 0.03g pre-roll) are left out."""
    import size_candidates
    cands = size_candidates.candidates({"variant": listing.get("variant"), "scraped_name": listing.get("name"),
                                        "description": listing.get("description"),
                                        "scraped_category": listing.get("category")})
    where = {"field": "store size field", "name": "name", "description": "description",
             "name+field": "count in the name x the store size field"}
    by_size: dict[str, list[str]] = {}
    for c in cands:
        if c.likely and c.source in where:
            how = where[c.source] + ("" if c.reading in ("", "as written") else f", {c.reading}")
            by_size.setdefault(c.label(), [])
            if how not in by_size[c.label()]:
                by_size[c.label()].append(how)
    return ", ".join(f"{size} ({'; '.join(hows)})" for size, hows in by_size.items())


def described_line(listing: dict, index: CatalogIndex) -> str | None:
    """The curated product line the listing's description names, when its name names none.

    Store copy often carries the line a name leaves out ("Stiiizy 40s pre-rolls are
    setting the standard..." under "King Louis XIII - 1G Infused Prerolls"). The same
    rule enrichment uses (canonical.line_from_description): only curated lines that
    declare a category, and a description naming two of them settles nothing. Measured
    2026-10-05 against wider hints, which did worse: the first 300 characters of the
    copy (21 brands: trusted matches gained and lost about evenly, and more wrong picks
    when the true product was missing, as copy is often pasted from another product),
    and any line of the brand's catalog (generic line names such as "Infused" or
    "Classic" turn up in copy about other products).
    """
    brand = index.brand_name
    if not listing.get("description") or canonical.find_product_line(brand, listing.get("name") or "",
                                                                     listing.get("category")):
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", listing["description"]))
    return canonical.line_from_description(brand, " ".join(text.split()), listing.get("category"))


def _cache_key(listing: dict, candidates: list[Candidate], index: CatalogIndex) -> str:
    parts = [
        QUESTION_VERSION, jev.MODEL, norm_name(listing.get("name") or ""),
        listing.get("category") or "", listing.get("subtype") or "", listing.get("variant") or "",
        [(k, e.get("id"), option_text(index.products[k], e)) for k, e, _ in candidates],
    ]
    # Only when it is in the question, so answers cached without one stay valid.
    line = described_line(listing, index)
    if line:
        parts.append(line)
    payload = json.dumps(parts, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()

class AnswerCache:
    def __init__(self, slug: str, enabled: bool = True):
        self.path = CACHE_DIR / f"{slug}.json"
        self.enabled = enabled
        self.data: dict[str, dict] = {}
        if enabled and self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                print(f"  [warn] unreadable match cache {self.path.name}; starting empty",
                      file=sys.stderr)

    def get(self, key: str) -> dict | None:
        return self.data.get(key) if self.enabled else None

    def put(self, key: str, value: dict) -> None:
        if self.enabled:
            self.data[key] = value

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)   # atomic: a kill mid-write cannot truncate the cache


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    listing: dict
    product_key: str | None
    entry: dict | None
    confidence: float
    method: str
    candidates: int = 0
    probabilities: dict | None = None


def gate(pick: str | None, p: float, auto: float | None = None) -> str:
    if not pick or pick == NONE:
        return "none"
    if p >= (AUTO if auto is None else auto):
        return "jev"
    if p >= REVIEW:
        return "jev_review"
    return "none"


def resolve(catalog: dict, listings: list[dict], *, use_jev: bool,
            cache: AnswerCache | None = None, usage: jev.Usage | None = None,
            workers: int = 8, exclude: dict[str, str] | None = None) -> list[Decision]:
    """Decide every listing of one brand.

    `exclude` (listing id -> product key) removes that product from the listing's
    options — the holdout used by --eval to measure how often Jev picks a wrong
    product when the right one is absent.
    """
    index = CatalogIndex(catalog)
    brand = catalog.get("brand_name") or ""
    cache = cache or AnswerCache(catalog.get("brand_slug") or "x", enabled=False)
    decisions: list[Decision | None] = [None] * len(listings)
    pending: list[tuple[int, list[Candidate], dict[str, Candidate], str]] = []
    jobs = []

    for i, l in enumerate(listings):
        name, cat = l.get("name") or "", l.get("category")
        held_out = (exclude or {}).get(str(l.get("id")))
        if merch_catalog.is_merch(cat, l.get("subtype"), name, brand):
            # Hardware and papers: their reading is the rules', computed here (merch_catalog).
            hit = merch_catalog.join(catalog.get("entries") or [],
                                     merch_catalog.reading(name, brand, l.get("subtype"), cat))
            if hit is not None:
                key = hit.get("product_key") or catalog_store._product_key(hit)
                if key in index.products and key != held_out:
                    decisions[i] = Decision(l, key, hit, 1.0, "attributes")
                    continue
        reading = l.get("reading")
        joined = index.join(reading, name)
        if joined and joined[0] != held_out \
                and not infused_veto(index.products[joined[0]], name, cat, l.get("description")):
            agrees = store_size_agrees(l, joined[1], (reading or {}).get("category"))
            if catalog_reading.trusted(reading, agrees):
                decisions[i] = Decision(l, joined[0], joined[1], 1.0, "attributes")
            else:
                # Read against the catalog, but unsurely: a product the catalog lacks
                # reads as its nearest one (catalog_reading). A suggestion for review.
                decisions[i] = Decision(l, joined[0], joined[1], _least_p(reading), "review_unsure")
            continue
        if not use_jev:
            decisions[i] = Decision(l, None, None, 0.0, review_reason(index, l, brand, held_out))
            continue
        cands = closest(near_entries(index, l, brand, exclude=held_out), name, index)
        if not cands:
            decisions[i] = Decision(l, None, None, 0.0, "none", len(cands))
            continue
        key = _cache_key(l, cands, index)
        hit = cache.get(key)
        state, questions, labels = jev_question(brand, l, index, cands)
        if hit is not None:
            decisions[i] = _decide(l, index, labels, hit["pick"], hit["p"], hit.get("probs"),
                                   len(cands))
            continue
        pending.append((i, cands, labels, key))
        jobs.append((state, questions))

    if jobs:
        results = jev.ask_many(jobs, workers=workers, usage=usage)
        for (i, cands, labels, key), res in zip(pending, results):
            l = listings[i]
            if res is None:
                # No decision: reported as "error" so a caller holding an earlier
                # answer can keep it (the importer does); treated as no match
                # otherwise. Not cached, so the next run asks again.
                decisions[i] = Decision(l, None, None, 0.0, "error", len(cands))
                continue
            pick, p, probs = res.choice("product")
            cache.put(key, {"pick": pick, "p": p, "probs": probs, "model": res.model})
            decisions[i] = _decide(l, index, labels, pick, p, probs, len(cands))
    cache.save()
    return [d for d in decisions if d is not None]


def store_size_agrees(listing: dict, entry: dict, category: str | None) -> bool:
    """Whether the store's own size field (or, without one, the name) names the entry's size."""
    want = sizes.parse(listing.get("variant"), listing.get("name") or "", category=category)
    return not want.is_empty() and \
        sizes.same_size(want, sizes.parse(entry.get("variant"), category=category)) is True


def _least_p(reading: dict | None) -> float:
    p = (reading or {}).get("p") or {}
    return round(min((p.get(k, 0.0) for k in ("category", "strain", "size")), default=0.0), 3)


def review_reason(index: "CatalogIndex", listing: dict, brand: str,
                  exclude: str | None = None) -> str:
    """Why the join left a listing, which says what fixes it (the review queue):

      review_missing  read against the catalog, its category or strain is none of the
                      catalog's: most likely a product the catalog lacks; add it
      review_unsure   some step was answered unsurely (catalog_reading.unsure_steps,
                      on the reading's `p`)
      review_near     one catalog entry misses its reading on one attribute alone
                      (near_entries): a size, line or format the catalog may lack
      none            nothing close
    """
    reading = listing.get("reading") or {}
    if reading.get("by") == "catalog" and (not reading.get("category") or not reading.get("strain")):
        return "review_missing"
    if catalog_reading.unsure_steps(reading):
        return "review_unsure"
    if near_entries(index, listing, brand, exclude=exclude):
        return "review_near"
    return "none"


def _decide(listing, index, labels, pick, p, probs, n_cands) -> Decision:
    """Jev's pick is one entry: the product and its size come with it."""
    method = gate(pick, p, auto_threshold(index.catalog))
    cand = labels.get(pick) if method in ("jev", "jev_review") else None
    if cand is None and method in ("jev", "jev_review"):
        method = "none"                 # a label no longer offered (an answer cached for another catalog)
    key, entry = (cand[0], cand[1]) if cand else (None, None)
    conf = p if key else float((probs or {}).get(NONE, 0.0))
    return Decision(listing, key, entry, round(conf, 3), method, n_cands, probs)

# ---------------------------------------------------------------------------
# Listings in, decisions out
# ---------------------------------------------------------------------------

def fetch_listings() -> list[dict]:
    """Active listings over PostgREST, in the shape resolve() reads.

    Read-only, so it works from the sandbox; writing goes through psycopg2 (below),
    which needs the 5432 path the Render worker has.
    """
    import db_http
    rows = db_http.select_all(
        "listings",
        "select=id,scraped_name,scraped_brand,scraped_category,subtype,variant,description,"
        "reading,catalog_entry_id,catalog_match_confidence,catalog_match_method&is_active=is.true&order=id")
    return [{"id": r["id"], "name": r.get("scraped_name") or "", "brand": r.get("scraped_brand"),
             "category": r.get("scraped_category"), "subtype": r.get("subtype"),
             "variant": r.get("variant"), "description": r.get("description"),
             # The listing's own reading; its category, strain and line columns are the
             # matched entry's (import_listings._overlay), so the join never reads them.
             "reading": r.get("reading"),
             "catalog_entry_id": r.get("catalog_entry_id"),
             "catalog_match_confidence": r.get("catalog_match_confidence"),
             "catalog_match_method": r.get("catalog_match_method")} for r in rows]


def write_decisions(decisions: list[Decision]) -> int:
    import psycopg2
    import psycopg2.extras
    catalog_store._load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set — --write needs a direct Postgres connection")
    # A failed call is not an answer: leave those listings' stored match alone.
    rows = [((d.entry or {}).get("id"), d.confidence if d.entry else None, d.method,
             str(d.listing["id"])) for d in decisions if d.method != "error"]
    if not rows:
        return 0
    conn = psycopg2.connect(url)
    try:
        cur = conn.cursor()
        psycopg2.extras.execute_values(
            cur,
            """
            UPDATE listings AS l SET
                catalog_entry_id         = v.entry_id::uuid,
                catalog_match_confidence = v.conf::real,
                catalog_match_method     = v.method
            FROM (VALUES %s) AS v(entry_id, conf, method, listing_id)
            WHERE l.id = v.listing_id::uuid
              -- a human's match is never overwritten by the pipeline
              AND COALESCE(l.catalog_match_method, '') <> 'manual'
            """,
            # One statement for every row: with paging, rowcount reports only the
            # last page, and the count printed is how an operator sees it landed.
            rows, page_size=len(rows),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def write_decisions_http(decisions: list[Decision], workers: int = 8) -> int:
    """write_decisions over Supabase's REST API, for a host without the 5432 path (the
    sandbox). Only a listing whose match changed is written. Each update is conditioned
    on the method this run read, so a listing matched by hand meanwhile ('manual'), or
    rewritten by another run, is left alone. Listings that get the same new values go
    in one request."""
    import db_http
    from concurrent.futures import ThreadPoolExecutor

    groups: dict[tuple, list[str]] = defaultdict(list)
    for d in decisions:
        old = d.listing.get("catalog_match_method")
        if d.method == "error" or old == "manual":
            continue
        entry = (d.entry or {}).get("id")
        conf = round(d.confidence, 4) if d.entry else None
        was = d.listing.get("catalog_match_confidence")
        same_conf = (conf is None and was is None) or \
            (conf is not None and was is not None and abs(conf - was) < 1e-3)
        if entry == d.listing.get("catalog_entry_id") and d.method == old and same_conf:
            continue
        groups[(entry, conf, d.method, old)].append(str(d.listing["id"]))

    def send(item) -> int:
        (entry, conf, method, old), ids = item
        n = 0
        guard = f"catalog_match_method=eq.{old}" if old else "catalog_match_method=is.null"
        for i in range(0, len(ids), 100):
            for attempt in range(4):
                # A dropped connection is retried (2026-10-08: one SSL EOF stopped a
                # full re-match part-way); the guard makes a repeat harmless.
                try:
                    rows = db_http.update("listings", f"id=in.({','.join(ids[i:i + 100])})&{guard}",
                                          {"catalog_entry_id": entry, "catalog_match_confidence": conf,
                                           "catalog_match_method": method})
                    break
                except db_http.DbHttpError:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
            n += len(rows)
        return n

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return sum(pool.map(send, groups.items()))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(brand: str, decisions: list[Decision], catalog: dict) -> None:
    total = len(decisions) or 1
    by = Counter(d.method for d in decisions)
    n_products = len({e.get("product_key") for e in catalog.get("entries") or []})
    print(f"\n{brand}: {len(decisions)} active listings, catalog has {n_products} products "
          f"[{catalog.get('_source', '?')}]")
    order = ["exact", "substring", "token", "jev", "jev_review", "ambiguous", "none"]
    for m in order + sorted(set(by) - set(order)):
        if by.get(m):
            print(f"  {m:11} {by[m]:>6} {by[m] / total:>7.1%}")
    trusted = sum(by.get(m, 0) for m in TRUSTED_METHODS)
    print(f"  {'TRUSTED':11} {trusted:>6} {trusted / total:>7.1%}")


def evaluate(catalog: dict, listings: list[dict], usage: jev.Usage,
             cache: AnswerCache) -> dict:
    """How well does the Jev tier gate, measured without hand labels?

    Silver labels: listings the attribute join decides. Then the holdout: ask Jev with
    that product removed from its options. The right answer is now "none", so any
    entry Jev still picks at probability >= t is a false match at threshold t —
    the number that should set AUTO. Only listings that still have options after
    the holdout count; no options is a free "none" and proves nothing.
    """
    index = CatalogIndex(catalog)
    first = resolve(catalog, listings, use_jev=True, cache=cache, usage=usage)
    silver = {str(d.listing["id"]): d.product_key for d in first if d.method == "attributes"}
    # The join skips a held-out product, so Jev decides them with the true product
    # gone; their reading stays, as Jev's options are built from it.
    labelled = [l for l in listings if str(l["id"]) in silver]
    holdout = resolve(catalog, labelled, use_jev=True,
                      cache=AnswerCache("holdout", enabled=False), usage=usage, exclude=silver)
    asked = [d for d in holdout if d.candidates > 0]

    def top_product_p(d: Decision) -> float:
        return max((p for k, p in (d.probabilities or {}).items() if k != NONE), default=0.0)

    out = {"listings": len(listings), "silver": len(labelled), "holdout_asked": len(asked),
           "first_pass": dict(Counter(d.method for d in first)), "false_match_at": {}}
    for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        out["false_match_at"][t] = sum(1 for d in asked if top_product_p(d) >= t) / max(1, len(asked))
    out["examples"] = [(d.listing.get("name"), index.products[silver[str(d.listing["id"])]].title,
                        round(top_product_p(d), 2),
                        max((k for k in (d.probabilities or {}) if k != NONE),
                            key=lambda k: d.probabilities[k], default=None))
                       for d in sorted(asked, key=top_product_p, reverse=True)[:8]]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Match listings to brand catalogs")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand", help="One brand, as written in listings")
    g.add_argument("--all", action="store_true", help="Every brand that has a catalog")
    ap.add_argument("--jev", action="store_true", help="Resolve non-exact listings with Jev")
    ap.add_argument("--write", action="store_true",
                    help="Persist catalog_entry_id/confidence/method (needs DATABASE_URL)")
    ap.add_argument("--eval", action="store_true", help="Measure Jev gating on silver labels")
    ap.add_argument("--source", choices=["auto", "db", "file"], default="auto",
                    help="Where catalogs come from (default: DB when reachable)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore cached Jev answers")
    ap.add_argument("--via-http", action="store_true",
                    help="--write over Supabase's REST API instead of DATABASE_URL")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--misses", action="store_true", help="Print unresolved listings")
    ap.add_argument("--sample", type=int, default=0, help="Print N decisions to hand-check")
    ap.add_argument("--json", help="Write every decision to this file")
    args = ap.parse_args()

    if (args.jev or args.eval) and not jev.available():
        sys.exit("No OPENROUTER_API_KEY — the Jev tier needs it (or drop --jev)")

    catalogs = catalog_store.load_all(args.source)
    if args.brand:
        cat = catalog_store.for_brand(catalogs, args.brand)
        if not cat:
            sys.exit(f"No catalog for {args.brand!r}. Have: "
                     + ", ".join(c['brand_name'] for c in catalogs.values()))
        catalogs = {catalog_store.brand_key(args.brand): cat}

    all_listings = fetch_listings()
    by_brand: dict[str, list[dict]] = defaultdict(list)
    for l in all_listings:
        by_brand[catalog_store.brand_key(l.get("brand"))].append(l)

    usage = jev.Usage()
    everything: list[Decision] = []
    dump = []
    for key, cat in sorted(catalogs.items()):
        listings = by_brand.get(key, [])
        if not listings:
            print(f"\n{cat['brand_name']}: no active listings")
            continue
        if args.eval:
            cache = AnswerCache(cat.get("brand_slug") or key, enabled=not args.no_cache)
            res = evaluate(cat, listings, usage, cache)
            print(f"\n{cat['brand_name']}: {res['listings']} listings, first pass {res['first_pass']}")
            print(f"  silver labels (decided by the attribute join): {res['silver']}")
            print(f"  holdout — true product removed, {res['holdout_asked']} still had candidates:")
            for t, r in res["false_match_at"].items():
                print(f"    would match a WRONG product at p>={t:.1f}: {r:.1%}")
            print("  highest-probability wrong picks:")
            for name, truth, p, wrong in res["examples"]:
                print(f"    {p:.2f}  {name[:56]:56} true={truth!r} picked={wrong!r}")
            continue
        cache = AnswerCache(cat.get("brand_slug") or key, enabled=not args.no_cache)
        decisions = resolve(cat, listings, use_jev=args.jev, cache=cache, usage=usage,
                            workers=args.workers)
        report(cat["brand_name"], decisions, cat)
        everything.extend(decisions)
        index = CatalogIndex(cat)
        for d in decisions:
            p = index.products.get(d.product_key) if d.product_key else None
            dump.append({"listing_id": d.listing["id"], "brand": cat["brand_name"],
                         "name": d.listing.get("name"), "category": d.listing.get("category"),
                         "variant": d.listing.get("variant"), "method": d.method,
                         "confidence": d.confidence, "product": p.title if p else None,
                         "entry_variant": (d.entry or {}).get("variant"),
                         "candidates": d.candidates, "probabilities": d.probabilities})
        if args.sample:
            step = max(1, len(decisions) // args.sample)
            print(f"  --- {args.sample} decisions to hand-check ---")
            for d in decisions[::step][:args.sample]:
                p = index.products.get(d.product_key) if d.product_key else None
                print(f"  [{d.method} {d.confidence:.2f}] {d.listing.get('name', '')[:60]}")
                print(f"      -> {p.title if p else '—'}  {(d.entry or {}).get('variant') or ''}")
        if args.misses:
            print("  --- unresolved ---")
            for d in decisions:
                if d.method not in TRUSTED_METHODS:
                    print(f"  [{d.method:10} {d.confidence:.2f} c={d.candidates:>2}] "
                          f"{d.listing.get('category') or '?':11} {d.listing.get('name', '')[:70]}")

    if usage.requests or usage.failures:
        print("\n" + usage.summary())
    if args.json:
        Path(args.json).write_text(json.dumps(dump, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {len(dump)} decisions to {args.json}")
    if args.write and everything:
        if args.via_http:
            n = write_decisions_http(everything, workers=args.workers)
            print(f"wrote match columns on {n} listings (the ones whose match changed)")
        else:
            n = write_decisions(everything)
            print(f"wrote match columns on {n} listings")


if __name__ == "__main__":
    main()
