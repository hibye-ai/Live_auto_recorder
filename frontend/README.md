# Broadcast library frontend

The React + TypeScript UI is embedded in the existing console at `/broadcasts`
and `/jobs`. The original dashboard and navigation remain in use; old `/v2`
links redirect to the existing console. Node.js is needed only for development
and building the assets, not as a separate runtime server.

## Build and development

Requires Node.js 22.12+ (or 24) and npm.

```sh
cd frontend
npm ci
npm run build
npm run dev       # rebuild on changes; not a Vite app server
```

Start `python app_entry.py` from the repository root and visit
`http://127.0.0.1:5000/broadcasts` or `/jobs`. The build writes
`templates/static/library/library.js` and `library.css` (plus any chunks or
assets). Docker builds these assets automatically.

Viewing the library does not enable the experimental durable engine. Keep
`LAR_V2_ENABLED=false` until the prerequisites and real-device release gates
in the [durable engine guide](../docs/v2/README.md) and
[validation checklist](../docs/v2/RELEASE_VALIDATION.md) are satisfied.

## Verification

```sh
npm test
npm run build
npx playwright install --with-deps chromium
npm run test:browser
```

The default browser tests use the real console templates with synthetic,
intercepted API responses; they do not use installation data. Set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` to choose a Chromium installation.
`UI_REAL_APP=1 npm run test:browser` uses a temporary full-app integration
fixture with synthetic media and empty configuration. Do not weaken browser
sandbox or security settings to run tests.

## Implementation notes

TanStack Query manages server state; the URL retains library filters and
selection. Mutations represent accepted requests, not completed jobs. Original
recording files are preserved, and server-side request validation remains the
source of truth. Keep API fixtures and `src/types.ts` aligned with server
contract changes.
