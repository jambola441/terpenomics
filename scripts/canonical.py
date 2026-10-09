"""
canonical.py — Deterministic post-enrichment canonicalization.

The LLM decides *what* a listing is; this module makes the answer *consistent*.
Three curated, brand-scoped vocabularies back that up. Two are applied after
enrichment (product_lines, strain_aliases); format_tokens is consulted by
enrich.py *before* the model call, so the category it settles also gives the
model the right subtype rails to answer within.

  product_lines   data/product_lines.json — {brand: [line, ...]}
                  A line is assigned when its text actually appears in the product
                  name (word-boundary match, punctuation/spacing insensitive), so
                  the assignment is a fact about the string, not a judgment. An
                  entry may instead be {"line": "Liquid Diamonds", "also": ["Liquid
                  Diamond"]}: every spelling stores print assigns the one line. With
                  "category" too, the line is that category's alone (a brand's "Live
                  Rosin" vapes beside its Live Rosin jars), and a name that carries
                  no line is given it when the
                  store's description names it and no other line of that category:
                  "King Louis XIII - 1G Infused Prerolls", whose description says
                  "Stiiizy 40s pre-rolls are...", is a 40's. This
                  is what the model is least reliable at: in the gold eval it found
                  lines for some brands and missed them for others (Flyers, Quicks,
                  Little Pandas), which splits one product family into several
                  groups in the products view.

  strain_aliases  data/strain_aliases.json — {brand: {variant: canonical}}
                  Collapses spelling drift for the SAME strain ("Blu Dreem" →
                  "Blue Dream"). The enrichment prompt tells the model to keep the
                  source spelling, which is right for avoiding hallucination but
                  cannot converge two dispensaries that spell a strain differently
                  — only a shared map can. "" as the canonical value clears the
                  strain.

  format_tokens   data/format_tokens.json — {brand: {token: category}}
                  Settles the category for products identifiable only by a brand's
                  hardware name ("Select Briq V2" is a vape with no vape word in
                  it). See find_format_category.

All three files use "*" as a brand key for entries that apply to every brand.

Why deterministic: these fixes cost nothing per run, are auditable, apply
identically across every dispensary, and compound — each entry added from an
audit finding is permanent. Prompt tweaks are none of those things.

Grow the maps from `python evals/enrich/audit.py --db --json out.json`: the
`strain_split` and `line_leaked_into_strain` findings are the candidate list.

    from canonical import canonicalize
    canonicalize(rows)   # mutates rows in place
"""

import json
import re
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"
_LINES_PATH = _DATA_DIR / "product_lines.json"
_ALIASES_PATH = _DATA_DIR / "strain_aliases.json"
_FORMATS_PATH = _DATA_DIR / "format_tokens.json"

_ANY = "*"

_caches: dict[str, dict] = {}


def _norm_brand(s: str) -> str:
    """Lowercase, fold '&'/'+' to 'and', strip punctuation, collapse whitespace — so
    "Papa & Barkley" and "Papa and Barkley" resolve to the same key."""
    s = re.sub(r"\s*[&+]\s*", " and ", (s or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s)).strip()


def _load(path: Path, cache_name: str) -> dict:
    """Load a canonical map, dropping "_comment"-style keys. Missing file -> {}."""
    if cache_name not in _caches:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        _caches[cache_name] = {_norm_brand(k) if k != _ANY else _ANY: v
                               for k, v in raw.items() if not k.startswith("_")}
    return _caches[cache_name]


def _for_brand(table: dict, brand: str):
    """Entries for this brand plus the wildcard bucket.

    Falls back to a leading-word-subsequence match in either direction, so one key
    covers a brand recorded inconsistently across dispensaries: a "Timeless" key
    serves "Timeless Vapes", and an "Eaton Botanicals" key serves "Eaton". Longest
    (most specific) match wins. Fold true synonyms into data/brand_aliases.json —
    this only rescues suffix drift."""
    key = _norm_brand(brand)
    own = table.get(key)
    if own is None and key:
        words = key.split()
        best = -1
        for k, v in table.items():
            if k == _ANY:
                continue
            kw = k.split()
            n = min(len(kw), len(words))
            if n and kw[:n] == words[:n] and len(kw) > best:
                own, best = v, len(kw)
    return own, table.get(_ANY)


def _line_pattern(line: str) -> re.Pattern:
    """Word-boundary matcher tolerant of spacing/punctuation between words, so a
    curated "Little Pandas" matches "little-pandas" and "LittlePandas". Boundaries
    keep a short line like "UP" from matching inside "Syrup"."""
    # A straight apostrophe in a spelling matches a curly one too: store copy says "40\u2019s".
    words = [re.escape(w).replace("'", "['\u2019]") for w in re.split(r"[\s\-_]+", line.strip()) if w]
    if not words:
        return re.compile(r"(?!)")  # never matches
    return re.compile(
        r"(?<![A-Za-z0-9])" + r"[\s\-_]*".join(words) + r"(?![A-Za-z0-9])", re.I
    )


_pattern_cache: dict[str, re.Pattern] = {}


def _pattern(line: str) -> re.Pattern:
    if line not in _pattern_cache:
        _pattern_cache[line] = _line_pattern(line)
    return _pattern_cache[line]


def _spellings(entry) -> tuple[str, list[str]]:
    """A curated line and every spelling that assigns it: "Liquid Diamonds" for a name
    that says "Liquid Diamond", "40's" for one that says "40s"."""
    if isinstance(entry, dict):
        return entry["line"], [entry["line"], *entry.get("also", [])]
    return entry, [entry]


def _find_line(brand: str, name: str, category: str | None = None) -> tuple[str, str] | None:
    """(curated line, the spelling of it found in `name`). The longest spelling wins,
    so "Flyers Blends" beats "Flyers" when both are curated. A line that declares a
    category belongs to it: given the listing's category, it is not assigned in
    another. Heavy Hitters' "Live Rosin" is a vape line, and its rosin jars say Live
    Rosin too."""
    own, shared = _for_brand(_load(_LINES_PATH, "lines"), brand)
    hits = [(line, spelling) for entry in list(own or []) + list(shared or [])
            if not (category and isinstance(entry, dict) and entry.get("category") not in (None, category))
            for line, spellings in [_spellings(entry)] for spelling in spellings
            if _pattern(spelling).search(name or "")]
    return max(hits, key=lambda h: len(h[1])) if hits else None


def line_from_description(brand: str, description: str, category: str | None) -> str | None:
    """The one curated line of `category` the description names, else None. Weaker
    evidence than the name, so only lines that declare a category take part, and a
    description naming two of them settles nothing."""
    if not description or not category:
        return None
    own, shared = _for_brand(_load(_LINES_PATH, "lines"), brand)
    hits = {entry["line"] for entry in list(own or []) + list(shared or [])
            if isinstance(entry, dict) and entry.get("category") == category
            for spelling in _spellings(entry)[1] if _pattern(spelling).search(description)}
    return hits.pop() if len(hits) == 1 else None


def find_product_line(brand: str, name: str, category: str | None = None) -> str | None:
    """The curated line for this brand whose text appears in `name`, else None (a line
    of another category than the listing's is not this listing's)."""
    hit = _find_line(brand, name, category)
    return hit[0] if hit else None


def canonical_strain(brand: str, strain: str) -> str | None:
    """Canonical spelling for a strain under this brand, or None if not mapped.
    A mapped value of "" means 'clear the strain'."""
    if not strain:
        return None
    own, shared = _for_brand(_load(_ALIASES_PATH, "aliases"), brand)
    key = strain.strip().lower()
    for table in (own, shared):
        if table and key in {k.lower() for k in table}:
            return next(v for k, v in table.items() if k.lower() == key)
    return None


def find_format_category(brand: str, name: str) -> str | None:
    """Category implied by a curated device/format token in the name, else None.

    Covers products whose only category signal is a brand's hardware name — a
    "Select Briq V2" or "Florist Farms Rechargeable OVL" carries no generic vape
    word, so the model reads "1G <something>" and answers concentrate. Longest
    token wins."""
    own, shared = _for_brand(_load(_FORMATS_PATH, "formats"), brand)
    merged = {**(shared or {}), **(own or {})}
    hits = [(tok, cat) for tok, cat in merged.items() if _pattern(tok).search(name or "")]
    return max(hits, key=lambda tc: len(tc[0]))[1] if hits else None


def _strip_line_from_strain(strain: str, line: str) -> str:
    """Remove the product line from a strain that swallowed it ("Night Cap
    Elderberry Sage" -> "Elderberry Sage"), with the pair joiner that tied it on
    ("Kush Mintz x Chopped Cheese" -> "Kush Mintz": a lowercase "x" at either end, as
    stores write a pair; an "X" in a name is a word). Returns strain unchanged if
    removing the line would leave nothing."""
    stripped = _pattern(line).sub(" ", strain)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip(" -|,")
    stripped = re.sub(r"^x\s+|\s+x$", "", stripped).strip(" -|,")
    return stripped or strain


def not_a_line(line: str | None, brand: str) -> bool:
    """A model-supplied line that is no line: a lone letter (one store prefixes every
    name "X| Brand | ...", and 156 readings took "X" for the line), or the brand's own
    name ("Canna Cure" for Cannacure Farms, "Lost Farms" for Lost Farm; 121 readings,
    2026-10-08)."""
    s = re.sub(r"[^a-z0-9]", "", (line or "").lower())
    b = re.sub(r"[^a-z0-9]", "", (brand or "").lower())
    if not s:
        return False
    return len(s) <= 1 or bool(b) and (s == b or s in b or s == b + "s")   # not "Level 5", "Jeeter XL"


def canonicalize(rows: list[dict]) -> dict:
    """Apply both maps to enriched rows, in place. Returns a count of what changed.

    Product lines are additive-then-corrective: a curated line whose text is in the
    name always wins (it is a string fact), but a model-supplied line is left alone
    when no curated entry matches, so uncurated brands keep whatever the model found.
    """
    stats = {"product_line_set": 0, "product_line_corrected": 0, "product_line_dropped": 0,
             "product_line_from_description": 0, "strain_delined": 0, "strain_aliased": 0}
    for row in rows:
        brand = row.get("brand") or row.get("scraped_brand") or ""
        name = row.get("name") or row.get("scraped_name") or ""

        hit = _find_line(brand, name, row.get("category") or row.get("scraped_category"))
        if hit:
            line, spelling = hit
            before = (row.get("product_line") or "").strip()
            if before != line:
                stats["product_line_corrected" if before else "product_line_set"] += 1
                row["product_line"] = line
            strain = (row.get("strain") or "").strip()
            for sp in {line, spelling}:
                if strain and _pattern(sp).search(strain):
                    strain = _strip_line_from_strain(strain, sp)
                    row["strain"] = strain
                    stats["strain_delined"] += 1
        elif not_a_line(row.get("product_line"), brand):
            row["product_line"] = None
            stats["product_line_dropped"] += 1
        if not hit and not (row.get("product_line") or "").strip():
            line = line_from_description(brand, row.get("description") or "",
                                         row.get("category") or row.get("scraped_category"))
            if line:
                row["product_line"] = line
                stats["product_line_from_description"] += 1

        canon = canonical_strain(brand, row.get("strain") or "")
        if canon is not None and canon != (row.get("strain") or ""):
            row["strain"] = canon
            stats["strain_aliased"] += 1
    return stats
