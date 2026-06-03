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

> **Reconciliación de nombres (2026-06-03).** El Epic
> [NSG-32](https://linear.app/nsg-engineering/issue/NSG-32) y su primera Story
> [NSG-33](https://linear.app/nsg-engineering/issue/NSG-33) — la expresión más
> reciente y específica del Architect — modelan el WIP como un **balance mutable
> por paso de ruta** (`WipBalance`), no como un par `WipPosition` + ledger
> append-only `WipMovement`. El Epic confirma explícitamente que **GP-005
> (inmutabilidad / append-only) NO aplica a `wip`**: el balance es stock mutable;
> la inmutabilidad/append-only vive en `traceability`. Este README se reconcilia
> con esa decisión. La fuente de verdad del modelo de dominio es el Epic NSG-32.

- `WipBalance` — entidad identificada por su `RouteStepRef`; expone la cantidad
  actualmente en proceso en ese paso de la OF. Es **stock mutable** (se ajusta con
  las operaciones de entrada/salida/scrap), no un registro append-only.
- `RouteStepRef` — value object que referencia el paso de ruta de una OF por
  identificadores (`order_id` + identificador de paso). Inmutable, igualdad por
  valor, y **sin importar `apps/orders/`** (regla de no-imports cross-context,
  `ARCHITECTURE.md`).
- `Quantity` — value object de cantidad **no negativa**. Inmutable, igualdad por
  valor. Usa `decimal.Decimal` (nunca `float`) porque el WIP puede ser fraccionario
  (kg, m) o discreto (piezas) — precisión exacta, en el espíritu de GP-002.
- `WipDomainError` — excepción base del dominio `wip` (`apps/wip/domain/exceptions.py`);
  el dominio nunca lanza built-ins como `ValueError`/`RuntimeError` (GP-012).

Las **operaciones de movimiento de stock** (entrada/salida/scrap y la invariante
"balance nunca negativo") y su persistencia ORM se construyen en Stories
posteriores del Epic (NSG-34/NSG-35), no en el skeleton.

## Use cases

- `record_step_in(...)` / `record_step_out(...)` — ajustan el `WipBalance` del paso
  y emiten `wip.movement_recorded`. (El movimiento se captura como **evento
  emitido**, no como entidad de dominio append-only.)
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
