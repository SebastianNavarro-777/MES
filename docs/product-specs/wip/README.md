---
module: wip
roadmap_phase: 1
status: skeleton
last_updated: 2026-06-03
---

# WIP (Work-In-Process)

## Overview

Tracks units in process at every step of every active manufacturing order. Reconciles with `orders` (consumes `orders.released`) and `traceability` (emits stock movements per lot).

## Domain entities

- `WipPosition` — order_id, route_step, qty_in, qty_out, qty_scrap.
- `WipMovement` — append-only ledger of in/out/scrap deltas.

## Use cases

- `record_step_in(...)` / `record_step_out(...)` — emits `wip.movement_recorded`.
- `confirm_completion(order_id)` — when last step balances, emits `wip.completion_confirmed`.

## API contract

`/api/v1/wip/positions/` — read-only projection. Movements are recorded via the operator UI or via PLC events.

## Events emitted

- `wip.movement_recorded`
- `wip.completion_confirmed`

## Events consumed

- `orders.released` — `{order_id, route: [{sequence, step_id, equipment_id}], schema_version: 1}`.
  Initialises one zero WIP position per **route step** (not only the first), built solely from
  the event payload — no synchronous call back into `orders`. See below.
- `plc.equipment.cycle_done` — auto-records step out.

### Initialisation from `orders.released`

The `orders.released` event carries the order's full route inline (event-carried state transfer;
see [ADR-0003](../../decisions/0003-orders-released-event-contract.md)). On receipt, the `wip`
consumer creates one zero-quantity WIP position for **every** step in `route`, keyed by
`(order_id, step_id)`, reading `sequence` and `equipment_id` straight from the payload.

This keeps `wip` decoupled from `orders` at runtime: it never imports `apps/orders/` and never
issues a synchronous read, honouring "no cross-context synchronous calls" (`ARCHITECTURE.md`,
NSG-32). Consumption is idempotent — replaying `orders.released` for an order that already has
positions must not create duplicates.

## Open questions

- TODO: regla de reconciliación cuando WIP físico no coincide con WIP de sistema (cierre de turno).
