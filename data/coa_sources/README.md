# Lab report (COA) recipes

One file per brand, `<brand-slug>.json`, read by `scripts/coa_crawl.py`. A recipe says
where a brand publishes its certificates of analysis and how to read the product and lot
from each link; `scripts/coa_read.py` then reads each PDF with no model.

A COA is the lab's report on **one lot**. Two lots of a product test differently, so a
report is kept per lot. A listing gets a lot's numbers as "a recent tested lot of this
product", unless its own batch id or Metrc tag is on the report.

## Writing one

1. Find where the brand keeps its reports: a lab-results page of PDF links, a file host
   (Dropbox, Google Drive), or a WordPress media library
   (`<site>/wp-json/wp/v2/media?mime_type=application/pdf` — it lists every uploaded PDF,
   including ones no page links to any more; Jaunty's page showed 26, its library ~1,000).
2. Write the recipe (below). Start from `jaunty.json` (WordPress) or `mfny.json` (a page).
3. `python3 scripts/coa_crawl.py list --brand "<Brand>"` until every link is a report and
   has a strain, then `check --brand "<Brand>" --limit 10` until:
   - no `UNKNOWN LAB` — a new lab needs a profile in `coa_read.LABS` (which value token
     after an analyte's name is the percent) and a fixture + test in
     `scripts/test_coa_read.py`;
   - every report has numbers (terpenes, cannabinoids or both);
   - the catalog line names the strains you expect; the ones with no report should be
     products the brand does not publish for, not names your rules misread.
4. `fetch --brand "<Brand>"` reads them all into `data/coas/<slug>.json` (gitignored).

## Format

```json
{
  "brand": "Jaunty",
  "site": "https://jaunty.com",
  "source": {"kind": "wp_media", "site": "https://jaunty.com", "link": "\\.pdf$",
             "skip": "(?i)catalog|budtender"},
  "learned": "when, what the site had",
  "notes": ["what the next person needs to know"],
  "name": [{"from": "file", "match": "^(?P<strain>.*?)-(?P<lot>J[A-Z]{3}...)\\.pdf$"}]
}
```

**source.kind**

| kind | fields |
| --- | --- |
| `links` | `pages`: pages whose `<a>` tags link to the reports |
| `wp_media` | `site`: a WordPress site; every PDF in its media library |

Both take `link` (regex a report's URL must match), `skip` (regex for PDFs that are not
reports: catalogs, menus) and `rewrite` (`[[find, replace]]` on the URL, e.g. Dropbox's
`dl=0` -> `dl=1`).

**category** (optional): `[{"when": {"lot": "^JIPR"}, "set": "preroll", "why": "..."}]`,
regexes over `lot`, `file` and `text`, for a brand whose lot or filename names its line.
Without one, a report's category comes from the words of its link, filename, product
line and the lab's sample type; a brand whose catalog has one category needs neither.
A report with no category is kept but linked to no catalog entry.

**lines** (optional): `[{"when": "\\(T PRO\\)", "line": "Traveler Pro"}]`, a regex over the
report's link text, filename, product line and lot, for a brand whose reports name a line
in their own shorthand. `"line": ""` means the line-less product. Without a rule, a report
takes the longest of the brand's lines written in it. A report that names no line, for a
strain the catalog has in two lines, is linked to neither.

**strain_code** (optional): a regex with a `code` group over the lot and filename, for a
brand whose lots abbreviate the strain (Fernway's `FNY-MANDAR-T2G-...`). The code is
resolved to the one catalog strain whose letters begin with it, or to nothing.

**name**: rules tried in order; each fills what earlier ones left empty (a filename's
strain, then a title's lot). `from` is `file` (the URL's file name,
decoded) or `text` (the link's text, or a media item's title). Named groups: `strain`,
`lot`, `product`. A lot read from the link is the brand's; the report's own lot fills in
when the link has none.
