---
module: orders
roadmap_phase: 1
status: skeleton
last_updated: 2026-06-03
---

# Orders

## Overview

Bounded context that owns the **manufacturing order (MO/OF)** lifecycle. Receives orders (manually or from ERP), validates against routing and BOM, releases them to the floor, tracks state transitions, and closes them when the WIP context confirms completion.

## Domain entities

- `ManufacturingOrder` — id, product, qty, route, due_date, status.
- `RouteStep` — sequence, equipment, expected cycle time.
- `OrderStatus` — enum: `draft → released → in_progress → completed → closed`.

_(Spec Writer fills invariants and value objects per ticket.)_

## Use cases

- `create_order(...)` — emits `orders.created`.
- `release_order(order_id)` — validates BOM, emits `orders.released`.
- `transition_state(order_id, new_state)` — guarded by state machine.
- `close_order(order_id)` — only callable after WIP confirms completion.

## API contract

`/api/v1/orders/` — list, create, retrieve, transition. _(Spec Writer fills exact schemas.)_

## Events emitted

- `orders.created` — `{order_id, product_id, qty, due_date, schema_version: 1}`
- `orders.released` — `{order_id, route: [{sequence, step_id, equipment_id}], schema_version: 1}`
- `orders.state_changed`
- `orders.closed`

### `orders.released` payload — event-carried route

`orders.released` carries the **full route** (ordered list of steps) inline. This is
event-carried state transfer: `release_order` assembles the order's route and publishes it
within the event, so downstream contexts (notably `wip`) self-initialise from the payload
alone — no synchronous read-back into `orders` and no separate read-model projection.

```json
{
  "order_id": "<uuid>",
  "route": [
    {"sequence": 1, "step_id": "<uuid>", "equipment_id": "<uuid>"}
  ],
  "schema_version": 1
}
```

- `route` is ordered by `sequence` (ascending) and is non-empty for a releasable order.
- Each entry identifies one `RouteStep`: its `sequence`, its `step_id`, and the `equipment_id`
  where the step runs.
- Published as `schema_version: 1`. The contract is versioned and append-only — any change to
  the route shape requires a new `schema_version` and re-emission/migration.

Rationale and the alternatives considered are recorded in
[ADR-0003](../../decisions/0003-orders-released-event-contract.md). The driving constraint is
"no cross-context synchronous calls" (`ARCHITECTURE.md`, NSG-32).

## Events consumed

- `wip.completion_confirmed` — triggers `close_order`.

## Open questions

- TODO: ¿Permite parcial release (split de cantidad)? Spec Writer debe escalar a Sebas.
- TODO: ¿Cómo se identifica externamente la OF — autoincremental o vienen del ERP?
