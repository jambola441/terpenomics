# Storefront recipes

One file per brand, `<brand-slug>.json`, read by `scripts/storefront.py`. A recipe says
where a brand's own product list is and how to read it; the script then runs it with no
model. PIPELINE.md, "Brand catalogs", says how storefront catalogs fit with the others.

## Writing or fixing one

1. Find the catalog. A Shopify `/products.json`, a WooCommerce Store API
   (`/wp-json/wc/store/v1/products`), a WordPress post type (`/wp-json/wp/v2/<type>`),
   product cards in a page's HTML, or JSON a page loads or embeds. Use the New York
   catalog where the brand has several: a state filter in the URL (`?state=81`,
   `?markets=47`), an `NY` tag, or a New York page.
2. Write the recipe (below). Start from `florist-farms.json`.
3. Run `python3 scripts/storefront.py check --brand "<Brand>" --via-http` and iterate until:
   - no `UNPARSED` line you did not mean (a skip rule is better than an accident);
   - no `NO SIZE` line — every entry has a gram weight (flower, pre-roll, vape,
     concentrate) or an mg dose (edible, tincture, topical);
   - the store products "on the site" are most of what stores sell. The ones listed as
     "only at stores" should be products the site really lacks (old stock, another
     state's line), not ones your rules misread — compare the names.
4. The brand name must be ours exactly (`listings.scraped_brand`), or check finds no
   store listings to compare with.

A site that lists strains but not which formats and sizes each comes in (a strain
list, a format page, lab results without sizes) cannot make entries; leave that brand
on its bootstrap catalog.

## Format

```json
{
  "brand": "Florist Farms",
  "site": "https://www.floristfarms.com",
  "source": {"kind": "shopify_json", "url": "https://www.floristfarms.com/products.json"},
  "learned": "when, by whom, what the site had",
  "notes": ["what the next person needs to know about this site"],
  "skip":     [{"when": {"title": "(?i)hoodie|hat"}, "why": "apparel"}],
  "category": [{"when": {"title": "(?i)pre-?roll"}, "set": {"category": "preroll"}}],
  "title":    [{"when": {"category": "^preroll$"},
                "match": "^(?P<strain>[^|]+?)\\s*\\|\\s*(?P<line>Live Resin Infused)\\s*\\|",
                "set": {"size": "1g"}}]
}
```

**source.kind**

| kind | url | also |
| --- | --- | --- |
| `shopify_json` | `https://x.com/products.json` | one item per variant; variant title is `variant` |
| `wc_store_api` | `https://x.com/wp-json/wc/store/v1/products` | one item per variation |
| `wp_json` | `https://x.com/wp-json/wp/v2/<type>` (filters allowed: `?state=81`) | term names are `tags`, class_list is `product_type`, ACF fields are `meta` |
| `html` | a listing page | `item`: CSS selector for one product (omit for one product per page); `fields`: our field -> selector (`"h3"`, `"a@href"`, `"@data-cat"`, `"."`); `pages`: `{"param": "page", "from": 1, "to": 15}`, or `urls`, or `sitemap`: `{"url": ".../sitemap.xml", "match": "/products/"}` |
| `json` | an API, or a page that embeds JSON | `items`: dot path to the products (`data.allProducts.nodes`, `*` fans out); `fields`: our field -> dot path; `extract`: regex whose group 1 is the JSON in a page; `lenient`: true for a JS object literal |

`post` (a form body) makes `html`/`json` requests POSTs, for an `admin-ajax.php` "load more";
with `pages` and `"in_post": true` the page number goes into the body as `{page}`. A paged
source ends at its first missing or empty page. `query` (`{"geocode": "us-ny"}`) adds
parameters to every page of a `urls` or `sitemap` source, for a site that shows a state's
sizes only in that state's view. One missing page of a list costs that product; most of
them missing fails the fetch.

**Fields** rules can test: `title`, `product_type`, `tags`, `vendor`, `url`, `body`,
`variant`, `meta`, `page` (the page an html/json item was read from) — and in a title
rule, `category`. Each is a regex (`re.search`; anchor
with `^...$` for an exact value; `(?i)` for case).

**Rules.** Each list is tried in order; the first match wins.
- `skip`: what is not a product we model — apparel, accessories, gift cards, bundles.
- `category`: `set.category` is one of flower, preroll, vaporizers, edible, concentrate,
  tinctures, topical (merch and other are not catalogued); `set.subtype` where the site
  says one the title does not. Prefer format words in the title over a site's own type
  field when they disagree — sites mislabel.
- `title`: `match` on the title with named groups `line`, `strain`, `strain2` (joined after
  `strain`, for a title that splits the product's name: "10mg 'Deep Sleep' Blackberry
  Dream"), `size`, `size2`;
  `extract` adds groups found in other fields (`{"body": "SIZE:\\s*(?P<size>\\d+\\s*CT)"}`);
  `set` gives constants (`line`, `strain`, `size`, `subtype`) for what the site leaves out.

**`store_aliases`** for products stores name differently from the site, so `check`
and `push` see them as the site's rather than as store-only products (which a push would
add as duplicates): `{"lines": {"Up": "", "Down": ""}, "names": {"Big Apple": "Sour
Apple"}}` — a store's line or strain on the left, the site's on the right, "" for none.
Use it only for names you have confirmed are the same product. An alias applies in every
category: `{"Gorilla Glue": "GG4"}` for a site that renamed its vapes would also turn the
stores' "Kief Coated Gorilla Glue" pre-roll into GG4. When that would be wrong, set the
name with a `title` rule for the one category instead.

**`title_case`: true** for a site that writes names in capitals ("UPLIFTING Pineapple"):
capitalised words longer than three letters become Title case, shorter ones (OG, GSC,
MAC) stay.

**What an entry gets.** Name is line + strain. Entries are one per product and size: a
site that repeats a product (a lab-results list, one row per lot) keeps the first. Size is read by `scripts/sizes.py` from
`size` (+ `size2`), else the variant, else the title: weight categories are written as
the package total ("3.5g"; "1/2 Gram Pre-Rolls | 7pk" is 3.5g), doses with the pack
("10pk 100mg"). Subtype comes from format words in the title (Cart, AIO, Pod) unless a
rule sets it; pre-rolls have none. A product line is the brand's named line ("Live
Resin Infused", "Calm"), not a format word or a strain type. An effect (Calm, Sleep, Bliss)
is the line only when the brand names no family; when it does (Camino's Sours, Ayrloom's
Mood), the family is the line and the effect goes into the product's name.
