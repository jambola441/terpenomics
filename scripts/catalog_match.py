#!/usr/bin/env python3
"""
catalog_match.py — Resolve listings to entries in their brand's catalog.

Enrichment extracts fields from a name; this matches the name to a product the brand
says it makes. When it resolves, the entry's fields are authoritative and every store
carrying that product lands on the same values — which is what collapses the
product_line split, where one product appears twice because the line was extracted on
some stores and not others (Jetpacks "FJ-Mini Afghani 0.6g" is written seven ways at
seven stores, with the line recorded as "FJ-Mini", "FJ Mini" or nothing).

How a listing is resolved
-------------------------
  exact       its normalised name is a catalog title or a recorded match term.
              Free, and accepted outright.
  shortlist   otherwise the brand's products are ranked by token containment and
              overlap, filtered to the listing's category and — when both sides state
              one — to a compatible size (sizes.py does the pack math, not the model).
  jev         Jev picks which shortlisted product the listing IS, or "none", and
              returns a probability for every option. The probability is the gate:

                p >= AUTO (0.85)     method "jev"          trusted for identity
                p >= REVIEW (0.50)   method "jev_review"   entry recorded, not trusted
                otherwise            method "none"

Without --jev the legacy deterministic tiers decide (exact / substring / token, or
"ambiguous" on a tie) — unchanged, so existing measurements stay reproducible.

**"No match" is a first-class outcome.** With a catalog a wrong answer stops being a
wrong string and becomes a specific wrong SKU, which reads as more authoritative and
travels further. The abstain option is offered *first* in every Jev question because
the model leans toward the first option (documented, jev-1.13 jaggedness): that bias
then pushes toward caution rather than toward whichever product ranked highest.

Cost and repeat runs
--------------------
One Jev call per unresolved listing, ~600 input tokens, $0.042/M, output free: about
$0.000025 a listing, so the whole fleet is cents. Answers are cached under
data/enrich_cache/catalog_match/ (the persistent disk on Render), keyed by the listing
name *and the candidate set*, so a catalog edit that changes a listing's shortlist
re-asks that listing and nothing else.

Usage
-----
  python scripts/catalog_match.py --brand Ayrloom                  # deterministic only
  python scripts/catalog_match.py --brand Ayrloom --jev --misses   # with the Jev tier
  python scripts/catalog_match.py --brand Ayrloom --eval           # measure Jev's gating
  python scripts/catalog_match.py --all --jev --write              # pipeline step (5432)
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brand_catalog import norm_name, strip_brand  # noqa: E402
import canonical  # noqa: E402
import catalog_store  # noqa: E402
import jev  # noqa: E402
import sizes  # noqa: E402
import taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# On the persistent disk the Render worker mounts, so repeat runs are free there too.
CACHE_DIR = ROOT / "data" / "enrich_cache" / "catalog_match"
# Bump when the question wording or the option rendering changes: cached answers were
# given to a different question.
QUESTION_VERSION = 2

# Legacy token tier. Set from the Ayrloom miss list: 'rescue 1:1 topical' -> 'rescue
# balm' shares one of two catalog tokens (0.5) and is correct, but 0.5 also admits
# unrelated single-word overlaps, so the threshold sits above it.
THRESHOLD = 0.66
# Set from the Ayrloom holdout (--eval, 2026-10-04): with the true product removed
# from the shortlist, Jev still picked a wrong one at p>=0.80 for 5.7% of listings,
# p>=0.85 for 2.3%, p>=0.90 for 0% — every one a near miss ("Half + Half" lemonade-
# and-tea read as "Lemonade"). Coverage on the same brand: 94.5% / 92.8% / 87.2%.
# 0.85 is the trade; the 0.50-0.85 band goes to review rather than being dropped.
AUTO = float(os.environ.get("CATALOG_MATCH_AUTO", "0.85"))
REVIEW = float(os.environ.get("CATALOG_MATCH_REVIEW", "0.50"))
# A catalog built from our own listings (catalog_bootstrap.py) omits products only
# one store carries, and a missing product is exactly when Jev's near-miss picks
# happen — the holdout's false matches above 0.85 vanish at 0.90.
AUTO_BOOTSTRAP = float(os.environ.get("CATALOG_MATCH_AUTO_BOOTSTRAP", "0.90"))


def auto_threshold(catalog: dict) -> float:
    return AUTO_BOOTSTRAP if catalog.get("source_method") == "listings_bootstrap" else AUTO
SHORTLIST = 25

# Methods counted as resolved in reports (the deterministic tiers included, for
# comparability with runs made before the Jev tier existed).
TRUSTED_METHODS = ("exact", "substring", "token", "jev", "manual")
# Methods whose entry may overwrite a listing's identity at import. Narrower than the
# above on purpose: a substring hit read a beverage title onto seven gummies on
# Ayrloom ("Pineapple Mango" vs "Island Time Pineapple Mango"), so on its own it only
# nominates candidates.
OVERLAY_METHODS = ("exact", "jev", "manual")

# Tokens that carry no identity — they appear in most names and inflate overlap.
STOPWORDS = {"the", "a", "an", "and", "of", "with", "pack", "pk", "mg", "g",
             "thc", "cbd", "cbn", "cbg", "each", "size", "count", "ct", "single",
             "indica", "sativa", "hybrid", "i", "s", "h"}


def _tokens(s: str) -> set[str]:
    return {t for t in norm_name(s).split() if t and t not in STOPWORDS and not t.isdigit()}


def _contained(needle: str, haystack: str) -> bool:
    """Whole-token containment, so 'up' does not match inside 'syrup'."""
    n, h = needle.split(), haystack.split()
    return bool(n) and any(h[i:i + len(n)] == n for i in range(len(h) - len(n) + 1))


# ---------------------------------------------------------------------------
# The catalog, as products
# ---------------------------------------------------------------------------

@dataclass
class Product:
    key: str
    entries: list[dict]
    title: str = ""
    category: str | None = None
    subtype: str | None = None
    product_line: str | None = None
    strain: str | None = None
    sizes: list[sizes.Size] = field(default_factory=list)
    terms: set[str] = field(default_factory=set)
    tokens: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, key: str, entries: list[dict]) -> "Product":
        first = entries[0]
        p = cls(key=key, entries=entries, title=first.get("name") or "",
                category=first.get("category"), subtype=first.get("subtype"),
                product_line=first.get("product_line"), strain=first.get("strain"))
        for e in entries:
            s = sizes.parse(e.get("variant"), category=p.category)
            if not s.is_empty():
                p.sizes.append(s)
            for t in [e.get("name")] + list(e.get("match_terms") or []):
                n = norm_name(t or "")
                if n:
                    p.terms.add(n)
        p.tokens = _tokens(p.title)
        return p

    def size_ok(self, listing_size: sizes.Size) -> bool | None:
        """True if any size this product comes in matches, False if none does, None if
        either side is silent."""
        verdicts = [sizes.same_size(listing_size, s) for s in self.sizes]
        known = [v for v in verdicts if v is not None]
        return None if not known else any(known)

    def describe(self) -> str:
        """The option description Jev reads. Every criterion spelled out, because the
        model reads literally (jev-1.13 jaggedness: 'literal reading')."""
        bits = [self.title]
        kind = "/".join(x for x in (self.category, self.subtype) if x)
        if kind:
            bits.append(kind)
        if self.product_line:
            bits.append(f"product line {self.product_line}")
        if self.strain and norm_name(self.strain) != norm_name(self.title):
            bits.append(f"strain/flavor {self.strain}")
        labels = sorted({e.get("variant") for e in self.entries if e.get("variant")})
        if labels:
            bits.append("sizes " + ", ".join(labels[:6]))
        return " · ".join(bits)


class CatalogIndex:
    """One brand's catalog, grouped by product so sizes resolve inside a product."""

    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.brand_name = catalog.get("brand_name") or ""
        groups: dict[str, list[dict]] = defaultdict(list)
        for e in catalog.get("entries") or []:
            if e.get("is_active", True):
                groups[e.get("product_key") or catalog_store._product_key(e)].append(e)
        self.products = {k: Product.build(k, v) for k, v in groups.items()}
        self.by_term: dict[str, list[str]] = defaultdict(list)
        for key, p in self.products.items():
            for t in p.terms:
                self.by_term[t].append(key)
        self.terms = sorted(self.by_term, key=len, reverse=True)

    # -- disambiguation and size resolution --------------------------------------
    def _disambiguate(self, keys: list[str], category: str | None) -> str | None:
        """Several products matched. Resolve only when it is genuinely safe.

        Titles repeat across categories — Ayrloom sells 'honeycrisp' as a vape and as
        a beverage. Category separates them; failing that the unique longest title
        wins; failing that, None rather than a guess.
        """
        keys = list(dict.fromkeys(keys))
        if len(keys) == 1:
            return keys[0]
        if category:
            on_cat = [k for k in keys if self.products[k].category == category]
            if len(on_cat) == 1:
                return on_cat[0]
            if on_cat:
                keys = on_cat
        longest = max(len(norm_name(self.products[k].title)) for k in keys)
        top = [k for k in keys if len(norm_name(self.products[k].title)) == longest]
        if len(top) == 1:
            return top[0]
        titled = [k for k in top if self.products[k].category]
        return titled[0] if len(titled) == 1 else None

    def pick_entry(self, key: str, listing_variant: str | None, category: str | None,
                   name: str = "") -> dict:
        """The entry for the size this listing sells; the product's first otherwise.

        The fields that decide identity (category, line, strain) are the same across a
        product's entries, so an unmatched size still resolves to the right product.
        """
        product = self.products[key]
        want = sizes.parse(listing_variant, name, category=category or product.category)
        for e in product.entries:
            got = sizes.parse(e.get("variant"), category=product.category)
            if sizes.same_size(want, got):
                return e
        if listing_variant:
            lv = norm_name(listing_variant)
            for e in product.entries:
                if e.get("variant") and norm_name(e["variant"]) == lv:
                    return e
        return product.entries[0]

    # -- tiers -------------------------------------------------------------------
    def exact(self, name: str, category: str | None) -> tuple[str | None, str]:
        """The name is a catalog title, or a store name recorded for one product.

        Compared with and without the brand's own words: recorded store names are
        kept brand-less (catalog_bootstrap) and most stores put the brand in, so
        without the second try a store's own name for a product would not match it.
        """
        for ln in dict.fromkeys((norm_name(name), strip_brand(name, self.brand_name))):
            if ln and ln in self.by_term:
                chosen = self._disambiguate(self.by_term[ln], category)
                return (chosen, "exact") if chosen else (None, "ambiguous")
        return None, "none"

    def deterministic(self, name: str, category: str | None) -> tuple[str | None, float, str]:
        """The legacy tiers: exact, substring, token. Used when Jev is off."""
        key, how = self.exact(name, category)
        if key or how == "ambiguous":
            return key, (1.0 if key else 0.0), how
        ln = norm_name(name)
        hits = [k for t in self.terms if _contained(t, ln) for k in self.by_term[t]]
        if hits:
            chosen = self._disambiguate(hits, category)
            if chosen is None:
                return None, 0.0, "ambiguous"
            conf = 0.80 + 0.15 * min(1.0, len(norm_name(self.products[chosen].title).split()) / 4)
            return chosen, conf, "substring"
        lt = _tokens(name)
        if lt:
            scored = []
            for key, p in self.products.items():
                if p.tokens:
                    cov = len(p.tokens & lt) / len(p.tokens)
                    if cov >= THRESHOLD:
                        scored.append((cov, key))
            if scored:
                best = max(c for c, _ in scored)
                chosen = self._disambiguate([k for c, k in scored if c == best], category)
                if chosen is None:
                    return None, 0.0, "ambiguous"
                return chosen, round(0.5 + 0.3 * best, 3), "token"
        return None, 0.0, "none"

    def shortlist(self, name: str, category: str | None, variant: str | None,
                  k: int = SHORTLIST, exclude: str | None = None,
                  subtype: str | None = None) -> list[str]:
        """Products worth asking about, best first. Possibly empty.

        Containment of a title or match term scores highest; otherwise token overlap.
        A product in a different known category is dropped (category is 100% on the
        gold suites — it is the one field we can lean on). Size filters only when it
        can: if no candidate states a compatible size, none is dropped for size,
        because a brand launching a new pack size is still the same product.

        Subtype filters the same soft way. It is what separates a gummy from a drink
        of the same flavour: in the Ayrloom holdout every wrong pick above p=0.85 was a
        gummy ("Sunny Days" pink lemonade) answered with the beverage "Lemonade", and
        the substring tier made the same mistake with "Island Time Pineapple Mango".
        Enrichment gets subtype right 97.9% of the time on the gold suites — enough to
        prune with, not enough to exclude with when it is the only thing left.

        `exclude` drops one product before anything else, as if the catalog did not
        contain it — the --eval holdout. Dropping it after the filters would let the
        true product shield its wrong-size siblings and flatter the result.
        """
        ln = norm_name(name)
        lt = _tokens(name)
        scored: list[tuple[float, str]] = []
        for key, p in self.products.items():
            if key == exclude:
                continue
            if category and p.category and p.category != category:
                continue
            best = 0.0
            for t in p.terms:
                if _contained(t, ln):
                    best = max(best, 2.0 + 0.1 * len(t.split()))
            if best == 0.0 and p.tokens and lt:
                overlap = len(p.tokens & lt) / len(p.tokens)
                if overlap > 0:
                    best = overlap
            if best > 0:
                scored.append((best, key))
        if not scored:
            return []
        listing_size = sizes.parse(variant, name, category=category)
        # Hard veto: a product whose subtype AND size both contradict the listing is
        # never it — a 100mg gummy is not a 10mg can — even if that empties the list.
        # In the holdout this was the last wrong pick above p=0.85 ("Sunny Days" pink
        # lemonade gummies -> the "Lemonade" drink, once Sunny Days was removed).
        if subtype and not listing_size.is_empty():
            scored = [(s, key) for s, key in scored
                      if not (self.products[key].subtype
                              and self.products[key].subtype != subtype
                              and self.products[key].size_ok(listing_size) is False)]
        if subtype:
            same = [(s, key) for s, key in scored
                    if not self.products[key].subtype or self.products[key].subtype == subtype]
            if any(self.products[key].subtype == subtype for _, key in same):
                scored = same
        if not listing_size.is_empty():
            fits = [(s, key) for s, key in scored
                    if self.products[key].size_ok(listing_size) is not False]
            if any(self.products[key].size_ok(listing_size) for _, key in fits):
                scored = fits
        scored.sort(key=lambda sk: (-sk[0], len(self.products[sk[1]].title)))
        return [key for _, key in scored[:k]]


def matched_subtype(entry: dict, name: str | None) -> str | None:
    """The subtype a listing resolved to `entry` takes.

    The entry's — unless a format word in the listing's own name says otherwise
    ("Cart", "AIO", "Starter Kit": taxonomy.SUBTYPE_TOKENS). The name is a fact about
    this listing; the entry's subtype is a claim about the product, and a bootstrap
    built from model answers can get a format wrong. Used wherever a catalog identity
    is applied — enrichment's catalog-first step and the importer's overlay — so the
    two never disagree. None for a category that keeps no subtype (pre-roll).
    """
    if not taxonomy.keeps_subtype(entry.get("category")):
        return None
    return taxonomy.token_subtype(entry.get("category"), name) or entry.get("subtype")


# ---------------------------------------------------------------------------
# The Jev question
# ---------------------------------------------------------------------------

NONE = "none"


def jev_question(brand: str, listing: dict, index: CatalogIndex,
                 candidates: list[str]) -> tuple[dict, dict, dict[str, str]]:
    """(state, questions, label -> product key) for one listing.

    The state is the listing and nothing else a decision does not need — of the sales
    copy, only a product line it names (described_line): 'large irrelevant state costs
    accuracy' is the third documented jagged edge.
    """
    size = sizes.parse(listing.get("variant"), listing.get("name"),
                       category=listing.get("category"))
    state = {
        "brand": brand,
        "listing_name": listing.get("name") or "",
        "listing_category": listing.get("category") or "",
        "listing_subtype": listing.get("subtype") or "",
        "listing_size": size.label() or (listing.get("variant") or ""),
    }
    line = described_line(listing, index)
    if line:
        state["product_line_in_description"] = line
    labels: dict[str, str] = {}
    criteria: dict[str, str] = {
        NONE: ("None of the products below is this listing — its flavor, strain or "
               "scent differs, its product line differs, or it is a product this "
               "catalog does not contain."),
    }
    for key in candidates:
        p = index.products[key]
        label = (p.title or key).strip()[:70] or key[:70]
        base, n = label, 2
        while label in criteria:
            label = f"{base} ({n})"
            n += 1
        labels[label] = key
        criteria[label] = p.describe()
    question = jev.Choice(
        instructions=(
            f"Which {brand} catalog product is this dispensary listing? Stores rename "
            "products freely: extra words, store codes, potency, lineage and the "
            "brand name itself are noise. Match on what the product is — the same "
            "flavor, strain or scent, and the same product line. Answer none when "
            "no option is that product."
        ),
        criteria=criteria,
    )
    return state, {"product": question}, labels


def described_line(listing: dict, index: CatalogIndex) -> str | None:
    """The curated product line the listing's description names, when its name names none.

    Store copy often carries the line a name leaves out ("Stiiizy 40s pre-rolls are
    setting the standard..." under "King Louis XIII - 1G Infused Prerolls"). The same
    rule enrichment uses (canonical.line_from_description): only curated lines that
    declare a category, and a description naming two of them settles nothing. Measured
    2026-10-05 against wider hints, which did worse: the first 300 characters of the
    copy (21 brands: trusted matches gained and lost about evenly, and more wrong picks
    when the true product was missing, as copy is often pasted from another product),
    and any line of the brand's catalog (generic line names such as "Infused" or
    "Classic" turn up in copy about other products).
    """
    brand = index.brand_name
    if not listing.get("description") or canonical.find_product_line(brand, listing.get("name") or ""):
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", listing["description"]))
    return canonical.line_from_description(brand, " ".join(text.split()), listing.get("category"))


def _cache_key(listing: dict, candidates: list[str], index: CatalogIndex) -> str:
    parts = [
        QUESTION_VERSION, jev.MODEL, norm_name(listing.get("name") or ""),
        listing.get("category") or "", listing.get("subtype") or "", listing.get("variant") or "",
        [(k, index.products[k].describe()) for k in candidates],
    ]
    # Only when it is in the question, so answers cached without one stay valid.
    line = described_line(listing, index)
    if line:
        parts.append(line)
    payload = json.dumps(parts, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class AnswerCache:
    def __init__(self, slug: str, enabled: bool = True):
        self.path = CACHE_DIR / f"{slug}.json"
        self.enabled = enabled
        self.data: dict[str, dict] = {}
        if enabled and self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                print(f"  [warn] unreadable match cache {self.path.name}; starting empty",
                      file=sys.stderr)

    def get(self, key: str) -> dict | None:
        return self.data.get(key) if self.enabled else None

    def put(self, key: str, value: dict) -> None:
        if self.enabled:
            self.data[key] = value

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)   # atomic: a kill mid-write cannot truncate the cache


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    listing: dict
    product_key: str | None
    entry: dict | None
    confidence: float
    method: str
    candidates: int = 0
    deterministic: str | None = None      # what the legacy tiers would have said
    probabilities: dict | None = None


def gate(pick: str | None, p: float, auto: float | None = None) -> str:
    if not pick or pick == NONE:
        return "none"
    if p >= (AUTO if auto is None else auto):
        return "jev"
    if p >= REVIEW:
        return "jev_review"
    return "none"


def resolve(catalog: dict, listings: list[dict], *, use_jev: bool,
            cache: AnswerCache | None = None, usage: jev.Usage | None = None,
            workers: int = 8, exclude: dict[str, str] | None = None) -> list[Decision]:
    """Decide every listing of one brand.

    `exclude` (listing id -> product key) removes that product from the listing's
    shortlist — the holdout used by --eval to measure how often Jev picks a wrong
    product when the right one is absent.
    """
    index = CatalogIndex(catalog)
    brand = catalog.get("brand_name") or ""
    cache = cache or AnswerCache(catalog.get("brand_slug") or "x", enabled=False)
    decisions: list[Decision | None] = [None] * len(listings)
    pending: list[tuple[int, list[str], dict[str, str], str]] = []
    jobs = []

    for i, l in enumerate(listings):
        name, cat = l.get("name") or "", l.get("category")
        det_key, det_conf, det_method = index.deterministic(name, cat)
        held_out = (exclude or {}).get(str(l.get("id")))
        if det_method == "exact" and det_key != held_out:
            decisions[i] = Decision(l, det_key, index.pick_entry(det_key, l.get("variant"), cat, name),
                                    1.0, "exact", deterministic=det_key)
            continue
        if not use_jev:
            entry = index.pick_entry(det_key, l.get("variant"), cat, name) if det_key else None
            decisions[i] = Decision(l, det_key, entry, det_conf, det_method, deterministic=det_key)
            continue
        cands = index.shortlist(name, cat, l.get("variant"), exclude=held_out,
                                subtype=l.get("subtype"))
        # Put the deterministic pick right after "none" so the model sees the
        # strongest lexical candidate first among the products.
        if det_key in cands:
            cands.remove(det_key)
            cands.insert(0, det_key)
        if not cands:
            decisions[i] = Decision(l, None, None, 0.0, "none", 0, det_key)
            continue
        key = _cache_key(l, cands, index)
        hit = cache.get(key)
        state, questions, labels = jev_question(brand, l, index, cands)
        if hit is not None:
            decisions[i] = _decide(l, index, labels, hit["pick"], hit["p"], hit.get("probs"),
                                   len(cands), det_key)
            continue
        pending.append((i, cands, labels, key))
        jobs.append((state, questions))

    if jobs:
        results = jev.ask_many(jobs, workers=workers, usage=usage)
        for (i, cands, labels, key), res in zip(pending, results):
            l = listings[i]
            if res is None:
                # No decision: reported as "error" so a caller holding an earlier
                # answer can keep it (the importer does); treated as no match
                # otherwise. Not cached, so the next run asks again.
                decisions[i] = Decision(l, None, None, 0.0, "error", len(cands))
                continue
            pick, p, probs = res.choice("product")
            cache.put(key, {"pick": pick, "p": p, "probs": probs, "model": res.model})
            decisions[i] = _decide(l, index, labels, pick, p, probs, len(cands), None)
    cache.save()
    return [d for d in decisions if d is not None]


def _decide(listing, index, labels, pick, p, probs, n_cands, det_key) -> Decision:
    method = gate(pick, p, auto_threshold(index.catalog))
    key = labels.get(pick) if method in ("jev", "jev_review") else None
    entry = index.pick_entry(key, listing.get("variant"), listing.get("category"),
                             listing.get("name") or "") if key else None
    conf = p if key else float((probs or {}).get(NONE, 0.0))
    return Decision(listing, key, entry, round(conf, 3), method, n_cands, det_key, probs)


# ---------------------------------------------------------------------------
# Listings in, decisions out
# ---------------------------------------------------------------------------

def fetch_listings() -> list[dict]:
    """Active listings over PostgREST, in the shape resolve() reads.

    Read-only, so it works from the sandbox; writing goes through psycopg2 (below),
    which needs the 5432 path the Render worker has.
    """
    import db_http
    rows = db_http.select_all(
        "listings",
        "select=id,scraped_name,scraped_brand,scraped_category,subtype,variant,description,"
        "catalog_entry_id,catalog_match_method&is_active=is.true&order=id")
    return [{"id": r["id"], "name": r.get("scraped_name") or "", "brand": r.get("scraped_brand"),
             "category": r.get("scraped_category"), "subtype": r.get("subtype"),
             "variant": r.get("variant"), "description": r.get("description"),
             "catalog_entry_id": r.get("catalog_entry_id"),
             "catalog_match_method": r.get("catalog_match_method")} for r in rows]


def write_decisions(decisions: list[Decision]) -> int:
    import psycopg2
    import psycopg2.extras
    catalog_store._load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set — --write needs a direct Postgres connection")
    # A failed call is not an answer: leave those listings' stored match alone.
    rows = [((d.entry or {}).get("id"), d.confidence if d.entry else None, d.method,
             str(d.listing["id"])) for d in decisions if d.method != "error"]
    if not rows:
        return 0
    conn = psycopg2.connect(url)
    try:
        cur = conn.cursor()
        psycopg2.extras.execute_values(
            cur,
            """
            UPDATE listings AS l SET
                catalog_entry_id         = v.entry_id::uuid,
                catalog_match_confidence = v.conf::real,
                catalog_match_method     = v.method
            FROM (VALUES %s) AS v(entry_id, conf, method, listing_id)
            WHERE l.id = v.listing_id::uuid
              -- a human's match is never overwritten by the pipeline
              AND COALESCE(l.catalog_match_method, '') <> 'manual'
            """,
            # One statement for every row: with paging, rowcount reports only the
            # last page, and the count printed is how an operator sees it landed.
            rows, page_size=len(rows),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(brand: str, decisions: list[Decision], catalog: dict) -> None:
    total = len(decisions) or 1
    by = Counter(d.method for d in decisions)
    n_products = len({e.get("product_key") for e in catalog.get("entries") or []})
    print(f"\n{brand}: {len(decisions)} active listings, catalog has {n_products} products "
          f"[{catalog.get('_source', '?')}]")
    order = ["exact", "substring", "token", "jev", "jev_review", "ambiguous", "none"]
    for m in order + sorted(set(by) - set(order)):
        if by.get(m):
            print(f"  {m:11} {by[m]:>6} {by[m] / total:>7.1%}")
    trusted = sum(by.get(m, 0) for m in TRUSTED_METHODS)
    print(f"  {'TRUSTED':11} {trusted:>6} {trusted / total:>7.1%}")


def evaluate(catalog: dict, listings: list[dict], usage: jev.Usage,
             cache: AnswerCache) -> dict:
    """How well does the Jev tier gate, measured without hand labels?

    Silver labels: listings where the deterministic tiers and Jev independently pick
    the same product (or the name is an exact title). Then the holdout: ask again with
    that product removed from the shortlist. The right answer is now "none", so any
    product Jev still picks at probability >= t is a false match at threshold t —
    the number that should set AUTO. Only listings that still have candidates after
    the holdout count; an empty shortlist is a free "none" and proves nothing.
    """
    index = CatalogIndex(catalog)
    first = resolve(catalog, listings, use_jev=True, cache=cache, usage=usage)
    silver: dict[str, str] = {}
    for d in first:
        det_key, _, _ = index.deterministic(d.listing.get("name") or "", d.listing.get("category"))
        if d.method == "exact" or (d.method == "jev" and det_key == d.product_key):
            silver[str(d.listing["id"])] = d.product_key
    labelled = [l for l in listings if str(l["id"]) in silver]
    holdout = resolve(catalog, labelled, use_jev=True,
                      cache=AnswerCache("holdout", enabled=False), usage=usage, exclude=silver)
    asked = [d for d in holdout if d.candidates > 0]

    def top_product_p(d: Decision) -> float:
        return max((p for k, p in (d.probabilities or {}).items() if k != NONE), default=0.0)

    out = {"listings": len(listings), "silver": len(labelled), "holdout_asked": len(asked),
           "first_pass": dict(Counter(d.method for d in first)), "false_match_at": {}}
    for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        out["false_match_at"][t] = sum(1 for d in asked if top_product_p(d) >= t) / max(1, len(asked))
    out["examples"] = [(d.listing.get("name"), index.products[silver[str(d.listing["id"])]].title,
                        round(top_product_p(d), 2),
                        max((k for k in (d.probabilities or {}) if k != NONE),
                            key=lambda k: d.probabilities[k], default=None))
                       for d in sorted(asked, key=top_product_p, reverse=True)[:8]]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Match listings to brand catalogs")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand", help="One brand, as written in listings")
    g.add_argument("--all", action="store_true", help="Every brand that has a catalog")
    ap.add_argument("--jev", action="store_true", help="Resolve non-exact listings with Jev")
    ap.add_argument("--write", action="store_true",
                    help="Persist catalog_entry_id/confidence/method (needs DATABASE_URL)")
    ap.add_argument("--eval", action="store_true", help="Measure Jev gating on silver labels")
    ap.add_argument("--source", choices=["auto", "db", "file"], default="auto",
                    help="Where catalogs come from (default: DB when reachable)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore cached Jev answers")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--misses", action="store_true", help="Print unresolved listings")
    ap.add_argument("--sample", type=int, default=0, help="Print N decisions to hand-check")
    ap.add_argument("--json", help="Write every decision to this file")
    args = ap.parse_args()

    if (args.jev or args.eval) and not jev.available():
        sys.exit("No OPENROUTER_API_KEY — the Jev tier needs it (or drop --jev)")

    catalogs = catalog_store.load_all(args.source)
    if args.brand:
        cat = catalog_store.for_brand(catalogs, args.brand)
        if not cat:
            sys.exit(f"No catalog for {args.brand!r}. Have: "
                     + ", ".join(c['brand_name'] for c in catalogs.values()))
        catalogs = {catalog_store.brand_key(args.brand): cat}

    all_listings = fetch_listings()
    by_brand: dict[str, list[dict]] = defaultdict(list)
    for l in all_listings:
        by_brand[catalog_store.brand_key(l.get("brand"))].append(l)

    usage = jev.Usage()
    everything: list[Decision] = []
    dump = []
    for key, cat in sorted(catalogs.items()):
        listings = by_brand.get(key, [])
        if not listings:
            print(f"\n{cat['brand_name']}: no active listings")
            continue
        if args.eval:
            cache = AnswerCache(cat.get("brand_slug") or key, enabled=not args.no_cache)
            res = evaluate(cat, listings, usage, cache)
            print(f"\n{cat['brand_name']}: {res['listings']} listings, first pass {res['first_pass']}")
            print(f"  silver labels (deterministic and Jev agree): {res['silver']}")
            print(f"  holdout — true product removed, {res['holdout_asked']} still had candidates:")
            for t, r in res["false_match_at"].items():
                print(f"    would match a WRONG product at p>={t:.1f}: {r:.1%}")
            print("  highest-probability wrong picks:")
            for name, truth, p, wrong in res["examples"]:
                print(f"    {p:.2f}  {name[:56]:56} true={truth!r} picked={wrong!r}")
            continue
        cache = AnswerCache(cat.get("brand_slug") or key, enabled=not args.no_cache)
        decisions = resolve(cat, listings, use_jev=args.jev, cache=cache, usage=usage,
                            workers=args.workers)
        report(cat["brand_name"], decisions, cat)
        everything.extend(decisions)
        index = CatalogIndex(cat)
        for d in decisions:
            p = index.products.get(d.product_key) if d.product_key else None
            dump.append({"listing_id": d.listing["id"], "brand": cat["brand_name"],
                         "name": d.listing.get("name"), "category": d.listing.get("category"),
                         "variant": d.listing.get("variant"), "method": d.method,
                         "confidence": d.confidence, "product": p.title if p else None,
                         "entry_variant": (d.entry or {}).get("variant"),
                         "candidates": d.candidates, "probabilities": d.probabilities})
        if args.sample:
            step = max(1, len(decisions) // args.sample)
            print(f"  --- {args.sample} decisions to hand-check ---")
            for d in decisions[::step][:args.sample]:
                p = index.products.get(d.product_key) if d.product_key else None
                print(f"  [{d.method} {d.confidence:.2f}] {d.listing.get('name', '')[:60]}")
                print(f"      -> {p.title if p else '—'}  {(d.entry or {}).get('variant') or ''}")
        if args.misses:
            print("  --- unresolved ---")
            for d in decisions:
                if d.method not in TRUSTED_METHODS:
                    print(f"  [{d.method:10} {d.confidence:.2f} c={d.candidates:>2}] "
                          f"{d.listing.get('category') or '?':11} {d.listing.get('name', '')[:70]}")

    if usage.requests or usage.failures:
        print("\n" + usage.summary())
    if args.json:
        Path(args.json).write_text(json.dumps(dump, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {len(dump)} decisions to {args.json}")
    if args.write and everything:
        n = write_decisions(everything)
        print(f"wrote match columns on {n} listings")


if __name__ == "__main__":
    main()
