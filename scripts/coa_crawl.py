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
  python scripts/coa_crawl.py push  --brand Jaunty [--dry-run] # PDFs -> `coas` bucket, rows -> coa_reports
  python scripts/coa_crawl.py link  --all                      # relink stored reports to the catalog
  python scripts/coa_crawl.py coverage                        # listings the fetched reports reach
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
sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
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


# File hosts whose share links open a viewer page: rewritten to the file itself, for
# every recipe (Grön links half its reports to Dropbox with dl=0).
DIRECT = [[r"(dropbox\.com/.*[?&])dl=0", r"\1dl=1"]]


def _upload(path: str, data: bytes) -> None:
    """Copy a PDF to the `coas` bucket, retrying Storage's transient 5xx (a 520 from its
    proxy now and then)."""
    from services import photo_store
    for attempt in range(RETRIES + 1):
        try:
            photo_store.upload(path, data, "application/pdf", bucket="coas")
            return
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == RETRIES:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == RETRIES:
                raise
        time.sleep(2 ** attempt)


def _candidates(src: dict) -> list[tuple[str, str]]:
    """(url, text) for every file a source lists, before the recipe's filters.

    links     `pages`: pages whose <a> tags link to the reports
    wp_media  `site`: a WordPress site's media library (/wp-json/wp/v2/media), which
              lists every uploaded PDF, including ones no page links to any more
    wp_posts  `url`: a WordPress post type of documents, filters in the URL; `file`
              names the field holding each report's URL (default download_url)"""
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
    elif kind == "wp_posts":
        # A post type whose items each carry a report (`file`: the field holding its URL),
        # filtered in the URL itself: ".../wp/v2/dlp_document?doc_categories=95".
        sep = "&" if "?" in src["url"] else "?"
        for page in range(1, src.get("max_pages", 100) + 1):
            try:
                rows = json.loads(_get(f"{src['url']}{sep}per_page=100&page={page}"))
            except urllib.error.HTTPError as e:
                if e.code == 400:
                    break
                raise
            if not rows:
                break
            out += [(r.get(src.get("file", "download_url")) or "",
                     html.unescape((r.get("title") or {}).get("rendered") or "")) for r in rows]
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
        for find, repl in src.get("rewrite", []) + DIRECT:
            url = re.sub(find, repl, url)
        if url in seen:
            continue
        seen.add(url)
        item = {"url": url, "text": text, "strain": None, "lot": None, "product": None,
                "_only": src.get("only")}
        for rule in recipe.get("name", []):  # each rule fills what earlier ones left empty
            field = urllib.parse.unquote(url.rsplit("/", 1)[-1].split("?")[0]) if rule["from"] == "file" else text
            m = re.search(rule["match"], field)
            if not m:
                continue
            g = {k: v for k, v in m.groupdict().items() if v}
            strain = re.sub(r"[_-]+", " ", g.get("strain") or "").strip().strip(" –—-")
            if strain and not item["strain"]:
                item["strain"] = strain.title() if strain.isupper() else strain
            item["lot"] = item["lot"] or g.get("lot")
            item["product"] = item["product"] or g.get("product")
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
    out = {k: v for k, v in item.items() if not k.startswith("_")}
    try:
        path = cached_pdf(item["url"])
    except Exception as e:  # one bad link costs that report, not the run
        return {**out, "error": f"fetch: {e}"}
    if not path:
        return {**out, "error": "not a PDF"}
    try:
        text = coa_read.pdf_text(path)
        reading = coa_read.read(text)
    except subprocess.CalledProcessError as e:
        return {**out, "error": f"pdftotext: {e}"}
    only = (item.get("_only") or "")
    if only and not re.search(only, text):
        return {**out, "error": "skipped: not this market (recipe `only`)"}
    out.update(reading)
    # The link's lot is the brand's word; the report's is the lab's. Keep both, and
    # use the report's where the link has none.
    out["lot"] = item["lot"] or reading["ids"].get("lot")
    return out


# ----------------------------------------------------------------------- category

# Our categories, by words a report, its link or its filename uses. Tried in order:
# "Vape Cartridge - Live Rosin" is a vape, "Infused Pre-Roll" a pre-roll, before the
# rosin and flower words they contain.
CATEGORY_WORDS: list[tuple[str, str]] = [
    ("tinctures",  r"tincture|\bdrops?\b"),
    ("topical",    r"topical|balm|lotion|intimacy|massage"),
    ("preroll",    r"pre-?\s?rolls?|\bjoints?\b|\bblunts?\b|\bpuffs\b|\bdogwalkers?\b"),
    ("vaporizers", r"\bvapes?\b|cart(?:ridge)?s?\b|\bpods?\b|disposable|all[- ]in[- ]one|\baio\b|\b510|traveler"),
    ("edible",     r"gumm|edible|chocolate|\bchews?\b|\bmints?\b|beverage|\bdrinks?\b|cookie|lozenge|"
                   r"\bpearls\b|\bpips\b|pixlz|\bmega\b|\bbar\b|caramel|taffy|seltzer"),
    ("concentrate", r"rosin|resin|badder|batter|\bsugar\b|\bhash\b|diamonds?|concentrate|\bwax\b|"
                    r"shatter|crumble|derivative|(?<!un-)(?<!un)extract"),
    ("flower",     r"flower|\bplant\b|un-?extracted|\bbuds?\b|eighth|\b3\.5g?\b|\b7g\b|\b14g\b|cured"),
]


def category(report: dict, recipe: dict, brand_categories: set[str]) -> str | None:
    """Our category for the product a report tested, or None if nothing says.

    A brand that makes one category needs no evidence. Otherwise the recipe's own
    rules (a lot prefix that names a line) come first, then the words of the link,
    the filename, the report's product line, and last the lab's sample type."""
    cats = brand_categories - {"merch"}
    if len(cats) == 1:
        return next(iter(cats))
    ids = report.get("ids") or {}
    fields = {"lot": report.get("lot") or "", "text": report.get("text") or "",
              "file": urllib.parse.unquote(report["url"].rsplit("/", 1)[-1].split("?")[0])}
    for rule in recipe.get("category", []):
        if all(re.search(rx, fields.get(f, "")) for f, rx in rule["when"].items()):
            return rule["set"]
    for hint in (fields["text"], fields["file"].replace("-", " ").replace("_", " "),
                 ids.get("product"), ids.get("sample_type")):
        for cat, rx in CATEGORY_WORDS:
            if hint and re.search(rx, hint, re.I) and (not cats or cat in cats):
                return cat
    return None


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


def match(report: dict, strains: dict[str, list[str]], code_rx: str | None = None) -> str | None:
    """The catalog strain this report is for: its link's strain; else the longest catalog
    strain named in its link text, filename or the lab's product line, with spaces or
    without ("BloomSuperLemonHazeVape1gPOD"); else, where the recipe gives `strain_code`,
    the one catalog strain whose letters begin with the code in the lot (Fernway's
    FNY-MANDAR-... is Mandarin...)."""
    if report.get("strain") and _norm(report["strain"]) in strains:
        return _norm(report["strain"])
    file = urllib.parse.unquote((report.get("url") or report.get("source_url") or "").rsplit("/", 1)[-1].split("?")[0])
    parts = [report.get("strain"), report.get("text") or report.get("link_text"), re.sub(r"[_-]+", " ", file),
             (report.get("ids") or {}).get("product") or report.get("product_name")]
    hay = " " + _norm(" ".join(filter(None, parts))) + " "
    hits = [s for s in strains if s and f" {s} " in hay]
    if not hits:
        squashed = hay.replace(" ", "")
        hits = [s for s in strains if len(s.replace(" ", "")) >= 6 and s.replace(" ", "") in squashed]
    if hits:
        return max(hits, key=len)
    if code_rx:
        m = re.search(code_rx, " ".join(filter(None, [report.get("lot"), file])))
        if m:
            code = m.group("code").lower()
            fits = [s for s in strains if s.replace(" ", "").startswith(code)]
            if len(fits) == 1:
                return fits[0]
    return None


# ---------------------------------------------------------------------------- cli

def _summary(r: dict) -> str:
    if r.get("error"):
        return f"  ERROR {r['error']}  {r['url']}"
    ids, t = r["ids"], r["totals"]
    total, rows = t["total_terpenes"], sum(r["terpenes"].values())
    # A stated total its own rows do not add up to is a misread column, not chemistry.
    flag = " TOTAL?" if total and rows and abs(total - rows) > max(0.15 * total, 0.05) else ""
    top = ", ".join(f"{k} {v:g}" for k, v in sorted(r["terpenes"].items(), key=lambda x: -x[1])[:3] if v)
    return (f"  {r.get('strain') or '?':22.22} lot {r['lot'] or '-':18.18} {ids['lab'] or 'UNKNOWN LAB':14.14} "
            f"tag {ids['metrc_tag'] or '-':24} THC {t['total_thc'] if t['total_thc'] is not None else '-'}  "
            f"terps {len(r['terpenes'])} ({t['total_terpenes'] if t['total_terpenes'] is not None else '-'}%){flag} {top}")


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
    skipped = [r for r in reports if (r.get("error") or "").startswith("skipped")]
    reports = [r for r in reports if r not in skipped]
    bad = [r for r in reports if r.get("error")]
    unnamed = [r for r in items if not r["strain"]]
    unknown_lab = [r for r in reports if not r.get("error") and not r["ids"]["lab"]]
    no_numbers = [r for r in reports if not r.get("error") and not r["terpenes"] and not r["cannabinoids"]]
    print(f"  {len(unnamed)} links with no strain read, {len(skipped)} other markets, {len(bad)} errors, "
          f"{len(unknown_lab)} unknown labs, {len(no_numbers)} with no numbers")
    if catalog:
        strains = catalog_strains(recipe["brand"])
        matched = {m for m in (match(i, strains) for i in items + [r for r in reports if not r.get("error")]) if m}
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


def catalog_entries(brand: str) -> tuple[str, list[dict]]:
    """The brand's catalog id and active entries (id, strain, category, line, subtype)."""
    from db_http import run_sql
    q = brand.replace("'", "''")
    cat = run_sql(f"select id from brand_catalogs where brand_name = '{q}'")
    if not cat:
        raise SystemExit(f"no brand_catalogs row for {brand!r}")
    rows = run_sql("select e.id, e.strain, e.category, e.product_line, e.subtype from brand_catalog_entries e "
                   f"where e.catalog_id = '{cat[0]['id']}' and e.is_active") or []
    return cat[0]["id"], rows


def cmd_push(recipe: dict, limit: int | None, dry_run: bool) -> None:
    """Every report the recipe finds: the PDF copied to the `coas` bucket (named by its
    hash, so a copy is uploaded once), a coa_reports row upserted by source URL, then the
    brand's coa_report_entries rebuilt. Rows already read by this reader version and
    already copied are left alone."""
    import db_http
    from services import photo_store

    brand = recipe["brand"]
    catalog_id, entries = catalog_entries(brand)
    strains: dict[str, list[str]] = {}
    for e in entries:
        if e["strain"]:
            strains.setdefault(_norm(e["strain"]), []).append(e["name"] if "name" in e else e["id"])
    brand_cats = {e["category"] for e in entries if e["category"]}
    try:
        have = {r["source_url"]: r for r in db_http.select_all(
            "coa_reports", f"select=id,source_url,sha256,file_url,reader_version&catalog_id=eq.{catalog_id}")}
    except db_http.DbHttpError:
        if not dry_run:
            raise  # migration 0022 not applied
        have = {}

    items = discover(recipe)[: limit or None]
    rows, copied, skipped, written = [], 0, 0, 0
    for it in items:
        old = have.get(it["url"])
        if old and old["file_url"] and old["reader_version"] == coa_read.VERSION and not dry_run:
            skipped += 1
            continue
        r = read_report(it)
        if (r.get("error") or "").startswith("skipped"):
            continue
        row = {"catalog_id": catalog_id, "source_url": it["url"], "link_text": it["text"] or None,
               "strain": it["strain"], "lot": r.get("lot"), "reader_version": coa_read.VERSION,
               "error": r.get("error"), "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if not r.get("error"):
            ids, t = r["ids"], r["totals"]
            path = cached_pdf(it["url"])
            data = open(path, "rb").read()
            sha = hashlib.sha256(data).hexdigest()
            storage_path = f"{slug(brand)}/{sha}.pdf"
            if not dry_run and not (old and old["sha256"] == sha and old["file_url"]):
                try:
                    _upload(storage_path, data)
                    copied += 1
                except Exception as e:  # kept as an error row, retried next push
                    row["error"] = f"upload: {e}"
                    rows.append(row)
                    continue
            row.update({
                "sha256": sha, "storage_path": storage_path, "bytes": len(data),
                "file_url": photo_store.public_url(storage_path, "coas") if photo_store.configured() else None,
                "lab": ids["lab"], "producer_license": ids["license"], "report_lot": ids["lot"],
                "metrc_tag": ids["metrc_tag"], "source_package": ids["source_package"],
                "product_name": ids["product"], "sample_type": ids["sample_type"],
                "category": category(r, recipe, brand_cats),
                "catalog_strain": match(r, strains, recipe.get("strain_code")),
                "test_date": ids["test_date"], "total_thc": t["total_thc"], "total_cbd": t["total_cbd"],
                "total_cannabinoids": t["total_cannabinoids"], "total_terpenes": t["total_terpenes"],
                "cannabinoids": r["cannabinoids"] or None, "terpenes": r["terpenes"] or None})
        rows.append(row)
        if not dry_run and len(rows) >= 100:  # write as we go: a crash loses one batch
            _write(rows)
            written += len(rows)
            rows = []

    print(f"{brand}: {len(items)} reports, {skipped} unchanged, {written + len(rows)} written, {copied} PDFs copied")
    if dry_run:
        for row in rows[:10]:
            print(f"  {row.get('catalog_strain') or '-':24.24} {row.get('category') or '-':11} "
                  f"lot {row['lot'] or '-':18.18} {row.get('lab') or row.get('error') or ''}")
        return
    _write(rows)
    link_entries(brand, {**recipe, "_catalog_id": catalog_id}, entries)


ROW_KEYS = ["catalog_id", "source_url", "link_text", "strain", "lot", "reader_version", "error",
            "updated_at", "sha256", "storage_path", "bytes", "file_url", "lab", "producer_license",
            "report_lot", "metrc_tag", "source_package", "product_name", "sample_type", "category",
            "catalog_strain", "test_date", "total_thc", "total_cbd", "total_cannabinoids",
            "total_terpenes", "cannabinoids", "terpenes"]


def _write(rows: list[dict]) -> None:
    """Upsert rows by source URL. Every row carries every key (null where unread), as
    PostgREST's bulk upsert needs, and so a re-read clears what a misread had set."""
    import db_http
    for i in range(0, len(rows), 200):
        db_http.upsert("coa_reports", [{k: row.get(k) for k in ROW_KEYS} for row in rows[i:i + 200]],
                       on_conflict="source_url")


SUBTYPE_WORDS = [("all-in-one", r"all[- ]in[- ]one|\baio\b|disposable|traveler|\bpod\b|\(T(?: PRO)?\)"),
                 ("cart", r"\bcart(?:ridge)?s?\b|\b510")]


def _evidence(r: dict) -> str:
    """Everything a report says about which product it is, as one string."""
    file = urllib.parse.unquote(r["source_url"].rsplit("/", 1)[-1].split("?")[0])
    return " ".join(filter(None, [r.get("link_text"), re.sub(r"[_-]+", " ", file), r.get("product_name"),
                                  r.get("sample_type"), r.get("lot")]))


def report_line(r: dict, recipe: dict, lines: list[str]) -> str | None:
    """The product line a report names: the recipe's rule, else the longest of the
    brand's lines (for this category) written in its link, filename or product line.
    "" is "no line" (a rule can say so); None is "the report does not say"."""
    ev = _evidence(r)
    for rule in recipe.get("lines", []):
        if re.search(rule["when"], ev, re.I):
            return rule["line"]
    for line in sorted(lines, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(line) + r"(?![a-z0-9])", ev, re.I):
            return line
    return None


def entries_for(r: dict, recipe: dict, by_strain: dict[tuple, list[dict]]) -> tuple[list[dict], str]:
    """The catalog entries a report tested, and how they were chosen.

    Strain and category must agree. Then the line: the one the report names, else the
    one line every candidate shares. Two lines and no word of which (Fernway's 510 cart
    and Traveler Pro of one strain) is no link, not both. Then cart against
    all-in-one where the report says. Sizes are not told apart: one oil, one gummy
    batch, tests the same in any pack."""
    cands = by_strain.get((r["catalog_strain"], r["category"]), [])
    if not cands:
        return [], "none"
    lines = {(e["product_line"] or "") for e in cands}
    line = report_line(r, recipe, [l for l in lines if l])
    if line is not None:
        cands = [e for e in cands if (e["product_line"] or "") == line]
        method = "line"
    elif len(lines) == 1:
        method = "only_line"
    else:
        return [], "ambiguous_line"
    ev = _evidence(r)
    for sub, rx in SUBTYPE_WORDS:
        if re.search(rx, ev, re.I):
            narrowed = [e for e in cands if e["subtype"] in (sub, None)]
            if narrowed:
                cands = narrowed
            break
    return cands, method


def link_entries(brand: str, recipe: dict, entries: list[dict]) -> None:
    """Rebuild the brand's report -> catalog entry links from coa_reports."""
    import db_http
    catalog_id = recipe["_catalog_id"]
    reports = db_http.select_all(
        "coa_reports", "select=id,source_url,link_text,product_name,sample_type,lot,catalog_strain,category"
        f"&catalog_id=eq.{catalog_id}&error=is.null")
    by_strain: dict[tuple, list[dict]] = {}
    for e in entries:
        if e["strain"]:
            by_strain.setdefault((_norm(e["strain"]), e["category"]), []).append(e)
    links, why = [], {}
    for r in reports:
        found, method = entries_for(r, recipe, by_strain) if r["catalog_strain"] and r["category"] else ([], "no_strain_or_category")
        why[method] = why.get(method, 0) + 1
        links += [{"report_id": r["id"], "entry_id": e["id"], "method": method} for e in found]
    ids = [r["id"] for r in reports]
    for i in range(0, len(ids), 100):
        db_http.delete("coa_report_entries", f"report_id=in.({','.join(ids[i:i + 100])})")
    for i in range(0, len(links), 500):
        db_http.insert("coa_report_entries", links[i:i + 500])
    linked = {l["report_id"] for l in links}
    print(f"  {len(linked)} of {len(reports)} reports linked to {len({l['entry_id'] for l in links})} "
          f"catalog entries ({len(entries)} active); " + ", ".join(f"{k} {v}" for k, v in sorted(why.items())))


def cmd_coverage() -> None:
    """How many active listings the fetched reports reach: exactly (the listing's batch id
    is a report's lot or Metrc tag) or by product (a report for its catalog entry's strain)."""
    from db_http import run_sql
    rows = []
    for f in sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []:
        doc = json.load(open(os.path.join(OUT, f)))
        brand = doc["brand"]
        ok = [r for r in doc["reports"] if not r.get("error")]
        strains = catalog_strains(brand)
        for r in ok:
            r["catalog_strain"] = r.get("catalog_strain") or match(r, strains)
        ids = sorted({x for r in ok for x in (r.get("lot"), (r.get("ids") or {}).get("lot"),
                                              (r.get("ids") or {}).get("metrc_tag"),
                                              (r.get("ids") or {}).get("source_package")) if x})
        q = brand.replace("'", "''")
        listings = run_sql(
            "select l.id, l.batch_id, e.strain from listings l "
            "join brand_catalog_entries e on e.id = l.catalog_entry_id "
            "join brand_catalogs b on b.id = e.catalog_id "
            f"where b.brand_name = '{q}' and l.is_active") or []
        covered = {r["catalog_strain"] for r in ok if r["catalog_strain"]}
        exact = sum(1 for l in listings if l["batch_id"] and l["batch_id"] in ids)
        by_product = sum(1 for l in listings if _norm(l["strain"]) in covered)
        rows.append((brand, len(ok), len(doc["reports"]) - len(ok), len(covered), len(strains),
                     len(listings), by_product, exact))
    print(f"{'brand':14} {'read':>5} {'failed':>6} {'strains':>9} {'listings':>8} {'by product':>10} {'exact':>5}")
    for b, ok, bad, cov, nstr, nl, bp, ex in rows:
        print(f"{b:14} {ok:5} {bad:6} {cov:4}/{nstr:<4} {nl:8} {bp:10} {ex:5}")
    t = [sum(r[i] for r in rows) for i in (1, 2, 5, 6, 7)]
    print(f"{'total':14} {t[0]:5} {t[1]:6} {'':9} {t[2]:8} {t[3]:10} {t[4]:5}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["list", "check", "fetch", "push", "link", "coverage"])
    who = ap.add_mutually_exclusive_group(required=False)
    who.add_argument("--brand")
    who.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, help="reports to read (check) or links to show (list)")
    ap.add_argument("--no-catalog", action="store_true", help="skip the catalog comparison (no database)")
    ap.add_argument("--dry-run", action="store_true", help="push: read and show, write nothing")
    args = ap.parse_args()
    if args.command == "coverage":
        cmd_coverage()
        return 0
    if not (args.all or args.brand):
        ap.error("--brand or --all")
    recipes = all_recipes() if args.all else [load_recipe(args.brand)]
    for recipe in recipes:
        if args.command == "list":
            cmd_list(recipe, args.limit)
        elif args.command == "check":
            cmd_check(recipe, args.limit, not args.no_catalog)
        elif args.command == "push":
            cmd_push(recipe, args.limit, args.dry_run)
        elif args.command == "link":
            catalog_id, entries = catalog_entries(recipe["brand"])
            print(recipe["brand"])
            link_entries(recipe["brand"], {**recipe, "_catalog_id": catalog_id}, entries)
        else:
            cmd_fetch(recipe, not args.no_catalog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
