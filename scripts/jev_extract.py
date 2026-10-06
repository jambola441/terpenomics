"""
jev_extract.py — A listing's strain and product line, picked by Jev from its name.

Jev cannot write text, so it cannot extract a strain the way an LLM does. But it does
not have to: in every gold case whose strain is set, the strain is already a phrase of
the listing's name (263 of 263). So code cuts the name into candidate phrases — the
stretches between separators, sizes, potencies and ratios, and their sub-phrases — and
Jev picks which one is the strain and which one, if any, is the product line, with
"none" offered first. Extraction becomes a choice, which is the question Jev answers.

Measured on the gold suites (evals/enrich/README.md): the right strain is among the
phrases for 99.6% of rows (6.7 phrases per row); at p >= 0.90 Jev's pick is right on
99.4%. A word set in quotes is shown as quoted, because stores mark product lines that
way ('Bliss', "Balance") — that alone took lines from 13/20 to 20/20.

The caller decides what to trust (enrich.py): a strain at JEV_TEXT_MIN (0.90), a named
line at JEV_LINE_MIN (0.80), "no line" at a lower bar (a missing line is cheaper than a
wrong one — the catalog bootstrap folds line-less listings back in). Anything less, or
the same phrase picked as both strain and line, goes to the LLM — which is then shown
the rows Jev settled, because without them it read the leftover hard rows worse.

    import jev_extract
    answers = jev_extract.extract([(row, category, subtype), ...])
    answers[0].strain, answers[0].p_strain, answers[0].line, answers[0].p_line
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical  # noqa: E402
import jev  # noqa: E402

# Bump when a question, the phrase rules or the option text change: enrich.py stamps
# cached answers with it, so answers to an older question are re-asked.
QUESTION_VERSION = 2

_NUM = r"(?:\d+(?:\.\d+)?|\.\d+)"
_CANNABINOID = r"(?:thca?|cbd|cbn|cbg|cbc|thcv|d8|d9|delta[\s-]?[89])"
# Stretches of a name that are never part of a strain. Each becomes a phrase boundary.
_CUT_RE = re.compile("|".join(f"(?:{c})" for c in (
    rf"{_NUM}\s*%\s*(?:{_CANNABINOID}\b)?",                         # 23.75% THC
    rf"\b{_CANNABINOID}\s*:?\s*{_NUM}\s*%",                          # THC 37.4%
    r"\b\d+(?:\.\d+)?(?:\s*:\s*\d+(?:\.\d+)?)+\b",                   # 1:1, 10:2:2
    rf"\b{_CANNABINOID}(?:\s*:\s*{_CANNABINOID})+\b",                # THC:CBD:CBN
    r"\b\d+\s*/\s*\d+\s*(?:oz|ounce)?\b",                            # 1/8, 1/8oz
    rf"{_NUM}\s*(?:mg|milligrams?|g|grams?|gr|oz|ounces?|ml|fl\.?\s*oz)\b"
    rf"(?:\s*{_CANNABINOID}\b)?",                                    # 3.5g, 100mg THC
    r"\b\d+\s*[-\s]?(?:pk|pack|packs|ct|count|pcs|pieces|pc|piece)\b",  # 10pk, 2 count
    rf"\b\d+\s*x(?=\s*{_NUM}\s*(?:g|mg)\b)|\bx\s*{_NUM}\s*(?:g|mg)\b",    # 5 x .6g, not "x 24k Gold"
    rf"\b{_CANNABINOID}\b(?=\s*[|\-–—()\[\],]|\s*$)",                # a bare trailing THC
)), re.I)
_SEPARATOR_RE = re.compile(
    r"\s+[-–—]\s+|[|()\[\]{},/;]|\s-|-\s|[\"“”]|''|(?<!\w)'|'(?!\w)|\s+:\s+|:\s|\s+\+\s+")
# What follows "for" is what the product is for, never part of its name: 1906's "Genius
# for Brain-Power" is Genius and "BOOST For Everything" is BOOST. No phrase crosses it.
_FOR_RE = re.compile(r"\s+(?i:for)\s+(?=[A-Z])")
_QUOTED_RE = re.compile(r"(?:''|\"|“|(?<!\w)')\s*([^'\"“”]{1,40}?)\s*(?:''|\"|”|'(?!\w))")
_EDGE = " -–—_.,:;!*#'\"&+"
# Words that alone are never a strain: a phrase is only offered whole, never cut down
# to start or end on one of these — "Sugar Cookie" survives, "Infused Flower" does not.
FORMAT_WORDS = frozenset("""
pre-roll pre-rolls preroll prerolls pre roll pre rolls joint joints blunt blunts infused
cart carts cartridge cartridges vape vapes pen pens disposable disposables aio all-in-one
all in one pod pods battery kit starter flower flowers smalls small buds bud ground
pre-ground preground shake gummy gummies chew chews edible edibles chocolate chocolates
bar bars beverage beverages drink drinks soda sodas seltzer seltzers shot shots tablet
tablets capsule capsules tincture tinctures drops oil oils balm balms lotion topical
topicals cream salve roll-on diamond diamonds rosin resin live cured badder budder sugar
sauce hash rso concentrate concentrates wax shatter crumble jar tin can cans pack packs
multipack variety the and with w/ of thc cbd cbn cbg thca hemp spectrum cone cones tips
palm unit rechargeable rechargable vaporizer vaporizers unscented unflavored dablicator
applicator feco scrub bomb bath pill pills
""".split())
MAX_WORDS = 6
MAX_PHRASES = 60
# Words that end a phrase by naming the category's own format, so a strain option ends
# before them: an edible's "Cookies N Cream Cones" is Cookies N Cream, a drink's "Black
# Cherry Sparkling Water" is Black Cherry. Per category, because elsewhere they are part
# of a strain: a pre-roll called "Grape Soda", a flower called "Sugar Cookie".
FORMAT_TAILS = {
    "preroll": "pre-roll pre-rolls preroll prerolls roll rolls joint joints blunt blunts cone cones "
               "infused mini minis",
    "vaporizers": "cart carts cartridge cartridges vape vapes pod pods disposable disposables aio "
                  "all-in-one pen pens battery",
    "flower": "flower flowers smalls bud buds ground pre-ground preground shake",
    "concentrate": "badder budder sugar sauce rosin resin wax shatter crumble diamonds rso "
                   "concentrate concentrates",
    "edible": "gummy gummies chew chews chocolate chocolates bar bars bites mint mints tablet "
              "tablets capsule capsules drops beverage beverages drink drinks soda sodas seltzer "
              "seltzers sparkling-water shot shots cone cones lozenge lozenges syrup",
    "tinctures": "tincture tinctures drops oil oils",
    "topical": "balm balms lotion lotions cream creams salve salves roll-on topical topicals rub "
               "spray soak stick sticks scrub oil",
}
FORMAT_TAILS = {cat: [tuple(w.split("-")) if w == "sparkling-water" else (w,) for w in words.split()]
                for cat, words in FORMAT_TAILS.items()}
# A topical's format also leads its name: Ayrloom's "Balm Revive" is Revive.
FORMAT_HEADS = {"topical": frozenset("balm lotion cream salve scrub stick oil soak spray rub".split())}

STRAIN_QUESTION = (
    "Which of these is this product's strain or flavor: the name that tells it apart from "
    "the brand's other products? A flavor counts as the strain for edibles, drinks, vapes "
    "and topicals, and a topical's scent or blend name counts too. It is never the brand, "
    "a product line or collection name, a format (pre-roll, cart, gummies, flower), a size "
    "or a potency. Choose the complete name, keeping version numbers like 2.0. A phrase "
    "that only restates the product's own format (\"Milk Chocolate\" on a chocolate bar) is "
    "not the strain; if nothing else is left, Sativa, Indica or Hybrid is. Choose none if "
    "the strain is not one of these.")
LINE_QUESTION = (
    "Which of these is a product line: a name the brand uses for a family of its products "
    "(like Releaf, Noir, UP, Night Cap, Flyers, Big Bang), written in this product's name? "
    "A word set in quotes in the name ('Bliss', \"Balance\") is usually the line. It is not "
    "the strain or flavor, the brand or part of the brand's name, a store's own label, a "
    "format or a size. Choose none if the name has no product line.")


# Lineage often arrives glued on with hyphens ("Heir Headz-Hybrid-"): split it off as a
# phrase of its own, where it stays available as the strain of last resort.
_LINEAGE_RE = re.compile(r"-?\b(sativa|indica|hybrid)\b-?", re.I)


def _segments(name: str) -> list[str]:
    text = _LINEAGE_RE.sub(r" | \1 | ", name or "")
    text = _CUT_RE.sub(" | ", text)
    out = []
    for part in _SEPARATOR_RE.split(text):
        part = re.sub(r"\s+", " ", part).strip(_EDGE + " ")
        if part:
            out.append(part)
    return out


def _bare(word: str) -> str:
    return word.lower().strip(_EDGE)


def _all_noise(words: list[str]) -> bool:
    return all(_bare(w) in FORMAT_WORDS or not re.search(r"[a-z]", w, re.I) for w in words)


def phrases(name: str, brand: str | None = "") -> list[str]:
    """The phrases of `name` that could be its strain or line, best first.

    Every stretch between separators is offered whole — a strain may contain a format
    word ("Sugar Cookie") or the brand's name ("Lemon Candy Runtz") — then its
    sub-phrases that neither start nor end on a format word, then neighbouring
    stretches joined. The brand alone is never offered.
    """
    brand_key = (brand or "").strip().lower()
    brand_words = {_bare(w) for w in brand_key.split()} - {""}
    out: list[str] = []
    seen: set[str] = set()

    def edge_ok(word: str) -> bool:
        w = _bare(word)
        return bool(re.search(r"\w", w)) and w not in FORMAT_WORDS and w not in {"x", "by"}

    def add(words: list[str], whole: bool = False) -> None:
        if not words or _all_noise(words):
            return
        if not whole and not (edge_ok(words[0]) and edge_ok(words[-1])):
            return
        phrase = " ".join(words).strip(_EDGE)
        key = phrase.lower()
        # Never the brand, nor a piece of it ("Papa", "Barkley" of Papa & Barkley).
        if brand_words and {_bare(w) for w in words} <= brand_words | {"&", "and", "+"}:
            return
        if phrase and key not in seen and key != brand_key:
            seen.add(key)
            out.append(phrase)

    chunks = [[s.split() for s in _segments(chunk)] for chunk in _FOR_RE.split(name or "")]
    stretches = [words for chunk in chunks for words in chunk]
    for words in stretches:
        add(list(words), whole=True)
    for words in stretches:
        for size in range(min(len(words), MAX_WORDS), 0, -1):
            for i in range(len(words) - size + 1):
                add(words[i:i + size])
    # Neighbouring stretches joined, for a strain a separator split — but never with what
    # the store set apart on purpose: a lineage ("Strawberry | Sativa"), a word in quotes
    # ("Watermelon Lemonade 'Bliss'"), the brand's curated line, or a bare number.
    quoted = {q.strip().lower() for q in _QUOTED_RE.findall(name or "")}

    def apart(words: list[str]) -> bool:
        text = " ".join(words)
        return (bool(_LINEAGE_RE.fullmatch(text.strip(_EDGE))) or text.lower() in quoted
                or text.lower().strip(_EDGE) == brand_key
                or not re.search(r"[a-z]", text, re.I)
                or canonical.find_product_line(brand or "", text) is not None)

    for chunk in chunks:
        for a, b in zip(chunk, chunk[1:]):
            if len(a) + len(b) <= MAX_WORDS and not apart(a) and not apart(b):
                add(a + b)
    return out[:MAX_PHRASES]


def strain_phrases(name: str, brand: str | None = "", category: str | None = None) -> list[str]:
    """phrases(), as strain options: a phrase that ends on the category's own format word
    is offered without it ("Cookies N Cream Cones" on an edible is Cookies N Cream), and
    the brand's curated product lines are left to the line question ("Releaf" is Papa &
    Barkley's line, not a strain)."""
    tails = FORMAT_TAILS.get((category or "").lower(), [])
    heads = FORMAT_HEADS.get((category or "").lower(), frozenset())
    out: list[str] = []
    for phrase in phrases(name, brand):
        words = phrase.split()
        trimmed_one = True
        while trimmed_one:
            trimmed_one = False
            for tail in tails:
                if len(words) > len(tail) and tuple(_bare(w) for w in words[-len(tail):]) == tail:
                    words, trimmed_one = words[:-len(tail)], True
                    break
        while len(words) > 1 and _bare(words[0]) in heads:
            words = words[1:]
        trimmed = " ".join(words).strip(_EDGE)
        line = canonical.find_product_line(brand or "", trimmed, category)
        if line and line.lower() == trimmed.lower():
            continue
        if trimmed and trimmed.lower() not in {o.lower() for o in out}:
            out.append(trimmed)
    return out


def tidy(phrase: str) -> str:
    """A picked phrase in the form the LLM is told to write a strain: Title Case for a
    phrase the store wrote all in one case, crosses joined by a lowercase "x".
    Mixed-case phrases keep the store's spelling, as the LLM is told to."""
    if phrase.isupper() or phrase.islower():
        keep = {"OG", "AK", "RSO", "CBD", "THC", "BC", "NYC", "LA", "GSC", "GMO", "MAC", "UK",
                "ATF", "OGKB", "ZKZ", "PCK", "GDP", "SFV", "GG", "DJ"}     # storefront.ACRONYMS
        words = []
        for w in phrase.split():
            words.append(w.upper() if w.upper() in keep or re.search(r"\d", w)
                         else w.capitalize())
        phrase = " ".join(words)
    return re.sub(r"(?<=\s)[xX](?=\s)", "x", phrase)


@dataclass
class TextAnswer:
    strain: str | None
    p_strain: float
    line: str | None
    p_line: float


def _options(candidates: list[str], quoted: set[str], none_text: str) -> dict[str, str]:
    opts = {"none": none_text}
    for i, c in enumerate(candidates):
        opts[f"p{i}"] = f"'{c}' (in quotes in the name)" if c.lower() in quoted else c
    return opts


def extract(items: list[tuple[dict, str | None, str | None]], *, workers: int = 8,
            usage: jev.Usage | None = None) -> list[TextAnswer | None]:
    """One answer per (row, category, subtype); None where Jev failed or the name offers
    no phrase at all."""
    jobs, phrase_lists, live = [], [], []
    for i, (row, category, subtype) in enumerate(items):
        name = row.get("name") or ""
        candidates = phrases(name, row.get("brand"))
        strains = strain_phrases(name, row.get("brand"), category)
        phrase_lists.append((strains, candidates))
        if not candidates:
            continue
        quoted = {q.strip().lower() for q in _QUOTED_RE.findall(name)}
        state = {"brand": row.get("brand") or "", "name": name,
                 "category": category or "", "subtype": subtype or ""}
        questions = {"line": jev.Choice(LINE_QUESTION,
                                        _options(candidates, quoted, "No product line in the name"))}
        if strains:     # every phrase was a format word or the brand's line: no strain to pick
            questions["strain"] = jev.Choice(STRAIN_QUESTION, _options(strains, quoted, "None of these"))
        jobs.append((state, questions))
        live.append(i)
    results = jev.ask_many(jobs, workers=workers, usage=usage)
    out: list[TextAnswer | None] = [None] * len(items)
    for i, res in zip(live, results):
        if res is None:
            continue
        picks = []
        for key, candidates in zip(("strain", "line"), phrase_lists[i]):
            if key not in res.answers:
                picks.append((None, 1.0))
                continue
            pick, p, _ = res.choice(key)
            phrase = None
            if pick and pick != "none" and pick[1:].isdigit() and int(pick[1:]) < len(candidates):
                phrase = candidates[int(pick[1:])]
            picks.append((phrase, p))
        out[i] = TextAnswer(picks[0][0], picks[0][1], picks[1][0], picks[1][1])
    return out
