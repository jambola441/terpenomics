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
                  the assignment is a fact about the string, not a judgment. This
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
    words = [re.escape(w) for w in re.split(r"[\s\-_]+", line.strip()) if w]
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


def find_product_line(brand: str, name: str) -> str | None:
    """The curated line for this brand whose text appears in `name`, else None.
    Longest match wins so "Flyers Blends" beats "Flyers" when both are curated."""
    own, shared = _for_brand(_load(_LINES_PATH, "lines"), brand)
    candidates = list(own or []) + list(shared or [])
    hits = [line for line in candidates if _pattern(line).search(name or "")]
    return max(hits, key=len) if hits else None


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
    Elderberry Sage" -> "Elderberry Sage"). Returns strain unchanged if removing
    the line would leave nothing."""
    stripped = _pattern(line).sub(" ", strain)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip(" -|,")
    return stripped or strain


def canonicalize(rows: list[dict]) -> dict:
    """Apply both maps to enriched rows, in place. Returns a count of what changed.

    Product lines are additive-then-corrective: a curated line whose text is in the
    name always wins (it is a string fact), but a model-supplied line is left alone
    when no curated entry matches, so uncurated brands keep whatever the model found.
    """
    stats = {"product_line_set": 0, "product_line_corrected": 0,
             "strain_delined": 0, "strain_aliased": 0}
    for row in rows:
        brand = row.get("brand") or row.get("scraped_brand") or ""
        name = row.get("name") or row.get("scraped_name") or ""

        line = find_product_line(brand, name)
        if line:
            before = (row.get("product_line") or "").strip()
            if before != line:
                stats["product_line_corrected" if before else "product_line_set"] += 1
                row["product_line"] = line
            strain = (row.get("strain") or "").strip()
            if strain and _pattern(line).search(strain):
                row["strain"] = _strip_line_from_strain(strain, line)
                stats["strain_delined"] += 1

        canon = canonical_strain(brand, row.get("strain") or "")
        if canon is not None and canon != (row.get("strain") or ""):
            row["strain"] = canon
            stats["strain_aliased"] += 1
    return stats
