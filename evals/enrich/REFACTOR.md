# Enrichment refactor — what is actually wrong

Written 2026-08-27 against the live database (16,031 active listings, 25 stores).
Every number here is measured, not estimated.

## The short version

The three instincts behind this are right, and two of them are measurable:

1. **One field set for every category is wrong.** `variant` is not one field, it is
   five incompatible unit systems discriminated by category. `strain` means four
   different things. The pipeline already knows this — it special-cases on category
   **105 times** — it just does not admit it in the schema.
2. **Cardinality is low enough to curate.** 731 brands, 3,719 strains, 10,415
   product rows. This is a vocabulary, not a long tail.
3. **A verified flag is not optional, it is load-bearing** — and today a human
   correction cannot survive a single scrape. Nothing in the pipeline protects it.

## 1. `variant` is a union type wearing one column

Shape of the value, by category, over the 16,031 active listings:

| category | grams | mg | pk/ct | oz/ml | other |
| --- | ---: | ---: | ---: | ---: | ---: |
| preroll | 4,219 | 0 | 0 | 0 | 0 |
| vaporizers | 3,431 | 0 | 0 | 0 | 0 |
| flower | 3,337 | 0 | 0 | 0 | 0 |
| concentrate | 475 | 0 | 0 | 0 | 0 |
| edible | 7 | 2,694 | 2 | 0 | 0 |
| tinctures | 13 | 224 | 0 | 0 | 0 |
| **topical** | **56** | **33** | 0 | **3** | 0 |
| merch | 0 | 0 | 243 | 0 | 262 |

Four categories are 100% grams. Two are ~95% mg. Merch is pack counts and free
text. The split is almost perfectly clean **by category** — which is the definition
of a discriminated union modelled as one nullable string.

`topical` is the exception that proves it: 56 grams, 33 mg, 3 oz/ml, in one
category. That is not variety, it is the absence of a rule. It is the same defect
the gold suites already catch — five always-fail cases where a topical's `Nmg` never
reaches `variant`.

`strain` is overloaded the same way, and the rulings are already scattered through
this repo's history rather than the schema:

| category | what `strain` actually holds |
| --- | --- |
| flower, preroll | cultivar — the real thing |
| edible (beverages) | flavour — "Black Cherry" |
| topical | scent — "Lavender" |
| merch | **colour** — "Pink" (ruled 2026-08-27) |

Each of those was a judgment call made under pressure because there was nowhere
else to put the value. They are defensible individually and incoherent together.

### The pipeline already concedes the point

`scripts/enrich.py` is 1,056 lines and mentions a specific category **105 times**:

```
merch 44   edible 11   flower 9   topical 9   tincture 8
beverage 7  concentrate 7   preroll 6   vape 4
```

Merch's 44 are all from this week — form-factor tokens, `merch_variant`,
`merch_strain`, a widened `SUBTYPES["merch"]` rail. That is what fixing one
category costs when the schema does not have a place for its attributes: the
"generic" pipeline grows a category-shaped lump.

## 2. The cardinality argument holds

| | |
| --- | --- |
| distinct brands | 731 |
| distinct strains | 3,719 |
| product rows | 10,415 |
| active listings | 16,031 |

3,719 strains across 731 brands is a **curatable vocabulary**. For comparison, the
curated maps that already drive the deterministic layer cover 18 brands of product
lines, 3 brands of strain aliases and 7 of format tokens. The ceiling on curation
is nowhere near reached, and the evidence from this session is that curated data
outperforms every prompt edit tried:

- `category` is 100% correct fleet-wide, driven by `CATEGORY_MAP` + `format_tokens.json`
- merch went from 223 to 886 product rows on deterministic rules alone, no model
- every regression this cycle came from a prompt edit; `_ENRICH_VERSION` 5 was
  written to fix one case and did not fix it (0/4 runs)

## 3. Verified listings — and why they cannot exist today

**A human correction is destroyed by the next scrape.** `import_listings.py`:

```sql
ON CONFLICT (dispensary_id, sku, COALESCE(variant, ''))
DO UPDATE SET subtype = EXCLUDED.subtype,
              strain  = EXCLUDED.strain,
              product_line = EXCLUDED.product_line, ...
```

Unconditional. There is no column the importer will not overwrite, and `enrich()`
likewise rewrites all four identity fields from the model or the token rules. So
today a reviewer's work has a lifetime of one scrape cycle. That alone justifies
the feature before any UI exists.

A verified flag needs four properties to be worth building:

1. **Survives import.** The upsert must exclude verified columns from `DO UPDATE`.
2. **Survives re-enrichment.** `enrich()` must skip verified rows entirely — which
   also makes them free, since they never reach the model.
3. **Survives a version bump.** `_ENRICH_VERSION` invalidates cache entries; a
   verified value is not a cache entry and must not be swept with them.
4. **Carries provenance.** Who, when, and which fields — because "verified" on a
   row whose name later changes is a claim about text that no longer exists.

Point 4 is the subtle one. Verification attaches to a `(listing, scraped_name)`
pair, not to a listing. If a dispensary renames a product, the verification is
stale and should lapse rather than silently vouch for the new name.

## What to actually build

### A. Per-category attributes, as a typed sidecar

Keep `listings` as the scrape record. Move identity into a per-category shape:

```
flower/preroll/vaporizers/concentrate   weight_g, count, infused (bool), lineage
edible/tinctures                        total_mg, per_piece_mg, count, form, flavour
topical                                 total_mg, volume_ml, scent, form
merch                                   form_factor, size, pack, colour, series, tips
```

Two ways to store it, and the choice matters less than the discipline:

- **`attributes jsonb`** on `listings`, one shape per category, validated in code.
  Cheap, no migration per category, queryable via GIN. Loses column typing.
- **Per-category tables** keyed on `listing_id`. Real types and constraints, more
  migration work, joins in the products view.

I would start with `jsonb` plus a schema registry in Python, because the shapes are
still moving. Freeze into columns once a category stops changing.

Keep `strain` meaning **cultivar only**, and let it be null everywhere it does not
apply. That single change removes the colour/flavour/scent overloads and makes
`strain_split` in the audit mean one thing.

### B. Category-owned enrichers

Replace the one generic pass with a registry — each category owns its extraction,
its rails, and its eval cases:

```python
ENRICHERS = {"flower": FlowerEnricher(), "merch": MerchEnricher(), ...}
```

The 105 category checks collapse into the enricher that owns each one. This is
mostly a re-home of code that already exists, not new logic. It also makes the
per-category gold suites natural — today there is no merch gold set at all, which
is exactly why the Blazy Susan collapse ran undetected.

### C. Verification, minimally

```
listings.verified_fields   jsonb   -- {"strain": {...}, "variant": {...}}
listings.verified_by       text
listings.verified_at       timestamptz
listings.verified_name_hash text    -- lapses the claim if the product is renamed
```

Then: `enrich()` skips rows with verified fields; the importer excludes them from
`DO UPDATE`; the audit reports verified coverage as a denominator, so "3 suspects
per 100" becomes "3 per 100 unverified".

## Sequencing

1. **Verification first.** It is small, it is the only item that protects work
   rather than producing it, and every hour of review before it exists is at risk.
2. **`strain` demotion to cultivar-only**, with colour/flavour/scent moving to
   category attributes. This is the change that makes the audit meaningful.
3. **One category through the enricher registry** — merch, since it is the most
   special-cased and has the least to lose. Prove the pattern, then migrate the rest.
4. **Per-category gold suites** as each one moves. No category should be refactored
   without a measurement that would have caught its last bug.

## What not to do

Do not start with the schema migration. The shapes in section A are inferred from
one week of looking at this data, and two of them (topical, merch) changed while
this document was being written. Get verification in place, move one category, and
let the shapes settle before they become DDL.
