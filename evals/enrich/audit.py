#!/usr/bin/env python3
"""
audit.py — Query enriched listings for likely enrichment errors.

The eval suite (run_eval.py) measures accuracy on labeled cases; this tool sweeps
FULL enriched output — a scrape CSV or the live listings table — and surfaces
suspects for review. It is the query layer of an audit loop: run it, hand the
JSON to an agent (or a human) to adjudicate, then encode confirmed fixes as
alias-map entries, CATEGORY_MAP additions, or prompt changes.

Checks
------
  category_token_conflict   name contains tokens of a different category (cart in
                            an edible, gummies in flower, ...)
  unmapped_category_bucket  large 'other' share whose names look categorizable —
                            usually a missing CATEGORY_MAP entry upstream
  unmapped_raw_category     exact raw source strings CATEGORY_MAP sends to 'other'
                            (needs the raw_category CSV column) — each is a
                            ready-to-add map entry
  strain_split              near-duplicate strain spellings within one brand
                            ("Blu Dreem" vs "Blue Dream") — splits product groups
  line_leaked_into_strain   a known product_line of the brand also appears inside
                            the strain value (double-counted identity)
  lineage_as_strain         strain is just Indica/Sativa/Hybrid while a real
                            differentiator may exist in the name
  variant_anomaly           unit doesn't fit the category (edible in grams, flower
                            in mg, bare numbers, unconverted oz)
  brand_split               one brand under several spellings (feeds brand_aliases)
  missing_enrichment        empty strain/subtype in enrichable categories

Usage
-----
  python evals/enrich/audit.py --csv data/scrapes/the-plug_*.csv
  python evals/enrich/audit.py --csv a.csv --csv b.csv --json out.json --md report.md
  python evals/enrich/audit.py --db          # active listings via DATABASE_URL
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from enrich import CATEGORIES, SUBTYPES  # noqa: E402
from scraper_common import map_category  # noqa: E402

# ---------------------------------------------------------------------------
# Category token signals — conservative on purpose: every hit is a *suspect*,
# not a verdict. Tokens that legitimately cross categories (e.g. "flower" in an
# infused pre-roll name) are excluded.
# ---------------------------------------------------------------------------

_SIGNALS: dict[str, re.Pattern] = {
    "vaporizers": re.compile(r"\b(cart|cartridge|carts|pod|pods|aio|all[\s-]*in[\s-]*one|disposable|510|dispo)\b", re.I),
    "edible":     re.compile(r"\b(gumm\w*|chocolate|seltzer|beverage|chews?|capsules?|tablets?)\b", re.I),
    "preroll":    re.compile(r"\b(pre[\s-]?rolls?|preroll|blunt|joint)\b", re.I),
    "tinctures":  re.compile(r"\btinctures?\b", re.I),
    "topical":    re.compile(r"\b(balm|lotion|salve|topical)\b", re.I),
}
# categories a signal is allowed to coexist with (no flag)
_SIGNAL_OK = {
    "vaporizers": {"vaporizers", "merch"},           # batteries/promos sit in merch
    "edible":     {"edible"},
    "preroll":    {"preroll"},
    "tinctures":  {"tinctures"},
    "topical":    {"topical"},
}

_ENRICHABLE = {"flower", "preroll", "vaporizers", "edible", "concentrate"}
_LINEAGE = {"indica", "sativa", "hybrid"}

_BARE_NUM_RE = re.compile(r"^\d+(\.\d+)?$")
_MG_RE       = re.compile(r"^\d+(\.\d+)?mg$", re.I)
_G_RE        = re.compile(r"^\d+(\.\d+)?g$", re.I)
_OZ_RE       = re.compile(r"\boz\b", re.I)
_FLOZ_RE     = re.compile(r"fl\s*\.?\s*oz", re.I)


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _norm_brand(s: str) -> str:
    return re.sub(r"[^\w\s]", "", (s or "").lower()).strip()


def _ref(r: dict) -> dict:
    return {"slug": r.get("dispensary_slug", ""), "sku": r.get("sku", ""),
            "name": r.get("name", ""), "brand": r.get("brand", "")}


# ---------------------------------------------------------------------------
# Checks — each returns a list of finding dicts.
# ---------------------------------------------------------------------------

def check_category_token_conflict(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        cat = (r.get("category") or "").strip().lower()
        if cat not in CATEGORIES:
            continue
        for signal_cat, pat in _SIGNALS.items():
            m = pat.search(r.get("name") or "")
            if m and cat not in _SIGNAL_OK[signal_cat]:
                out.append({**_ref(r), "category": cat, "token": m.group(0),
                            "suggests": signal_cat})
                break
    return out


def check_unmapped_category_bucket(rows: list[dict]) -> list[dict]:
    other = [r for r in rows if (r.get("category") or "").lower() == "other"]
    if not other:
        return []
    tokened = defaultdict(list)
    for r in other:
        for signal_cat, pat in _SIGNALS.items():
            if pat.search(r.get("name") or ""):
                tokened[signal_cat].append(r)
                break
    out = []
    for signal_cat, hits in tokened.items():
        if len(hits) >= 5:  # a handful is noise; dozens is a map gap
            out.append({"suggests": signal_cat, "count": len(hits),
                        "other_total": len(other),
                        "samples": [_ref(r)["name"] for r in hits[:5]]})
    return out


def check_unmapped_raw_category(rows: list[dict]) -> list[dict]:
    """Raw source category strings that CATEGORY_MAP sends to 'other' — each one is
    a candidate map entry. Needs the raw_category CSV column (scrapes made after it
    was added); silently empty on older CSVs."""
    counts: dict[str, int] = defaultdict(int)
    samples: dict[str, str] = {}
    for r in rows:
        raw = (r.get("raw_category") or "").strip()
        if raw and map_category(raw) == "other":
            counts[raw] += 1
            samples.setdefault(raw, r.get("name") or "")
    return [{"raw_category": raw, "count": n, "sample_name": samples[raw]}
            for raw, n in sorted(counts.items(), key=lambda x: -x[1])]


def check_strain_split(rows: list[dict]) -> list[dict]:
    by_brand: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        s = (r.get("strain") or "").strip()
        if s and s.lower() not in _LINEAGE:
            by_brand[_norm_brand(r.get("brand") or "")].add(s)
    out = []
    for brand, strains in by_brand.items():
        pool = sorted(strains)
        for i, a in enumerate(pool):
            for b in pool[i + 1:]:
                if _squash(a) == _squash(b) or SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.88:
                    out.append({"brand": brand, "strains": [a, b]})
    return out


def check_line_leaked_into_strain(rows: list[dict]) -> list[dict]:
    lines_by_brand: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        pl = (r.get("product_line") or "").strip()
        if pl:
            lines_by_brand[_norm_brand(r.get("brand") or "")].add(pl)
    out = []
    for r in rows:
        s = (r.get("strain") or "").strip()
        if not s:
            continue
        for pl in lines_by_brand.get(_norm_brand(r.get("brand") or ""), ()):
            if _squash(pl) and _squash(pl) in _squash(s):
                out.append({**_ref(r), "strain": s, "product_line": pl})
                break
    return out


def check_lineage_as_strain(rows: list[dict]) -> list[dict]:
    return [{**_ref(r), "strain": r["strain"]}
            for r in rows if (r.get("strain") or "").strip().lower() in _LINEAGE]


def check_variant_anomaly(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        cat = (r.get("category") or "").lower()
        v = (r.get("variant") or "").strip()
        if not v:
            continue
        reason = None
        if _BARE_NUM_RE.match(v):
            reason = "bare number, no unit"
        elif cat == "edible" and _G_RE.match(v):
            reason = "edible in grams (should be total mg, or fl oz for drinks)"
        elif cat in ("flower", "preroll") and _MG_RE.match(v):
            reason = f"{cat} dosed in mg"
        elif _OZ_RE.search(v) and not _FLOZ_RE.search(v):
            reason = "unconverted oz"
        if reason:
            out.append({**_ref(r), "category": cat, "variant": v, "reason": reason})
    return out


def check_brand_split(rows: list[dict]) -> list[dict]:
    groups: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        b = (r.get("brand") or "").strip()
        if b:
            groups[_norm_brand(b)].add(b)
    return [{"spellings": sorted(v)} for v in groups.values() if len(v) > 1]


def check_missing_enrichment(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        cat = (r.get("category") or "").lower()
        if cat not in _ENRICHABLE:
            continue
        missing = [f for f in ("strain", "subtype") if not (r.get(f) or "").strip()]
        if missing:
            out.append({**_ref(r), "category": cat, "missing": missing})
    return out


CHECKS = [
    ("category_token_conflict",  check_category_token_conflict),
    ("unmapped_category_bucket", check_unmapped_category_bucket),
    ("unmapped_raw_category",    check_unmapped_raw_category),
    ("strain_split",             check_strain_split),
    ("line_leaked_into_strain",  check_line_leaked_into_strain),
    ("lineage_as_strain",        check_lineage_as_strain),
    ("variant_anomaly",          check_variant_anomaly),
    ("brand_split",              check_brand_split),
    ("missing_enrichment",       check_missing_enrichment),
]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_csvs(paths: list[str]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    return rows


def load_db() -> list[dict]:
    import os
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        env = Path(__file__).parent.parent.parent / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip()
    if not url:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("""
        SELECT d.slug, l.sku, l.scraped_name, l.scraped_brand, l.scraped_category,
               l.subtype, l.strain, l.product_line, l.variant, l.verified_fields
        FROM listings l JOIN dispensaries d ON d.id = l.dispensary_id
        WHERE l.is_active = TRUE
    """)
    cols = ["dispensary_slug", "sku", "name", "brand", "category",
            "subtype", "strain", "product_line", "variant", "verified_fields"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def verification_summary(rows: list[dict]) -> str:
    """Verified coverage, so a suspect rate reads as 'per 100 unverified'.

    A suspect count over the whole table gets less meaningful as review lands:
    the rows a human has signed are not candidates for review, so leaving them in
    the denominator understates how much of the remaining surface is dirty.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        import verification
    except ImportError:
        return ""
    live = sum(1 for r in rows if verification.verified_fields(r))
    lapsed = sum(1 for r in rows if verification.lapsed_fields(r))
    if not live and not lapsed:
        return ""
    out = [f"\n## Verification\n",
           f"- verified: **{live:,}** of {len(rows):,} listings "
           f"({live / len(rows) * 100:.2f}%)"]
    if lapsed:
        out.append(f"- lapsed: **{lapsed:,}** — renamed since review, needs re-checking")
    out.append(f"- suspect rates below are over all {len(rows):,} rows; the "
               f"{live:,} verified ones are not review candidates")
    return "\n".join(out) + "\n"


def to_markdown(results: dict, n_rows: int, rows: list[dict] | None = None) -> str:
    lines = [f"# Enrichment audit — {n_rows} listings\n"]
    if rows:
        summary = verification_summary(rows)
        if summary:
            lines.append(summary)
    lines.append("| check | findings |")
    lines.append("|---|---|")
    for name, findings in results.items():
        lines.append(f"| {name} | {len(findings)} |")
    for name, findings in results.items():
        if not findings:
            continue
        lines.append(f"\n## {name} ({len(findings)})\n")
        for f in findings[:15]:
            lines.append(f"- `{json.dumps(f, ensure_ascii=False)}`")
        if len(findings) > 15:
            lines.append(f"- ... and {len(findings) - 15} more (see JSON)")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit enriched listings for suspect enrichments")
    ap.add_argument("--csv", action="append", default=[], help="Scrape CSV (repeatable)")
    ap.add_argument("--db", action="store_true", help="Audit active listings from DATABASE_URL")
    ap.add_argument("--json", help="Write full findings JSON here")
    ap.add_argument("--md", help="Write markdown report here")
    args = ap.parse_args()

    if not args.csv and not args.db:
        ap.error("give --csv PATH (repeatable) or --db")

    rows = load_db() if args.db else load_csvs(args.csv)
    results = {name: fn(rows) for name, fn in CHECKS}

    md = to_markdown(results, len(rows), rows)
    print(md)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"full findings -> {args.json}")


if __name__ == "__main__":
    main()
