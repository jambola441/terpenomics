"""
jev_classify.py — A listing's category and subtype, decided by Jev.

Enrichment's first model call (enrich.py, "pass A") asks an LLM to classify each
listing into a category and a subtype and to write its size. Category and subtype
are closed-set decisions — every answer is clamped to taxonomy.py's rails anyway —
which is exactly the question shape Jev answers (jev.py): pick one of these options,
with a calibrated probability, for a fraction of an LLM call's price (input only;
Jev's output tokens are free). The size is text, which Jev cannot write, so when
this classifier is in use the size moves to enrichment's second call, the LLM one.

One request per listing, asking every question at once — the category, and the
subtype *within each category that has a choice to make*. Jev evaluates questions
in isolation against the same state, so asking all five subtype questions costs a
few hundred input tokens, not latency, and the caller keeps the answer for whichever
category won. Merch is never asked: its subtype comes from MerchEnricher's name
tokens, as it does on the LLM path.

Option text spells every criterion out, because Jev reads literally
(docs.typesafe.ai/model-jaggedness/jev-1.13). The criteria are the LLM prompt's
rules (enrich.py _CLASSIFY_BODY) and the token rules (taxonomy.SUBTYPE_TOKENS), restated
per option. Jev leans toward the first option, so the scraper's category and the
rule-based subtype go first: on the LLM path those hints are "usually correct —
trust them", and this is the same prior expressed the way Jev takes it.

    import jev_classify
    answers = jev_classify.classify([(row, hint_category, hint_subtype), ...])
    answers[0].category, answers[0].subtype, answers[0].p_category
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jev  # noqa: E402
import taxonomy  # noqa: E402

# Bump when a question or option text changes: enrich.py stamps cached answers with
# it, so answers given to an older question are re-asked rather than trusted.
QUESTION_VERSION = 1

# Jev degrades on large irrelevant state; the first few hundred characters of a
# description carry the format words, the rest is marketing copy.
DESCRIPTION_CHARS = 300

CATEGORY_CRITERIA: dict[str, str] = {
    "flower": "Cannabis flower sold by weight: buds, eighths, ounces, smalls, shake or "
              "pre-ground flower, infused flower. Not rolled, not a vape, not an extract.",
    "preroll": "Pre-rolled joints or blunts, single or in packs, including infused "
               "pre-rolls (kief, diamonds, live resin).",
    "vaporizers": "Vapes: cartridges (510 carts), pods, all-in-one or disposable vape "
                  "pens, and vape batteries. Anything named vape, cart, pod, AIO or "
                  "disposable is a vaporizer even if the store files it as a concentrate.",
    "edible": "Eaten or drunk: gummies, chews, chocolates, beverages and drinks, "
              "tablets, pills and capsules, other foods. Dosed in mg of THC. An edible "
              "made with live resin or rosin (a live resin gummy or rope) is an edible.",
    "concentrate": "Extracts for dabbing, not in a vape and not an edible: diamonds, "
                   "rosin, live resin, badder, sauce, sugar, hash, RSO.",
    "tinctures": "Tinctures: drops, oils or sprays taken by mouth, dosed in total mg.",
    "topical": "Topicals applied to the skin: balms, lotions, salves, creams, roll-ons, "
               "patches, bath products.",
    "merch": "Accessories with no cannabis in them: grinders, rolling papers, cones, "
             "lighters, trays, glass, batteries sold alone, apparel, gift cards.",
    "other": "None of the above.",
}

SUBTYPE_CRITERIA: dict[str, dict[str, str]] = {
    "flower": {
        "flower": "Regular flower — whole buds.",
        "smalls": "Smalls: small buds, sold as smalls, minis, popcorn or littles.",
        "preground": "Pre-ground flower: ground flower, shake, milled, ready-to-roll.",
        "infused": "Infused flower: buds coated or infused with concentrate, kief, oil "
                   "or diamonds (moon rocks).",
    },
    "preroll": {
        "single": "One plain pre-roll — not infused and not a multi-pack.",
        "infused": "Infused pre-roll(s): contains kief, diamonds, hash, live resin or live "
                   "rosin, or is called infused. Infused wins over pack — an infused 5-pack "
                   "is infused.",
        "pack": "A multi-pack of plain (non-infused) pre-rolls: 2pk, 5pk, variety pack.",
    },
    "vaporizers": {
        "cart": "Cartridge: a 510-thread cart, cartridge, preload or reload.",
        "all-in-one": "All-in-one or disposable vape: battery and oil together, rechargeable "
                      "or disposable pen, AIO.",
        "pod": "Pod for a proprietary device (e.g. STIIIZY pod, PAX Era pod).",
        "battery": "A vape battery or device sold without oil, or a starter kit.",
        "other": "A vape product that is none of these.",
    },
    "edible": {
        "gummy": "Gummies, chews, fruit chews, ropes, pearls.",
        "chocolate": "Chocolate bars and chocolates.",
        "beverage": "Drinks: sodas, seltzers, teas, shots, drink mixes, sparkling water.",
        "tablet": "Tablets, pills, capsules, mints, beans or drops in tablet form.",
        "other": "Any other edible: baked goods, candy that is not a gummy or chocolate, "
                 "honey, syrups, cooking oil.",
    },
    "concentrate": {
        "diamonds": "THCA diamonds, diamonds and sauce.",
        "rosin": "Rosin, live rosin, hash rosin — solventless pressed extract.",
        "resin": "Live resin or cured resin — the name says resin (live resin badder "
                 "is resin).",
        "hash": "Hash, bubble hash, kief, temple ball.",
        "rso": "RSO (Rick Simpson Oil), FECO, full-spectrum oil syringes.",
        "other": "Any other concentrate, including a texture named without resin or "
                 "rosin: badder, budder, sugar, crumble, wax, shatter.",
    },
}

assert set(CATEGORY_CRITERIA) == set(taxonomy.CATEGORY_ORDER)
assert all(set(v) == set(taxonomy.SPECS[c].subtypes) for c, v in SUBTYPE_CRITERIA.items())


@dataclass
class Answer:
    category: str
    p_category: float
    subtypes: dict[str, tuple[str, float]]   # category -> (subtype, probability)

    def subtype_for(self, category: str) -> tuple[str | None, float]:
        return self.subtypes.get(category, (None, 0.0))


def _first(options: dict[str, str], first: str | None) -> dict[str, str]:
    """The same options with `first` moved to the front (Jev's default position)."""
    if first not in options:
        return dict(options)
    return {first: options[first], **{k: v for k, v in options.items() if k != first}}


def state(row: dict, hint_category: str | None, hint_subtype: str | None) -> dict:
    s = {
        "brand": row.get("brand") or "",
        "name": row.get("name") or "",
        "store_category": hint_category or "",
        "size": row.get("variant") or "",
    }
    desc = (row.get("description") or "").strip()
    if desc:
        s["description"] = desc[:DESCRIPTION_CHARS]
    return s


def questions(hint_category: str | None, hint_subtype: str | None) -> dict[str, jev.Choice]:
    qs = {"category": jev.Choice(
        "Which kind of cannabis dispensary product is this? Judge from the name first; "
        "store_category is the store's own filing and is usually right.",
        _first(CATEGORY_CRITERIA, hint_category))}
    for cat, options in SUBTYPE_CRITERIA.items():
        first = hint_subtype if hint_category == cat else taxonomy.SPECS[cat].default_subtype
        qs[f"subtype.{cat}"] = jev.Choice(
            f"If this product is {cat}, which {cat} format is it?", _first(options, first))
    return qs


def classify(items: list[tuple[dict, str | None, str | None]], *, workers: int = 8,
             usage: jev.Usage | None = None) -> list[Answer | None]:
    """One answer per (row, hint_category, hint_subtype); None where Jev failed."""
    jobs = [(state(r, hc, hs), questions(hc, hs)) for r, hc, hs in items]
    results = jev.ask_many(jobs, workers=workers, usage=usage)
    out: list[Answer | None] = []
    for res in results:
        if res is None:
            out.append(None)
            continue
        cat, p_cat, _ = res.choice("category")
        if cat not in CATEGORY_CRITERIA:
            out.append(None)
            continue
        subs = {}
        for c in SUBTYPE_CRITERIA:
            pick, p, _ = res.choice(f"subtype.{c}")
            if pick:
                subs[c] = (pick, p)
        out.append(Answer(cat, p_cat, subs))
    return out
