"""Product-page links for stores whose own site is not addressed by Dutchie's `cName`.

Most Dutchie stores fill a `product_url_template` from dispensaries.json (see
scrape_graphql.product_url). A store that runs its own storefront names its product pages
in its own way, so its entry carries a `product_url_source` instead:

  {"type": "sitemap", "sitemap": <sitemap.xml>, "template": <url with {brand_slug} {name_slug}>}
      The page is the store's slug for brand + name. Only a URL the store's sitemap lists is
      kept: a guessed link that 404s is worse than none.

  {"type": "joint", "site": <origin>, "business_id": <Joint business id>}
      Dagmar's Joint Commerce menu. Its products carry the POS id Dutchie calls `_id`, and
      its pages are addressed by Joint's own UUID, so the menu is read once to pair them.

A resolver is a function from a Dutchie product dict to a URL, "" when it has none. The
indexes are fetched once per scrape; if that fails the scrape goes on without links (the
importer keeps any link already stored) rather than failing a store over a convenience.
"""

import re
from typing import Callable

Resolver = Callable[[dict], str]

JOINT_SEARCH = "/wp-json/joint-ecommerce/v1/products/ecommerce-production/_search"
JOINT_PAGE = 100


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _no_links(_: dict) -> str:
    return ""


def _session():
    from curl_cffi import requests as cffi_req
    return cffi_req.Session(impersonate="chrome")


def sitemap_resolver(cfg: dict) -> Resolver:
    xml = _session().get(cfg["sitemap"], timeout=30)
    xml.raise_for_status()
    live = set(re.findall(r"<loc>([^<]+)</loc>", xml.text))
    template = cfg["template"]

    def resolve(p: dict) -> str:
        # An unbranded product keeps its slot: the site writes "-name", not "name".
        brand = slugify((p.get("brand") or {}).get("name") or "")
        url = template.replace("{brand_slug}", brand).replace("{name_slug}", slugify(p.get("Name") or ""))
        return url if url in live else ""
    return resolve


def joint_resolver(cfg: dict) -> Resolver:
    site, session = cfg["site"].rstrip("/"), _session()
    headers = {"Content-Type": "application/json", "Origin": site, "Referer": site + "/menu/"}
    # The endpoint refuses a query that is not shaped like the menu page's own.
    flt = [{"bool": {"should": [{"term": {"businessId": str(cfg["business_id"])}}]}},
           {"bool": {"should": [{"term": {"menuType": "RECREATIONAL"}}]}},
           {"bool": {"must_not": [{"term": {"isDeleted": True}}]}}]
    joint_id: dict[str, str] = {}
    offset = 0
    while True:
        resp = session.post(site + JOINT_SEARCH, headers=headers, timeout=30, json={
            "from": offset, "size": JOINT_PAGE, "_source": ["jointId", "posId"],
            "query": {"bool": {"filter": flt}}})
        resp.raise_for_status()
        hits = resp.json()["hits"]["hits"]
        for h in hits:
            src = h.get("_source") or {}
            if src.get("posId") and src.get("jointId"):
                joint_id[src["posId"]] = src["jointId"]
        if len(hits) < JOINT_PAGE:
            break
        offset += JOINT_PAGE

    def resolve(p: dict) -> str:
        jid = joint_id.get(str(p.get("_id") or ""))
        return f"{site}/products/?product_page={jid}" if jid else ""
    return resolve


SOURCES = {"sitemap": sitemap_resolver, "joint": joint_resolver}


def build(store: dict) -> "Resolver | str":
    """What normalise_gql should use for this store: a resolver for a `product_url_source`,
    else the store's `product_url_template` (or "" for none)."""
    source = store.get("product_url_source")
    if not source:
        return store.get("product_url_template") or ""
    try:
        return SOURCES[source["type"]](source)
    except Exception as exc:  # a missing index costs links, not the scrape
        print(f"  [WARN] product links for {store.get('slug')}: {exc}; continuing without")
        return _no_links
