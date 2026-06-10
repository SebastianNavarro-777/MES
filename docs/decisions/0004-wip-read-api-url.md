---
adr: 0004
title: WIP read API URL — wip-owned positions endpoint
status: Accepted
date: 2026-06-02
deciders: Sebas (NSG founder)
tags: [wip, orders, api, contract, cross-context, frontend]
---

# 0004 — WIP read API URL: wip-owned positions endpoint

## Status

Accepted — 2026-06-02.

## Context and problem statement

NSG-41 adds a panel to the order (OF) detail screen that shows WIP balances per route
step, consumed from the backend through a fetch hook (TanStack Query) living in `frontend/`.
The backend endpoint does not exist yet (its sibling ticket NSG-37, "Expose REST API to read
WIP balances by order and route step", is not built), and the read projection crosses two
bounded contexts.

Two sources disagree on the URL the frontend should call:

1. **The Story (NSG-41)** says to consume `GET /api/v1/orders/{id}/wip/`.
2. **The authoritative `wip` spec** (`docs/product-specs/wip/README.md`) documents the read
   projection as `/api/v1/wip/positions/`.

The conflict matters because `ARCHITECTURE.md` and the WIP Phase-1 Epic (NSG-32) forbid
coupling the two contexts — `apps/wip/` must not import `apps/orders/`, and there are no
synchronous cross-context calls. Nesting the WIP read under the `orders/` namespace would force
`orders` to expose or proxy `wip` data, tensioning that boundary.

This is a cross-context API contract that the frontend hook will hard-code. Choosing wrong means
the hook targets a URL that later changes, forcing rework on both frontend and backend and risking
a context-boundary violation. The endpoint not yet existing made it un-inventable without rework
risk, so it was escalated via the Question ticket NSG-42.

## Decision drivers

- **Bounded-context boundary** (NSG-32, `ARCHITECTURE.md`): `orders` must not expose or proxy
  `wip` data; `apps/wip/` does not import `apps/orders/`.
- **Single source of truth for the contract**: the `wip` spec already documents the read
  projection under the `wip` namespace.
- **Irreversibility**: the frontend hook hard-codes the URL; getting it wrong forces dual rework.
- **Phase-1 cost**: minimise the infrastructure built for a simple read in Phase 1.

## Considered options

### A) `GET /api/v1/wip/positions/?order_id={id}` ← **chosen**

The `wip` context owns and exposes the read projection; the frontend filters by `order_id`.

Pros:
- Matches the contract already documented in `docs/product-specs/wip/README.md`.
- Respects the context boundary — `orders` exposes no `wip` data.
- No new composition infrastructure needed.

Cons:
- The Story text (NSG-41) must be corrected to point at this URL.

### B) `GET /api/v1/orders/{id}/wip/`

Matches the current Story text and is a parent-resource-oriented URL.

Cons:
- Forces `orders` to expose/proxy `wip` data, coupling both contexts in tension with
  `ARCHITECTURE.md` and the NSG-32 Epic decision.

### C) BFF/gateway layer aggregating both contexts behind `/api/v1/orders/{id}/wip/`

Keeps the Story URL without `orders` importing `wip`.

Cons:
- Requires a composition layer not yet designed — over-cost for Phase 1.

## Decision outcome

**Option A — `GET /api/v1/wip/positions/?order_id={id}`.** The `wip` bounded context owns and
exposes its read projection of balances; the frontend panel queries it filtering by `order_id`.
This is the only option that respects the context boundary (NSG-32, `ARCHITECTURE.md`) while
matching the contract already documented in the `wip` spec, with no extra Phase-1 infrastructure.

Follow-ups (handled by the Spec Writer / Worker on the relevant tickets, not by this ADR):

- **Correct the Story text** in NSG-41 to consume `GET /api/v1/wip/positions/?order_id={id}`.
- **Pin the response schema** on the backend exposure ticket NSG-37: per `route_step`,
  `qty_in`, `qty_out`, `qty_scrap`.

### Positive consequences

- The context boundary is preserved with zero extra infrastructure: `orders` exposes no `wip`
  data and `apps/wip/` does not import `apps/orders/`.
- The frontend hook targets the URL the `wip` spec already documents — one source of truth.
- No BFF/composition layer needed in Phase 1.

### Negative consequences

- The Story text in NSG-41 must be corrected (the original `orders/`-nested URL is dropped).
- The URL is less "parent-resource-oriented" than `/orders/{id}/wip/`; clients filter by query
  parameter instead of a nested path.

## Pros and cons summary

Option A wins because it is the only path that honours the context boundary (NSG-32,
`ARCHITECTURE.md`) while matching the already-documented `wip` contract, at no extra Phase-1 cost.
Option B was rejected for coupling `orders` to `wip`; Option C for requiring a composition layer
not justified in Phase 1. The cost is a one-line correction to the Story text.

## Links

- Source decision: Question ticket [NSG-42](https://linear.app/nsg-engineering/issue/NSG-42/bajo-que-url-expone-wip-la-lectura-de-balances-por-of).
- Blocking story: [NSG-41](https://linear.app/nsg-engineering/issue/NSG-41/show-wip-balances-on-the-order-detail-screen) — Show WIP balances on the order detail screen.
- Backend exposure ticket: [NSG-37](https://linear.app/nsg-engineering/issue/NSG-37) — Expose REST API to read WIP balances by order and route step (pin the response schema here).
- Epic: [NSG-32](https://linear.app/nsg-engineering/issue/NSG-32/mes-phase-1-wip-work-in-process-inventory-per-route-step) — MES Phase 1 WIP per route step.
- Context boundary rule: [/ARCHITECTURE.md](../../ARCHITECTURE.md) (no cross-context coupling / synchronous calls).
- WIP spec: `docs/product-specs/wip/README.md` (read projection `/api/v1/wip/positions/`).
- Related contract ADR: [0003](0003-orders-released-event-contract.md) — orders.released event contract.
