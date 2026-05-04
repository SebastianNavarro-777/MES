---
module: scheduling
roadmap_phase: 5
status: skeleton
last_updated: 2026-05-04
---

# Scheduling

## Overview

Finite scheduling per equipment. Receives orders from `orders` (and ultimately from ERP via integration), sequences them against equipment calendar and capacity, exposes a Gantt to the supervisor, and emits dispatch events to the floor.

## Domain entities

- `EquipmentCalendar` — shifts, breaks, planned downtime windows.
- `ScheduleEntry` — order_id, route_step, equipment_id, planned_start, planned_end, sequence_index.
- `Schedule` — set of entries belonging to a planning horizon.

## Use cases

- `auto_schedule(horizon)` — first-fit / forward-loading; deterministic; no genetic optimisation in v1 (per `vision/non-goals.md`).
- `manual_reorder(entry_id, new_position)` — supervisor drags entries in the Gantt.
- `lock_schedule(horizon)` — freezes; emits `scheduling.published`.

## API contract

`/api/v1/scheduling/entries/` (list, update sequence).
`/api/v1/scheduling/calendar/` (CRUD calendars).
`/api/v1/scheduling/publish/` (POST → lock).

## Events emitted

- `scheduling.published`
- `scheduling.entry_started`

## Events consumed

- `orders.released` — adds entries.
- `oee.window_closed` — feedback loop on equipment performance for next horizon.

## Open questions

- TODO: política cuando una orden no cabe en el horizonte (push, alert, escalate).
