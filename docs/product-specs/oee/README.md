---
module: oee
roadmap_phase: 3
status: skeleton
last_updated: 2026-05-04
---

# OEE (Overall Equipment Effectiveness)

## Overview

Computes Availability × Performance × Quality per equipment, per shift, per day. Always at the equipment level (per `golden-principles.md` GP-006); plant-level OEE is derived by aggregation in the read model.

## Domain entities

- `OeeWindow` — equipment_id, shift, period_start, period_end, A, P, Q, OEE.
- `LossBucket` — categorisation of OEE losses (planned downtime, unplanned, speed loss, scrap, rework).

## Use cases

- `compute_oee(equipment_id, period)` — pure function in `domain/`; pulls inputs via repository.
- `publish_window(window)` — emits `oee.window_closed` to the event bus.

## API contract

`/api/v1/oee/windows/?equipment_id=&from=&to=` — read-only.

## Events emitted

- `oee.window_closed`

## Events consumed

- `downtime.event_recorded` — feeds Availability.
- `wip.movement_recorded` — feeds Performance and Quality.

## Open questions

- TODO: definición de "planned production time" por planta (turnos, almuerzos, mantenimiento programado).
