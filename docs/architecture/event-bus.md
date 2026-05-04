---
title: Event bus
status: skeleton
last_updated: 2026-05-04
---

# Event bus

Implementation: **Redis Streams**, accessed only from `infrastructure/`.

## Wire format

```json
{
  "schema_version": 1,
  "occurred_at": "2026-05-04T12:00:00Z",
  "context": "orders",
  "type": "orders.created",
  "aggregate_id": "MO-123",
  "actor": "user:42",
  "payload": { ... }
}
```

- Timestamps are timezone-aware UTC ISO-8601 (per `golden-principles.md` GP-003).
- `schema_version` is mandatory; consumers MUST tolerate forward additions.

## Streams

One stream per context: `orders.events`, `traceability.events`, etc. Consumers use Redis consumer groups for at-least-once delivery.

## Idempotency

Consumers MUST be idempotent. Recommended pattern: dedupe on `(type, aggregate_id, occurred_at)` via a Redis set with TTL > stream retention.

## Schema evolution

- Adding fields: allowed without bumping `schema_version`. Consumers ignore unknown fields.
- Renaming or removing fields: REQUIRES bumping `schema_version` and a migration plan documented in `docs/exec-plans/active/`.
- Old versions remain consumable for one full release cycle after a bump.

## Observability

Each event emission and consumption is logged with `aggregate_id` so an operator can trace the full path from `orders.created` to `wip.completion_confirmed` for a given order.

## Open question

- TODO: ¿stream-per-aggregate (e.g., `orders.events.MO-123`) o stream-per-context? Trade-off entre fan-out y orden de eventos. Architect debe decidir antes de Fase 2.
