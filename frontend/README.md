# DEC-MAPF research workspace frontend

React + TypeScript + Vite client for the local `/api/v1` application API. The main viewport is Canvas 2D; the separate `spike.html` retains a reproducible Canvas/Pixi comparison.

From the repository root:

```bash
npm --prefix frontend ci
npm --prefix frontend run schema
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend test
```

Browser tests use an actual locally spawned Python API, temporary run storage and real solvers. The macOS run uses installed Chrome; CI uses Playwright Chromium. Build before testing. For interactive development start the API on port 8000, then run `npm --prefix frontend run dev`.

See [workspace guide](../docs/gui/WORKSPACE.md), [contracts](../docs/gui/CONTRACTS.md) and [integration policy](../docs/gui/INTEGRATION_POLICY.md). Dependency versions are exact in package.json and resolved in package-lock.json. Generated TypeScript types are in `src/api/generated.ts`.

No remote fonts, authentication SDKs, analytics or paid API are required by the workspace. Inherited unused Vite/React template graphics are excluded from the final bundle; the takeover backup preserves them. UI diagrams, styles and Canvas graphics are code-native.
