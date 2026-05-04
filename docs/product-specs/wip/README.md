---
module: wip
roadmap_phase: 1
status: skeleton
last_updated: 2026-05-04
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

- `orders.released` — opens initial position at first step.
- `plc.equipment.cycle_done` — auto-records step out.

## Open questions

- TODO: regla de reconciliación cuando WIP físico no coincide con WIP de sistema (cierre de turno).
