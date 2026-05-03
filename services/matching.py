"""
Shared product-matching logic used by both the API and match_listings.py script.
"""

import re
from difflib import SequenceMatcher


def _norm_brand(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def score_candidates(
    scraped_name: str,
    scraped_brand: str,
    scraped_variant: str,
    scraped_category: str,
    products: list,
    brand_aliases: dict[str, str],
    top_n: int = 5,
) -> list[dict]:
    """
    Score DB products against a scraped listing.

    products: list of objects with .id, .name, .brand, .variant, .category
    Returns top_n candidates sorted by score descending.
    """
    resolved_brand = brand_aliases.get(scraped_brand, scraped_brand)
    nb = _norm_brand(resolved_brand)

    brand_pool = [p for p in products if _norm_brand(p.brand or "") == nb]
    if not brand_pool:
        return []

    variant_l  = scraped_variant.lower()
    category_l = scraped_category.lower()

    def _cat(p) -> str:
        c = p.category
        return (c.value if hasattr(c, "value") else str(c)).lower()

    by_var_cat = [p for p in brand_pool if (p.variant or "").lower() == variant_l and _cat(p) == category_l]
    by_var     = [p for p in brand_pool if (p.variant or "").lower() == variant_l]
    by_cat     = [p for p in brand_pool if _cat(p) == category_l]

    if by_var_cat:
        pool, basis = by_var_cat, "brand+variant+category"
    elif by_var:
        pool, basis = by_var, "brand+variant"
    elif by_cat:
        pool, basis = by_cat, "brand+category"
    else:
        return []  # brand-only match is too loose to surface as a candidate

    scored = sorted(
        [{"product": p, "score": round(_similarity(scraped_name, p.name), 3), "basis": basis}
         for p in pool],
        key=lambda x: -x["score"],
    )
    return scored[:top_n]
