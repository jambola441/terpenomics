#!/usr/bin/env python3
"""
storefront.py — A brand's catalog, read off its own website by a recipe.

A brand's site is the one place its products are written down by the brand itself.
A bootstrap catalog (catalog_bootstrap.py) is a consensus of how stores list a
brand; a storefront catalog is the brand's own word, and replaces the bootstrap for
that brand when pushed.

Sites differ, so each brand has a recipe, data/storefronts/<brand-slug>.json. A
recipe is written once — by an agent pass that studies the site, or by hand — and
from then on this script runs it with no model involved:

  source     where the products are (SOURCES): a Shopify store's /products.json, a
             WooCommerce Store API, a WordPress post type, product cards in a page's
             HTML (CSS selectors), or JSON — an API, or a blob a page embeds
  skip       what is not a product we model: apparel, gift cards, bundles
  category   the site's own fields (product_type, tags, title...) -> our category,
             and a subtype where the site says one the title does not
  title      regexes that split the site's title into line and strain (named groups
             `line`, `strain`, `size`), with constants for what the title leaves out,
             such as a gummy pack's dose

Each list is tried in order and the first rule that matches wins. A rule's `when`
holds regexes (re.search) over the product's fields: title, product_type, tags,
vendor, url, body, variant, meta (a source's structured extras as JSON text: SKU,
options, custom fields) — and, for a title rule, the category just decided. A title
rule's `match` is tried against the title; its `extract` adds groups found in other
fields, for a site that keeps the size in the description ("SIZE: 10CT STRENGTH:
100MG"). Groups: line, strain, size, size2 (read together with size).

Size and subtype come from the shared readers (sizes.py, taxonomy.token_subtype)
unless a rule sets them, so a storefront entry is written the way a bootstrap entry
is: weight by package total ("3.5g"), doses with their pack ("10pk 100mg"),
pre-rolls with no subtype. Sizes of one product share a product key, so the matcher
resolves a size inside a product rather than choosing between two "Mule Fuel"s.

An entry's external id is its identity followed by the site's own id
("sf:edible:gummy:calm:peach:10pk100mg:4412..."), the way a bootstrap id is its
identity. A push never rewrites an existing entry's identity fields (a person's edits
are kept), so a product the site renames, or a recipe now reads differently, arrives
as a new entry and the old one is retired.

Stores sell products a brand's site does not list: old stock, a size the site
dropped, a format it never showed (Florist Farms on 2026-10-05: Gorilla Glue vapes at
four stores, absent from the site). So a push is the site's entries plus the stores'
consensus for those products only — catalog_bootstrap.propose() over our listings of
the brand, minus every product the site has. "The site has it" allows for spelling
(SIMILAR): stores write "Mandarin Dog" and "Granddaddy Purp" for the site's
"Mandarine Dog" and "Granddaddy Purple", and those must not come back as duplicates.

The push retires every other entry, the brand's old bootstrap entries included, and
records the site as the catalog's source, so catalog_bootstrap --rebuild leaves the
brand to this script from then on. A recipe that leaves more than MAX_UNPARSED of
the site's items unhandled is not pushed at all: that is the site changing shape
under the recipe rather than products going away. Check it and fix the recipe (or
re-run the agent pass).

`check` is a recipe's test. It fetches the site, lists every product no rule
handled, and compares the result with what stores sell under the brand: the
products the bootstrap would build from our listings that the site lacks. Run it
after writing or changing a recipe, and whenever a refresh reports drift.

Usage
-----
  python scripts/storefront.py check --brand "Florist Farms"
  python scripts/storefront.py fetch --brand "Florist Farms"     # data/catalogs/<slug>.json
  python scripts/storefront.py push  --brand "Florist Farms" --via-http
  python scripts/storefront.py push  --all --via-http            # every recipe
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sizes  # noqa: E402
import taxonomy  # noqa: E402
from brand_catalog import norm_name, strip_brand  # noqa: E402
import catalog_bootstrap  # noqa: E402
from catalog_bootstrap import squash, strain_key  # noqa: E402
from scraper_common import slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RECIPE_DIR = ROOT / "data" / "storefronts"
CATALOG_DIR = ROOT / "data" / "catalogs"
TIMEOUT_SECONDS = 30
USER_AGENT = "Mozilla/5.0 (compatible; terpenomics-catalog/1.0)"
FIELDS = ("title", "product_type", "tags", "vendor", "url", "body", "variant", "meta")
GROUPS = {"line", "strain", "size", "size2"}
TITLE_FIELDS = FIELDS + ("category",)
SET_KEYS = {"category", "subtype", "line", "strain", "size"}
MAX_UNPARSED = 0.10
# difflib ratio at which two names of one category and size are one product:
# "mandarindog"/"mandarinedog" 0.96, "grandadypurp"/"grandadypurple" 0.92, while
# "bluedream"/"bluedreamhaze" is 0.82 and "gelato33"/"gelato41" 0.75.
SIMILAR = 0.85


@dataclass
class Item:
    """One sellable thing as the site lists it: a product, or one of its variants."""
    id: str
    title: str
    variant: str | None = None
    fields: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- sources

def _get_text(url: str, post: str | None = None) -> str:
    """The body at `url` as text. Some hosts send gzip whether or not it was asked for
    (Webflow's page data), so the magic bytes decide, not the headers."""
    import gzip
    req = urllib.request.Request(url, data=post.encode() if post is not None else None, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        **({"Content-Type": "application/x-www-form-urlencoded"} if post is not None else {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
        body = r.read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body.decode("utf-8", errors="replace")


def _get_json(url: str):
    return json.loads(_get_text(url))


def _text(fragment: str | None) -> str:
    """HTML to one line of plain text."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def _page(url: str, **params) -> str:
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query))
    query.update({k: str(v) for k, v in params.items()})
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _variant_label(label: str | None) -> str | None:
    label = (label or "").strip()
    return None if not label or label.lower() == "default title" else label


def shopify(source: dict, get=_get_json) -> list[Item]:
    """A Shopify store's public /products.json, 250 products a page, one item per
    variant: the variant id is the entry's external id, as brand_catalog.py has
    always used for Shopify."""
    items = []
    for page in range(1, 41):
        products = get(_page(source["url"], limit=250, page=page)).get("products") or []
        for p in products:
            base = {"title": (p.get("title") or "").strip(),
                    "product_type": p.get("product_type") or "",
                    "tags": ", ".join(p.get("tags") or []),
                    "vendor": p.get("vendor") or "",
                    "url": urllib.parse.urljoin(source["url"], f"/products/{p.get('handle')}"),
                    "body": _text(p.get("body_html"))[:2000]}
            for v in p.get("variants") or [{"id": p.get("id")}]:
                label = _variant_label(v.get("title"))
                meta = json.dumps({"sku": v.get("sku"), "options": [v.get(f"option{i}") for i in (1, 2, 3)]})
                items.append(Item(str(v.get("id")), base["title"], label,
                                  {**base, "variant": label or "", "meta": meta}))
        if len(products) < 250:
            break
    return items


def woocommerce(source: dict, get=_get_json) -> list[Item]:
    """WooCommerce's public Store API (/wp-json/wc/store/v1/products), 100 a page, one
    item per variation where a product has them."""
    items = []
    for page in range(1, 101):
        products = get(_page(source["url"], per_page=100, page=page)) or []
        for p in products:
            base = {"title": _text(p.get("name")),
                    "product_type": ", ".join(_text(c.get("name")) for c in p.get("categories") or []),
                    "tags": ", ".join(_text(t.get("name")) for t in p.get("tags") or []),
                    "vendor": "",
                    "url": p.get("permalink") or "",
                    "body": _text(f"{p.get('short_description') or ''} {p.get('description') or ''}")[:2000],
                    "meta": json.dumps({"sku": p.get("sku"), "attributes": p.get("attributes")})}
            variations = p.get("variations") or []
            for v in variations:
                label = " / ".join(a.get("value") or "" for a in v.get("attributes") or []) or None
                items.append(Item(str(v.get("id")), base["title"], label, {**base, "variant": label or ""}))
            if not variations:
                items.append(Item(str(p.get("id")), base["title"], None, {**base, "variant": ""}))
        if len(products) < 100:
            break
    return items


def wordpress(source: dict, get=_get_json) -> list[Item]:
    """A WordPress post type over the REST API (/wp-json/wp/v2/<type>), 100 a page, with
    `_embed` so each post's taxonomy terms come with their names (tags). class_list —
    the term slugs WordPress puts on the post — is product_type; custom fields (ACF)
    are meta."""
    import urllib.error
    items = []
    for page in range(1, 101):
        try:
            posts = get(_page(source["url"], per_page=100, page=page, _embed=1)) or []
        except urllib.error.HTTPError as e:
            if e.code == 400 and page > 1:     # past the last page
                break
            raise
        for p in posts:
            classes = p.get("class_list") or []
            classes = list(classes.values()) if isinstance(classes, dict) else classes
            terms = [t.get("name") or "" for group in (p.get("_embedded") or {}).get("wp:term") or []
                     for t in group or []]
            title = _text((p.get("title") or {}).get("rendered"))
            items.append(Item(str(p.get("id")), title, None, {
                "title": title, "product_type": " ".join(classes),
                "tags": ", ".join(_text(t) for t in terms if t), "vendor": "", "url": p.get("link") or "",
                "body": _text(f"{(p.get('content') or {}).get('rendered') or ''} "
                              f"{(p.get('excerpt') or {}).get('rendered') or ''}")[:2000],
                "variant": "", "meta": json.dumps(p.get("acf") or p.get("meta") or {})}))
        if len(posts) < 100:
            break
    return items


def _pages(source: dict, get_text=_get_text) -> list[tuple[str, str]]:
    """(url, text) for every page a source names: `url` alone; `url` with `pages`
    ({"param": "page", "from": 1, "to": 15}, stopping at the first empty page is the
    caller's business); `urls`; or `sitemap` ({"url": ..., "match": regex}) for a site
    whose products are each on their own page."""
    post = source.get("post")
    if source.get("sitemap"):
        sm = source["sitemap"]
        urls = [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", get_text(sm["url"]))
                if re.search(sm.get("match") or "", u)]
    elif source.get("pages"):
        pg = source["pages"]
        urls = [_page(source["url"], **{pg["param"]: n}) for n in range(pg.get("from", 1), pg["to"] + 1)]
    else:
        urls = source.get("urls") or [source["url"]]
    return [(u, get_text(u, post)) for u in urls]


def _css(node, spec: str) -> str:
    """One field from a node: "h3", "a@href", "@data-category", "." for the node's own
    text. Several matches are joined with " | "."""
    sel, _, attr = spec.partition("@")
    found = [node] if sel.strip() in ("", ".") else node.select(sel)
    vals = [(n.get(attr) or "") if attr else n.get_text(" ", strip=True) for n in found]
    vals = [" ".join(v) if isinstance(v, list) else v for v in vals]
    return " | ".join(v.strip() for v in vals if v and v.strip())


def html_cards(source: dict, get_text=_get_text) -> list[Item]:
    """Product cards in a page's HTML: `item` is a CSS selector for one product (the
    whole page when absent, as on a sitemap of product pages), `fields` maps our
    fields to selectors within it. A paged listing stops at its first empty page."""
    from bs4 import BeautifulSoup
    items, spec = [], source["fields"]
    for url, text in _pages(source, get_text):
        soup = BeautifulSoup(text, "html.parser")
        cards = soup.select(source["item"]) if source.get("item") else [soup]
        if not cards and source.get("pages"):
            break
        for card in cards:
            f = {k: _css(card, sel) for k, sel in spec.items()}
            if f.get("url"):
                f["url"] = urllib.parse.urljoin(url, f["url"])
            title = f.get("title") or ""
            if title:
                items.append(Item(f.get("id") or f.get("url") or squash(title), title,
                                  f.get("variant") or None, {**{k: "" for k in FIELDS}, **f}))
    return items


def _at(node, path: str):
    """A dot path into parsed JSON; "*" fans out over a list or a dict's values."""
    nodes = [node]
    for key in [k for k in path.split(".") if k]:
        nxt = []
        for n in nodes:
            if key == "*":
                nxt += list(n.values()) if isinstance(n, dict) else list(n) if isinstance(n, list) else []
            elif isinstance(n, dict) and key in n:
                nxt.append(n[key])
            elif isinstance(n, list) and key.isdigit() and int(key) < len(n):
                nxt.append(n[int(key)])
        nodes = nxt
    return nodes


def _flat(values) -> str:
    out = []
    for v in values:
        if isinstance(v, list):
            out.append(_flat(v))
        elif isinstance(v, dict):
            out.append(json.dumps(v))
        elif v is not None:
            out.append(_text(str(v)))
    return ", ".join(x for x in out if x)


def json_items(source: dict, get_text=_get_text) -> list[Item]:
    """Products in JSON: an API (a Gatsby page-data file, a headless CMS query) or a
    blob a page embeds, pulled out by `extract` (a regex whose first group is the
    JSON). `lenient` parses a JavaScript object literal (unquoted keys) with json5.
    `items` is the dot path to the products; `fields` maps our fields to dot paths
    within one."""
    items, spec = [], source["fields"]
    for url, text in _pages(source, get_text):
        if source.get("extract"):
            m = re.search(source["extract"], text, re.S)
            if not m:
                raise ValueError(f"{url}: extract pattern found nothing")
            text = m.group(1)
        if source.get("lenient"):
            import json5
            data = json5.loads(text)
        else:
            data = json.loads(text)
        for node in _at(data, source["items"]):
            f = {k: _flat(_at(node, path)) for k, path in spec.items()}
            if f.get("url"):
                f["url"] = urllib.parse.urljoin(url, f["url"])
            title = f.get("title") or ""
            if title:
                items.append(Item(f.get("id") or f.get("url") or squash(title), title,
                                  f.get("variant") or None, {**{k: "" for k in FIELDS}, **f}))
    return items


# kind -> (reader, the catalog's source_method)
SOURCES = {
    "shopify_json": (shopify, "shopify_products_json"),
    "wc_store_api": (woocommerce, "wc_store_api"),
    "wp_json": (wordpress, "wp_json"),
    "html": (html_cards, "storefront_html"),
    "json": (json_items, "storefront_json"),
}


# --------------------------------------------------------------------------- recipes

def recipe_path(brand: str) -> Path:
    return RECIPE_DIR / f"{slugify(brand)}.json"


def load_recipe(brand: str) -> dict:
    path = recipe_path(brand)
    if not path.is_file():
        raise SystemExit(f"No recipe at {path}")
    return validate(json.loads(path.read_text(encoding="utf-8")), str(path))


def all_recipes() -> list[dict]:
    return [validate(json.loads(p.read_text(encoding="utf-8")), str(p))
            for p in sorted(RECIPE_DIR.glob("*.json"))]


def validate(recipe: dict, where: str = "recipe") -> dict:
    """Fail on load, naming the rule, rather than half-way through a fetch."""
    def bad(msg):
        raise SystemExit(f"{where}: {msg}")

    if not recipe.get("brand"):
        bad("no brand")
    kind = (recipe.get("source") or {}).get("kind")
    if kind not in SOURCES:
        bad(f"source.kind {kind!r} is not one of {sorted(SOURCES)}")
    src = recipe["source"]
    if not (src.get("url") or src.get("urls") or src.get("sitemap")):
        bad("source needs url, urls or sitemap")
    if kind in ("html", "json") and not (src.get("fields") or {}).get("title"):
        bad(f"source.fields.title is required for {kind}")
    if kind == "json" and not src.get("items"):
        bad("source.items (the dot path to the products) is required for json")
    unknown = set(src.get("fields") or {}) - set(FIELDS) - {"id"}
    if unknown:
        bad(f"source.fields: unknown fields {sorted(unknown)} (fields: id, {', '.join(FIELDS)})")
    for section in ("skip", "category", "title"):
        fields = TITLE_FIELDS if section == "title" else FIELDS
        for i, rule in enumerate(recipe.get(section) or []):
            for f, pattern in (rule.get("when") or {}).items():
                if f not in fields:
                    bad(f"{section}[{i}].when: unknown field {f!r} (fields: {', '.join(fields)})")
                try:
                    re.compile(pattern)
                except re.error as e:
                    bad(f"{section}[{i}].when.{f}: {e}")
            unknown = set(rule.get("set") or {}) - SET_KEYS
            if unknown:
                bad(f"{section}[{i}].set: unknown keys {sorted(unknown)}")
    for i, rule in enumerate(recipe.get("category") or []):
        cat = (rule.get("set") or {}).get("category")
        if cat not in taxonomy.SPECS:
            bad(f"category[{i}]: category {cat!r} is not one of {sorted(taxonomy.SPECS)}")
    for i, rule in enumerate(recipe.get("title") or []):
        patterns = {"match": rule.get("match") or "",
                    **{f"extract.{f}": p for f, p in (rule.get("extract") or {}).items()}}
        for where_, pattern in patterns.items():
            if where_.startswith("extract.") and where_[8:] not in FIELDS:
                bad(f"title[{i}].{where_}: unknown field")
            try:
                names = set(re.compile(pattern).groupindex)
            except re.error as e:
                bad(f"title[{i}].{where_}: {e}")
            if names - GROUPS:
                bad(f"title[{i}].{where_}: groups other than {'/'.join(sorted(GROUPS))}: {sorted(names)}")
    return recipe


def fetch(recipe: dict) -> list[Item]:
    reader, _ = SOURCES[recipe["source"]["kind"]]
    return reader(recipe["source"])


# --------------------------------------------------------------------------- build

def _when(rule: dict, fields: dict) -> bool:
    return all(re.search(p, fields.get(f) or "") for f, p in (rule.get("when") or {}).items())


def _clean(s: str | None) -> str | None:
    s = re.sub(r"\s+", " ", s or "").strip(" -|,:")
    return s or None


def _variant(size: sizes.Size, measure: str) -> str | None:
    if measure == "weight" and size.grams is not None:
        return f"{size.grams:g}g"          # the package total, as bootstrap entries have it
    return size.label() or None


def _size_complete(entry: dict) -> bool:
    s = sizes.parse(entry.get("variant"), category=entry["category"])
    measure = taxonomy.SPECS[entry["category"]].measure
    return (s.grams is not None) if measure == "weight" else \
        (s.mg is not None) if measure == "dose" else True


def build(recipe: dict, items: list[Item]) -> tuple[dict, dict]:
    """The catalog document for the recipe's brand, and what happened to each item."""
    brand = recipe["brand"]
    _, method = SOURCES[recipe["source"]["kind"]]
    entries, skipped, unparsed = [], Counter(), []
    for it in items:
        rule = next((r for r in recipe.get("skip") or [] if _when(r, it.fields)), None)
        if rule is not None:
            skipped[rule.get("why") or "skip rule"] += 1
            continue
        crule = next((r for r in recipe.get("category") or [] if _when(r, it.fields)), None)
        if crule is None:
            unparsed.append({"title": it.title, "variant": it.variant, "why": "no category rule"})
            continue
        category = crule["set"]["category"]
        if category not in taxonomy.catalogable():
            skipped[f"{category}: not catalogued"] += 1
            continue
        trule, m = None, None
        fields = {**it.fields, "category": category}
        for r in recipe.get("title") or []:
            if _when(r, fields) and (m := re.search(r["match"], it.title)):
                trule = r
                break
        if trule is None:
            unparsed.append({"title": it.title, "variant": it.variant, "why": "no title rule"})
            continue
        consts = {**crule.get("set", {}), **trule.get("set", {})}
        got = {k: v for k, v in m.groupdict().items() if v}
        for f, pattern in (trule.get("extract") or {}).items():
            if (em := re.search(pattern, fields.get(f) or "")):
                got = {**{k: v for k, v in em.groupdict().items() if v}, **got}
        line = _clean(got.get("line") or consts.get("line"))
        strain = _clean(got.get("strain") or consts.get("strain"))
        stated = " ".join(x for x in (got.get("size"), got.get("size2")) if x) or consts.get("size")
        spec = taxonomy.SPECS[category]
        size = sizes.parse(*([stated] if stated else [it.variant, it.title]), category=category)
        subtype = consts.get("subtype") or taxonomy.token_subtype(category, it.title) \
            or spec.default_subtype
        if not taxonomy.keeps_subtype(category):
            subtype = None
        name = " ".join(x for x in (line, strain) if x) or it.title
        product_key = f"sf:{category}:{subtype or ''}:{squash(line)}:{squash(strain or name)}"
        variant = _variant(size, spec.measure) or it.variant
        entries.append({
            "external_id": f"{product_key}:{squash(variant) or 'nosize'}:{it.id}",
            "product_key": product_key,
            "name": name,
            "product_line": line,
            "category": category,
            "subtype": subtype,
            "strain": strain,
            "variant": variant,
            "attributes": None,
            "match_terms": sorted({t for t in (strip_brand(it.title, brand), norm_name(it.title)) if t}),
            "source": method,
        })
    doc = {
        "brand_slug": slugify(brand),
        "brand_name": brand,
        "source_url": recipe["source"]["url"],
        "source_method": method,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "product_count": len({e["product_key"] for e in entries}),
        "entries": entries,
    }
    report = {
        "brand": brand, "items": len(items), "entries": len(entries),
        "products": doc["product_count"], "skipped": dict(skipped), "unparsed": unparsed,
        "by_category": dict(Counter(e["category"] for e in entries)),
        "size_incomplete": [f"{e['name']} ({e['category']}: {e['variant']})"
                            for e in entries if not _size_complete(e)],
    }
    return doc, report


# --------------------------------------------------------------------------- stores

def _total(entry: dict) -> str:
    s = sizes.parse(entry.get("variant"), category=entry["category"])
    return f"{s.grams:g}g" if s.grams is not None else f"{s.mg:g}mg" if s.mg is not None else ""


def _names(entry: dict) -> dict:
    """The entry's name keys, norm_name first so "Strawberries & Cream" is "Strawberries
    and Cream": the line, the strain, and both read together."""
    line = norm_name(entry.get("product_line") or "")
    strain = norm_name(entry.get("strain") or entry.get("name") or "")
    return {"line": strain_key(line), "strain": strain_key(strain), "full": strain_key(line + strain)}


def _same_names(a: dict, b: dict) -> bool:
    """One product's two names. Exactly the same with the line read in or left out (a
    store that writes "Live Resin Jealousy" as the strain, or drops the line); or, where
    the lines do not disagree, strains that differ only in spelling ("Mandarin Dog",
    "Mandarine Dog"). Never a ratio over line and strain together: a shared line makes
    "Live Resin Jealousy Haze" look like "Live Resin Jealousy"."""
    if a["full"] in (b["full"], b["strain"]) or a["strain"] == b["full"]:
        return True
    lines_agree = not a["line"] or not b["line"] or a["line"] == b["line"]
    return lines_agree and SequenceMatcher(None, a["strain"], b["strain"]).ratio() >= SIMILAR


def split_store_products(doc: dict, listings: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """The products stores sell under the brand, as catalog_bootstrap.propose() builds
    them from our listings: those the site's catalog has, those only stores have, and
    the store names to add to site entries ({external_id: names}).

    A store product that matches one site product unambiguously brings its store
    names along, so those listings keep resolving `exact`, with no model call, as they
    did against the bootstrap entry. One that matches two (stores' "Mule Fuel 1g"
    against the site's plain and Live Resin Infused singles) brings none."""
    proposed = catalog_bootstrap.propose(doc["brand_name"], listings)["catalog"]["entries"]
    site = defaultdict(list)
    for e in doc["entries"]:
        site[e["category"]].append((_total(e), _names(e), e))
    found, only_stores, terms = [], [], defaultdict(set)
    for p in proposed:
        total, names = _total(p), _names(p)
        hits = [e for t, n, e in site[p["category"]]
                if catalog_bootstrap._same_total(total, t) and _same_names(names, n)]
        if not hits:
            only_stores.append(p)
            continue
        found.append(p)
        if len({e["product_key"] for e in hits}) == 1:
            for e in hits:
                terms[e["external_id"]].update(p.get("match_terms") or [])
    return found, only_stores, dict(terms)


def with_store_products(doc: dict, only_stores: list[dict], terms: dict | None = None) -> dict:
    """The catalog to push: the site's entries, with the store names that resolve to
    them, then the stores' consensus for products the site does not list. Those keep
    their bootstrap ids and source, so they read as what they are in the admin and stay
    stable from push to push."""
    terms = terms or {}
    site = [{**e, "match_terms": sorted(set(e["match_terms"]) | terms.get(e["external_id"], set()))}
            for e in doc["entries"]]
    return {**doc, "entries": site + only_stores,
            "product_count": len({e["product_key"] for e in site + only_stores})}


def store_listings(brand: str, via_http: bool) -> list[dict]:
    """Our active listings of the brand, in the shape catalog_bootstrap reads: over
    Supabase's REST API from a sandbox, over DATABASE_URL on the worker."""
    cols = ("id", "dispensary_id", "scraped_name", "scraped_brand", "scraped_category", "subtype",
            "strain", "product_line", "variant")
    if via_http:
        import db_http
        rows = db_http.select_all(
            "listings", f"select={','.join(cols)}&is_active=is.true"
                        f"&scraped_brand=eq.{urllib.parse.quote(brand)}&order=id")
    else:
        import brand_catalog
        conn = brand_catalog._connect()
        cur = conn.cursor()
        cur.execute(f"SELECT {', '.join(cols)} FROM listings WHERE is_active AND scraped_brand = %s "
                    "ORDER BY id", (brand,))
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
    return [{"id": str(r["id"]), "dispensary_id": str(r["dispensary_id"]),
             "name": r.get("scraped_name") or "", "brand": r.get("scraped_brand"),
             "category": r.get("scraped_category"), "subtype": r.get("subtype"),
             "strain": r.get("strain"), "product_line": r.get("product_line"),
             "variant": r.get("variant")} for r in rows]


def refusal(report: dict) -> str | None:
    """Why a push must not happen, or None."""
    handled = report["items"] - sum(report["skipped"].values())
    if not report["entries"]:
        return "no entries"
    if len(report["unparsed"]) > MAX_UNPARSED * max(handled, 1):
        return (f"{len(report['unparsed'])} of {handled} items no rule handled; the site has "
                f"changed shape. Run check and fix the recipe.")
    return None


def print_check(report: dict, found: list[dict] | None, only_stores: list[dict] | None) -> None:
    print(f"{report['brand']}: {report['items']} items -> {report['entries']} entries, "
          f"{report['products']} products {report['by_category']}")
    if report["skipped"]:
        print("  skipped: " + ", ".join(f"{k} {v}" for k, v in report["skipped"].items()))
    for u in report["unparsed"]:
        print(f"  UNPARSED ({u['why']}): {u['title']!r}" + (f" [{u['variant']}]" if u["variant"] else ""))
    for s in report["size_incomplete"]:
        print(f"  NO SIZE: {s}")
    if found is not None:
        print(f"  stores sell {len(found) + len(only_stores)} products (2+ stores): {len(found)} on the "
              f"site, {len(only_stores)} only at stores (kept from the stores' consensus):")
        for e in sorted(only_stores, key=lambda e: e["name"]):
            print(f"    - {e['name']} ({e['category']} {e['variant'] or ''}, {e['support']} stores)")


# --------------------------------------------------------------------------- CLI

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("check", "fetch", "push"))
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--brand")
    who.add_argument("--all", action="store_true", help="every recipe in data/storefronts/")
    ap.add_argument("--via-http", action="store_true", default=os.environ.get("DB_VIA_HTTP") == "1",
                    help="push over Supabase's REST API (a sandbox; DB_ACCESS.md)")
    ap.add_argument("--dry-run", action="store_true", help="push: report the effect, write nothing")
    ap.add_argument("--offline", action="store_true",
                    help="skip our listings: check without the comparison, push the site alone")
    args = ap.parse_args()

    recipes = all_recipes() if args.all else [load_recipe(args.brand)]
    failed = 0
    for recipe in recipes:
        try:
            doc, report = build(recipe, fetch(recipe))
        except Exception as e:  # one site down must not stop the rest
            print(f"{recipe['brand']}: fetch failed: {e}")
            failed += 1
            continue
        found = only_stores = terms = None
        if not args.offline:
            found, only_stores, terms = split_store_products(
                doc, store_listings(recipe["brand"], args.via_http))
        if args.command == "check":
            print_check(report, found, only_stores)
        elif args.command == "fetch":
            CATALOG_DIR.mkdir(parents=True, exist_ok=True)
            path = CATALOG_DIR / f"{doc['brand_slug']}.json"
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"{recipe['brand']}: {report['entries']} entries -> {path}")
        else:
            import brand_catalog
            why = refusal(report)
            if why:
                print(f"{recipe['brand']}: NOT pushed — {why}")
                failed += 1
                continue
            if report["unparsed"]:
                print(f"  {recipe['brand']}: {len(report['unparsed'])} items no rule handled "
                      f"(run check) — pushing the rest")
            print(f"{recipe['brand']}: {report['entries']} site entries + {len(only_stores or [])} "
                  f"products only stores sell; store names carried to {len(terms or {})} site entries")
            brand_catalog.push(with_store_products(doc, only_stores or [], terms),
                               dry_run=args.dry_run, via_http=args.via_http)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
