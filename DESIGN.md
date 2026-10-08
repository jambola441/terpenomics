# Terpee design language

One system for the customer portal, the admin and partner pages, and the
mobile app. The values live in code, not here:

| What | Where |
|---|---|
| Colour, type, space, radius, motion | `ui/my-app/src/design/tokens.ts` |
| Icons (interface + product glyphs) | `ui/my-app/src/design/icons.ts` |
| Web accessors (`t.bg`, `font.family.display`…) | `ui/my-app/src/theme.ts` |
| Web primitives (Pill, Bullet, TerpeneProfile…) | `ui/my-app/src/components/ui.tsx`, `Icon.tsx` |
| App theme + primitives | `mobile/src/lib/theme.ts`, `mobile/src/components/ui.tsx`, `Icon.tsx` |
| Brand files | `ui/my-app/public/brand/`, `ui/my-app/public/favicon.svg`, `mobile/assets/` |

The app imports the web's token and icon files directly (`@web/design/...`), so
there is one copy. Change a value in `tokens.ts` and both platforms follow.

## The idea

**A field guide to what is on the city's shelves.** Three references, kept in
balance:

- **The specimen label** — botany and the lab. Mono eyebrows, hairline rules,
  numbers that line up, a warm paper white.
- **The subway map** — New York. Stores wear their borough's MTA line colour as
  a lettered bullet, on the map and everywhere else a store appears.
- **The terpene** — the thing the product is named after. Every terpene has a
  colour taken from what it smells like, and the terpene profile is the
  signature chart.

What it is not: neon green on black, emoji as icons, a rounded bubble for
everything.

## Colour

Two layers, after the Uniform design system (design.uniformrealestate.com):
**palette** primitives, and **roles** that screens use. Screens never write a
hex value. If a role is missing, add it to `tokens.ts`.

| Role | Value | Use |
|---|---|---|
| `bg` | Loam `#0c0f0d` | App ground — near-black tinted toward leaf green |
| `surface1/2/3` | `#131714` `#1a201c` `#242925` | Cards → inputs/chips → pressed |
| `border` / `borderStrong` | `#222723` / `#323934` | Hairlines; a raised surface is separated by its edge, not a shadow |
| `text1` | Paper `#f2f0e9` (16.9:1) | Names, headings, values |
| `text2` | `#bebeb6` (10.3:1) | Readable secondary |
| `text3` | `#93958d` (6.4:1) | Labels, captions — the lowest step allowed for text you need to read |
| `text4` | `#676a64` (3.5:1) | Placeholders, disabled, decoration only |
| `accent` | Resin `#f0b550` (10.5:1) | The primary action. Little else. |
| `accentInk` | `#221505` (9.7:1 on resin) | Text on a resin fill |
| `success` / `danger` / `warning` / `info` | leaf / ember / saffron / sky | State — always with a word or icon, never colour alone. Each has a `…Tint` wash and `…Edge` border |
| `tile` | `#f3f1ea` | The light plate product photos sit on |

**Resin** is the only brand colour: the amber of ripe trichomes, and of the cab
that gets you there. It marks the one thing to press on a screen (Reserve,
Add to cart, Save). Prices are paper white, not accent. Savings and "in stock"
are leaf green.

### Category, strain and terpene hues

All drawn from one OKLCH ring at the same lightness (L .78–.80, chroma ≤ .13),
so no hue shouts over another and every one is ≥ 8:1 on the ground.

- **Categories** each have a hue *and* a glyph (`categoryStyle()`), so colour is
  never the only difference: flower `bud`, pre-roll `preroll`, vapes `cart`,
  edibles `gummy`, concentrates `crystal`, tinctures `dropper`, topicals `tube`,
  merch `tote`.
- **Strain type** (indica / sativa / hybrid) is a lettered bullet — `I`, `S`,
  `H` — not another coloured pill, so "Flower · Hybrid" never shows two green
  pills side by side.
- **Terpenes** take the colour of their aroma (`terpeneStyle()`): myrcene mango,
  limonene citrus, caryophyllene pepper, linalool lavender, pinene pine… The
  profile is drawn as one labelled row per terpene with a bar for its share;
  the name and number carry identity, the colour is the second cue. (A stacked
  bar was tried and rejected: sixteen hues at one lightness can't be told
  apart side by side.)

### Stores

A store's avatar is a subway bullet: its initial on its borough's MTA colour
(`StoreBullet`; colours in `utils/boroughs.ts`) — Brooklyn orange, Manhattan
red, Queens purple, Bronx green, Staten Island blue, yellow with a black letter
when the borough is unknown. The map pins are the same disc.

## Type

| Face | Role | Notes |
|---|---|---|
| **Fraunces** 600 | Display: page titles, store names, section headers | Soft old-style serif. Never for UI controls or body copy. Tracking −0.015em. |
| **Public Sans** 400–700 | Everything you read and tap | Civic grotesk (from Uniform). Body 14, callout 15. |
| **IBM Plex Mono** 400/500 | Data: eyebrows, sizes (3.5g), potency, lab values, codes | Uppercase eyebrows at 11px, +0.08em. Figures that must line up use `className="num"` (tabular). |

All three are SIL OFL and self-hosted (`@fontsource*` on the web, TTFs via
`@expo-google-fonts/*` in the app) — no font CDN.

Scale (px): micro 10 · caption 11 · small 12 · body 14 · callout 15 · title 17
· heading 20 · display 24 · hero 30. Weights stop at 700 in UI; 800 is gone.

## Icons

One 24-unit line set (`design/icons.ts`), round caps and joins, stroke 1.75 by
default, inheriting the text colour. Interface glyphs are Lucide (ISC);
product glyphs are drawn for Terpee on the same grid. Use
`<Icon name="…" />` and `<CategoryIcon category={…} />`; never an emoji, never
a text arrow (`→`, `←`, `↗`) standing in for an icon.

| Need | Glyph |
|---|---|
| Back / forward / disclose | `arrow-left`, `chevron-right`, `chevron-down` |
| External link | `arrow-up-right` |
| Close / remove | `close` |
| Location | `pin`; locate me `locate` |
| Cart | `bag` |
| Points | `drop` (the resin bead from the mark) |
| Empty / error | `FeedState` draws one in a soft disc |

## The mark

A terpene ring holding a bead of resin: a hexagon (the six-carbon ring every
terpene skeleton is drawn with) around a filled drop. Resin on Loam. The
wordmark is `terpee`, lowercase, Fraunces 600, −0.02em. `<Logo />`
renders the lockup; `<Icon name="mark" />` the mark alone. Don't recolour it
beyond resin, paper, or resin-ink on a resin tile.

## Shape, space, motion

- Radius: xs 4 · sm 6 · md 8 · lg 12 · xl 16 · 2xl 20 · pill. Cards 12–16,
  inputs and buttons 8–10, chips pill. Tighter than before — objects, not bubbles.
- Space: 4pt grid (`space[1..8]` = 4…40). Screen gutters 16.
- Motion: 120 / 180 / 280ms, standard ease; a spring for sheets. Everything
  respects reduced motion.

## Components (web)

- **Primary button**: resin fill, `accentInk` text, 600–700 weight, radius 10.
- **Secondary**: transparent, `borderStrong` edge, `text1`.
- **Pill / tag**: mono 10.5–11px uppercase, tinted fill at 10%, edge at 36%.
  Status pills use `tone` (`neutral | accent | success | danger | warning | info`).
- **Eyebrow** (`Label`): mono uppercase, `text3`.
- **Section header**: Fraunces 20 + quiet "See all ›" in `text2`.
- **Product plate**: photos on `tile`; no photo → the category glyph sketched in
  `tileInk`, never a stock photo of some other product.
- **Admin**: the same tokens on desktop density; tables use `surface1` rows,
  `border` rules, mono uppercase headers.

## Principles, borrowed from Uniform and kept

1. Build with roles, not the palette.
2. Keep the words meaningful without the colour.
3. One accent, used sparingly.
4. Dark by default; the tokens are layered so a light theme is a second set of
   role values, not a rewrite.
5. No third-party requests for fonts or icons.

## What we did not take from Uniform

Uniform's palette, wordmark, symbol and "brand dot" belong to Uniform Real
Estate (its LICENSE-BRAND reserves them), and a real-estate slate-and-red
identity would read wrong on a cannabis marketplace. We took its method:
the two-layer token model, the role names, AA-tuned on-dark variants, Public
Sans and IBM Plex Mono, the mono eyebrow, the restraint.

## Shipping notes

- **Mobile needs a new development build.** Icons render through
  `react-native-svg`, a native module, so `eas build --profile development`
  (or `npx expo run:ios|android`) before the next dev session. Fonts load at
  runtime with `useFonts`, so they need nothing extra.
- **App icons** (`mobile/assets/*.png`) and the web favicons were regenerated
  from the mark; the old Expo and Vite placeholders are gone.
- **No stock fallbacks.** A product with no photo shows its category glyph on
  the plate. The six category photos that used to stand in were removed — they
  showed some other product.
- `expo-symbols` is no longer imported anywhere; it can be dropped from
  `mobile/package.json` whenever convenient.
