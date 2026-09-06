"""
attributes.py — per-category identity attributes, kept out of the shared columns.

`strain` was doing four jobs: cultivar for flower and prerolls, flavour for
beverages, scent for topicals, colour for merch. Each was ruled individually and
they are incoherent together — `strain_split` in the audit cannot mean one thing
while the column means four.

This is where the category-specific parts go, so `strain` can shrink back to
meaning cultivar. Stored in listings.attributes (jsonb), one shape per category,
validated here rather than in the database: the shapes are still moving, and DDL
per category would freeze them before they have settled.

Measured against 16,031 live listings, the merch vocabulary is closed and small —
548 rows carry 28 distinct values, cleanly splitting into 19 colours and 9
flavours. That is a vocabulary, not a long tail, which is why it is curated here
rather than asked of a model.

  merch      colour, flavour   what separates otherwise identical accessories
  topical    scent             see the note below — topicals need more than this

NOT YET MODELLED — topical
--------------------------
`strain` on topicals holds three different things at once, and the top values make
that plain: Revive (22), Restore (15), Rescue (15), Releaf (12), Relief (5) are
Ayrloom and Papa & Barkley PRODUCT LINES; Lavender, Eucalyptus Sage and Blue Tansy
Rose are scents; Balm, Pain Balm and Relief Balm are form words that belong to
subtype. Splitting those needs product_lines.json entries for the brands first,
otherwise moving them here just relocates the confusion. Left alone deliberately.
"""

from __future__ import annotations

import re

# Colours seen across the fleet's merch, plus the compounds that appear in it.
# Order here does not matter — matching is longest-first and non-overlapping, so
# "Rose Gold" is claimed by the compound rather than by "gold" or "rose" alone.
# That mattered: five merch products were merging into plain Gold before this.
_MERCH_COLOURS = [
    "rose gold", "gun metal", "unbleached", "assorted", "rainbow", "natural",
    "purple", "silver", "yellow", "orange", "clear", "black", "green", "white",
    "onyx", "gold", "rose", "pink", "blue", "teal", "red",
]

# Flavours seen on wraps and papers. Distinct from colour: "Blueberry" wraps are
# flavoured, "Blue" cones are coloured, and one field for both would claim those
# are the same kind of difference.
_MERCH_FLAVOURS = [
    "watermelon", "strawberry", "blueberry", "vanilla", "banana", "cherry",
    "grape", "mango", "peach",
]


def _match_all(name: str, vocabulary: list[str]) -> str | None:
    """Every term the name carries, longest-first and non-overlapping.

    Two properties matter, and both came from real merges in the live data:

      longest-first    "Rose Gold" is one colour, not "gold" preceded by noise
      non-overlapping  having matched "rose gold", neither "gold" nor "rose" may
                       also claim those characters
      all matches      a Black/White tee is not a Black tee; keeping only the
                       first match merged genuinely two-tone items into one

    Returned in the order they appear in the name, joined with "/", so
    "Black and White" and "White and Black" do not become different products.
    """
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, str]] = []
    for term in sorted(vocabulary, key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(term)}\b", name or "", re.I):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), term.title()))
            break
    if not found:
        return None
    return "/".join(t for _, t in sorted(found))


def merch_attributes(name: str) -> dict:
    """{colour?, flavour?} for an accessory. Empty when the name carries neither."""
    out = {}
    colour = _match_all(name, _MERCH_COLOURS)
    flavour = _match_all(name, _MERCH_FLAVOURS)
    if colour:
        out["colour"] = colour
    if flavour:
        out["flavour"] = flavour
    return out


# Category -> the function that reads its attributes from a product name.
# Adding a category here is the whole extension point; nothing else needs to know.
EXTRACTORS = {
    "merch": merch_attributes,
}


def for_category(category: str | None, name: str) -> dict:
    """Attributes for a listing, or {} for a category that has none modelled yet."""
    fn = EXTRACTORS.get((category or "").strip().lower())
    return fn(name or "") if fn else {}


def identity_key(attributes: dict | None) -> tuple:
    """A stable, hashable form for grouping.

    Sorted so two rows with the same attributes in a different key order land in
    the same product, which matters because jsonb does not preserve insertion
    order and the products view groups on this.
    """
    if not attributes:
        return ()
    return tuple(sorted((k, str(v)) for k, v in attributes.items() if v is not None))
