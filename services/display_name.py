# services/display_name.py
"""What a listing should be *called* on screen.

Scraped names are written for a store's own catalogue page, not for ours. They
repeat the brand, carry the potency, the weight, the pack count, the format and
sometimes the scraper's own debris:

    'Apricot Punch -Indica- 85.45% THC | 0.5g Classic Surf All-In-One (Vape) | Bloom  -sss11 front'

Enrichment already pulled the useful parts out of that string into `strain`,
`product_line`, `subtype`, `classification` and `variant`, and the cards render
brand, category and variant in their own slots. So the name only has to carry
the product's identity, and for ~85% of listings the enriched fields already
hold it -- `compose` just reads them back.

The rest are mostly merch, topicals and tinctures, where the raw name really is
the identity ('Relief Balm', 'Jet Pocket Lighter') wrapped in the same noise.
`clean` strips the noise rather than inventing a name, because there is nothing
better to fall back to and the raw string is still mostly right.

The stripping is done *inside* each segment rather than by discarding segments
that look noisy: 'Organic Medium Dog CBD Oil' mentions a cannabinoid and
'Bubble Hash' ends in a format word, but both are the product's actual name.
Only what is left over decides whether a segment carried anything.

Deterministic on purpose: this runs on every listing in every response, so it
cannot be a model call, and a rule that misfires can be read off the input.
"""
from __future__ import annotations

import re
from typing import Optional

# Segment separators as stores actually write them: pipes, spaced dashes, and
# the unspaced trailing dash in 'Grön- Milk Chocolate Mini Bar- Daytime'.
_SEGMENT_SPLIT = re.compile(r"\s*\|\s*|\s+[-–—]\s+|(?<=\w)[-–—]\s+")

# Scraper debris pinned to the end: '-ii3 front', '-AC4', '-yyy7 front', '-JJ9 BACK'.
_TRAILING_CODE = re.compile(r"[-–—]\s*[A-Za-z]{1,5}\d{1,3}\s*(?:front|back)?\s*$", re.I)

_CANNABINOID = r"THC|CBD|CBN|CBG|CBC|THCV|THCA|TAC"

# Noise that appears *within* an otherwise meaningful segment. Order matters:
# the compound potency patterns must run before the bare measure pattern, or
# '150MG THC : 450MG CBD' loses its numbers and leaves stray cannabinoid words.
_INLINE_NOISE = [
    # '85.45% THC', '-31% THC', '13.40%'
    re.compile(rf"[-–—]?\s*\d+(?:\.\d+)?\s*%\s*(?:{_CANNABINOID})?", re.I),
    # '864mg TAC THC:CBG 150mg:600mg', '150MG THC : 450MG CBD', '1:1 THC/CBD'
    re.compile(
        rf"\b\d+(?:\.\d+)?\s*(?:mg|g)?\s*(?:[:x×/]\s*\d+(?:\.\d+)?\s*(?:mg|g)?\s*)*"
        rf"(?:{_CANNABINOID})\b(?:\s*[:/]\s*(?:{_CANNABINOID})\b)*",
        re.I,
    ),
    # 'THC : THCV : CBG' with no numbers at all
    re.compile(rf"\b(?:{_CANNABINOID})\b(?:\s*[:/]\s*(?:{_CANNABINOID})\b)+", re.I),
    # '3.5g', '100MG', '15ml', '1 oz'
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:g|mg|ml|oz|gram|grams)\b\.?", re.I),
    # '20pk', '10 PCS', '6 Pack', '4pk', 'x 2pk'
    re.compile(r"\b(?:x\s*)?\d+\s*(?:pk|pack|packs|pc|pcs|ct|count)\b", re.I),
    # A bare ratio the card cannot use: '1:1:1 Chews', '3:1'
    re.compile(r"\b\d+(?::\d+)+\b"),
    # A bare classification the card shows in its own slot: '-Indica-', 'Sativa/Hybrid'
    re.compile(r"\b(?:indica|sativa|hybrid)(?:\s*/\s*(?:indica|sativa|hybrid))*\b", re.I),
]

# Words that only describe the format, which the card already shows as its
# category and subtype. A segment made *only* of these carries nothing -- but a
# format word inside a longer name ('Bubble Hash', 'Stick Battery') is the noun.
_FORMAT_WORDS = {
    "aio", "allinone", "cart", "cartridge", "concentrate", "cone", "cones",
    "disposable", "drink", "edible", "edibles", "flower", "gummies", "gummy",
    "preroll", "prerolls", "smoke", "vape", "vapes",
}

# Inside parentheses a format word is always a restatement of the category:
# '(Topical)', '(Vape Pen)', '(Edibles)'. Outside them the same word is often the
# product's own noun ('Bubble Hash', 'Releaf Balm'), so this stays scoped here.
_PARENTHETICAL_FORMAT = _FORMAT_WORDS | {
    "balm", "beverage", "chocolate", "cream", "hash", "lotion", "oil", "pen",
    "roll", "rolls", "sublingual", "tincture", "tinctures", "topical", "topicals",
}

_FILLER = {"the", "a", "an", "and", "with", "by", "x"}

# Sizes stores write without a unit: '1 1/4' papers, '510' thread.
_BARE_NUMBER = re.compile(r"^[\d\s./x×+:]+$")


def _norm(value: str) -> str:
    """Casefold, fold '&'/'+' to 'and', drop punctuation -- so 'Head & Heal',
    'Head and Heal' and 'head-heal' all compare equal."""
    folded = re.sub(r"\s*[&+]\s*", " and ", value.lower())
    return re.sub(r"[^a-z0-9]+", "", folded)


def _words(value: str) -> list[str]:
    """Whitespace only -- 'Black/Yellow' is one word on the card, not two."""
    return [w for w in value.split() if w]


def _tokens(value: str) -> list[str]:
    """Words split further on '/' for testing meaning, never for rebuilding text."""
    return [w for w in re.split(r"[\s/]+", value.strip()) if w]


def _strip_inline_noise(segment: str) -> str:
    """Remove potency, size, pack count and classification from inside a segment."""
    text = segment
    for pattern in _INLINE_NOISE:
        text = pattern.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip().strip("-–—|,:·/").strip()


def _carries_meaning(segment: str, brand_key: str) -> bool:
    """Is there anything left here the card is not already showing?"""
    if not segment:
        return False
    key = _norm(segment)
    if not key or (brand_key and key == brand_key):
        return False
    if _BARE_NUMBER.match(segment):
        return False
    return any(
        tok and tok not in _FILLER and tok not in _FORMAT_WORDS and not _BARE_NUMBER.match(w)
        for w, tok in ((w, _norm(w)) for w in _tokens(segment))
    )


def _drop_brand(text: str, brand_key: str) -> str:
    """Stores put the brand on either end: 'MK Lighter Cultivate Series Jet Pocket
    Lighter', '15ml (Topical) Papa & Barkley'. Drop it from whichever end it is on,
    never both, and never if it is the whole name."""
    if not brand_key:
        return text
    words = _words(text)
    for take in range(min(len(words), 4), 0, -1):
        if _norm(" ".join(words[:take])) == brand_key and words[take:]:
            return " ".join(words[take:])
        if _norm(" ".join(words[len(words) - take:])) == brand_key and words[: len(words) - take]:
            return " ".join(words[: len(words) - take])
    return text


def _tidy(segment: str, brand_key: str) -> str:
    text = _strip_inline_noise(segment)

    # '(Vape)' / '(Topical)' / '(100mg)' restate what the card already shows,
    # wherever in the segment the store put them.
    def _drop_empty_parens(match: re.Match) -> str:
        inner = _strip_inline_noise(match.group(1))
        if not _carries_meaning(inner, brand_key):
            return " "
        if all(_norm(w) in _PARENTHETICAL_FORMAT for w in _tokens(inner)):
            return " "
        return match.group(0)

    text = re.sub(r"\s*\(([^)]*)\)", _drop_empty_parens, text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = _drop_brand(text, brand_key)

    # Dropping the brand can strand the conjunction that joined it on:
    # 'Old Pal x Babish' -> 'x Babish'.
    words = _words(text)
    while words and _norm(words[0]) in _FILLER:
        words.pop(0)
    text = " ".join(words) if words else text

    text = text.strip().strip("-–—|,:·/").strip()

    # SHOUTED names read as noise beside everything else on the card.
    if text.upper() == text and re.search(r"[A-Z]{4,}", text):
        text = text.title()

    return text


def clean(raw: Optional[str], brand: Optional[str] = None) -> Optional[str]:
    """Strip a scraped name back to the product's identity, or None if nothing survives.

    Keeps at most the first two surviving segments: past that a name is
    restating the catalogue row rather than naming the product.
    """
    if not raw or not raw.strip():
        return None

    brand_key = _norm(brand or "")

    text = raw.strip()
    previous = None
    while previous != text:
        previous = text
        text = _TRAILING_CODE.sub("", text).strip()

    kept: list[str] = []
    seen: set[str] = set()
    for segment in _SEGMENT_SPLIT.split(text):
        if not segment or not segment.strip():
            continue
        tidied = _tidy(segment, brand_key)
        if not _carries_meaning(tidied, brand_key):
            continue
        if _norm(tidied) in seen:
            continue
        seen.add(_norm(tidied))
        kept.append(tidied)
        if len(kept) == 2:
            break

    if not kept:
        return None
    return " · ".join(kept)


def compose(
    *,
    scraped_name: Optional[str] = None,
    brand: Optional[str] = None,
    product_line: Optional[str] = None,
    strain: Optional[str] = None,
    subtype: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """The name to show for a listing, best source first.

    Enriched fields win because they are the parsed truth about the product; a
    cleaned raw name is the fallback for rows enrichment found no strain in
    (merch, topicals, most tinctures); the category is the last resort so a card
    never renders blank.
    """
    line = (product_line or "").strip()
    strain_name = (strain or "").strip()

    if strain_name:
        # 'Flyers' + 'Fast Lane' -> 'Flyers Fast Lane', but never 'Flyers Flyers Blend'.
        if line and _norm(line) not in _norm(strain_name):
            return f"{line} {strain_name}"
        return strain_name

    cleaned = clean(scraped_name, brand)
    if cleaned:
        return cleaned

    if line:
        return line
    if subtype and subtype.strip():
        return subtype.strip().title()
    if category and category.strip():
        return category.strip().title()
    return "—"
