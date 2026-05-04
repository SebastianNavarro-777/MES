---
title: Bounded contexts
status: skeleton
last_updated: 2026-05-04
---

# Bounded contexts

A bounded context = one Django app under `apps/`. Cross-context imports are **rejected by the architecture linter**. Communication happens exclusively through the event bus.

## Catalog

| Context        | Phase | Owns                                          | Key events emitted                                    |
|----------------|:-----:|-----------------------------------------------|-------------------------------------------------------|
| `orders`       | 1     | Manufacturing orders, routing, state machine. | `orders.created`, `orders.released`, `orders.closed`  |
| `wip`          | 1     | Work-in-process positions and movements.      | `wip.movement_recorded`, `wip.completion_confirmed`   |
| `traceability` | 2     | Lot genealogy (forward and backward).         | `traceability.consumed`, `traceability.produced`      |
| `oee`          | 3     | OEE windows per equipment.                    | `oee.window_closed`                                   |
| `downtime`     | 3     | Downtime events with reason catalog.          | `downtime.event_recorded`                             |
| `quality`      | 4     | Inspection plans, measurements, NCRs, SPC.    | `quality.measurement_recorded`, `quality.ncr_*`       |
| `scheduling`   | 5     | Finite scheduling per equipment.              | `scheduling.published`                                |
| `maintenance`  | 5     | Preventive plans, work orders, MTTR/MTBF.     | `maintenance.work_order_*`                            |

## Naming conventions

- Stream name = `<context>.events`. Event type = `<context>.<verb>`.
- Schema versioning is mandatory: every event payload includes `schema_version: int`.
- Anti-corruption layers (ACLs) translate inbound external system events into our internal vocabulary in `infrastructure/`.

## Cross-context dependencies allowed

Only via:
1. **Domain events** (Redis Streams, async).
2. **Read-model projections** populated by event consumers (queryable via that context's interface layer).

## Open question template

When adding a new context, the Architect agent fills:

- Why is it not part of an existing context?
- What events does it need from existing contexts?
- What new events does it emit?
- Compliance implications?
