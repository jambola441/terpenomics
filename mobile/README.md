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
| SMS sign-in | `src/app/sign-in.tsx` | `/auth/sms/start`, `/auth/sms/verify`, then `/me/link-customer` on first login |
| Home feed (combined) | `src/app/(tabs)/index.tsx` | `/me/feed?view=combined` |
| Shop → category | `src/app/(tabs)/shop/` | `/customer/categories`, `/customer/categories/{name}`, `/customer/products/detail` |
| Listing detail | `src/app/listing/[dispensaryId]/[listingId].tsx` | `/customer/dispensaries/{id}/listings/{id}` |
| Orders (with cancel) | `src/app/(tabs)/orders.tsx` | `/me/orders`, `/me/orders/{id}/cancel` |
| You | `src/app/(tabs)/profile.tsx` | `/me`, `/me/preferred-dispensaries` |

The session lives in the iOS Keychain (`src/lib/supabase.ts`), chunked
because a Supabase session can exceed what SecureStore advises per value.

## Not ported yet

Roughly in order of value:

1. **Cart and checkout**: the web `CartDrawer` + `Checkout` → `POST /me/orders`.
   Without it the app browses and tracks orders but can't place one.
2. **Cross-store product page** (`ProductView`); category taps currently jump
   to the cheapest store's listing instead.
3. **Brands** and **Search** tabs.
4. **Map** and following/unfollowing stores (`react-native-maps` replaces
   Leaflet). Until then, stores are followed on the web.
5. Per-store feed view, price/terpene filters, purchase feedback.

Admin screens stay web-only.

## Before the App Store

Marketplaces like Leafly ship reserve-for-pickup apps on the App Store, so
this is a known path. App Store guideline 1.4.3 restricts apps that facilitate
cannabis sales. Apps like Leafly typically get through with:

- an **organization** Apple Developer account (a registered business, not an
  individual one);
- a **21+ age gate** at sign-up, and a 17+ age rating in App Store Connect;
- **geo-restriction** to where sale is legal (New York for now);
- **no in-app payment** for cannabis. Pay-at-pickup already satisfies this.

The age gate and geo-restriction aren't built yet. TestFlight internal testing
skips App Review, so none of this blocks development.
