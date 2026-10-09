#!/usr/bin/env python3
"""
merch_catalog.py — Hardware and rolling papers in brand catalogs.

Brand catalogs modelled cannabis only: merch identity was "fully determined by name
tokens" (taxonomy.py), so a PAX Era Go battery or a RAW Classic King Size pack was
never an entry, and the matcher had nothing to put those listings on. The owner's
call (2026-10-09): hardware and papers get entries of their own.

Which merch: papers (paper, cone, wrap, filter-tip) and hardware (battery, charger).
A grinder, tray or bong stays out: one-off accessories with no range to model.

A merch product is its format (subtype), the brand's line ("Classic", "Organic Hemp",
"Era Go", "Pro XL"), and its colour ("Black", "Gold"); a paper also comes in sizes,
written as the merch enricher writes them: width, count, tips ("king size 32ct",
"1 1/4 50ct w/tips"). Every part is read from the name by rules, the same ones
enrichment applies (enrichers.MerchEnricher, data/product_lines.json, attributes.py),
so a listing's merch reading is computed here, never asked of a model:

  reading(name, brand, subtype)   -> {category, subtype, product_line, colour, size}

Entries come from the stores' consensus like the bootstrap's (2+ stores), built by
catalog_bootstrap.propose() through propose_entries() and kept in the brand's catalog
by whichever push writes it (a storefront push carries them as products only stores
sell). Hardware is filed under vaporizers by some stores ("PAX - Flow Portable
Vaporizer"): a vaporizer read as a battery is merch here.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import attributes as attribute_registry  # noqa: E402
import enrichers  # noqa: E402
import canonical  # noqa: E402
from canonical import find_product_line  # noqa: E402

PAPERS = ("paper", "cone", "wrap", "filter-tip")
HARDWARE = ("battery", "charger")
CATALOGED = frozenset(PAPERS + HARDWARE)
# Formats that are a product only in a size: a paper's width and count make the SKU. Tips
# and hardware are products without one (a site rarely states a tip's count).
SIZED = ("paper", "cone", "wrap")
NOUN = {"paper": "Papers", "cone": "Cones", "wrap": "Wraps", "filter-tip": "Tips",
        "battery": "Battery", "charger": "Charger"}
_MERCH = enrichers.for_category("merch")


_DEVICE = re.compile(r"\b(vaporizer|vaporiser|battery|batteries|device|kit|charger)\b", re.I)
# Finishes only hardware comes in: a "Blue" in a vape's name is as likely "Blue Dream".
_FINISHES = {"onyx", "greenstone", "periwinkle", "lavender", "oxblood", "sage", "sky"}


def is_merch(category: str | None, subtype: str | None, name: str = "", brand: str = "") -> bool:
    """A listing this module may model: merch (its reading decides whether the format is
    cataloged), a vaporizer read as a battery, or a vaporizer whose name carries one of the
    brand's hardware lines with a device word or a hardware finish ("PAX Plus | Onyx",
    "Pax - Four Vaporizer - Greenstone": stores file devices as vapes)."""
    if category == "merch" or (category == "vaporizers" and subtype == "battery"):
        return True
    if category != "vaporizers" or not name:
        return False
    if not line_subtype(brand, find_product_line(brand or "", name, "merch")):
        return False
    colour = (attribute_registry.for_category("merch", name) or {}).get("colour") or ""
    return bool(_DEVICE.search(name)) or colour.lower() in _FINISHES


# ---------------------------------------------------------------------------
# Sizes: width, count, tips
# ---------------------------------------------------------------------------

_COUNT = re.compile(r"\b(\d+)\s*(?:pk|ct)\b")
_WIDTH = re.compile(r"^(ks wide|king size|1 1/4|1 1/2|single wide|100s|\d+(?:\.\d+)?\s*(?:mm|in|inch|\"))")


@dataclass(frozen=True)
class MerchSize:
    width: str | None = None
    count: int | None = None
    tips: bool = False

    def is_empty(self) -> bool:
        return self.width is None and self.count is None

    def label(self) -> str | None:
        parts = [self.width, f"{self.count}ct" if self.count else None, "w/tips" if self.tips else None]
        return " ".join(p for p in parts if p) or None


def parse_size(variant: str | None) -> MerchSize:
    """A size as the merch enricher writes it ("king size 32ct", "1 1/4 50pk w/tips")."""
    text = (variant or "").strip().lower()
    w = _WIDTH.match(text)
    c = _COUNT.search(text)
    return MerchSize(w.group(1) if w else None, int(c.group(1)) if c else None, "w/tips" in text)


def same_size(a: MerchSize, b: MerchSize) -> bool:
    """Whether two paper sizes can be one: width and count agree wherever both state one,
    and tips agree (a booklet with tips is another SKU, named the same otherwise)."""
    if a.tips != b.tips:
        return False
    if a.width and b.width and a.width != b.width:
        return False
    if a.count and b.count and a.count != b.count:
        return False
    return True


# ---------------------------------------------------------------------------
# A listing's merch reading
# ---------------------------------------------------------------------------

def line_subtype(brand: str, line: str | None) -> str | None:
    """The format a curated merch line declares (data/product_lines.json: PAX's Flow is a
    device, filed with batteries), or None."""
    if not line:
        return None
    own, shared = canonical._for_brand(canonical._load(canonical._LINES_PATH, "lines"), brand or "")
    for entry in list(own or []) + list(shared or []):
        if isinstance(entry, dict) and entry.get("line") == line and entry.get("category") == "merch":
            return entry.get("subtype")
    return None


def reading(name: str, brand: str, subtype: str | None = None, category: str | None = None) -> dict:
    """What the rules read off a merch listing's name: format, line, colour, size. A name
    with no format word takes its line's (a "PAX Flow | Onyx" is a device), and a
    vaporizer a store filed as a battery is one."""
    line = find_product_line(brand or "", name or "", "merch")
    sub = _MERCH.token_subtype(name) or line_subtype(brand, line) or subtype
    if category == "vaporizers" and sub not in CATALOGED:
        sub = "battery"                     # a vape-filed device: its format word was a vape's
    if not line and sub in PAPERS:
        line = default_line(brand, sub)
    colour = (attribute_registry.for_category("merch", name) or {}).get("colour")
    if colour and line and _key(colour) in _key(line):
        colour = None                       # RAW Black is a line: its black is no colour of its own
    size = _MERCH.variant(name, None)
    if size and comes_with_tips(line) and "w/tips" not in size:
        size += " w/tips"
    return {"category": "merch", "subtype": sub, "product_line": line, "colour": colour, "size": size}


def comes_with_tips(line: str | None) -> bool:
    """A range sold with tips in the pack, whether or not a name says so: RAW's
    Connoisseur is its papers with tips."""
    return "connoisseur" in (line or "").lower()


_DEFAULTS: dict | None = None


def default_line(brand: str, subtype: str) -> str | None:
    """The line a brand's paper or cone is when its name names none: RAW's plain papers are
    Classic, the range the brand calls its own ("_merch_default_lines" in
    data/product_lines.json)."""
    global _DEFAULTS
    if _DEFAULTS is None:
        import json
        _DEFAULTS = json.loads(canonical._LINES_PATH.read_text(encoding="utf-8")).get("_merch_default_lines") or {}
    defaults = _DEFAULTS
    own = next((v for k, v in defaults.items() if _key(k) == _key(brand)), None) or {}
    return own.get(subtype)


# ---------------------------------------------------------------------------
# A brand's own site (storefront.py): one entry per size its page states
# ---------------------------------------------------------------------------

# Bulk and display boxes are a distributor's unit, not a store's: "500 bulk box",
# "24 packs per box", "Mega Bulk Box".
_BULK = re.compile(r"\b(bulk|box|boxes|display|case|jar|bag of)\b", re.I)
_PACK_PHRASE = re.compile(
    r"(\d+)\s*(?:-\s*)?(?:cone|cones|pre-?rolled tips?|tips?|leaves|leaf|papers?|sheets?|pieces?|piece)?"
    r"\s*(?:per\s+)?(?:pack|pk|booklet)\b", re.I)
_LEAVES = re.compile(r"(\d+)\s*(?:leaves|sheets)\s+per\s+(?:pack|booklet)", re.I)
# Widths named in a site's SKU or copy that the title leaves out ("RAW Classic Kingsize",
# SKUs RAWKSWIDE and RAWK-SSLIM: the slim and the wide).
_SKU_WIDTHS = [(re.compile(r"KS-?WIDE|KSW\b|-KSW-", re.I), "ks wide"),
               (re.compile(r"K-?S-?SLIM|KSS\b|-KSS-|-KS-|KS\d", re.I), "king size"),
               (re.compile(r"-114-|114\b|\bRAW1-4\b|(?<=[A-Z])1\b", re.I), "1 1/4"),
               (re.compile(r"-112-|112\b|\bRAW1-2\b", re.I), "1 1/2")]


def site_sizes(title: str, sku: str, body: str, line: str | None = None) -> list[MerchSize]:
    """The retail sizes a site's product page states: the widths its title and SKUs name,
    times the pack counts its copy names, bulk and display boxes left out. A page that
    names no count gives its widths with the count open."""
    widths = []
    w = parse_size(_MERCH.variant(title, None)).width
    if w:
        widths.append(w)
    for pattern, width in _SKU_WIDTHS:
        if pattern.search(sku or "") and width not in widths and not (w and width.startswith("k") != w.startswith("k")):
            widths.append(width)
    if re.search(r"\bwide\b", body or "", re.I) and "king size" in widths and "ks wide" not in widths:
        widths.append("ks wide")
    counts = []
    for m in list(_PACK_PHRASE.finditer(body or "")) + list(_LEAVES.finditer(body or "")):
        tail = (body or "")[m.end():m.end() + 12]
        if _BULK.search(m.group(0)) or re.match(r"\s*(?:per\s+)?(?:bulk\s+)?(?:box|display|case)\b", tail, re.I):
            continue
        n = int(m.group(1))
        if 1 <= n < 100 and n not in counts:
            counts.append(n)
    tips = comes_with_tips(line) or bool(_MERCH._tips.search(title or ""))
    return fold_partial([MerchSize(w, c, tips) for w in (widths or [None]) for c in (counts or [None])
                         if w or c])


def fold_partial(sizes: list[MerchSize]) -> list[MerchSize]:
    """One product's sizes without the partial ones a complete size covers: a page or a
    store that gives "32ct" beside "king size 32ct" names that size, and kept apart it
    would make every king size 32ct listing fit two entries."""
    whole = [x for x in sizes if x.width and x.count]
    return [x for x in sizes if (x.width and x.count) or not any(same_size(x, w) for w in whole)]


def site_entries(title: str, sku: str, body: str, brand: str, subtype: str, method: str,
                 item_id: str) -> list[dict]:
    """Catalog entries for one product page of a brand's site, read by the same rules as
    a store listing (reading), one per size the page states (site_sizes)."""
    r = reading(title, brand, subtype)
    sub = r["subtype"]                      # a format word in the title, else the site's category
    if sub not in CATALOGED:
        return []
    sizes = site_sizes(title, sku, body, r["product_line"]) if sub in PAPERS else [MerchSize()]
    if not sizes and sub not in SIZED:
        sizes = [MerchSize()]
    product_key = f"sf:merch:{sub}:{_key(r['product_line'])}:{_key(r['colour'])}:{_key(range_name(title, r))}"
    out = []
    for size in sizes:
        out.append({
            "external_id": f"{product_key}:{_key(size.label()) or 'nosize'}:{item_id}",
            "product_key": product_key,
            "name": " ".join(x for x in (r["product_line"], r["colour"], range_name(title, r), NOUN[sub]) if x),
            "product_line": r["product_line"],
            "category": "merch",
            "subtype": sub,
            "strain": None,
            "variant": size.label(),
            "attributes": {"colour": r["colour"]} if r["colour"] else None,
            "match_terms": [],
            "source": method,
        })
    return out


def range_name(title: str, r: dict) -> str | None:
    """Nothing yet: a site product's range beyond its line (Lean, Peacemaker) is not read,
    so two such ranges of one line and width are one product. Kept as a hook."""
    return None


def _key(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ---------------------------------------------------------------------------
# Entries from the stores' consensus
# ---------------------------------------------------------------------------

def propose_entries(brand: str, listings: list[dict], min_stores: int = 2) -> list[dict]:
    """Catalog entries for the brand's papers and hardware: one product per format, line
    and colour, one entry per size.

    Papers need `min_stores` stores, as the bootstrap's products do, and a size: a
    listing that names neither width nor count ("RAW Cones") says too little to be a
    product. A partial size ("20ct", "king size") is the product's one complete size it
    fits, folded in; one that fits several stays out. Hardware whose line the curated
    rules name ("Era Go", "Pro XL") is admitted on one store: the line and the colour
    are read by rules, so its name is clean (the curation rule for one-store products)."""
    groups: dict[tuple, list[tuple[dict, dict]]] = defaultdict(list)
    for l in listings:
        if not is_merch(l.get("category"), l.get("subtype"), l.get("name") or "", brand):
            continue
        r = reading(l.get("name") or "", brand, l.get("subtype"), l.get("category"))
        if r["subtype"] not in CATALOGED:
            continue
        size = parse_size(r["size"]) if r["subtype"] in PAPERS else MerchSize()
        if r["subtype"] in SIZED and size.is_empty():
            continue
        groups[(r["subtype"], _key(r["product_line"]), _key(r["colour"]), size)].append((l, r))

    # A partial size joins the one complete size of its product it fits.
    for key in [k for k in groups if k[0] in PAPERS and (k[3].width is None or k[3].count is None)]:
        whole = [k for k in groups if k[:3] == key[:3] and k[3].width and k[3].count
                 and same_size(key[3], k[3])]
        if len(whole) == 1:
            groups[whole[0]].extend(groups.pop(key))
        elif whole:
            groups.pop(key)

    entries = []
    for (subtype, line_key, colour_key, size), rows in sorted(groups.items(), key=lambda kv: (kv[0][:3], kv[0][3].label() or "")):
        stores = len({l.get("dispensary_id") for l, _ in rows})
        line_name = next((r["product_line"] for _, r in rows if r["product_line"]), None)
        need = 1 if subtype in HARDWARE and line_subtype(brand, line_name) else min_stores
        if stores < need:
            continue
        line = Counter(r["product_line"] for _, r in rows if r["product_line"]).most_common(1)
        colour = Counter(r["colour"] for _, r in rows if r["colour"]).most_common(1)
        line, colour = (line[0][0] if line else None), (colour[0][0] if colour else None)
        product_key = f"mb:merch:{subtype}:{line_key}:{colour_key}"
        shown_colour = colour if _key(colour) != line_key else None     # "Natural Natural Wraps"
        noun = NOUN[subtype]
        if subtype == "battery" and sum("vapori" in (l.get("name") or "").lower() for l, _ in rows) * 2 > len(rows):
            noun = "Vaporizer"                 # PAX's Flow, Plus, Mini and Four are dry-herb devices
        entries.append({
            "external_id": f"{product_key}:{_key(size.label()) or 'nosize'}",
            "product_key": product_key,
            "name": " ".join(x for x in (line, shown_colour, noun) if x),
            "product_line": line,
            "category": "merch",
            "subtype": subtype,
            "strain": None,
            "variant": size.label(),
            "attributes": {"colour": colour} if colour else None,
            "match_terms": [],
            "source": "listings_bootstrap",
            "support": stores,
        })
    return entries


# ---------------------------------------------------------------------------
# The attribute join for merch
# ---------------------------------------------------------------------------

def entry_colour(entry: dict) -> str | None:
    return (entry.get("attributes") or {}).get("colour")


def join(entries: list[dict], r: dict) -> dict | None:
    """The one active entry a merch reading names: the same format; the same line where
    the reading has one; the same colour where either side has one; a paper's size
    agreeing. None when no entry or several fit."""
    if r.get("subtype") not in CATALOGED:
        return None
    want = parse_size(r.get("size"))
    if r["subtype"] in SIZED and want.is_empty():
        return None
    hits = []
    for e in entries:
        if not e.get("is_active", True) or e.get("category") != "merch" or e.get("subtype") != r["subtype"]:
            continue
        if r.get("product_line") and _key(e.get("product_line")) != _key(r["product_line"]):
            continue
        if not r.get("product_line") and e.get("product_line"):
            continue                       # a line the reading lacks is no agreement
        if _key(entry_colour(e)) != _key(r.get("colour")):
            continue
        if r["subtype"] in PAPERS and not want.is_empty() and e.get("variant") \
                and not same_size(want, parse_size(e.get("variant"))):
            continue
        hits.append(e)
    # A listing that states no size, of a product with sized and size-less entries
    # (RAW's Tips: the page's 10ct and 21ct, and one without a count), is the size-less one.
    if len(hits) > 1 and len({e.get("product_key") for e in hits}) == 1:
        # ...and one that states a size is the entry of that size, not the size-less one.
        hits = ([e for e in hits if not e.get("variant")] if want.is_empty()
                else [e for e in hits if e.get("variant")]) or hits
    return hits[0] if len(hits) == 1 else None
