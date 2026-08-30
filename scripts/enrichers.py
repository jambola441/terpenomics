"""
enrichers.py — one owner per category, instead of 105 category checks in one pass.

`enrich.py` grew a category-shaped lump every time a category needed something the
shared fields could not express: merch alone accounts for 44 of the 105 places the
old pipeline names a specific category. Those checks are not incidental complexity
— each category genuinely has different attributes — so the fix is to give each
one somewhere to live rather than to keep threading them through a generic pass.

An enricher owns, for its category:

  subtypes      the rail its answers are clamped to
  tokens        the name patterns that settle a subtype without asking anything
  variant()     how a size or dose is written for this kind of product
  attributes()  the category-specific identity fields
  needs_model   whether a model is required at all

That last one is the point, not a detail. Merch identity is entirely a function of
the product name — form factor, size, pack, colour, flavour — so MerchEnricher
declares `needs_model = False` and its 1,300 listings never reach the model. Every
category that reaches the same state stops costing anything.

Registering a category here is the whole extension point. Nothing in enrich.py
needs to learn about it.
"""

from __future__ import annotations

import re
from collections import OrderedDict

import attributes as attribute_registry
from canonical import find_product_line


class CategoryEnricher:
    """Base: a category with nothing special, handled by the shared pipeline."""

    category: str = ""
    subtypes: tuple[str, ...] = ("other",)
    default_subtype: str | None = None
    tokens: OrderedDict = OrderedDict()
    # Whether this category's fields need a model. False means the pipeline can
    # answer it from the name alone, and the rows are skipped entirely.
    needs_model: bool = True

    def hint_subtype(self, name: str) -> str | None:
        """Subtype from the name alone, or None to fall back to the default.

        The NAME only, deliberately. 376 of 1,300 live merch names carry no form
        word, and falling back to the description recovers a subtype for 173 of
        them — but a sample of 25 was wrong roughly 10 times, because merch
        descriptions are sales copy that names adjacent gear constantly: "Hemp
        Wick" reads as paper, "Puck Press" as pipe, "Original Tips" as paper, a
        Dr.Dabber vape pen as dab-tool. Leaving those at the category default is
        a smaller error than confidently mis-subtyping them, so the gap is closed
        by adding name tokens, not by reading prose.
        """
        return self.token_subtype(name) or self.default_subtype

    def token_subtype(self, name: str) -> str | None:
        """The subtype a name token settles, or None when none fires.

        Kept separate from hint_subtype because "no token fired" and "the default"
        are different facts: a caller holding a better answer (the model's, already
        stored on the row) must be able to keep it rather than have it overwritten
        by the default. backfill_merch_identity.py depends on that distinction.
        """
        for subtype, pattern in self.tokens.items():
            if pattern.search(name or ""):
                return subtype
        return None

    def subtype(self, name: str, current: str | None = None) -> str | None:
        """The subtype to store: a token if one fires, else whatever is already
        there if it is on this category's rail, else the default. `current` is how
        a model-derived answer for a name the tokens do not cover survives a
        re-enrichment — 376 of 1,300 live merch names are in exactly that state."""
        token = self.token_subtype(name)
        if token:
            return token
        if current and current in self.subtypes:
            return current
        return self.default_subtype

    def variant(self, name: str, scraped: str | None) -> str | None:
        """How this category writes a size or dose. None to leave the scraped value."""
        return None

    def attributes(self, name: str) -> dict:
        return attribute_registry.for_category(self.category, name)

    def strain(self, name: str, model_answer: str | None) -> str | None:
        """The cultivar. Categories without one return None so `strain` keeps a
        single meaning across the table."""
        return model_answer

    def product_line(self, brand: str, name: str, model_answer: str | None) -> str | None:
        curated = find_product_line(brand or "", name or "")
        return curated or model_answer


class MerchEnricher(CategoryEnricher):
    """Accessories: no cultivar, no dose, and nothing a model can see better.

    Everything that distinguishes one accessory from another is written in its
    name — a cone is not a grinder, 20pk is not 50pk, pink is not purple. Before
    this had an owner, merch had a single subtype and empty strain and variant, so
    the products view grouped 1,514 listings into 223 rows on brand alone.
    """

    category = "merch"
    needs_model = False
    default_subtype = "merch"
    subtypes = ("gift-card", "filter-tip", "roller", "ashtray", "cone", "paper",
                "wrap", "grinder", "tray", "bong", "pipe", "dab-tool", "charger",
                "battery", "lighter", "storage", "apparel", "cleaning", "scale",
                "merch")

    # Order is load-bearing, first match wins: bong before pipe because a "water
    # pipe" is a bong, charger before battery because a "510 Thread USB Charger"
    # is not a battery, ashtray before tray.
    tokens = OrderedDict([
        ("gift-card",  re.compile(r"\bgift\s*cards?\b", re.I)),
        ("filter-tip", re.compile(r"\bfilter\s*tips?\b|\btips?\s*tin\b|\bcrutch", re.I)),
        ("roller",     re.compile(r"\broller\b|\brolling\s*machine\b", re.I)),
        ("ashtray",    re.compile(r"\bash\s*trays?\b", re.I)),
        ("cone",       re.compile(r"\bcones?\b", re.I)),
        ("paper",      re.compile(r"\b(rolling\s+)?papers?\b|\bbooklet\b", re.I)),
        ("wrap",       re.compile(r"\bwraps?\b", re.I)),
        ("grinder",    re.compile(r"\bgrinders?\b", re.I)),
        ("tray",       re.compile(r"\btrays?\b", re.I)),
        ("bong",       re.compile(r"\bbongs?\b|\bwater\s*pipe\b|\brigs?\b|\bbubbler\b", re.I)),
        ("pipe",       re.compile(r"\bpipes?\b|\bspoon\b|\bchillum\b|\bone.?hitter\b", re.I)),
        ("dab-tool",   re.compile(r"\bdabber\b|\bdab\s+tool\b|\bbanger\b|\bcarb\s*cap\b|\bnails?\b", re.I)),
        ("charger",    re.compile(r"\bchargers?\b", re.I)),
        ("battery",    re.compile(r"\bbatter(?:y|ies)\b|\b510\s*thread\b", re.I)),
        ("lighter",    re.compile(r"\blighters?\b|\btorch\b", re.I)),
        ("storage",    re.compile(r"\b(jars?|stash|containers?|pouch|tins?)\b", re.I)),
        ("apparel",    re.compile(r"\b(t-?shirts?|hoodie|hats?|caps?|socks|tee)\b", re.I)),
        ("cleaning",   re.compile(r"\bclean(?:er|ing)\b|\bisopropyl\b|\bwipes?\b", re.I)),
        ("scale",      re.compile(r"\bscales?\b", re.I)),
    ])

    # Pack count is the purchasable unit and size is the spec, and accessories need
    # both: cones differ by pack at one size ("Pink 98mm Cones 20pk" vs "50pk"),
    # papers differ by width at one count, since a brand ships its whole range at
    # 33ct. Emitting both avoids a per-subtype rule.
    _pack = re.compile(r"\b(\d+)\s*(pk|pack|ct|count|leaves)\b", re.I)
    # Width normalised because one brand writes it several ways in one menu — RAW
    # has "KS Slim", "King Size Slim" and "Slim KS" for the same paper, which split
    # one product three ways. "Slim" is a thinness, not a width, so it is not a
    # key; "KS Wide" is a genuinely different width, so it is.
    _widths = [
        (re.compile(r"\bks\s*wide\b|\bking\s*size\s*wide\b", re.I), "ks wide"),
        (re.compile(r"\bking\s*size\b|\bkingsize\b|\bks\b", re.I),   "king size"),
        (re.compile(r"\b1\s*1/4\b|\b1\.25\b", re.I),                 "1 1/4"),
        (re.compile(r"\b1\s*1/2\b|\b1\.5\b", re.I),                  "1 1/2"),
        (re.compile(r"\bsingle\s*wide\b", re.I),                     "single wide"),
        (re.compile(r"\b100s\b", re.I),                              "100s"),
    ]
    _dim = re.compile(
        r'\b(\d+\s*mm)\b|\b(\d+(?:\.\d+)?\s*(?:inch|in))\b|(\d+(?:\.\d+)?\s*(?:"|”))',
        re.I)
    # A booklet sold with filter tips is a different SKU at a different price and
    # is otherwise named identically to the plain one.
    _tips = re.compile(
        r"w/\s*(?:pre[\s-]*rolled\s+)?tips?\b|\+\s*tips?\b|\bwith\s+tips?\b", re.I)

    def _size(self, name: str) -> str:
        for pattern, canonical in self._widths:
            if pattern.search(name or ""):
                return canonical
        m = self._dim.search(name or "")
        if not m:
            return ""
        return re.sub(r"\s+", " ", next(g for g in m.groups() if g)).strip().lower()

    def _pack_of(self, name: str) -> str:
        m = self._pack.search(name or "")
        if not m:
            return ""
        n, unit = m.group(1), m.group(2).lower()
        # leaves, count and ct all mean the same thing; keeping them apart would
        # split one product across three spellings.
        return f"{n}pk" if unit in ("pk", "pack") else f"{n}ct"

    def variant(self, name: str, scraped: str | None) -> str | None:
        parts = [self._size(name), self._pack_of(name)]
        if self._tips.search(name or ""):
            parts.append("w/tips")
        return " ".join(p for p in parts if p) or None

    def strain(self, name: str, model_answer: str | None) -> str | None:
        # Accessories have no cultivar. Colour and flavour, which is what actually
        # separates them, are attributes — see scripts/attributes.py.
        return None


REGISTRY: dict[str, CategoryEnricher] = {
    e.category: e for e in (MerchEnricher(),)
}

_DEFAULT = CategoryEnricher()


def for_category(category: str | None) -> CategoryEnricher:
    """The owner for a category, or a pass-through for one with no owner yet."""
    return REGISTRY.get((category or "").strip().lower(), _DEFAULT)


def skips_model(category: str | None) -> bool:
    """True when a category can be answered from the name alone."""
    return not for_category(category).needs_model
