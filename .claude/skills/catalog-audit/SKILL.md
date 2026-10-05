---
name: catalog-audit
description: Spot-check brand catalogs (brand_catalogs / brand_catalog_entries) for irregular structure — product lines with one or two strains, strains, flavours or effects filed as lines, products that lost their line, two entries for one product, store-only copies of site products, odd sizes — then trace each to the step that caused it and recommend the fix there. Use whenever the user asks to spot check, audit, review, sanity check or look over a brand's catalog, says a catalog looks off or has duplicates, asks which catalogs need attention, or after a storefront recipe or bootstrap rebuild lands, even if they never say "audit".
---

# Catalog audit

A brand catalog is our list of what a brand makes: category → product line → strain or
flavour → sizes. Every store listing of the brand resolves to one of its entries and
takes that entry's identity, so a catalog shaped wrong spreads to every listing of the
brand. The point of an audit is to judge whether a catalog is shaped like the brand's real
range, find where it is not, trace each irregularity to the step that produced it, and
recommend a fix at that step.

The judgment is the work. `scripts/catalog_shape.py` does the reading — the layout and a
list of *leads*, places the shape looks unusual — but a lead is a pointer, not a finding.
Confirm or dismiss each one with evidence.

## What a well-shaped catalog looks like

Hold this model while you read. Each point says what breaking it usually means.

- **Lines have several members.** A brand sells named lines ("Live Resin Infused"
  pre-rolls, "Sours" gummies, "40's"), each in several strains or flavours — three or four
  is common, more is normal. A line with one or two members does happen (a collab, a
  limited drop, a new line) but it is rare. *Many* thin lines in one category mean the
  catalog is filing something else as the line: a strain, a flavour, an effect ("Sleep",
  "Uplifting"), or a format.
- **A line is a name the brand gave a family.** It is not a format word (cart, gummies,
  chews), a strain type (indica), a size, or a potency. Extraction words (Live Resin,
  Rosin, Distillate) often *are* real lines.
- **No-line products are fine when the whole category has no lines.** Many brands sell a
  core range as plain "Blue Dream 3.5g". A large group of line-less products *beside*
  named lines is not fine: stores usually still write the line, and something dropped it.
- **One concept, one model.** If a brand's vapes file effects as strains of an
  "Effect-Based" line, its gummies should not file the same effects as lines.
- **One product, one entry per size.** Two entries for one product split its listings and
  make it appear twice. The causes are spelling variants, a line on one copy and not the
  other, and a store-only copy of a site product.
- **Sizes follow one form.** Weight categories (flower, preroll, vaporizers, concentrate)
  use the package total in grams ("3.5g"). Dose categories (edible, tinctures, topical)
  use the pack with the total mg ("10pk 100mg"). Within a line, the sizes should look
  related.

## Where a catalog comes from

You need this to know where a fix goes. `catalog_shape.py show` prints the source on its
first line.

- **Storefront.** The source_method is shopify_products_json, storefront_html,
  storefront_json, wp_json or wc_store_api. `scripts/storefront.py` runs the recipe in
  `data/storefronts/<slug>.json` against the brand's own site with no model involved.
  - Line and strain come from the recipe's title rules. A misread line is a recipe bug.
  - Entries whose source is `listings_bootstrap` are store-only gap fills: products two or
    more stores sell that matched no site product. Some are real (old stock, a size the
    site omits). Others are site products the stores name differently, and those are
    duplicates. `data/storefronts/README.md` covers the recipe format and `store_aliases`.
- **Bootstrap.** The source_method is listings_bootstrap. `scripts/catalog_bootstrap.py`
  builds it from our own listings, by the consensus of how two or more stores name each
  product.
  - Line and strain are whatever enrichment read from listing names (`listings.product_line`
    and `listings.strain`), so a line enrichment missed is missing here too.
  - A product only one store carries is absent. A thin line can therefore be a coverage
    gap, not an error.
- **Edits survive.** A re-push never rewrites the name, line, category, subtype, strain or
  variant of an existing entry (`brand_catalog.push`), so an admin edit sticks. A fixed
  recipe or rule creates entries with new external ids, and the next push retires the old
  ones.
- **Listings follow.** The daily `catalog_match` run re-resolves every listing against the
  *active* entries, so listings move after an entry is deactivated or added. Matches
  marked "manual" are never moved.

## Procedure

### 1. Pick the catalogs

If the user named brands, audit those. Otherwise run:

```
python3 scripts/catalog_shape.py triage
```

It ranks every catalog by weighted leads. Take two or three from the top, ideally one
storefront and one bootstrap, and tell the user why you picked them. A high score means
"most to look at", not "most broken". A big clean catalog can outscore a small broken one.

### 2. Read the shape and write down your model of the brand

```
python3 scripts/catalog_shape.py show "<Brand>"                  # whole catalog, then leads
python3 scripts/catalog_shape.py show "<Brand>" --category edible
```

Each product row shows its sizes, then the listings matched to it and the number of
stores they come from. `[store-only n]` marks a gap fill kept from n stores.

Before reading the leads, read the structure top to bottom. Write a sentence or two per
category on how you think the brand organises its range: which lines are real, what the
members of each are, and whether the brand uses lines in that category at all. That model
is what you test. If you start from the leads you will only re-describe them.

### 3. Work the leads, then look past them

| lead | what it suggests | how to confirm |
| --- | --- | --- |
| `mixed-lines` | a big line-less group beside named lines; the line was lost for most products | look at their store names (`listings`); do stores write a line word? |
| `stray` | line-less products whose strain is under a line, or whose store names mostly say a line | `listings "<Brand>" "<strain>"`: one product filed twice, or a genuinely separate product? |
| `thin-lines` / `thin-line` | lines with 1-2 members; the "line" may be a strain, flavour or effect, or the line's other members are filed elsewhere | the brand's site: is it one product per name? For bootstrap, check single-store listings for the line's missing members |
| `line-is-strain` | the line's name is a strain or flavour here (another category, swapped line and strain) or in other brands' catalogs | the brand's site and store names: which word is the family and which is the flavour? |
| `line-word` | the line is a format, strain type or size | almost always a misread; find the real line or set none |
| `similar-lines` | two spellings of one line ("Bagel Hole" / "BagelHole") | pick the brand's spelling; resin and rosin are different lines |
| `near-dup` | two strain spellings in one line ("Skywalker" / "Skywalker OG") | the site's or most stores' spelling; check the sizes match |
| `line-in-strain` | the line sits inside the strain ("Calm Peach" with no line next to line "Calm") | nearly always the same product as the lined entry |
| `strain-word` | a format, type or size word inside a strain ("Gelato Cart") | a parsing leftover; the strain should lose the word |
| `size` | missing, implausible, or written two ways in one line ("100mg" beside "10pk 100mg") | the site or the store variants; a bare total is often the same package |
| `store-copy` | a store-only entry that looks like a site product | `entries` for both: same product and size → a `store_aliases` fix; a size the site lacks → a real gap fill, but check its line |

Then look for what no lead catches:
- the same concept modelled differently across categories;
- a line that is really two (or two that are really one);
- another brand's products mixed in;
- bundles, variety packs or merch filed as products;
- a category that should not be there;
- lines the store names show that the catalog lacks entirely. Use
  `listings "<Brand>" --unmatched` to see listings no entry caught.

### 4. Gather evidence before calling anything wrong

A shape alone is not a finding. A one-flavour line is correct if the brand really sells one
flavour under that name. Use these sources, strongest first:

1. **The brand's own site.**
   - Storefront catalogs: the `show` header prints the site and the recipe path. The
     recipe's `notes` and `learned` fields describe how the site is laid out.
   - Other catalogs: find the brand's site.
   - Read pages with WebFetch or `curl -sL`. The site settles what the lines are and what
     each contains.
2. **How stores write the name.**
   ```
   python3 scripts/catalog_shape.py listings "<Brand>" "(?i)<regex>"
   ```
   Each row groups the listings that share a name, variant, enrichment reading and
   matched entry, and shows how many stores carry them. Many stores agreeing on a line
   word is strong evidence. Enrichment's line/strain reading shows what the bootstrap
   built from. Listings matched across several entries for one product are direct proof
   of a split.
3. **The entries themselves.**
   ```
   python3 scripts/catalog_shape.py entries "<Brand>" "(?i)<regex>"
   ```
   This shows every field: source, support, external id, listings matched, and the store
   names recorded as match terms. Inactive entries are included and marked.
4. **A fresh read of the site** (storefront only):
   ```
   python3 scripts/storefront.py check --brand "<Brand>" --via-http
   ```
   It re-runs the recipe and lists the products that are only at stores.

Every command here is read-only.

### 5. Trace the cause and choose where to fix it

Fix at the source when three or more entries share a cause. Hand edits are for one-offs.

| cause | fix |
| --- | --- |
| storefront: a title rule misreads line or strain (effect taken as line, format word kept) | the recipe's `title` rules; re-run `storefront.py check`, then `push` |
| storefront: a store-only entry is a site product under the stores' name | `store_aliases` in the recipe (names or lines, confirmed aliases only), then `push` |
| storefront: a store-only entry is a real size the site omits but lost the line | admin edit of its line; if several, propose carrying the site product's naming onto same-name gap fills in `storefront.with_store_products` |
| bootstrap: stores write the line but enrichment missed it | a few entries: admin edit; many: a storefront recipe if the brand's site is readable (`data/storefronts/README.md`), else a product-line rule for enrichment |
| bootstrap: thin line from coverage (members sold at one store) | nothing to fix; say so |
| any: two entries for one product | deactivate the wrong one in the admin UI (never delete: listings point at entries), add its store names to the survivor's match terms; the next `catalog_match` moves the listings |
| any: wrong size form | admin edit of `variant`; if a recipe produced it, fix the rule's size group |

### 6. Report

Use this shape for each catalog:

```
## <Brand> — <storefront|bootstrap>, <N> products · <sound | N irregularities>

How the brand organises its range (from the site and store names): a short paragraph.

| # | irregularity | evidence | cause | fix (where) | confidence |
| - | --- | --- | --- | --- | --- |

Leads checked and fine: one line each, so the reader sees they were considered.
```

Close with patterns across the catalogs you audited. One rule that fixes three brands
beats twenty admin edits. Name the entries, quote store names, and give counts. "Line
'Sleep' has one flavour; the site sells Midnight Blueberry as the Sleep gummy" is useful;
"some lines look thin" is not.

## Ground rules

- **An audit is read-only.** Do not write to the database, edit entries, or push catalogs
  while auditing. Recommend instead. Apply fixes only when the user asks. Use the recipe
  plus `storefront.py push` for storefront fixes, and the admin UI or API for single
  entries.
- **Never delete catalog entries.** Deactivate them.
- **Stay with the evidence.** When you cannot reach the site or the evidence is split,
  say so, give the readings, and mark the finding low confidence. Do not guess.
- **Keep the base rate in mind.** Lines with one or two members are rare but real.
  Several of them in one catalog is a pattern worth explaining.
