---
adr: 0003
title: orders.released event contract — event-carried route
status: Accepted
date: 2026-06-02
deciders: Sebas (NSG founder)
tags: [orders, wip, events, contract, cross-context]
---

# 0003 — orders.released event contract: event-carried route

## Status

Accepted — 2026-06-02.

## Context and problem statement

NSG-39 implements a Celery consumer in the `wip` bounded context that must create a
zero `WipBalance` for **every route step** of a manufacturing order (OF) when it receives
the `orders.released` event. To do so it needs to know the route steps of that order.

Two constraints frame the problem:

1. **No cross-context synchronous calls.** NSG-32 explicitly forbids initialising WIP via a
   synchronous call ("la inicialización… nunca por llamada síncrona"), and `ARCHITECTURE.md`
   states "No cross-context synchronous calls". The `wip` context reacts to events and never
   imports `apps/orders/`.
2. **The contract gap.** The `orders` spec documents `orders.released` **without a payload**
   (only `orders.created` carries a schema: `{order_id, product_id, qty, due_date, schema_version: 1}`),
   and **no documented event carries the route**. Without defining this, `wip` has no legitimate
   way to obtain the steps.

The event contract is **versioned and append-only** (`ARCHITECTURE.md`). Changing it after
publication forces a new `schema_version` plus re-emission / migration. The decision binds both
NSG-16 / `orders` (what it emits) and NSG-39 / `wip` (what it consumes): it is an irreversible
cross-context contract that the Spec Writer must not invent unilaterally. It was escalated via the
Question ticket NSG-43.

## Decision drivers

- **No synchronous cross-context calls** (NSG-32, `ARCHITECTURE.md`): `wip` must self-initialise
  from the event alone.
- **Irreversibility of the contract**: events are versioned and append-only; getting the payload
  wrong is expensive to undo.
- **Phase-1 cost**: minimise the infrastructure `wip` must build in Phase 1.
- **Coupling vs. decoupling**: weigh embedding the route in the event against maintaining a separate
  read-model projection.

## Considered options

### A) Event-carried state transfer ← **chosen**

`orders.released` includes the full route, e.g.
`{order_id, route: [{sequence, step_id, equipment_id}], schema_version: 1}`.

Pros:
- `wip` initialises solely from the payload; satisfies "no synchronous calls" with no extra
  infrastructure.
- Minimal Phase-1 work in `wip` (no projection store, no extra consumer).

Cons:
- Couples the event size to the route length.
- Requires NSG-16 / `orders` to emit the route inside the event.

### B) Read-model projection in `wip`

`orders` emits the route in some event (today `orders.created` does **not** carry it) and `wip`
maintains a local projection; `orders.released` then carries only `{order_id}`.

Pros:
- Minimal, decoupled payload.

Cons:
- Requires a new event/field for the route in `orders` plus projection storage and a projection
  consumer in `wip` — more Phase-1 work.

### C) Synchronous read via the `orders` HTTP interface (`GET /api/v1/orders/{id}/route`)

Listed only to be formally rejected.

Cons:
- **Violates** NSG-32 and the event-bus rule ("No cross-context synchronous calls").

## Decision outcome

**Option A — event-carried state transfer.** The `orders.released` event carries the complete
route in its payload, published as `schema_version: 1`, e.g.:

```json
{
  "order_id": "<uuid>",
  "route": [
    {"sequence": 1, "step_id": "<uuid>", "equipment_id": "<uuid>"}
  ],
  "schema_version": 1
}
```

`wip` initialises one zero `WipBalance` per route step directly from this payload, with no
synchronous call to `orders` and no local projection. This is the only option consistent with
"no synchronous calls" without building an extra projection in Phase 1.

The contract must be documented in `docs/product-specs/orders/README.md` (payload of
`orders.released`) and `docs/product-specs/wip/README.md` (event consumed) as a follow-up; those
spec edits are handled by the Spec Writer / Worker on NSG-16 and NSG-39, not by this ADR.

### Positive consequences

- `wip` self-initialises from the event alone; the "no synchronous cross-context calls" rule
  (NSG-32, `ARCHITECTURE.md`) is preserved with zero extra infrastructure.
- No projection store or extra consumer needed in `wip` for Phase 1 — lowest implementation cost.
- A single, self-contained, versioned event is easy to replay and reason about.

### Negative consequences

- The event payload grows with the route length; very long routes produce larger messages.
- NSG-16 / `orders` must assemble and emit the full route inside `orders.released` at release time.
- If the route shape later needs to change, a new `schema_version` and re-emission/migration are
  required (inherent to the append-only contract).

## Pros and cons summary

Option A wins because it is the only path that honours "no synchronous cross-context calls" while
avoiding the extra projection infrastructure that Option B would impose in Phase 1. Option C was
rejected outright for violating the event-bus rule. The larger-payload cost is acceptable for
Phase-1 route sizes and is the price of decoupling `wip` from `orders` at runtime.

## Links

- Source decision: Question ticket [NSG-43](https://linear.app/nsg-engineering/issue/NSG-43/el-evento-ordersreleased-transporta-los-pasos-de-ruta-de-la-of).
- Blocking story: [NSG-39](https://linear.app/nsg-engineering/issue/NSG-39/initialize-wip-balances-from-order-route-on-order-release) — Initialize WIP balances from order route on order release.
- Emitting context: [NSG-16](https://linear.app/nsg-engineering/issue/NSG-16/crear-bounded-context-orders-con-modelos-base) — `orders` bounded context.
- Epic: [NSG-32](https://linear.app/nsg-engineering/issue/NSG-32/mes-phase-1-wip-work-in-process-inventory-per-route-step) — MES Phase 1 WIP per route step.
- Event-bus rule: [/ARCHITECTURE.md](../../ARCHITECTURE.md) (no cross-context synchronous calls; versioned append-only events).
- Orders spec: `docs/product-specs/orders/README.md` (`orders.released` payload — follow-up).
- WIP spec: `docs/product-specs/wip/README.md` (consumed event — follow-up).
