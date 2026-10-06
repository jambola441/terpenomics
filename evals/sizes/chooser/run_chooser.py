"""Measure Jev choosing a listing's size among the readings size_candidates.py finds.

The cases are the 285 listings of evals/sizes whose readings conflicted on 2026-10-06,
labelled by model readers who saw everything a person would: the text, the store's
size field, the price, and the matched catalog product's sizes and prices. See
../README.md. The chooser is the one measured there:

  1. the code settles what it can (size_candidates.assess);
  2. for weights, a size whose price per gram is under a third or over three times the
     brand's usual is dropped, and if one size is left it is the answer;
  3. Jev picks among the rest, each option saying in words which readings give it and
     what a package that size sells for; under the confidence bar the store's size
     field stands.

    python evals/sizes/chooser/run_chooser.py                  # asks Jev (~$0.007), then scores
    python evals/sizes/chooser/run_chooser.py --split test --threshold 0.7
    python evals/sizes/chooser/run_chooser.py --answers answers.json   # re-score saved answers
    python evals/sizes/chooser/run_chooser.py --show S0216     # print one question
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent.parent / "scripts"))

import jev  # noqa: E402
import size_candidates as sc  # noqa: E402
import sizes  # noqa: E402

CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
PRICES = json.loads((HERE / "prices.json").read_text(encoding="utf-8"))

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


def _fmt(v: float, unit: str) -> str:
    return f"{v:g}{unit}"


def size_sentences(description: str | None, limit: int = 350) -> str:
    """What the description says about size, and nothing else: the sentences with a
    figure or a count in them (Jev reads a long state worse)."""
    text = " ".join(re.sub(r"<[^>]+>", " ", description or "").split())
    said = " … ".join(s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if _SIZE_TEXT.search(s))
    return said[:limit] + ("…" if len(said) > limit else "")


def per_gram(case: dict) -> tuple[float, str] | None:
    """(cents per gram, whose): the brand's usual for the category, else the category's."""
    brand = (case["brand"] or "").strip()
    b = PRICES["brand_per_g"].get(f"{brand.lower()}|{case['category']}")
    if b:
        return b["median"], f"{brand}{chr(39) if brand.endswith('s') else chr(39) + 's'} usual"
    pts = [(float(k.split("|")[1]), v["median"], v["n"]) for k, v in PRICES["category"].items()
           if k.split("|")[0] == case["category"]]
    if not pts:
        return None
    return sum(p / x * n for x, p, n in pts) / sum(n for _, _, n in pts), f"the usual {case['category']}"


def size_price(case: dict, v: float) -> str | None:
    """What a package of exactly this size sells for: the matched product's, the brand's,
    or the category's."""
    unit = case["unit"]
    for p in case["product_sizes"]:
        if sc.same(p["value"], v, unit) and p["typical"]:
            return f"this product's {_fmt(v, unit)} typically sells for {p['typical']}"
    b = PRICES["brand_size"].get(f"{(case['brand'] or '').strip().lower()}|{case['category']}|{round(v, 3):g}")
    if b:
        return f"{case['brand']}'s {_fmt(v, unit)} {KIND.get(case['category'], '')} typically sell for ${b['median'] / 100:,.2f}"
    g = PRICES["category"].get(f"{case['category']}|{round(v, 3):g}")
    if g and g["n"] >= 5:
        return f"{KIND.get(case['category'], case['category'])} of {_fmt(v, unit)} typically sell for ${g['median'] / 100:,.2f}"
    return None


def price_fits(case: dict, v: float) -> bool:
    """A weight whose price per gram is within 3x of the usual. Dose sizes are priced too
    unevenly to judge this way (a 10mg single sells for what a 20mg 2-pack lists at)."""
    if case["unit"] != "g" or not case["price_cents"] or v <= 0:
        return True
    pg = per_gram(case)
    return not pg or PRICE_BOUNDS[0] <= (case["price_cents"] / v) / pg[0] <= PRICE_BOUNDS[1]


def reading_words(c: sc.Candidate, case: dict, reads: list[sc.Candidate]) -> str:
    """One reading, in words a literal reader cannot misread."""
    unit, noun = case["unit"], NOUN.get(case["category"], "unit")
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


def decide_or_ask(case: dict, price: str = "both"):
    """(settled size, how) when code decides; else (None, (state, questions, labels)).

    `price` says where the listing's price is used: "code" (the per-gram check drops
    sizes), "jev" (Jev reads it and each option's typical price), "both" or "none"."""
    unit = case["unit"]
    listing = {"variant": case["field"], "scraped_name": case["name"], "description": case["description"],
               "scraped_category": case["category"]}
    a = sc.assess(listing, [{"variant": p["variant"], "category": case["category"]} for p in case["product_sizes"]])
    if a.status in ("settled", "silent"):
        return (a.values[0] if a.values else None), "code"
    reads = [c for c in a.candidates if c.likely or c.source == "catalog"] or a.candidates
    values = sc.distinct_values(reads)
    if price in ("both", "code"):
        values = [v for v in values if price_fits(case, v)] or values
        if len(values) == 1:
            return values[0], "price"
    state = {"brand": case["brand"], "listing_name": case["name"], "category": case["category"],
             "store_size_field": case["field"] or "(empty)"}
    if said := size_sentences(case["description"]):
        state["description_says"] = said
    if case["price_cents"] and price in ("both", "jev"):
        state["price"] = f"${case['price_cents'] / 100:,.2f}"
        if unit == "g" and (pg := per_gram(case)):
            state["price_suggests"] = f"about {case['price_cents'] / pg[0]:.2g}g at {pg[1]} ${pg[0] / 100:,.2f} per gram"
    criteria, labels = {}, {}
    for v in values:
        bits = list(dict.fromkeys(reading_words(c, case, a.candidates) for c in reads if sc.same(c.value, v, unit)))
        if price in ("both", "jev") and (tp := size_price(case, v)):
            bits.append(tp)
        labels[_fmt(v, unit)] = v
        criteria[_fmt(v, unit)] = f"The package holds {_fmt(v, unit)}. Read from: " + "; ".join(bits) + "."
    instructions = (f"What size is the package this dispensary listing sells? The size is {MEASURE[unit]}. "
                    "Each option says how the listing or the store's size field gives that size. Stores write "
                    "sizes loosely: a figure beside a pack count can be each unit's or the whole pack's, the "
                    "store's size field is sometimes the count times a figure that was already the total, and a "
                    "description can be copied from another size of the product."
                    + (" The price should fit the size." if price in ("both", "jev") else ""))
    if len(criteria) < 2:
        criteria["none"] = "None of these sizes fits."
    return None, (state, {"size": jev.Choice(instructions=instructions, criteria=criteria)}, labels)


def field_size(case: dict) -> float | None:
    s = sizes.parse(case["field"], category=case["category"])
    return s.mg if case["unit"] == "mg" else s.grams


def parse_size(case: dict) -> float | None:
    s = sizes.parse(case["field"], case["name"], category=case["category"])
    return s.mg if case["unit"] == "mg" else s.grams


def ask(cases: list[dict], price: str = "both") -> dict[str, dict]:
    out, jobs = {}, []
    for c in cases:
        value, how = decide_or_ask(c, price)
        if value is not None or how in ("code", "price"):
            out[c["sid"]] = {"value": value, "p": 1.0, "by": how}
        else:
            jobs.append((c, how))
    usage = jev.Usage()
    results = jev.ask_many([(state, qs) for _, (state, qs, _) in jobs], usage=usage)
    for (c, (_, _, labels)), r in zip(jobs, results):
        pick, p, _ = r.choice("size") if r else (None, 0.0, {})
        out[c["sid"]] = {"value": labels.get(pick), "p": p, "by": "jev"}
    print(usage.summary())
    return out


def _label(s) -> float | None:
    m = re.match(r"^\s*(\d+(?:\.\d+)?|\.\d+)\s*(g|mg)\s*$", str(s or ""), re.I)
    return float(m.group(1)) if m else None


def score(cases: list[dict], answers: dict[str, dict], threshold: float) -> None:
    rows = {"store size field": lambda c: field_size(c),
            "sizes.parse (field, then name)": lambda c: parse_size(c),
            f"chooser (Jev below {threshold} -> field)": lambda c: (
                answers[c["sid"]]["value"] if answers[c["sid"]]["value"] is not None
                and answers[c["sid"]]["p"] >= threshold else field_size(c)),
            "chooser, only its confident answers": lambda c: (
                answers[c["sid"]]["value"] if answers[c["sid"]]["p"] >= max(threshold, 0.8) else None)}
    for label_name in ("label", "blind"):
        judged = [c for c in cases if _label(c[label_name]) is not None]
        print(f"\nagainst the {'full-information' if label_name == 'label' else 'blind (name + description)'} labels: {len(judged)} cases")
        for name, pick in rows.items():
            verdicts = Counter()
            for c in judged:
                v = pick(c)
                verdicts["none" if v is None else "right" if sc.same(v, _label(c[label_name]), c["unit"]) else "wrong"] += 1
            answered = verdicts["right"] + verdicts["wrong"]
            print(f"  {name:<40} {verdicts['right']:>4} right {verdicts['wrong']:>4} wrong {verdicts['none']:>4} no answer"
                  f"   {verdicts['right'] / answered:.1%} of answers" if answered else "")
    print("\ndecided by:", dict(Counter(answers[c["sid"]]["by"] for c in cases)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--split", choices=["all", "dev", "test"], default="all")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--answers", help="score these saved answers instead of asking Jev")
    ap.add_argument("--save", help="save the answers here")
    ap.add_argument("--show", help="print the question for one case id")
    ap.add_argument("--price", choices=["both", "code", "jev", "none"], default="both",
                    help="where the price is used (an ablation; the chooser uses both)")
    args = ap.parse_args()
    cases = [c for c in CASES if args.split == "all" or c["split"] == args.split]
    if args.show:
        c = next(x for x in CASES if x["sid"] == args.show)
        value, how = decide_or_ask(c, args.price)
        if value is not None or how in ("code", "price"):
            print(f"decided by {how}: {value}")
            return
        state, qs, _ = how
        print(json.dumps(state, indent=1, ensure_ascii=False))
        print(qs["size"].instructions)
        for k, v in qs["size"].criteria.items():
            print(f"  [{k}] {v}")
        return
    answers = json.loads(Path(args.answers).read_text()) if args.answers else ask(cases, args.price)
    if args.save:
        Path(args.save).write_text(json.dumps(answers, indent=1))
    score(cases, answers, args.threshold)


if __name__ == "__main__":
    main()
