---
module: maintenance
roadmap_phase: 5
status: skeleton
last_updated: 2026-05-04
---

# Maintenance

## Overview

Preventive maintenance plans (per hours of operation, per cycles, per calendar), work orders, MTTR/MTBF metrics, and scheduling integration so preventive windows show up in the equipment calendar.

## Domain entities

- `MaintenancePlan` — equipment, trigger (`hours | cycles | calendar`), interval, tasks.
- `WorkOrder` — plan, status, assigned_to, opened_at, closed_at.
- `MaintenanceMetric` — equipment, MTTR, MTBF, period.

## Use cases

- `evaluate_triggers()` — periodic; opens work orders when thresholds reached.
- `complete_work_order(...)` — emits `maintenance.work_order_closed`; updates MTTR/MTBF.

## API contract

`/api/v1/maintenance/plans/` (CRUD).
`/api/v1/maintenance/work-orders/` (CRUD with state guard).
`/api/v1/maintenance/metrics/?equipment_id=` (read).

## Events emitted

- `maintenance.work_order_opened`
- `maintenance.work_order_closed`

## Events consumed

- `oee.window_closed` — equipment hours of operation feed into hour-based triggers.
- `downtime.event_recorded` — categorised as planned vs. unplanned for MTTR/MTBF.

## Open questions

- TODO: separar mantenimiento correctivo (reactivo) en su propio sub-módulo o vivir aquí también.
