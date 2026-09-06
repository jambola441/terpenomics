#!/usr/bin/env python3
"""
catalog_enricher.py — Feed a brand's real product list into the enrichment prompt.

Pass B already nudges the model with `known_strains` / `known_product_lines`, but
those come from the `listings` table — that is, from the model's own previous output.
Every quality number in this repo is computed from the same output it judges, and the
hint has the same problem: it makes the pipeline self-consistent, not correct. A brand
catalog is the first external referent, so it belongs in exactly those slots.

**A hint, not an answer.** The catalog is added to the model's context and the model
still decides. It does not bypass the model, does not overwrite an extracted field,
and does not decide what a product is. An earlier attempt did answer directly and was
measurably worse: taking the catalog's pack variant ('10mg / 12 pack') over the
listing's own dose ('10mg') is wrong for a single can, and forcing the catalog's
category rail flipped 89 beverages from subtype 'beverage' to 'other'. The catalog
knows what the brand sells; the listing knows what this store is selling.

Reads `data/catalogs/<brand-slug>.json`, never Postgres — enrich.py has no DB access
today and that is load-bearing: enrichment runs where 5432 is blocked, and a CSV plus
a cache file is a self-contained handoff.

Because this only changes the prompt, a cached answer stays valid and no
_ENRICH_VERSION bump is implied. Rows that hit the cache never build a payload, so
they are unaffected; the hint reaches exactly the rows that were going to the model
anyway.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brand_catalog import norm_name  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "data" / "catalogs"

# How many catalog titles to put in front of the model for one item. The shortlist is
# the nearest few by name similarity, not the whole catalog: Ayrloom alone has 65
# titles, and pasting all of them into every item would cost more in input tokens than
# the extraction saves while burying the relevant one.
MAX_HINTS = 5

_catalogs: dict[str, dict] | None = None


_MASKED = re.compile(r"\w\*+\w")


def _is_masked(s: str) -> bool:
    """True for a self-censored spelling like 'alaskan thunder fu*k'.

    MEASURED, and the reason this filter exists. Offering that title as a hint made
    the model answer strain 'Alaskan Thunder Fu*K' on a case it had previously got
    right — the eval went from pass to fail on exactly this row. A hint is an
    invitation to copy a string verbatim, so a brand's marketing spelling is not
    automatically the value we want stored: the catalog is authoritative about which
    products exist, not about how to spell them in our schema.

    Dropped from the hint pools only. The catalog file keeps the real title, and
    catalog_match.py still matches on it, because there the string is compared rather
    than copied.
    """
    return bool(_MASKED.search(s or ""))


def _brand_key(brand: str | None) -> str:
    return norm_name(brand or "")


def _load() -> dict[str, dict]:
    """Lazily load every catalog on disk, keyed by normalised brand name.

    A malformed or unreadable catalog is skipped with a warning rather than raising:
    a bad file in data/catalogs must not take down a fleet enrichment run.
    """
    global _catalogs
    if _catalogs is None:
        out: dict[str, dict] = {}
        if CATALOG_DIR.is_dir():
            for path in sorted(CATALOG_DIR.glob("*.json")):
                try:
                    cat = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as e:
                    print(f"  [warn] unreadable catalog {path.name}: {e}", file=sys.stderr)
                    continue
                entries = cat.get("entries") or []
                titles, strains, lines = {}, {}, {}
                for e in entries:
                    if e.get("name") and not _is_masked(e["name"]):
                        titles[norm_name(e["name"])] = e["name"]
                    if e.get("strain") and not _is_masked(e["strain"]):
                        strains[norm_name(e["strain"])] = e["strain"]
                    if e.get("product_line"):
                        lines[norm_name(e["product_line"])] = e["product_line"]
                out[_brand_key(cat.get("brand_name"))] = {
                    "titles": sorted(titles.values()),
                    "strains": sorted(strains.values()),
                    "product_lines": sorted(lines.values()),
                }
        _catalogs = out
    return _catalogs


def brands() -> list[str]:
    """Normalised brand keys we hold a catalog for."""
    return sorted(_load())


def _squash(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Token overlap a catalog title needs before it is worth showing when it is not
# contained outright. The DB-derived hint next door uses difflib with cutoff=0.0 and
# always returns a full shortlist; neither half of that works here. A catalog holds
# everything a brand sells, so returning something regardless put 'PrideBites
# honeycrisp plush can dog toy' in front of a cider — and an irrelevant hint is not
# neutral, it is a wrong answer offered to a model that would not have considered it.
# But whole-string similarity is also the wrong measure: a store writes
# 'ayrloom | Sweet Plum "Dreamweaver" | 1:3 | 100MG' for the product the catalog calls
# 'dreamweaver', and those two strings are barely similar even though one contains the
# other. So score containment first, overlap second.
HINT_MIN_OVERLAP = 0.5

_STOPWORDS = {"the", "a", "an", "and", "of", "with", "pack", "pk", "mg", "g",
              "thc", "cbd", "cbn", "cbg", "each", "size", "count", "ct", "single"}


def _toks(s: str) -> set[str]:
    return {t for t in norm_name(s).split() if t and t not in _STOPWORDS}


def _contained(needle: str, haystack: str) -> bool:
    """Whole-token containment, so 'up' does not match inside 'syrup'."""
    n, h = norm_name(needle).split(), norm_name(haystack).split()
    return bool(n) and any(h[i:i + len(n)] == n for i in range(len(h) - len(n) + 1))


def _relevant(name: str, pool: list[str], n: int = MAX_HINTS) -> list[str]:
    """Catalog values worth showing for this name, best first, possibly none."""
    lt = _toks(name)
    scored: list[tuple[float, str]] = []
    for item in pool:
        it = _toks(item)
        if not it:
            continue
        if _contained(item, name):
            scored.append((2.0, item))
            continue
        overlap = len(it & lt) / len(it)
        if overlap >= HINT_MIN_OVERLAP:
            scored.append((overlap, item))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    return [s for _, s in scored[:n]]


def hints(brand: str | None, name: str) -> dict:
    """Catalog context for one item, or {} when we hold no catalog for the brand.

    Three slots, each one the brand's own words:
      catalog_products     — the nearest real product titles, so the model can see
                             that 'Sweet Plum "Dreamweaver"' is the Dreamweaver product
      known_strains        — cultivars/flavours the brand actually ships
      known_product_lines  — lines named in this listing's name, squash-matched so
                             'Night Cap' still matches 'Nightcap'
    """
    cat = _load().get(_brand_key(brand))
    if not cat:
        return {}
    out: dict[str, list[str]] = {}
    titles = _relevant(name, cat["titles"])
    if titles:
        out["catalog_products"] = titles
    strains = _relevant(name, cat["strains"])
    if strains:
        out["known_strains"] = strains
    name_sq = _squash(name)
    lines = [pl for pl in cat["product_lines"]
             if _squash(pl) and _squash(pl) in name_sq][:MAX_HINTS]
    if lines:
        out["known_product_lines"] = lines
    return out
