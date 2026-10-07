# Listing identity conventions

One place for how a listing's identity is written: what the catalog entries follow, what
the labelled test cases expect, and what the review agent is told. Where a rule here
and a catalog disagree, one of them is wrong; fix it rather than carry both.

A listing's identity is five fields: **category, subtype, strain, product line, size**.

## Who decides

From strongest to weakest:

1. A field a person signed (`verified_fields`).
2. The catalog entry of a trusted match (`exact`, `jev` at p ≥ 0.85, 0.90 for catalogs
   built from store listings, or `manual`). It gives subtype, strain and product line;
   the size follows the entry when the listing's readings confirm it.
3. House rules: curated product lines and strain spellings (`data/product_lines.json`,
   `data/strain_aliases.json`).
4. Enrichment: Jev, the size code and chooser, a model.

## Category and subtype

- The categories and subtypes are `scripts/taxonomy.py`'s.
- A pre-roll keeps no subtype.
- A format word in the listing's own name beats the entry's subtype ("Pod" on a listing
  of a cart entry is a pod).

## Product line

A line is a name the brand gives a family of its products.

- Not a format (cart, gummies, chews), a strain type (indica), a size, a potency, or
  another brand (Camino is its own brand, not a Kiva line).
- A word the store puts in quotes ('Bliss') is usually the line, subject to the effect
  rule below.
- A line stays in its category, except a family the brand prints across formats
  (Papa & Barkley's Releaf is a gummy, a tincture and a balm).
- **The effect rule** (2026-10-05). An effect name (Calm, Bliss, Sleep, Energy, Social…)
  is the line only when it is the only family name the brand gives the product: Florist
  Farms' "Calm | Peach Gummies" is line Calm, strain Peach. When the brand names a family
  and puts effects under it, the family is the line and the effect goes in the strain:

  | Listing | Line | Strain |
  | --- | --- | --- |
  | Camino Sours 'Balance' Orchard Peach | Sours | Balance Orchard Peach |
  | Camino Wild Berry 'Chill' Gummies | Gummies | Chill Wild Berry |
  | Camino Chews Pineapple Paradise | Fruit Chews | Bliss Pineapple Paradise |
  | 1906 Bliss Drops | Drops | Bliss |
  | Level Protab Boost | Protab | Boost |
  | Ayrloom Mood – Bliss | Mood | Bliss |
  | Papa & Barkley Sleep Releaf | Releaf | Sleep |

  The catalog's wording wins where the listing leaves the effect out: Camino's
  "Pineapple Habanero | Gummies" is the catalog's Uplifting Pineapple Habanero.

## Strain

The name that tells the product apart from the brand's others in its line.

- A flavour counts as the strain for edibles, drinks, vapes and topicals; so does a
  topical's scent or blend name (Ayrloom's Revive, Restore, Rescue).
- Never the brand, the line, a format, a size or a potency.
- Keep version numbers ("Creamsicle x Rainbow Beltz 2.0").
- A phrase that only restates the format ("Milk Chocolate" on a chocolate bar) is not
  the strain; with nothing else, the lineage (Sativa, Indica, Hybrid) is.
- Spelling is the catalog's, or the curated alias's. A brand's self-censored spelling
  ("Alaskan Thunder Fu*k") is never copied onto a listing.

## Size

- **The package total.**
- **Weights** (flower, pre-roll, vaporizers, concentrate) in grams. A cart stated in mg
  reads in grams ("1000mg" is 1g).
- **Doses** (edible, tinctures, topical) in mg of **THC only**:
  - not CBD, CBN or CBG;
  - not THC plus the others ("150MG THC : 450MG CBD" is 150mg, not 600mg);
  - a per-piece figure times the count when the text gives it per piece;
  - two THC figures for one piece add up (REMZzz's "2.5mg THC Hash, 2.5mg THC/piece" is
    5mg a piece, and its 1:1:1 ratio and "100 mg/unit" agree).
- New York caps an edible package at 100mg of THC: a figure above it is not one
  edible package's.
- Catalog entries for dose products are written as the pack and total ("20pk 100mg");
  a listing's size is the total ("100mg").
- When the readings disagree, `size_choice` decides. Code alone writes a size only when
  every reading agrees (`enrich.stated_size`).
