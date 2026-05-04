---
title: Frontend — conventions and stack
status: skeleton
last_updated: 2026-05-04
---

# FRONTEND

Conventions for `frontend/`. React 18 + Vite + TypeScript. Skeleton — populated by Workers as the first screens are built.

## Stack

- **React 18** with function components + hooks; no class components.
- **TypeScript strict** (`strict: true`, `noUncheckedIndexedAccess: true`).
- **Vite** for dev server and build.
- **TanStack Query** for server state; **Zustand** (or React context) for local UI state. No Redux.
- **TanStack Router** (or React Router) — TBD by first frontend Worker.
- Charts: **Recharts** for simple, **ECharts** for dense dashboards. Gantt: TBD.

## Folder layout (proposed)

```
frontend/
├── src/
│   ├── routes/         # one file per page
│   ├── components/     # reusable, dumb where possible
│   ├── features/       # one folder per bounded context (orders/, oee/, etc.)
│   ├── api/            # generated client from DRF schema
│   ├── lib/            # framework-agnostic helpers
│   └── styles/
└── tests/              # Playwright (E2E) and Vitest (unit)
```

## API client

Auto-generated from DRF's OpenAPI schema (`drf-spectacular`) into `frontend/src/api/`. Workers do not hand-write the client.

## Auth

Session cookie + CSRF. Token auth for mobile / kiosk later.

## Styling

Tailwind (v4 if stable by Phase 1, otherwise v3). Utility-first; component classes only when a pattern repeats > 3 times.

## Accessibility

WCAG 2.1 AA target. Buttons have labels; form fields have associated labels; colour-coded status (andon) always paired with text/icon.

## i18n

Initially Spanish (es-MX) only. Externalise strings to `src/i18n/` from day one even if only one locale.

## Testing

- **Playwright** for E2E (used by QA Smoke agent).
- **Vitest** for components with non-trivial logic.
- Visual regression: TBD.
