#!/usr/bin/env python3
"""
coa_read.py — Read a certificate of analysis (COA) PDF's text into fields.

A COA is the lab's report on one lot. NY labels must link to it (9 NYCRR
128.5(b)(10)), and some brands post theirs on their own sites (coa_crawl.py finds
them). This module reads one, with no model: `read(text)` takes `pdftotext -layout`
output and returns

  ids          lab, license (the producer's), lot, metrc_tag, source_package,
               product, test_date — what links the report to a product and a batch
  cannabinoids {canonical name: percent}
  terpenes     {canonical name: percent}
  totals       total_thc, total_cbd, total_cannabinoids, total_terpenes (percent),
               as the lab states them

Every lab lays its tables out differently, so the numbers are read through a lab
PROFILE: which token after an analyte's name is the percent result. Names are
found anywhere in a line, so a two-column table ("beta-Myrcene 0.00064 0.079
Isopulegol 0.00066 <LOQ") reads as two rows. A result below the lab's limit of
quantitation (<LOQ, ND, "<0.10") is 0.0. A lab with no profile still yields its
ids; its numbers are left empty rather than guessed.

Usage
-----
  python scripts/coa_read.py report.pdf        # prints the reading as JSON
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

# Bump when a change would read a stored report differently; coa_crawl.py push re-reads
# rows an older version read.
VERSION = 3

# ----------------------------------------------------------------------- analytes

# canonical name -> aliases, as regexes matched case-insensitively at word starts.
# Canonical terpene names follow prototypes/lab-report-scraper/checkweedny.py.
CANNABINOIDS: dict[str, list[str]] = {
    "THCa":    [r"tetrahydrocannabinolic acid", r"THC-?A\b"],
    "D9-THC":  [r"(?:Δ|∆|delta-?\s?|d)9-?THC\b(?!-?V)", r"Δ9-tetrahydrocannabinol"],
    "D8-THC":  [r"(?:Δ|∆|delta-?\s?|d)8-?THC\b"],
    "D10-THC": [r"(?:Δ|∆|delta-?\s?|d)10-?THC(?:-R[RS])?\b"],
    "THCVa":   [r"tetrahydrocannabivarinic acid", r"THCV-?A\b"],
    "THCV":    [r"tetrahydrocannabivarin\b", r"(?:Δ|∆|d)9-?THCV\b", r"THCV\b"],
    "CBDa":    [r"cannabidiolic acid", r"cannabinadiolic acid", r"CBD-?A\b"],
    "CBD":     [r"cannabidiol\b", r"CBD\b"],
    "CBDV":    [r"cannabidivarin\b", r"CBDV\b"],
    "CBGa":    [r"cannabigerolic acid", r"CBG-?A\b"],
    "CBG":     [r"cannabigerol\b", r"CBG\b"],
    "CBN":     [r"cannabinol\b", r"CBN\b"],
    "CBC":     [r"cannabichromene\b", r"CBC\b"],
}

TERPENES: dict[str, list[str]] = {
    "β-Caryophyllene": [r"(?:beta|b|β|trans)-?\s?caryophyllene(?!\s*oxide)", r"caryophyllene(?!\s*-?\s*oxide)"],
    "Caryophyllene Oxide": [r"caryophyllene\s*-?\s*oxide"],
    "Limonene":        [r"(?:d-)?limonene"],
    "Myrcene":         [r"(?:beta|b|β)-?\s?myrcene", r"myrcene"],
    "α-Pinene":        [r"(?:alpha|a|α)-?\s?pinene"],
    "β-Pinene":        [r"(?:beta|b|β)-?\s?pinene"],
    "Humulene":        [r"(?:alpha|a|α)-?\s?humulene", r"humulene"],
    "Linalool":        [r"linalool"],
    "Terpinolene":     [r"terpinolene"],
    "Ocimene":         [r"(?:trans|cis)-?\s?(?:beta|b|β)?-?\s?ocimene", r"(?:beta|b|β)-?\s?ocimene", r"ocimene"],
    "Bisabolol":       [r"(?:alpha|a|α)-?\s?bisabolol", r"bisabolol"],
    "Terpineol":       [r"(?:alpha|a|α|gamma|γ)[- ]?terpineol", r"terpineol"],
    "Valencene":       [r"valencene"],
    "Farnesene":       [r"(?:trans-)?(?:beta|b|β)?-?farnesene"],
    "Fenchol":         [r"fenchol", r"fenchyl alcohol"],
    "Fenchone":        [r"fenchone"],
    "Guaiol":          [r"guaiol"],
    "Geraniol":        [r"geraniol"],
    "Geranyl Acetate": [r"geranyl acetate"],
    "Eucalyptol":      [r"eucalyptol", r"1,8-cineole"],
    "Camphene":        [r"camphene"],
    "Camphor":         [r"camphor"],
    "Borneol":         [r"(?<!iso)borneol"],
    "Isoborneol":      [r"isoborneol"],
    "Isopulegol":      [r"isopulegol"],
    "Menthol":         [r"menthol"],
    "Nerol":           [r"nerol(?!idol)"],
    "trans-Nerolidol": [r"trans-?\s?nerolidol"],
    "cis-Nerolidol":   [r"cis-?\s?nerolidol"],
    "Nerolidol":       [r"nerolidol"],
    "Pulegone":        [r"pulegone"],
    "Sabinene Hydrate": [r"sabinene hydrate"],
    "Sabinene":        [r"sabinene(?!\s*hydrate)"],
    "α-Phellandrene":  [r"(?:alpha|a|α)-?\s?phellandrene"],
    "α-Terpinene":     [r"(?:alpha|a|α)-?\s?terpinene"],
    "γ-Terpinene":     [r"(?:gamma|g|γ)-?\s?terpinene"],
    "α-Cedrene":       [r"(?:alpha|α)-?\s?cedrene", r"cedrene"],
    "Cedrol":          [r"cedrol"],
    "Δ3-Carene":       [r"(?:Δ|delta|d)?-?3-?\s?carene"],
}


def _compile(table: dict[str, list[str]], kind: str) -> list[tuple[re.Pattern, str, str]]:
    out = []
    for name, aliases in table.items():
        for a in aliases:
            out.append((re.compile(r"(?<![\w-])" + a, re.I), name, kind))
    # Longest alias first, so "tetrahydrocannabivarinic acid" is tried before "THCV".
    return sorted(out, key=lambda t: -len(t[0].pattern))


ANALYTES = _compile(CANNABINOIDS, "cannabinoids") + _compile(TERPENES, "terpenes")

# ------------------------------------------------------------------------- labs

# How each lab's tables read. `sign`: a regex that identifies the lab in the text.
# `cannabinoids` / `terpenes`: the index of the percent result among the value tokens
# after an analyte's name (CAS numbers and parentheticals are dropped first), or
# "grid" for a table with analytes across the top and a "%" row beneath.
LABS: dict[str, dict] = {
    "Smithers CTS": {"sign": r"Smithers CTS", "cannabinoids": 1, "terpenes": 1},
    # Smithers' older Phyto-farma template: Average (%w/w), mg/serving, SD.
    "Phyto-farma":  {"sign": r"Phyto-?farma", "cannabinoids": 0, "terpenes": 1},
    # Terpenes: LOQ, mg/unit, %. Cannabinoids: a grid.
    "Kaycha Labs":  {"sign": r"Kaycha Labs", "cannabinoids": "grid", "terpenes": 2},
    # Terpenes: (CAS), LOQ, %. Cannabinoids are a subcontracted lab's attached COA.
    "Keystone State Testing": {"sign": r"Keystone State Testing", "cannabinoids": None, "terpenes": 1},
    # Cannabinoids: LOQ (ug/mL), %, mg/g, mg/unit. Terpenes: LOQ, %, status.
    "ACT Laboratories": {"sign": r"ACT Laboratories", "cannabinoids": 1, "terpenes": 1},
    # Hemp Hunter Labs dba Cirona Labs. Cannabinoids: % w/w, mg/serving, MRL. Terpenes: %, MRL.
    "Cirona Labs": {"sign": r"Cirona Labs|Hemp Hunter Labs", "cannabinoids": 0, "terpenes": 0},
    # Same report template as Cirona: % w/w first, "< MRL" below the limit.
    "Green Analytics": {"sign": r"Green Analytics", "cannabinoids": 0, "terpenes": 0},
    # Result first, with a % sign; each analyte named twice ("CBC  Cannabichromene").
    "MCR Labs": {"sign": r"MCR Labs", "cannabinoids": 0, "terpenes": 0},
    # Confident LIMS template. Cannabinoids: LOQ (mg/g), %, mg/g; on a unit product
    # (gummy) the columns are LOQ, mg/unit, mg/g, so the percent is mg/g / 10.
    # Terpenes: LOQ, %, mg/g. Placed last: other labs' reports can name DRS as sampler.
    "DRS Testing": {"sign": r"DRS Testing", "cannabinoids": 1, "terpenes": 1,
                    "unit_columns": {"when": r"Result\s+Result\s*\n\s*mg/g\s+mg/unit\s+mg/g",
                                     "cannabinoids": 2, "scale": 0.1}},
}

# ---------------------------------------------------------------------------- ids

ID_PATTERNS: dict[str, list[str]] = {
    "metrc_tag":      [r"Metrc (?:Tag|Package ID|Batch)\s*:?\s*(1A4[0-9A-F]{21})",
                       r"Regulator Sample ID\s*:?\s*(1A4[0-9A-F]{21})",
                       r"METRC Test Tag ID\s*:?\s*(1A4[0-9A-F]{21})"],
    "source_package": [r"Regulator Source Package ID\s*:?\s*(1A4[0-9A-F]{21})",
                       r"Metrc Source Package\s*:?\s*(1A4[0-9A-F]{21})",
                       r"METRC Source ID\s*:?\s*(1A4[0-9A-F]{21})"],
    "lot":            [r"Lot\s*(?:#|Number|No\.?)\s*:?\s*((?-i:[A-Z0-9][A-Z0-9._/-]{2,}))",
                       r"Harvest/Lot (?:ID|#)\s*:?\s*((?-i:[A-Z0-9][A-Z0-9._/-]{2,}))",
                       r"Batch Lot ID\s*:?\s*((?-i:[A-Z0-9][A-Z0-9._/-]{2,}))",
                       r"Batch\s*#\s*:?\s*((?-i:[A-Z0-9][A-Z0-9._/-]{2,}?))(?=[,;]|\s)",
                       r"Regulator Batch ID\s*:?\s*((?-i:[A-Z0-9][A-Z0-9._/-]{2,}))"],
    "license":        [r"License\s*(?:#|Number)\s*:?\s*((?:OCM-)?[A-Z]{3,5}-\d{2,4}-\d{5,6}(?:-[A-Z0-9]+)?)"],
    "product":        [r"Sample Description\s*:\s*(.+?)\s{2,}", r"Sample Description\s*:\s*(.+)$",
                       r"Strain\s*:\s*([^,\n]+?)\s*,",
                       # Cirona / Green Analytics: each section is headed with the sample's name.
                       r"^\s*Cannabinoids:\s*(.+?)\s*\(",
                       # Smithers: the product's name stands alone above "Metrc Package ID".
                       r"^[ \t]*(\S[^\n]*?)[ \t]*\n(?:[ \t]*\n)*[ \t]*Metrc Package ID"],
    # What the lab says the sample is; coa_crawl.category() turns it into ours.
    "sample_type":    [r"^\s*(Concentrates & Extracts[^\n]*?|Flower[^\n,]*?|Edibles?[^\n,]*?)\s*$",
                       r"(?<![\w/])Type\s*:\s*(\S.{1,40}?)(?:\s{2,}|$)",
                       r"Sample Type\s*:\s*(\S.{1,40}?)(?:\s{2,}|$)",
                       r"Category/Type\s*:\s*(\S.{1,40}?)(?:\s{2,}|$)",
                       r"(?:Sample )?Matrix\s*:\s*(\S.{1,40}?)(?:\s{2,}|$)"],
    "test_date":      [r"(?:Published|Date Released|Analyzed Date|Date analyzed)\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})"],
}

TOTAL_PATTERNS: dict[str, list[str]] = {
    "total_thc":           [r"^\s*Total THC\s*\[.*?\][ \t]+([\d.]+)",r"^\s*Total (?:Tetrahydrocannabinol \(THC\)|THC)[ \t]+-?[ \t]*([\d.]+)\s",
                            r"Total THC\s*\n\s*([\d.]+)\s*%",
                            r"^[ \t]*([\d.]+)\s*%[^\n]*\n\s*Total THC\b(?!/)",
                            r"^\s*Total THC = .*?\)\s+([\d.]+)%"],
    "total_cbd":           [r"^\s*Total CBD = .*?\)\s+([\d.]+)%",r"^\s*Total CBD\s*\[.*?\][ \t]+([\d.]+)",r"^\s*Total (?:Cannabidiol \(CBD\)|CBD)[ \t]+-?[ \t]*([\d.]+)\s"],
    "total_cannabinoids":  [r"^\s*Total Active Cannabinoids \(sum of above table\)\s+([\d.]+)%",r"^\s*Total Cannabinoids[ \t]+([\d.]+)\s"],
    "total_terpenes":      [r"^\s*TOTAL TERPENES[ \t]+[\d.]+[ \t]+[\d.]+[ \t]+([\d.]+)[ \t]+[\d.]+",  # Kaycha: limit, LOQ, %, mg
                            r"^\s*Total Terpenes \(% w/w\)[ \t]+([\d.]+)",r"^\s*Total Terpenes\s+(?:[\d,]+\s+)?([\d.]+)\s+(?:Passed|Tested)",
                            r"^\s*Total Terpenes\s+([\d.]+)\s*$", r"^\s*Total Terpenes\s+([\d.]+)\s", r"Terpene Total.*?\(([\d.]+)%\)",
                            r"^\s*Total \(%\)\s+([\d.]+)"],
}

# --------------------------------------------------------------------------- read

_VALUE = re.compile(r"<\s*(?:LOQ|MRL|LOD)\b|\bN\.?D\.?\b|<\s*\d*\.?\d+|(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", re.I)
_CAS = re.compile(r"\b\d{2,7}-\d{2}-\d\b")
_PAREN = re.compile(r"\([^)]*\)")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _normalize(text: str) -> str:
    return (text.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("†", " ").replace(" ", " "))


def _value(token: str) -> float | None:
    t = token.strip().upper().replace(" ", "")
    if t.startswith("<") or t.replace(".", "") == "ND":
        return 0.0
    try:
        return float(t)
    except ValueError:
        return None


def _hits(line: str) -> list[tuple[int, int, str, str]]:
    """Non-overlapping analyte names in a line: (start, end, canonical, kind)."""
    taken: list[tuple[int, int, str, str]] = []
    for pat, name, kind in ANALYTES:
        for m in pat.finditer(line):
            if not any(m.start() < e and s < m.end() for s, e, _, _ in taken):
                taken.append((m.start(), m.end(), name, kind))
    return sorted(taken)


def _rows(lines: list[str], kinds: dict) -> dict[str, dict[str, float]]:
    """Analyte -> percent, for each kind whose profile gives a column index."""
    out: dict[str, dict[str, float]] = {"cannabinoids": {}, "terpenes": {}}
    for line in lines:
        if re.match(r"\s*Total\b", line, re.I) or re.search(r"=.*[*+]|[*+].*=", line[:100]):
            continue  # totals and formulas ("Total THC = THCa*0.877 + Δ9-THC"); a note
            # far to the right of a row ("ND = Not Detected") is not a formula
        hits = _hits(line)
        for i, (s, e, name, kind) in enumerate(hits):
            idx = kinds.get(kind)
            if not isinstance(idx, int) or name in out[kind]:
                continue  # the first table to name an analyte is its profile
            seg = line[e: hits[i + 1][0] if i + 1 < len(hits) else len(line)]
            seg = _PAREN.sub(" ", _CAS.sub(" ", _THOUSANDS.sub("", seg)))
            vals = [_value(m.group()) for m in _VALUE.finditer(seg)]
            vals = [v for v in vals if v is not None]
            if len(vals) > idx and 0.0 <= vals[idx] <= 100.0:
                out[kind][name] = vals[idx]
    return out


def _grid(lines: list[str], kind: str) -> dict[str, float]:
    """A table with analyte names across one line and a '%' row below: each value is
    the token whose column is nearest its name's."""
    for i, line in enumerate(lines):
        heads = [(s, e, n) for s, e, n, k in _hits(line) if k == kind]
        if len(heads) < 4:
            continue
        for row in lines[i + 1: i + 4]:
            if not re.match(r"\s*%\s", row):
                continue
            cells = [(m.start(), _value(m.group())) for m in _VALUE.finditer(row) if m.start() > row.index("%") + 1]
            out: dict[str, float] = {}
            for s, e, n in heads:
                mid = (s + e) / 2
                pos, v = min(cells, key=lambda c: abs(c[0] - mid), default=(None, None))
                if v is not None and n not in out:
                    out[n] = v
            return out
    return {}


def _first(patterns: list[str], text: str, flags=re.M) -> str | None:
    for p in patterns:
        m = re.search(p, text, flags | re.I)
        if m:
            return m.group(1).strip()
    return None


def read(text: str) -> dict:
    text = _normalize(text)
    lab = next((name for name, p in LABS.items() if re.search(p["sign"], text, re.I)), None)
    profile = LABS.get(lab, {})
    lines = text.splitlines()

    ids = {k: _first(v, text) for k, v in ID_PATTERNS.items()}
    ids["lab"] = lab
    if ids["metrc_tag"] and ids["metrc_tag"] == ids["source_package"]:
        ids["source_package"] = None

    kinds = {k: profile.get(k) for k in ("cannabinoids", "terpenes")}
    scale = 1.0
    alt = profile.get("unit_columns")
    if alt and re.search(alt["when"], text):  # a per-unit product: mg columns, not %
        kinds["cannabinoids"], scale = alt["cannabinoids"], alt["scale"]
    found = _rows(lines, kinds)
    if scale != 1.0:
        found["cannabinoids"] = {k: round(v * scale, 4) for k, v in found["cannabinoids"].items()}
    for kind in ("cannabinoids", "terpenes"):
        if profile.get(kind) == "grid":
            found[kind] = _grid(lines, kind)

    totals = {}
    for k, pats in TOTAL_PATTERNS.items():
        v = _first(pats, text)
        totals[k] = float(v) if v and _value(v) is not None and float(v) <= 100 else None
    if scale != 1.0:  # a per-unit product's stated totals are mg, not percent
        totals.update(total_thc=None, total_cbd=None, total_cannabinoids=None)
    # Kaycha: "Total THC   Total CBD   Total Cannabinoids" over a row of percents.
    m = re.search(r"Total THC\s+Total CBD\s+Total Cannabinoids\s*\n(?:\s*\n)*\s*([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%", text)
    if m:
        for k, v in zip(("total_thc", "total_cbd", "total_cannabinoids"), m.groups()):
            totals[k] = totals[k] if totals[k] is not None else float(v)
    # ACT: "Total THC" and "Total Cannabinoids" on two lines, their values on the next two.
    m = re.search(r"^\s*Total THC\s*\n\s*Total Cannabinoids\s*\n\s*([\d.]+)\s*\n\s*([\d.]+)\s*$", text, re.M)
    if m:
        totals["total_thc"] = totals["total_thc"] if totals["total_thc"] is not None else float(m.group(1))
        totals["total_cannabinoids"] = totals["total_cannabinoids"] if totals["total_cannabinoids"] is not None else float(m.group(2))
    # Total THC by the formula every NY lab prints (THCa * 0.877 + Δ9 + Δ8 + Δ10),
    # where the lab leaves the total out of the text.
    c = found["cannabinoids"]
    if totals["total_thc"] is None and ("THCa" in c or "D9-THC" in c):
        totals["total_thc"] = round(c.get("THCa", 0) * 0.877 + c.get("D9-THC", 0)
                                    + c.get("D8-THC", 0) + c.get("D10-THC", 0), 4)
    if totals["total_terpenes"] is None and found["terpenes"]:
        totals["total_terpenes"] = round(sum(found["terpenes"].values()), 4)

    return {"ids": ids, "cannabinoids": found["cannabinoids"], "terpenes": found["terpenes"],
            "totals": totals}


def pdf_text(path: str) -> str:
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True,
                          check=True).stdout


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(read(pdf_text(p) if p.endswith(".pdf") else open(p).read()),
                         indent=2, ensure_ascii=False))
