# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

## Portal map basemap

The store map (`src/components/DispensaryMap.tsx`) needs a keyed tile provider.
CARTO — the provider the map originally used — now stamps *"API KEY REQUIRED"*
across every tile when it is called without a key.

Set two variables:

```
VITE_MAP_PROVIDER=thunderforest   # thunderforest | maptiler | stadia | carto
VITE_MAP_TILE_KEY=...
```

| Provider        | Default style         | Character                                     |
| --------------- | --------------------- | --------------------------------------------- |
| `thunderforest` | `transport-dark`      | Dark base, transit lines picked out in colour  |
| `maptiler`      | `streets-v2-dark`     | Clean dark streets, strong labels              |
| `stadia`        | `alidade_smooth_dark` | Minimal, low-clutter dark                      |
| `carto`         | Voyager + dark labels | Warm daylight colour toned down under labels   |

`VITE_MAP_STYLE` swaps a provider's style, `VITE_MAP_TILE_FILTER` overrides the
CSS filter used to tone it, and `VITE_MAP_TILE_URL` bypasses the presets for a
provider that isn't listed. With no key set, the map falls back to
OpenStreetMap's own tiles inverted into a night palette — fine for local dev,
not for production traffic.

Store pins are coloured by borough using MTA line colours; see
`src/utils/boroughs.ts`.
