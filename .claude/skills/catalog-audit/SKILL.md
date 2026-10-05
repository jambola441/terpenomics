---
name: catalog-audit
description: Spot-check brand catalogs (brand_catalogs / brand_catalog_entries) for irregular structure — product lines with one or two strains, lines that cross categories, strains, flavours or effects filed as lines, products that lost their line, two entries for one product, store-only copies of site products, one brand inside another's catalog, odd sizes — then trace each to the step that caused it and recommend the fix there. Use whenever the user asks to spot check, audit, review, sanity check or look over a brand's catalog, says a catalog looks off or has duplicates, asks which catalogs need attention, or after a storefront recipe or bootstrap rebuild lands, even if they never say "audit".
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

## Brand-shape rules

These rules describe how brands really organise a range. Hold them while you read a
catalog. Each one says what breaking it usually means, and which leads (step 3) catch
it. They are rules of thumb, not laws: a break is a question, and evidence answers it.

1. **Lines have several members.** A brand sells named lines ("Live Resin Infused"
   pre-rolls, "Sours" gummies, "40's"), each in several strains or flavours. Three or
   four is common, and more is normal. A line with one or two members happens (a collab,
   a limited drop, a new line), but it is rare. *Many* thin lines in one category mean
   the catalog is filing something else as the line: a strain, a flavour, an effect
   ("Sleep", "Uplifting"), or a format.
   - *Effect names* (the user's rule, 2026-10-05). An effect such as Calm, Bliss, Sleep,
     Happy, Energize or Social is the line only when it is the only family name the brand
     gives the product: Florist Farms' "Calm | Peach Gummies" is line Calm, flavour Peach.
     When the brand names a family and puts effects under it, the family is the line and
     the effect goes in the product name. Examples:
     - Ayrloom "Mood – Bliss" vapes: Mood → Bliss.
     - 1906 "Bliss Drops": Drops → Bliss.
     - Level "Protab – Boost": Protab → Boost.
     - PUFF "Uplift – Blended – Prerolls": Blended → Uplift.
     - Papa & Barkley "Sleep Releaf": Releaf → Sleep.
     - Camino "Sours 'Bliss' Raspberry Lemonade": Sours → Bliss Raspberry Lemonade.
     - A tell that the effect is not the line: one effect spanning formats or families
       (Camino's "Bliss" was a gummy, a sour and a chew).
     - One-flavour effect lines under the first case are the brand's design, not a fault.
       Report them once, not per line.
   Leads: `thin-lines`, `thin-line`, `line-is-strain`.
2. **A line stays in its category.** "40's" are pre-rolls, "Sours" are gummies, and
   "Liquid Diamonds" are vapes. When the same name is a line in two categories, it is
   usually not a line at all, or some products are filed in the wrong category. Words
   that cross categories this way include extraction words ("Live Resin", "Live
   Rosin"), brand-wide names ("Classics") and effects. The category holding fewer of
   them is the usual suspect.
   - An extraction word may stay as the line when it is the brand's own naming and the
     only thing that tells two products apart (a live resin cart versus a live rosin
     cart). Say so in the report rather than calling it a fault.
   - So may a family the brand itself prints across formats: Papa & Barkley's Releaf
     is a gummy, a tincture and a balm.
   Leads: `cross-category`.
3. **A line is a name the brand gave a family.** It is not a format word (cart, gummies,
   chews), a strain type (indica), a size or a potency. It is also not another brand:
   Camino is its own brand, not a Kiva line.
   Leads: `line-word`, `line-is-brand`.
4. **No-line products are fine when the whole category has no lines.** Many brands sell
   a core range as plain "Blue Dream 3.5g". A large group of line-less products *beside*
   named lines is not fine: stores usually still write the line, and something dropped
   it. A size can give the line away too: when every infused pre-roll is a 5-pack, a
   line-less 5-pack is probably infused.
   Leads: `mixed-lines` (bootstrap only), `stray`, `line-in-strain`, `size-of-other-line`.
5. **One concept, one model.** If a brand's vapes file effects as strains of an
   "Effect-Based" line, its gummies should not file the same effects as lines.
   Leads: `line-is-strain` naming another category, `cross-category`.
6. **One product, one entry per size.** Two entries for one product split its listings
   and make it appear twice. The usual causes are spelling variants, a line on one copy
   and not the other, a store-only copy of a site product, and the product sitting in
   two brands' catalogs. A site can also rename a product the stores still sell under
   the old name: Florist Farms' "GG4" vapes have no listings, while store-only "Gorilla
   Glue" entries of the same format and size hold them.
   Leads: `near-dup`, `similar-lines`, `stray`, `store-copy`, `orphan-site`, `line-is-brand`.
7. **Sizes follow one form.** Weight categories (flower, preroll, vaporizers,
   concentrate) use the package total in grams ("3.5g"). Dose categories (edible,
   tinctures, topical) use the pack with the total mg ("10pk 100mg"). Within a line,
   the sizes should look related.
   Leads: `size`.
8. **Names are clean.** A strain holds the strain or flavour, nothing else. No format
   ("Gelato Cart"), no size, no line ("Calm Peach" when "Calm" is the line).
   Leads: `strain-word`, `line-in-strain`.
9. **One strain in several formats is several products.** Florist Farms sells every
   classic vape strain as both a 1g cart and a 1g all-in-one. Those are two products
   (subtype tells them apart), never duplicates, and lead names carry the format
   ("Gorilla Glue" [cart]) for that reason. A range that sells most strains in a format
   pair makes a strain with only one half of the pair stand out. The other half may be
   filed under another name or line, or too few stores sell it for a bootstrap to keep.
   Leads: `missing-pair`.
10. **Stores mistype sizes** (the user's find, 2026-10-05). A listing's size is the
    store's own field (`variant`), copied as typed. For a dose product matched with
    trust, the importer puts the catalog's size in `size`, which product pages group on.
    Any other typo shows as a product of its own even when the match is right. A size no
    product of the line comes in, at one store, is usually one of these:
    - a mistyped unit: The Spot's STIIIZY 40's "5 x 0.9g ... (2.5g Pre-Roll Pack)" showed
      as 4.5g, where 40's come in 1g and 2.5g;
    - a cannabinoid sum or the CBD figure: Ayrloom's 150mg Everyday drops listed as
      600mg (150mg THC + 450mg CBD) or 450mg;
    - a per-piece dose typed as the size.

    The counts give it away before any single row does. `show` prints each line's sizes
    as the stores write them, and a size on two listings beside sizes on dozens is the
    one to open, even when the catalog has an entry for that size. Open it with
    `listings "<Brand>" "<strain>" --photos --descriptions`:
    - the listing's own name or description usually states the real size ("(2.5g
      Pre-Roll Pack)", "0.5g each / 2.5g total");
    - a pack of a size the line sells ("2PK 1G Pods") is a bundle, not a typo;
    - two or more stores agreeing on a size nothing contradicts is probably a size the
      catalog lacks.

    Read: the `stores write` row in `show`.

**These rules grow.** When the user names another way brands do (or never do) things,
add it here as a numbered rule. When an audit turns up a pattern worth checking every
time, propose the rule in the report: an audit edits nothing, this file included. If a
rule can be computed from the entries alone, it also belongs as a lead in
`scripts/catalog_shape.py` `leads()`, with a test in `scripts/test_catalog_shape.py`.

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
  - Curated lines in `data/product_lines.json` fix that for a brand. A line is set
    wherever its exact text is in the name, which brings three limits:
    - singular and plural are different texts ("Liquid Diamond", "Liquid Diamonds");
    - it never clears a line the model invented;
    - it applies at a listing's next enrichment, so the catalog needs a rebuild after.

    `data/strain_aliases.json` folds a brand's strain spellings the same way.
  - A product only one store carries is absent. A thin line can therefore be a coverage
    gap, not an error.
  - Support counts listings seen in the last 21 days (`BOOTSTRAP_FRESH_DAYS`), since a
    store that stops scraping leaves its menu active. The storefront gap fill uses the
    same window.
- **Listings echo their entry.** A matched listing takes its entry's line and strain, and
  the bootstrap and the gap fill are rebuilt from listings. So a duplicate's own listings
  vote for it at every rebuild, and a lost line stays lost until something outside the
  loop changes: a rule, an alias, an edit or a deactivation.
- **Match methods.** Every listing's match records how it was made:
  - `exact`: the name is an entry's name or one of its recorded store names.
  - `jev`: the model picked the entry with p ≥ 0.85, or ≥ 0.90 in a bootstrap catalog.
    Trusted.
  - `jev_review`: p ≥ 0.50. Recorded, not trusted.
  - `none`: the model abstained.
- **Brand names.** `data/brand_aliases.json` maps scraped brand strings only. A
  sub-brand that stores file under its parent ("KIVA - Camino ...") lands in the parent's
  catalog, which then holds a second copy of the sub-brand.
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
stores they come from. In a storefront catalog, a size marked `*` came only from the
stores, and `[store-only n]` marks a whole product kept from n stores. Watch the counts:
a site product at 0/0 beside a store-only product of the same shape is a rename to check.

Under each line, `stores write` lists the sizes the line's listings state, as
listings/stores, commonest first. `(no product)` marks a size no product of the line comes
in. One package written two ways ("0.5g 5-pack | 2.5g", "Multi-Pack | 2.5g") is counted
once, under the catalog's size. Compare the counts as you read: a size on a couple of
listings beside sizes on dozens is worth opening (rule 10). No lead does this for you; the
row is the check.
- STIIIZY's 40's read `1g 76/12 · 2.5g 54/12 · 5pk 4.5g 2/1 (no product)`. The 4.5g was
  one store's typo for the 2.5g pack.
- Camino's Gummies showed `20pk 72mg 5/1`: one store typing 72mg on five different
  gummies, a store habit no single listing reveals.

For a bootstrap catalog, `python3 scripts/catalog_shape.py preview "<Brand>"` shows
what a rebuild would propose from today's fresh listings: entries it would add, and
entries it no longer would. It writes nothing. A catalog that drifted from its listings
is a finding of its own.

Before reading the leads, read the structure top to bottom. Write a sentence or two per
category on how you think the brand organises its range: which lines are real, what the
members of each are, and whether the brand uses lines in that category at all. That model
is what you test. If you start from the leads you will only re-describe them.

### 3. Work the leads, then look past them

| lead | what it suggests | how to confirm |
| --- | --- | --- |
| `mixed-lines` | a big line-less group beside named lines; the line was lost for most products | look at their store names (`listings`); do stores write a line word? |
| `stray` | line-less products whose store names (for that size) mostly say a line | `listings "<Brand>" "<strain>"`: the same product as the lined one, or a separate plain product? |
| `size-of-other-line` | a size rare in its own group but typical of another line (a line-less 5-pack where every infused pre-roll is a 5-pack) | store names for that size; the site's listing of that size |
| `split-size` | a line-less product whose strain is in one line, in sizes that line lacks (line-less Biscotti 1g beside 40's Biscotti 2.5g) | store names: do they say the line? A line defined by its size (a 0.5g-only pen) makes this a false alarm |
| `thin-lines` / `thin-line` | lines with 1-2 members; the "line" may be a strain, flavour or effect, or the line's other members are filed elsewhere | the brand's site: is it one product per name? For bootstrap, check single-store listings for the line's missing members |
| `line-is-strain` | the line's name is a strain or flavour here (another category, swapped line and strain) or in other brands' catalogs | the brand's site and store names: which word is the family and which is the flavour? |
| `cross-category` | one name is a line in two categories; it is likely not a line, or products sit in the wrong category | the products in the smaller category: misfiled? Is the name an extraction word or brand-wide name? |
| `line-word` | the line is a format, strain type or size | almost always a misread; find the real line or set none |
| `line-is-brand` | the line is another brand we keep a catalog for | `show` that brand: the same products listed under both? |
| `similar-lines` | two spellings of one line ("Bagel Hole" / "BagelHole") | pick the brand's spelling; resin and rosin are different lines |
| `near-dup` | two strain spellings in one line ("Skywalker" / "Skywalker OG") | the site's or most stores' spelling; check the sizes match |
| `line-in-strain` | the line sits inside the strain ("Calm Peach" with no line next to line "Calm") | nearly always the same product as the lined entry |
| `strain-word` | a format, type or size word inside a strain ("Gelato Cart") | a parsing leftover; the strain should lose the word |
| `size` | missing, implausible, or written two ways in one line ("100mg" beside "10pk 100mg") | the site or the store variants; a bare total is often the same package |
| `store-copy` | a store-only size that looks like a site product of the same format and size | `entries` for both: the same product → a `store_aliases` fix |
| `orphan-site` | a store-only size with listings beside site products of its shape that have none | is one of them the same product renamed on the site? Compare the site's handle and tags with the store names |
| `missing-pair` | a range that pairs formats (cart + all-in-one) has strains with only one | coverage (bootstrap), or the other half filed under another name or line |
| `rare-format` | a format with 1-3 products beside a main format of 10+ (3 carts beside 37 pods) | does the brand sell it? Usually a format word misread from a menu |
| `idle` | bootstrap entries no listing matches now | their support was stale, or their listings moved to another entry |
| `inside-other-catalog` | another brand's catalog has a line named like this brand | `show` that brand: the same products under both? |

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
   Each row groups the listings that share a name, variant, line/strain and matched
   entry, and shows how many stores carry them.
   - Only the store's own name is independent evidence. A matched listing's line and
     strain are copied from its entry, so only unmatched and `jev_review` rows show what
     enrichment itself read.
   - `--photos` adds a package photo per row. The pack prints the dose, the count and
     the effect. It settled "Excite" against "Exhilarate", and a CBD total typed as a
     size.
   - `--descriptions` adds the store's description. A store that leaves the line out of
     the name often has it there: Hold Up Roll Up's "King Louis XIII - 1G Infused
     Prerolls" says "Stiiizy 40s pre-rolls are..." (the user's find).
     - A curated line with a `category` in `data/product_lines.json` is applied from the
       description when the name has no line.
     - The `lines` view counts such listings in its last column.
   - Many stores agreeing on a line word is strong evidence.
   - Listings matched across several entries for one product are direct proof of a
     split.
   - `SIZE DIFFERS` marks a listing whose size disagrees with its entry's, such as a
     7-pack matched to a single. That is a wrong match.
   - `--unmatched` shows listings no entry caught. It mixes other brands' products
     filed under this one, single-store products, and listings not matched yet (method
     shown).
3. **The entries themselves.**
   ```
   python3 scripts/catalog_shape.py entries "<Brand>" "(?i)<regex>"
   ```
   This shows every field: source, support, external id, listings matched, and the store
   names recorded as match terms. Inactive entries are included and marked. Store names
   are stored normalised ("40's" as "40 s", ".5g" as "5g"), so write the regex for that
   form.
4. **Line words against what was recorded.**
   ```
   python3 scripts/catalog_shape.py lines "<Brand>" --word "Liquid Diamond" --word LIIIL
   ```
   For each of the catalog's lines plus any `--word`, this counts the store names that
   print it and how many of those listings have it recorded as their line. STIIIZY's
   "Original" was printed on 73 listings and recorded on 8: a line enrichment misses.
5. **A fresh read of the site** (storefront only):
   ```
   python3 scripts/storefront.py check --brand "<Brand>" --via-http
   python3 scripts/storefront.py check --recipe <scratch>/draft.json --via-http
   ```
   It re-runs the recipe and lists the products that are only at stores. With
   `--recipe`, it runs a draft copy, so a proposed recipe change can be tested without
   editing the real file. For how the site titles a product, fetch the source itself:
   for Shopify, `<site>/products.json`. A site entry's external id ends in the site's
   variant id, which joins the two.

Every command here is read-only.

### 5. Trace the cause and choose where to fix it

Fix at the source when three or more entries share a cause. Hand edits are for one-offs.

| cause | fix |
| --- | --- |
| storefront: a title rule misreads line or strain (effect taken as line, format word kept) | the recipe's `title` rules; re-run `storefront.py check`, then `push` |
| storefront: a store-only entry is a site product under the stores' name (or the site renamed it) | `store_aliases` in the recipe (names or lines, confirmed aliases only), then `push`. Aliases apply in every category; when one would misfire elsewhere (a "Kief Coated Gorilla Glue" pre-roll), use a `title` rule's `set` for that category instead |
| storefront: a store-only entry is a real size the site omits but lost the line | admin edit of its line; if several, propose carrying the site product's naming onto same-name gap fills in `storefront.with_store_products` |
| bootstrap: stores write the line but enrichment missed it | a few entries: admin edit. Many: a storefront recipe if the brand's site is readable (`data/storefronts/README.md`), else the brand's lines in `data/product_lines.json`. List each spelling stores print (singular, plural, "40's" and "40s"), then preview and rebuild the catalog after the next run |
| bootstrap: one strain spelled two ways ("Skywalker" / "Skywalker OG") | `data/strain_aliases.json` for the brand; for the entries already split, deactivate one and move its store names |
| storefront: two store-only copies of one product | `store_aliases` cannot merge them: aliases change only the comparison with the site. Deactivate all but one, or make the product a site product by exempting its page from a skip rule |
| storefront: a store-only size that is the site's package written another way (a CBD total, a cannabinoid sum) | deactivate it; if several brands show it, propose a rule in `split_store_products` for dose categories |
| bootstrap: thin line from coverage (members sold at one store) | nothing to fix; say so |
| any: two entries for one product | deactivate the wrong one in the admin UI (never delete: listings point at entries), add its store names to the survivor's match terms; the next `catalog_match` moves the listings |
| any: one brand's products inside another brand's catalog | a skip rule in the parent's recipe (or deactivations), plus a proposed name-based sub-brand rule at import, so stores' "Kiva - Camino ..." listings resolve to the sub-brand. `brand_aliases.json` alone cannot: it maps brand strings, not names |
| any: products in the wrong category | admin edit of `category` (and subtype); if a recipe produced it, fix its `category` rule |
| any: wrong size form | admin edit of `variant`; if a recipe produced it, fix the rule's size group |
| any: a store mistyped a size (rule 10) | nothing in the catalog, which is right. A dose product matched with trust already shows on its product's page (`listings.size`, `catalog_match.catalog_size`). A weight typo, or a review-only match, keeps its own page: report the store and the size |
| any: a size 2+ stores agree on that the catalog lacks | it arrives by itself: a store-only size at the next storefront push, an entry at the next bootstrap rebuild. One store's bundle ("2PK 1G Pods") stays out on purpose |

### 6. Report

Imports and `catalog_match` keep running while you audit, so counts move. Re-run `show`
just before writing, and give the time your counts are from.

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

- **An audit is read-only.** Do not write to the database, edit entries, push catalogs,
  or edit repo files (recipes, rule files, this skill) while auditing. Recommend instead,
  and test a recipe change on a scratch copy with `check --recipe`. Apply fixes only
  when the user asks: the recipe plus `storefront.py push` for storefront fixes, rule
  files plus a rebuild for bootstrap ones, the admin UI or API for single entries.
- **Never delete catalog entries.** Deactivate them.
- **Stay with the evidence.** When you cannot reach the site or the evidence is split,
  say so, give the readings, and mark the finding low confidence. Do not guess.
- **Keep the base rate in mind.** Lines with one or two members are rare but real.
  Several of them in one catalog is a pattern worth explaining.
