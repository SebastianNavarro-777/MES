---
module: wip
roadmap_phase: 1
status: skeleton
last_updated: 2026-06-13
---

# WIP (Work-In-Process)

## Overview

Tracks the quantity in process at every step of every active manufacturing
order. Reconciles with `orders` (reacts to `orders.released`; never imports
`apps/orders/`) and `traceability` (emits stock movements per lot).

> **Vocabulary reconciliation (Story NSG-33 / Epic NSG-32).** Earlier drafts of
> this spec named the entities `WipPosition` / `WipMovement`. The Architect's
> most recent and specific expression — Epic NSG-32 and Story NSG-33 — models the
> Phase-1 skeleton as a `WipBalance` entity plus the value objects `RouteStepRef`
> and `Quantity`, with a base `WipDomainError`. This spec now follows that
> vocabulary. The drift previously forced a default-of-record on NSG-33. The
> movement/operation entities are ratified in the follow-up Story NSG-34, **not**
> in the skeleton.

## Domain entities (Phase-1 skeleton — NSG-33)

- `WipBalance` — entity identified by a `RouteStepRef`; holds the current
  in-process quantity for one (order, route step). Built with non-negative
  `Quantity`; invalid data raises `WipDomainError`. WIP is **mutable** stock
  (see *Golden principles* below).

## Value objects

- `RouteStepRef` — references a manufacturing order's route step by identifier
  (e.g. `order_id` + route-step id). Does **not** import `apps/orders/`
  (cross-context boundary, ARCHITECTURE.md). Immutable, value-equality.
- `Quantity` — non-negative quantity. Uses `decimal.Decimal`, **never** `float`,
  because WIP can be fractional (kg, m) or discrete (pieces) and float
  introduces precision errors (spirit of GP-002). Immutable, value-equality;
  constructing with a negative value raises `WipDomainError`.

## Exceptions

- `WipDomainError` (`apps/wip/domain/exceptions.py`) — base for all `wip` domain
  errors. The domain never raises built-ins such as `ValueError` / `RuntimeError`
  (GP-012).

## Stock-movement operations (ratified in NSG-34 — out of skeleton scope)

The in/out/scrap movement operations and the "balance never negative" invariant
are implemented in the follow-up Story NSG-34, not in the skeleton. The exact
entity naming for movements (e.g. a movement/ledger record) is ratified there.
Use cases will record step in/out and emit `wip.movement_recorded`;
`confirm_completion(order_id)` emits `wip.completion_confirmed` when the last
step balances.

## API contract

`/api/v1/wip/...` — read-only projection of balances by order and route step.
The exact read URL is pending Question **NSG-42**. Movements are recorded via the
operator UI or via PLC events.

## Events emitted

- `wip.movement_recorded`
- `wip.completion_confirmed`

## Events consumed

- `orders.released` — opens an initial `WipBalance` at zero for each route step.
  Whether the event payload carries the route steps is pending Question **NSG-43**.
- `plc.equipment.cycle_done` — auto-records step out.

## Golden principles relevant to `wip`

- **GP-005 does NOT apply to `wip`.** WIP is mutable stock; the immutable /
  append-only audit trail is `traceability`'s responsibility, not `wip`'s. Do
  **not** add append-only / audit-log behaviour here. (Confirmed by Epic NSG-32 —
  this corrects the earlier "append-only ledger" framing.)
- **GP-003.** Any `datetime` on future movements/balances must be
  timezone-aware UTC.
- **GP-010.** Any enumerated state must be `enum.StrEnum` /
  `models.TextChoices`, never string literals.

## Open questions

- TODO: regla de reconciliación cuando WIP físico no coincide con WIP de sistema
  (cierre de turno).
- Read URL for balances — tracked in Question **NSG-42**.
- Whether `orders.released` carries route steps — tracked in Question **NSG-43**.
