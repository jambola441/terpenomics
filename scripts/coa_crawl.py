#!/usr/bin/env python3
"""
coa_crawl.py — Find a brand's published lab reports (COAs) by a recipe, and read them.

Some brands post a certificate of analysis for every lot on their own site: a page
of PDF links (Jaunty, Revert) or a library on a file host (MFNY's mycoa.info, on
Dropbox). A recipe, data/coa_sources/<brand-slug>.json, says where that page is and
how to read the product and lot from each link; this script runs it with no model,
and coa_read.py reads each PDF. See data/coa_sources/README.md for the format.

A COA describes one lot, not a product: two lots of one strain test differently.
So a report is kept per lot and linked to the brand's catalog by strain name; a
listing gets a lot's numbers only as "a recent tested lot of this product" unless
its own batch id or Metrc tag is on the report.

PDFs are cached under COA_CACHE (default .cache/coas/, gitignored) by URL, so a
re-run fetches only new reports.

Usage
-----
  python scripts/coa_crawl.py list  --brand Jaunty            # the links the recipe finds
  python scripts/coa_crawl.py check --brand Jaunty --limit 5  # read 5, report fields + catalog match
  python scripts/coa_crawl.py fetch --brand Jaunty            # all -> data/coas/<slug>.json
  python scripts/coa_crawl.py check --all --limit 3
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(__file__))
import coa_read  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RECIPES = os.path.join(ROOT, "data", "coa_sources")
OUT = os.path.join(ROOT, "data", "coas")
CACHE = os.environ.get("COA_CACHE", os.path.join(ROOT, ".cache", "coas"))
USER_AGENT = "Mozilla/5.0 (compatible; terpenomics-coa/1.0)"
TIMEOUT_SECONDS = 30
RETRIES = 3
DELAY_SECONDS = 0.5  # between PDF downloads: these are brands' own small sites


# ------------------------------------------------------------------------ recipes

def slug(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", brand.lower().replace("ö", "o")).strip("-")


def load_recipe(brand: str) -> dict:
    path = os.path.join(RECIPES, f"{slug(brand)}.json")
    if not os.path.exists(path):
        sys.exit(f"no recipe at {os.path.relpath(path, ROOT)}")
    return json.load(open(path))


def all_recipes() -> list[dict]:
    return [json.load(open(os.path.join(RECIPES, f)))
            for f in sorted(os.listdir(RECIPES)) if f.endswith(".json")]


# -------------------------------------------------------------------------- fetch

def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if (e.code < 500 and e.code != 429) or attempt == RETRIES:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == RETRIES:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


class _Links(HTMLParser):
    """(href, text) for every <a>, text being everything inside it."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._open: list[list] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._open.append([dict(attrs).get("href") or "", []])

    def handle_data(self, data):
        for a in self._open:
            a[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._open:
            href, text = self._open.pop()
            self.links.append((href, " ".join("".join(text).split())))


def _candidates(src: dict) -> list[tuple[str, str]]:
    """(url, text) for every file a source lists, before the recipe's filters.

    links     `pages`: pages whose <a> tags link to the reports
    wp_media  `site`: a WordPress site's media library (/wp-json/wp/v2/media), which
              lists every uploaded PDF, including ones no page links to any more"""
    kind = src.get("kind", "links")
    out: list[tuple[str, str]] = []
    if kind == "links":
        for page in src["pages"]:
            p = _Links()
            p.feed(_get(page).decode("utf-8", "replace"))
            out += [(urllib.parse.urljoin(page, html.unescape(h)), t) for h, t in p.links]
    elif kind == "wp_media":
        base = src["site"].rstrip("/") + "/wp-json/wp/v2/media?mime_type=application/pdf&per_page=100&orderby=date&page="
        for page in range(1, src.get("max_pages", 50) + 1):
            try:
                rows = json.loads(_get(base + str(page)))
            except urllib.error.HTTPError as e:
                if e.code == 400:  # past the last page
                    break
                raise
            if not rows:
                break
            out += [(r["source_url"], html.unescape((r.get("title") or {}).get("rendered") or "")) for r in rows]
    else:
        raise SystemExit(f"unknown source kind {kind!r}")
    return out


def discover(recipe: dict) -> list[dict]:
    """Every report the recipe's source lists, in the source's order (newest first
    where it has one), deduped by URL: [{url, text, strain, lot, product}]."""
    src = recipe["source"]
    link_re = re.compile(src["link"])
    skip_re = re.compile(src["skip"]) if src.get("skip") else None
    seen, out = set(), []
    for url, text in _candidates(src):
        if not link_re.search(url) or (skip_re and skip_re.search(url)):
            continue
        for find, repl in src.get("rewrite", []):
            url = re.sub(find, repl, url)
        if url in seen:
            continue
        seen.add(url)
        item = {"url": url, "text": text, "strain": None, "lot": None, "product": None}
        for rule in recipe.get("name", []):
            field = urllib.parse.unquote(url.rsplit("/", 1)[-1].split("?")[0]) if rule["from"] == "file" else text
            m = re.search(rule["match"], field)
            if m:
                g = {k: v for k, v in m.groupdict().items() if v}
                strain = re.sub(r"[_-]+", " ", g.get("strain") or "").strip()
                strain = strain.strip(" –—-")
                item["strain"] = strain.title() if strain.isupper() else strain or None
                item["lot"] = g.get("lot")
                item["product"] = g.get("product")
                break
        out.append(item)
    return out


def cached_pdf(url: str) -> str | None:
    """The PDF at `url`, from the cache or fetched into it; None if it is not a PDF."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha256(url.encode()).hexdigest()[:24] + ".pdf")
    if not os.path.exists(path):
        body = _get(url)
        time.sleep(DELAY_SECONDS)
        if not body.startswith(b"%PDF"):
            return None
        with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as f:
            f.write(body)
        os.replace(f.name, path)
    return path


def read_report(item: dict) -> dict:
    out = dict(item)
    try:
        path = cached_pdf(item["url"])
    except Exception as e:  # one bad link costs that report, not the run
        return {**out, "error": f"fetch: {e}"}
    if not path:
        return {**out, "error": "not a PDF"}
    try:
        reading = coa_read.read(coa_read.pdf_text(path))
    except subprocess.CalledProcessError as e:
        return {**out, "error": f"pdftotext: {e}"}
    out.update(reading)
    # The link's lot is the brand's word; the report's is the lab's. Keep both, and
    # use the report's where the link has none.
    out["lot"] = item["lot"] or reading["ids"].get("lot")
    return out


# -------------------------------------------------------------------------- match

def catalog_strains(brand: str) -> dict[str, list[str]]:
    """Normalized strain -> the brand's active catalog entry names with that strain."""
    from db_http import run_sql
    rows = run_sql(
        "select e.name, e.strain from brand_catalog_entries e join brand_catalogs b on b.id = e.catalog_id "
        f"where b.brand_name = '{brand.replace(chr(39), chr(39) * 2)}' and e.is_active and e.strain is not null")
    out: dict[str, list[str]] = {}
    for r in rows or []:
        out.setdefault(_norm(r["strain"]), []).append(r["name"])
    return out


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def match(report: dict, strains: dict[str, list[str]]) -> str | None:
    """The catalog strain this report is for: its link's strain, else the longest
    catalog strain named in its link text or the lab's product description."""
    if report.get("strain") and _norm(report["strain"]) in strains:
        return _norm(report["strain"])
    hay = " " + _norm(" ".join(filter(None, [report.get("strain"), report.get("text"),
                                              (report.get("ids") or {}).get("product")]))) + " "
    hits = [s for s in strains if s and f" {s} " in hay]
    return max(hits, key=len) if hits else None


# ---------------------------------------------------------------------------- cli

def _summary(r: dict) -> str:
    if r.get("error"):
        return f"  ERROR {r['error']}  {r['url']}"
    ids, t = r["ids"], r["totals"]
    top = ", ".join(f"{k} {v:g}" for k, v in sorted(r["terpenes"].items(), key=lambda x: -x[1])[:3] if v)
    return (f"  {r.get('strain') or '?':22.22} lot {r['lot'] or '-':18.18} {ids['lab'] or 'UNKNOWN LAB':14.14} "
            f"tag {ids['metrc_tag'] or '-':24} THC {t['total_thc'] if t['total_thc'] is not None else '-'}  "
            f"terps {len(r['terpenes'])} ({t['total_terpenes'] if t['total_terpenes'] is not None else '-'}%) {top}")


def cmd_list(recipe: dict, limit: int | None) -> None:
    items = discover(recipe)
    print(f"{recipe['brand']}: {len(items)} reports")
    for it in items[:limit or len(items)]:
        print(f"  {it['strain'] or 'UNNAMED':24.24} lot {it['lot'] or '-':18.18} {it['url']}")


def cmd_check(recipe: dict, limit: int | None, catalog: bool) -> dict:
    items = discover(recipe)
    sample = items[:limit] if limit else items
    print(f"{recipe['brand']}: {len(items)} reports found, reading {len(sample)}")
    reports = [read_report(it) for it in sample]
    for r in reports:
        print(_summary(r))
    bad = [r for r in reports if r.get("error")]
    unnamed = [r for r in items if not r["strain"]]
    unknown_lab = [r for r in reports if not r.get("error") and not r["ids"]["lab"]]
    no_numbers = [r for r in reports if not r.get("error") and not r["terpenes"] and not r["cannabinoids"]]
    print(f"  {len(unnamed)} links with no strain read, {len(bad)} errors, "
          f"{len(unknown_lab)} unknown labs, {len(no_numbers)} with no numbers")
    if catalog:
        strains = catalog_strains(recipe["brand"])
        matched = {m for m in (match(i, strains) for i in items) if m}
        print(f"  catalog: {len(matched)} of {len(strains)} strains have a report; "
              f"no report: {', '.join(sorted(set(strains) - matched)[:12])}")
    return {"reports": reports}


def cmd_fetch(recipe: dict, catalog: bool) -> None:
    items = discover(recipe)
    strains = catalog_strains(recipe["brand"]) if catalog else {}
    reports = []
    for it in items:
        r = read_report(it)
        if strains and not r.get("error"):
            r["catalog_strain"] = match(r, strains)
        reports.append(r)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{slug(recipe['brand'])}.json")
    with open(path, "w") as f:
        json.dump({"brand": recipe["brand"], "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "reports": reports}, f, indent=1, ensure_ascii=False)
    ok = [r for r in reports if not r.get("error")]
    print(f"{recipe['brand']}: {len(ok)} of {len(reports)} reports read -> {os.path.relpath(path, ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["list", "check", "fetch"])
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--brand")
    who.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, help="reports to read (check) or links to show (list)")
    ap.add_argument("--no-catalog", action="store_true", help="skip the catalog comparison (no database)")
    args = ap.parse_args()
    recipes = all_recipes() if args.all else [load_recipe(args.brand)]
    for recipe in recipes:
        if args.command == "list":
            cmd_list(recipe, args.limit)
        elif args.command == "check":
            cmd_check(recipe, args.limit, not args.no_catalog)
        else:
            cmd_fetch(recipe, not args.no_catalog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
