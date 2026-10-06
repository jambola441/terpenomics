"""
size_choice.py — Choose a listing's size among the readings size_candidates.py finds.

size_candidates lists every size a listing could mean and says when the readings
disagree. This module settles the disagreements:

  1. code settles what it can (size_candidates.assess);
  2. for weights, a size whose price per gram is under a third or over three times the
     brand's usual (the category's when the brand has too few listings) is dropped, and
     if one size is left it is the answer — arithmetic stays in code;
  3. Jev picks among the rest. Each option says in words which readings give it and what
     a package that size typically sells for; the state carries the price and only the
     description's sentences about size. Below the confidence bar the store's size field
     stands.

Measured on 167 held-out conflicts (evals/sizes/chooser): 83.7% right, against 69.3%
for the store's size field and 57.8% for sizes.parse. The price is what does it: 72.3%
without it, and Jev's answers at p >= 0.8 go from 77% to 94% right.

    from size_choice import Item, PriceBook, choose
    picks = choose([Item(name=..., category="preroll", variant="1g", price_cents=15000)],
                   PriceBook.load("prices.json"))
    picks[0].value, picks[0].by, picks[0].p
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import jev  # noqa: E402
import size_candidates as sc  # noqa: E402
import sizes  # noqa: E402

THRESHOLD = 0.7
PRICE_BOUNDS = (0.33, 3.0)
NOUN = {"preroll": "pre-roll", "vaporizers": "cart or pod", "edible": "piece"}
KIND = {"preroll": "pre-roll packs", "vaporizers": "vapes", "edible": "edibles", "tinctures": "tinctures",
        "topical": "topicals", "flower": "flower", "concentrate": "concentrates"}
MEASURE = {"g": "the net weight, in grams, of everything in the package",
           "mg": "the total THC, in milligrams, in the whole package"}
_SIZE_TEXT = re.compile(
    r"(\d+(?:[.,]\d+)?\s*-?\s*(?:g|gr|grams?|mg|milligrams?|oz|ounces?)\b|\b\d+\s*-?\s*(?:pk|pack|packs|ct|count|pcs|pieces?)\b|"
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|half|eighth|quarter)\b[\w\s.-]{0,25}?"
    r"\b(?:pre-?rolls?|gumm(?:y|ies)|pieces?|pods?|carts?|joints?|cones?|pills?|tablets?|grams?|ounces?|mg)\b)", re.I)


@dataclass
class Item:
    """One listing, as the chooser needs it. product_sizes: the matched catalog product's
    sizes, as {"value", "variant", "typical"} ("typical" a price string or None)."""
    name: str
    category: str
    variant: str | None = None
    description: str | None = None
    brand: str | None = None
    price_cents: int | None = None
    product_sizes: list[dict] = field(default_factory=list)

    @property
    def unit(self) -> str | None:
        return sc.unit_of(self.category)


@dataclass
class PriceBook:
    """Typical prices, from listings whose own readings settle on one size:
    category   "category|size" -> {"median": cents, "n": listings}
    brand_size "brand|category|size" -> {"median", "n"}
    brand_per_g "brand|category" -> {"median": cents per gram, "n"}"""
    category: dict = field(default_factory=dict)
    brand_size: dict = field(default_factory=dict)
    brand_per_g: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path) -> "PriceBook":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d.get("category", {}), d.get("brand_size", {}), d.get("brand_per_g", {}))

    def per_gram(self, item: Item) -> tuple[float, str] | None:
        """(cents per gram, whose): the brand's usual for the category, else the category's."""
        brand = (item.brand or "").strip()
        b = self.brand_per_g.get(f"{brand.lower()}|{item.category}")
        if b:
            return b["median"], f"{brand}{chr(39) if brand.endswith('s') else chr(39) + 's'} usual"
        pts = [(float(k.split("|")[1]), v["median"], v["n"]) for k, v in self.category.items()
               if k.split("|")[0] == item.category]
        if not pts:
            return None
        return sum(p / x * n for x, p, n in pts) / sum(n for _, _, n in pts), f"the usual {item.category}"

    def size_price(self, item: Item, v: float) -> str | None:
        """What a package of exactly this size sells for: the matched product's, the
        brand's, or the category's."""
        unit = item.unit
        for p in item.product_sizes:
            if sc.same(p["value"], v, unit) and p.get("typical"):
                return f"this product's {_fmt(v, unit)} typically sells for {p['typical']}"
        b = self.brand_size.get(f"{(item.brand or '').strip().lower()}|{item.category}|{round(v, 3):g}")
        if b:
            return (f"{item.brand}'s {_fmt(v, unit)} {KIND.get(item.category, '')} typically sell "
                    f"for ${b['median'] / 100:,.2f}")
        g = self.category.get(f"{item.category}|{round(v, 3):g}")
        if g and g["n"] >= 5:
            return f"{KIND.get(item.category, item.category)} of {_fmt(v, unit)} typically sell for ${g['median'] / 100:,.2f}"
        return None

    def fits(self, item: Item, v: float) -> bool:
        """A weight whose price per gram is within 3x of the usual. Dose sizes are priced
        too unevenly to judge this way (a 10mg single sells for what a 20mg 2-pack lists at)."""
        if item.unit != "g" or not item.price_cents or v <= 0:
            return True
        pg = self.per_gram(item)
        return not pg or PRICE_BOUNDS[0] <= (item.price_cents / v) / pg[0] <= PRICE_BOUNDS[1]


@dataclass
class Pick:
    value: float | None     # the package total in the item's unit; None when nothing settles it
    by: str                 # "code", "price", "jev", or "field" (Jev below the bar or no answer)
    p: float = 1.0


def _fmt(v: float, unit: str) -> str:
    return f"{v:g}{unit}"


def size_sentences(description: str | None, limit: int = 350) -> str:
    """What the description says about size, and nothing else: the sentences with a
    figure or a count in them (Jev reads a long state worse)."""
    text = " ".join(re.sub(r"<[^>]+>", " ", description or "").split())
    said = " … ".join(s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if _SIZE_TEXT.search(s))
    return said[:limit] + ("…" if len(said) > limit else "")


def _reading_words(c: sc.Candidate, item: Item, reads: list[sc.Candidate]) -> str:
    """One reading, in words a literal reader cannot misread."""
    unit, noun = item.unit, NOUN.get(item.category, "unit")
    where = {"field": "the store's size field", "name": "the listing name", "description": "the description"}
    m = re.match(r"as (\d+) x ([\d.]+)(g|mg)", c.reading)
    if c.source == "catalog":
        return "a size the matched catalog product comes in"
    if "+" in c.source:
        a, b = c.source.split("+")
        whose = "the store's size field" if b == "field" else f"the {b}"
        return (f"if {whose} gives one {noun}'s size: the count {m.group(1)} in the "
                f"{'store size field' if a == 'field' else a} times its {m.group(2)}{unit}")
    if c.reading.startswith("as written"):
        return f"{where[c.source]} states {c.label()}"
    if c.reading == "as the pack total":
        counts = sorted({int(x) for o in reads if o.source == c.source
                         for x in re.findall(r"as (\d+) x", o.reading)})
        each = "; ".join(f"{c.value / n:.3g}{unit} per {noun} if {n} in the pack" for n in counts[:2])
        return f"{where[c.source]}'s {c.label()} taken as the whole pack" + (f" ({each})" if each else "")
    if m:
        return f"{where[c.source]} read as {m.group(1)} {noun}s of {m.group(2)}{m.group(3)} each"
    return f"{where[c.source]}: {c.reading}"


def field_size(item: Item) -> float | None:
    s = sizes.parse(item.variant, category=item.category)
    return s.mg if item.unit == "mg" else s.grams


def decide_or_ask(item: Item, prices: PriceBook, price: str = "both"):
    """(Pick, None) when code decides; else (None, (state, questions, labels)).

    `price` says where the listing's price is used — "code" (the per-gram check),
    "jev" (Jev reads it and each option's typical price), "both", or "none"."""
    unit = item.unit
    listing = {"variant": item.variant, "scraped_name": item.name, "description": item.description,
               "scraped_category": item.category}
    a = sc.assess(listing, [{"variant": p["variant"], "category": item.category} for p in item.product_sizes])
    if a.status in ("settled", "silent"):
        return Pick(a.values[0] if a.values else None, "code"), None
    reads = [c for c in a.candidates if c.likely or c.source == "catalog"] or a.candidates
    values = sc.distinct_values(reads)
    if price in ("both", "code"):
        values = [v for v in values if prices.fits(item, v)] or values
        if len(values) == 1:
            return Pick(values[0], "price"), None
    state = {"brand": item.brand or "", "listing_name": item.name, "category": item.category,
             "store_size_field": item.variant or "(empty)"}
    if said := size_sentences(item.description):
        state["description_says"] = said
    if item.price_cents and price in ("both", "jev"):
        state["price"] = f"${item.price_cents / 100:,.2f}"
        if unit == "g" and (pg := prices.per_gram(item)):
            state["price_suggests"] = f"about {item.price_cents / pg[0]:.2g}g at {pg[1]} ${pg[0] / 100:,.2f} per gram"
    criteria, labels = {}, {}
    for v in values:
        bits = list(dict.fromkeys(_reading_words(c, item, a.candidates) for c in reads if sc.same(c.value, v, unit)))
        if price in ("both", "jev") and (tp := prices.size_price(item, v)):
            bits.append(tp)
        labels[_fmt(v, unit)] = v
        criteria[_fmt(v, unit)] = f"The package holds {_fmt(v, unit)}. Read from: " + "; ".join(bits) + "."
    if len(criteria) < 2:
        criteria["none"] = "None of these sizes fits."
    instructions = (f"What size is the package this dispensary listing sells? The size is {MEASURE[unit]}. "
                    "Each option says how the listing or the store's size field gives that size. Stores write "
                    "sizes loosely: a figure beside a pack count can be each unit's or the whole pack's, the "
                    "store's size field is sometimes the count times a figure that was already the total, and a "
                    "description can be copied from another size of the product."
                    + (" The price should fit the size." if price in ("both", "jev") else ""))
    return None, (state, {"size": jev.Choice(instructions=instructions, criteria=criteria)}, labels)


def choose(items: list[Item], prices: PriceBook | None = None, *, threshold: float = THRESHOLD,
           price: str = "both", usage: jev.Usage | None = None) -> list[Pick]:
    """A Pick per item: code's, the price check's, Jev's at or above `threshold`, else the
    store's size field (by="field"). One Jev request per item code leaves open."""
    prices = prices or PriceBook()
    out: list[Pick | None] = [None] * len(items)
    jobs = []
    for i, item in enumerate(items):
        if not item.unit:
            out[i] = Pick(None, "code")
            continue
        pick, ask = decide_or_ask(item, prices, price)
        if pick:
            out[i] = pick
        else:
            jobs.append((i, ask))
    results = jev.ask_many([(state, qs) for _, (state, qs, _) in jobs], usage=usage) if jobs else []
    for (i, (_, _, labels)), r in zip(jobs, results):
        choice, p, _ = r.choice("size") if r else (None, 0.0, {})
        value = labels.get(choice)
        out[i] = (Pick(value, "jev", p) if value is not None and p >= threshold
                  else Pick(field_size(items[i]), "field", p))
    return out
