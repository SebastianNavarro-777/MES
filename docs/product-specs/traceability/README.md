---
module: traceability
roadmap_phase: 2
status: skeleton
last_updated: 2026-05-04
---

# Traceability

## Overview

Genealogy of every lot produced. Forward (which finished goods came from a raw lot) and backward (what raw lots fed a given finished lot). Append-only event log; no hard deletes.

## Domain entities

- `Lot` — id, product, qty, parent_lot_ids, child_lot_ids, status.
- `GenealogyEvent` — `consumed | produced`, timestamp, equipment, order_id.

## Use cases

- `record_consumption(lot_id, qty, order_id, equipment_id)` — emits `traceability.consumed`.
- `record_production(lot_id, qty, parents, order_id, equipment_id)` — emits `traceability.produced`.
- `get_genealogy(lot_id, direction)` — read projection.

## API contract

`/api/v1/lots/` — list, retrieve, genealogy report.

## Events emitted

- `traceability.consumed`
- `traceability.produced`

## Events consumed

- `wip.movement_recorded` — auto-creates genealogy events when configured.

## Open questions

- TODO: tamaño de lote (un solo número, rangos, sub-lotes por turno).
- TODO: estrategia de identificación física de lotes (código de barras vs. RFID).
