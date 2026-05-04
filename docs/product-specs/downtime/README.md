---
module: downtime
roadmap_phase: 3
status: skeleton
last_updated: 2026-05-04
---

# Downtime

## Overview

Records planned and unplanned downtimes per equipment, with a configurable reason catalog (per planta). Source can be manual (operator press andon button) or automatic (PLC-driven via OPC-UA).

## Domain entities

- `DowntimeEvent` — equipment_id, started_at, ended_at, reason_code, source (`manual | plc`), notes.
- `ReasonCatalog` — tree of categories → causes → root causes.

## Use cases

- `start_event(equipment_id, reason_code, source)` — emits `downtime.started`.
- `close_event(event_id, ended_at)` — emits `downtime.event_recorded`.
- `auto_attribute_from_plc(plc_signal)` — opens/closes events based on equipment status signals.

## API contract

`/api/v1/downtime/events/` — list, create, close.
`/api/v1/downtime/reasons/` — read catalog.

## Events emitted

- `downtime.started`
- `downtime.event_recorded`

## Events consumed

- `plc.equipment.status_changed` — drives auto attribution.

## Open questions

- TODO: jerarquía del catálogo de razones — global vs. por planta vs. por equipo.
