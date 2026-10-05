# terpenomics mobile

The customer portal as an iOS app (Android comes along for free), built with
Expo and React Native. It talks to the same FastAPI backend and Supabase
project as the web portal in `ui/my-app`.

## What's shared with the web app

- **Types**: response types are imported straight from
  `ui/my-app/src/types` as `@web/types`, so a backend shape change that the
  web types pick up breaks this app's typecheck too, instead of drifting.
- **Pure helpers**: `@web/utils/format` (money, dates, distance).
- `metro.config.js` adds `ui/my-app/src` to Metro's watch folders so those
  imports bundle. Only import framework-free files from there: anything that
  touches the DOM, `import.meta.env` or Leaflet will not run on a phone.

Duplicated on purpose, because the web versions can't run here:
`src/lib/theme.ts` (CSS variables → values), `src/lib/phone.ts`
(`import.meta.env`) and `src/lib/api.ts` (the customer half of
`ui/my-app/src/api/client.ts`, minus admin). Change both sides together.

## Running it

```sh
cd mobile
npm install
cp .env.example .env.local   # fill in the API URL and Supabase publishable key
npx expo start
```

`expo-secure-store` and `expo-symbols` are native modules, so use a
development build rather than Expo Go:

```sh
npx eas-cli@latest build --profile development --platform ios   # simulator build, no Mac needed
# or, on a Mac with Xcode:
npx expo run:ios
```

TestFlight: `npx eas-cli@latest build --profile production --platform ios`
then `npx eas-cli@latest submit --platform ios`. Needs an Apple Developer
account; the bundle id is `com.terpenomics.app` in `app.json`.

Before declaring a change done: `npm run typecheck` and `npx expo lint`.

## What's in it

| Screen | Route | Backend |
| --- | --- | --- |
| 21+ age gate (once per device) | `src/app/age-gate.tsx` | none; stored in the Keychain |
| SMS sign-in | `src/app/sign-in.tsx` | `/auth/sms/start`, `/auth/sms/verify`, then `/me/link-customer` on first login |
| Home feed (combined) | `src/app/(tabs)/index.tsx` | `/me/feed?view=combined` |
| Shop → category | `src/app/(tabs)/shop/` | `/customer/categories`, `/customer/categories/{name}`, `/customer/products/detail` |
| Listing detail | `src/app/listing/[dispensaryId]/[listingId].tsx` | `/customer/dispensaries/{id}/listings/{id}` |
| Cart → reserve for pickup | `src/app/cart.tsx` | location check (`src/lib/region.ts`), then `POST /me/orders` |
| Orders (with cancel) | `src/app/(tabs)/orders.tsx` | `/me/orders`, `/me/orders/{id}/cancel` |
| Terpee points, receipts | `src/app/(tabs)/points.tsx` | `/me/points`, `/me/receipts` |
| Upload a receipt (modal) | `src/app/receipt.tsx` | `/me/partners`, `POST /me/receipts` |
| You | `src/app/(tabs)/profile.tsx` | `/me`, `/me/preferred-dispensaries` |

The cart holds one store's items at a time, because an order goes to one
store. Adding from a second store asks before replacing the cart. It enforces
the same per-line and line-count limits as `routes/orders.py`. It is in memory
only and resets on sign-out.

Receipt photos come from the camera or the photo library (`expo-image-picker`)
and are shrunk to 1600px JPEG before upload (`expo-image-manipulator`,
`src/lib/receiptImage.ts`), as the web portal does. Both are native modules, so
adding them needs a new development build.

The session lives in the iOS Keychain (`src/lib/supabase.ts`), chunked
because a Supabase session can exceed what SecureStore advises per value.

## Not ported yet

Roughly in order of value:

1. **Cross-store product page** (`ProductView`); category taps currently jump
   to the cheapest store's listing instead.
2. **Brands** and **Search** tabs.
3. **Map** and following/unfollowing stores (`react-native-maps` replaces
   Leaflet). Until then, stores are followed on the web.
4. Per-store feed view, price/terpene filters, purchase feedback.

Admin screens stay web-only.

## Before the App Store

Marketplaces like Leafly ship reserve-for-pickup apps on the App Store, so
this is a known path. App Store guideline 1.4.3 restricts apps that facilitate
cannabis sales. Apps like Leafly typically get through with:

- [ ] an **organization** Apple Developer account (a registered business, not
  an individual one);
- [x] a **21+ age gate** before sign-in (`src/app/age-gate.tsx`). Also set a
  17+ age rating in App Store Connect;
- [x] **geo-restriction**: placing an order requires the device to be in New
  York (`src/lib/region.ts`). Browsing works anywhere. Also limit App Store
  availability to the US;
- [x] **no in-app payment** for cannabis. Orders are pay-at-pickup.

Known gaps: the age confirmation is device-local self-attestation (the
backend has no date-of-birth field), and the location check is client-side
only. Neither is enforced by the API.
