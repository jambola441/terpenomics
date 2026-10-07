"""
review_tools.py — The review agent's tools, independent of which model drives them.

The review agent labels listings Jev was unsure of and that no catalog entry settled
(evals/enrich/CONVENTIONS.md is the labelling standard). These are its tools; the
agent loop that calls a model lives elsewhere. Every tool here reads only: answers
are returned to the caller, and a catalog fix is only ever proposed, never written.

Each tool is a function taking keyword arguments and returning a JSON-serialisable
dict, with a JSON schema in TOOLS. ReviewContext holds what they read: the catalogs,
the live listings of the queued brands, the run's typical prices.

    ctx = ReviewContext.from_db(brands=["Grön"])
    run_tool(ctx, "search_catalog", {"brand": "Grön", "query": "baja blaze"})
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

import catalog_store
import size_candidates
import size_choice
import sizes
import taxonomy

MAX_RESULTS = 25
PAGE_CHARS = 4000


@dataclass
class ReviewContext:
    """What the tools read. `listings` are the live listings of the brands under
    review, as {id, brand, name, category, size_field, price_cents, description,
    url, strain, product_line, store, catalog_entry_id, catalog_match_method}."""
    catalogs: dict                                   # brand_key -> catalog (catalog_store shape)
    listings: list[dict] = field(default_factory=list)
    prices: size_choice.PriceBook = field(default_factory=size_choice.PriceBook)
    queue: dict[str, dict] = field(default_factory=dict)   # listing id -> the listing under review
    proposals: list[dict] = field(default_factory=list)
    answers: dict[str, dict] = field(default_factory=dict)
    fetch_page: callable = None                      # url -> html; None turns the tool off

    @classmethod
    def from_db(cls, brands: list[str]) -> "ReviewContext":
        """Catalogs and the live listings of `brands`, over the same transport the
        pipeline uses (DB_VIA_HTTP or DATABASE_URL)."""
        import os
        catalogs = catalog_store.load_all("db")
        keys = {catalog_store.brand_key(b) for b in brands}
        listings = []
        if os.environ.get("DB_VIA_HTTP", "").strip().lower() in ("1", "true", "yes"):
            import db_http
            cols = ("id,scraped_brand,scraped_name,scraped_category,variant,price_cents,description,url,"
                    "strain,product_line,dispensary_id,catalog_entry_id,catalog_match_method")
            for row in db_http.select_all("listings", f"select={cols}&is_active=eq.true"):
                if catalog_store.brand_key(row.get("scraped_brand")) in keys:
                    listings.append(_listing(row))
        else:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""SELECT id, scraped_brand, scraped_name, scraped_category, variant,
                                          price_cents, description, url, strain, product_line,
                                          dispensary_id, catalog_entry_id, catalog_match_method
                                   FROM listings WHERE is_active""")
                    listings = [_listing(dict(r)) for r in cur.fetchall()
                                if catalog_store.brand_key(r["scraped_brand"]) in keys]
            finally:
                conn.close()
        return cls(catalogs=catalogs, listings=listings, prices=size_choice.prices_for_run(),
                   fetch_page=_http_get)


def _listing(row: dict) -> dict:
    return {"id": str(row["id"]), "brand": row.get("scraped_brand") or "", "name": row.get("scraped_name") or "",
            "category": row.get("scraped_category"), "size_field": row.get("variant"),
            "price_cents": row.get("price_cents"), "description": row.get("description"),
            "url": row.get("url"), "strain": row.get("strain"), "product_line": row.get("product_line"),
            "store": str(row.get("dispensary_id") or ""), "catalog_entry_id": row.get("catalog_entry_id"),
            "catalog_match_method": row.get("catalog_match_method")}


def _http_get(url: str) -> str:
    import requests
    r = requests.get(url, timeout=15, headers={"User-Agent": "terpenomics-review/1.0"})
    r.raise_for_status()
    return r.text


def _words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _score(query: str, *texts: str | None) -> float:
    q = _words(query)
    if not q:
        return 0.0
    have = set().union(*(_words(t) for t in texts))
    return len(q & have) / len(q)


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------

def search_catalog(ctx: ReviewContext, brand: str, query: str = "") -> dict:
    """The brand's catalog entries best matching `query` (all when empty)."""
    cat = ctx.catalogs.get(catalog_store.brand_key(brand))
    if not cat:
        return {"brand": brand, "has_catalog": False, "entries": []}
    rows = []
    for e in cat.get("entries") or []:
        s = _score(query, e.get("name"), e.get("strain"), e.get("product_line")) if query else 1.0
        if s > 0:
            rows.append((s, e))
    rows.sort(key=lambda x: -x[0])
    out = []
    for _, e in rows[:MAX_RESULTS]:
        unit = size_candidates.unit_of(e.get("category"))
        parsed = sizes.parse(e.get("variant"), category=e.get("category"))
        value = parsed.mg if unit == "mg" else parsed.grams
        typical = ctx.prices.product.get(f"{e.get('catalog_id')}|{e.get('product_key') or e.get('id')}|{round(value, 3):g}") \
            if value is not None else None
        out.append({"entry_id": e.get("id"), "name": e.get("name"), "category": e.get("category"),
                    "subtype": e.get("subtype"), "strain": e.get("strain"), "product_line": e.get("product_line"),
                    "size": e.get("variant"),
                    "typical_price": f"${typical['median'] / 100:,.2f}" if typical else None})
    return {"brand": cat.get("brand_name") or brand, "has_catalog": True,
            "source": cat.get("source_method"), "entries": out}


def other_store_listings(ctx: ReviewContext, brand: str, query: str) -> dict:
    """How other dispensaries list the brand's products matching `query`: their names,
    sizes, prices, and the strain and line already recorded for them."""
    key = catalog_store.brand_key(brand)
    hits = [(_score(query, l["name"]), l) for l in ctx.listings
            if catalog_store.brand_key(l["brand"]) == key and l["id"] not in ctx.queue]
    hits = sorted([h for h in hits if h[0] > 0], key=lambda x: -x[0])[:MAX_RESULTS]
    return {"brand": brand, "listings": [
        {"store": l["store"], "name": l["name"], "size_field": l["size_field"],
         "price": f"${l['price_cents'] / 100:,.2f}" if l.get("price_cents") else None,
         "strain": l.get("strain"), "product_line": l.get("product_line"),
         "catalog_match": l.get("catalog_match_method")} for _, l in hits]}


def listing_page(ctx: ReviewContext, listing_id: str) -> dict:
    """The text of the listing's own product page on the dispensary's site, when the
    store records its URL. Only that URL: the agent cannot fetch anything else here."""
    l = ctx.queue.get(listing_id)
    if not l:
        return {"error": f"{listing_id} is not a listing under review"}
    if not l.get("url") or ctx.fetch_page is None:
        return {"listing_id": listing_id, "text": None, "note": "no product page recorded"}
    try:
        raw = ctx.fetch_page(l["url"])
    except Exception as e:  # noqa: BLE001 — a dead page is an answer, not a crash
        return {"listing_id": listing_id, "text": None, "note": f"page unavailable: {e}"}
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()
    return {"listing_id": listing_id, "url": l["url"], "text": text[:PAGE_CHARS]}


def size_readings(ctx: ReviewContext, listing_id: str) -> dict:
    """Every size the listing's texts could mean (size_candidates), each with where it
    comes from and what a package that size typically sells for."""
    l = ctx.queue.get(listing_id)
    if not l:
        return {"error": f"{listing_id} is not a listing under review"}
    item = size_choice.Item(name=l["name"], category=l["category"], variant=l.get("size_field"),
                            description=l.get("description"), brand=l["brand"], price_cents=l.get("price_cents"))
    a = size_candidates.assess({"variant": l.get("size_field"), "scraped_name": l["name"],
                                "description": l.get("description"), "scraped_category": l["category"]})
    unit = size_candidates.unit_of(l["category"])
    readings = [{"size": c.label(), "source": c.source, "reading": c.reading, "likely": c.likely}
                for c in a.candidates]
    prices = {f"{v:g}{unit}": ctx.prices.size_price(item, v) for v in a.options()} if unit else {}
    pg = ctx.prices.per_gram(item) if unit == "g" else None
    return {"listing_id": listing_id, "unit": unit, "status": a.status, "readings": readings,
            "typical_prices": prices,
            "brand_price_per_gram": f"${pg[0] / 100:,.2f} ({pg[1]})" if pg else None,
            "listing_price": f"${l['price_cents'] / 100:,.2f}" if l.get("price_cents") else None}


def submit_labels(ctx: ReviewContext, listing_id: str, category: str, strain: str | None,
                  product_line: str | None, size: str | None, confidence: str,
                  evidence: str, subtype: str | None = None) -> dict:
    """Record the agent's answer for one listing, checked against the taxonomy.
    confidence: "sure" | "likely" | "unsure" — an unsure answer keeps Jev's and goes
    to the daily audit."""
    if listing_id not in ctx.queue:
        return {"accepted": False, "error": f"{listing_id} is not a listing under review"}
    problems = []
    if category not in taxonomy.CATEGORY_ORDER:
        problems.append(f"category must be one of {list(taxonomy.CATEGORY_ORDER)}")
    rail = taxonomy.rails().get(category, [])
    if subtype and taxonomy.keeps_subtype(category) and subtype not in rail:
        problems.append(f"subtype for {category} must be one of {rail}")
    if confidence not in ("sure", "likely", "unsure"):
        problems.append('confidence must be "sure", "likely" or "unsure"')
    unit = size_candidates.unit_of(category)
    if size and unit:
        parsed = sizes.parse(size, category=category)
        if (parsed.mg if unit == "mg" else parsed.grams) is None:
            problems.append(f"size must be a package total in {'mg' if unit == 'mg' else 'grams'}, like "
                            f"{'100mg' if unit == 'mg' else '3.5g'}")
    if problems:
        return {"accepted": False, "errors": problems}
    ctx.answers[listing_id] = {
        "category": category, "subtype": subtype if taxonomy.keeps_subtype(category) else None,
        "strain": strain or None, "product_line": product_line or None, "size": size or None,
        "confidence": confidence, "evidence": evidence}
    return {"accepted": True}


def propose_catalog_fix(ctx: ReviewContext, brand: str, change: str, evidence: str,
                        listing_ids: list[str] | None = None) -> dict:
    """Suggest a catalog change for a person to approve in the daily audit: a missing
    product or size, a wrong entry, a product line to curate. Nothing is written."""
    ctx.proposals.append({"brand": brand, "change": change, "evidence": evidence,
                          "listing_ids": listing_ids or []})
    return {"recorded": True, "note": "queued for the daily audit; nothing was changed"}


FUNCTIONS = {f.__name__: f for f in (search_catalog, other_store_listings, listing_page,
                                     size_readings, submit_labels, propose_catalog_fix)}

_STR = {"type": "string"}
_NSTR = {"type": ["string", "null"]}
TOOLS = [
    {"name": "search_catalog",
     "description": "The brand's catalog entries (our list of what the brand makes) matching a query: "
                    "name, category, subtype, strain, product line, size and typical price. An empty "
                    "query lists the whole catalog. A listing that is in the catalog should take its "
                    "entry's identity.",
     "input_schema": {"type": "object", "properties": {"brand": _STR, "query": _STR},
                      "required": ["brand", "query"], "additionalProperties": False}},
    {"name": "other_store_listings",
     "description": "How other dispensaries list the brand's products matching a query: names, size "
                    "fields, prices, and the strain and line already recorded for them. Agreement "
                    "across stores is strong evidence; a lone store's spelling is weak.",
     "input_schema": {"type": "object", "properties": {"brand": _STR, "query": _STR},
                      "required": ["brand", "query"], "additionalProperties": False}},
    {"name": "listing_page",
     "description": "The text of the listing's own product page on the dispensary's website, when "
                    "recorded (often the full description, pack count and dose per piece).",
     "input_schema": {"type": "object", "properties": {"listing_id": _STR},
                      "required": ["listing_id"], "additionalProperties": False}},
    {"name": "size_readings",
     "description": "Every size the listing's size field, name and description could mean, with where "
                    "each comes from, whether its unit could exist, and what a package that size "
                    "typically sells for. Use it instead of doing pack arithmetic yourself.",
     "input_schema": {"type": "object", "properties": {"listing_id": _STR},
                      "required": ["listing_id"], "additionalProperties": False}},
    {"name": "submit_labels",
     "description": "Record your answer for one listing. Call once per listing. category and subtype "
                    "from the taxonomy; strain and product_line as the conventions say (null when there "
                    "is none); size as the package total (mg of THC for doses, grams for weights). "
                    "confidence: sure, likely, or unsure (unsure keeps the current answer and sends the "
                    "listing to a person). evidence: one or two sentences naming what decided it.",
     "input_schema": {"type": "object", "properties": {
         "listing_id": _STR, "category": _STR, "subtype": _NSTR, "strain": _NSTR,
         "product_line": _NSTR, "size": _NSTR,
         "confidence": {"type": "string", "enum": ["sure", "likely", "unsure"]}, "evidence": _STR},
         "required": ["listing_id", "category", "subtype", "strain", "product_line", "size",
                      "confidence", "evidence"], "additionalProperties": False}},
    {"name": "propose_catalog_fix",
     "description": "Suggest a catalog change for a person to approve: a product or size the catalog "
                    "lacks, an entry that is wrong, a product line to curate. Nothing is changed.",
     "input_schema": {"type": "object", "properties": {
         "brand": _STR, "change": _STR, "evidence": _STR,
         "listing_ids": {"type": "array", "items": _STR}},
         "required": ["brand", "change", "evidence", "listing_ids"], "additionalProperties": False}},
]


def run_tool(ctx: ReviewContext, name: str, args: dict) -> str:
    """Run one tool call and return its result as the JSON text a tool result carries."""
    fn = FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        return json.dumps(fn(ctx, **args), ensure_ascii=False, default=str)
    except TypeError as e:
        return json.dumps({"error": f"bad arguments for {name}: {e}"})
