# NSG MES — Frontend

React 18 + Vite + TypeScript (strict) scaffold for the MES UI. Foundational
slice from **NSG-19**; every UI Story (NSG-20 orders list, NSG-30 login) builds
on this.

Stack is fixed by [ADR-0001](../docs/decisions/0001-stack-django-react.md):
React 18, Vite, TypeScript strict, **pnpm**. Dependency versions are pinned in
[`package.json`](./package.json) and locked in `pnpm-lock.yaml`.

## Prerequisites

- Node ≥ 20.
- pnpm 9.15.0. This repo pins it via the `packageManager` field, so
  [Corepack](https://nodejs.org/api/corepack.html) will use the right version:

  ```bash
  corepack enable          # one-time, may need elevated permissions
  # or, without global activation:
  corepack pnpm install
  ```

## Commands

| Command | What it does | AC |
|---|---|---|
| `pnpm install` | Install pinned dependencies. | — |
| `pnpm dev` | Start the Vite dev server with HMR at `http://localhost:5173`. | AC-1 |
| `pnpm build` | Type-check (`tsc --noEmit`) **and** produce a production build. Fails on any type error. | AC-2 |
| `pnpm typecheck` | `tsc --noEmit` in strict mode. | AC-2, AC-7 |
| `pnpm lint` | ESLint (typescript-eslint, `no-explicit-any`). | AC-7 |
| `pnpm test:unit` | Vitest unit/component tests (jsdom). | AC-3, AC-4, AC-5 |
| `pnpm test:e2e` | Playwright smoke test — boots the app and checks the page renders. | AC-6 |
| `pnpm gen:api` | Regenerate the typed API client from `openapi/schema.json`. | AC-4 |

First-time Playwright also needs browsers: `pnpm exec playwright install chromium`.

## Configuration (AC-5)

Copy `.env.example` to `.env.local` and adjust. Nothing is hardcoded to a
developer's machine:

- `VITE_API_BASE_URL` — base URL the typed client calls (default `/api`,
  relative so the dev proxy keeps requests same-origin).
- `VITE_API_PROXY_TARGET` — origin the Vite dev server proxies `/api` to
  (default `http://localhost:8000`).
- `VITE_DEV_PORT` — dev server / Playwright port (default `5173`).

The HTTP layer ([`src/api/http.ts`](./src/api/http.ts)) sends Django's session
cookie (`credentials: "include"`) and echoes the CSRF token (`X-CSRFToken`) on
mutating requests, reading it from the `csrftoken` cookie. **No credentials or
tokens are stored in `localStorage`.** Auth endpoints don't exist yet
(NSG-30/NSG-25); this behaviour is pre-wired so those Stories just plug in.

## Typed API client (AC-4)

The client is **generated**, never hand-written, and routes are never hardcoded:

```
openapi/schema.json  ──(pnpm gen:api)──►  src/api/generated/schema.d.ts
                                          consumed by src/api/http.ts (openapi-fetch)
```

`openapi/schema.json` is the OpenAPI document. As of NSG-19 the backend has **no
business endpoints** (`docs/generated/api-routes.md` = 0 endpoints), so the
schema is a minimal placeholder with one trivial `/health/` probe used to
validate the pipeline end-to-end.

**When the backend exists** (NSG-18 orders, NSG-25 auth), regenerate the schema
from drf-spectacular and rerun codegen — do **not** edit generated files:

```bash
# from the Django backend, once it exists:
python manage.py spectacular --file frontend/openapi/schema.json
# then, here:
pnpm gen:api
```

Changing the schema's operations/types and rerunning `pnpm gen:api` updates the
generated client (new operations and types appear) with no manual edits.

## Enumerated states (GP-010)

Order states, user roles, etc. must come from the generated client's enum
schemas or from typed `as const` objects — never scattered string literals. See
[`src/api/enums.ts`](./src/api/enums.ts) for the pattern to follow.

## Layering

`frontend/` is outside the Python layer rules in
[`ARCHITECTURE.md`](../ARCHITECTURE.md), but the cross-context ban still holds:
the frontend does **not** import from `apps/`. It talks to the backend only over
HTTP through the generated client.
