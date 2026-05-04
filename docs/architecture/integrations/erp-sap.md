---
title: ERP integration — SAP
status: skeleton
last_updated: 2026-05-04
---

# ERP integration — SAP

Bidirectional. **Idempotency keys on every endpoint** (per `golden-principles.md` GP-008).

## Inbound (SAP → MES)

- Production orders.
- Master data (products, BOMs, routings, work centers).

Channel options (Architect chooses per customer):
1. **IDoc** over SAP PI/PO landing in our SFTP, parsed by a Celery worker.
2. **OData / REST** when SAP exposes a service we can consume directly.

## Outbound (MES → SAP)

- Material consumption per work order.
- Production confirmations (yields, scrap).
- Downtime / quality summaries (configurable cadence).

Channel: BAPI calls (via PyRFC) or REST inbound on SAP side, depending on customer.

## Anti-corruption layer

Translation lives in `apps/orders/infrastructure/sap/` (orders-context view) and `packages/infrastructure/sap/` (shared primitives). Internal code never sees raw SAP types.

## Open questions

- TODO: estrategia de retry y dead-letter cuando SAP rechaza una confirmación.
- TODO: ¿qué pasa si el ERP devuelve un material code que no está en master data del MES?
