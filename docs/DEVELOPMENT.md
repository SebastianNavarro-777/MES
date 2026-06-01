---
title: Development — engineering handbook
status: living
audience: every agent that writes code (Worker primarily; Spec Writer when writing notas técnicas).
last_updated: 2026-06-01
---

# Development handbook

This is the **bridge between mechanical rules and product philosophy**. It says how to write code in this repo — naming, layer patterns, error handling, testing, logging, migrations, common gotchas.

| Doc | Sits at | When you read it |
|---|---|---|
| [vision/core-beliefs.md](vision/core-beliefs.md) | Product philosophy | When two valid options compete on values, not on tech. |
| [DEVELOPMENT.md](DEVELOPMENT.md) (this file) | Engineering philosophy + patterns | Every coding session. |
| [golden-principles.md](golden-principles.md) | Mechanical rules | Reference; Reviewer enforces. |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Layer boundaries | Reference; arch linter enforces. |
| [QUALITY.md](QUALITY.md) | Lint/test/coverage thresholds | Reference; verifier enforces. |

If this file contradicts `golden-principles.md` or `ARCHITECTURE.md`, **those win** — they're machine-enforced. Open a Harness-Fix ticket so this file gets corrected.

---

## Philosophy in one paragraph

We're building a long-lived, compliance-sensitive system that will be edited by agents and humans interchangeably for years. **Code is read 10× more than written**, so optimise for the next person staring at the diff at 2 AM trying to figure out what broke. Boring code, explicit names, narrow boundaries, exhaustive tests for the parts that matter. Cleverness goes in the commit message, not in the implementation.

When in doubt: copy the existing pattern in the same module, then question it in the PR description if you think it's wrong.

---

## Naming conventions

### Files

- `snake_case.py` always — no exceptions.
- Domain entity file: `<entity>.py` (singular: `manufacturing_order.py`, not `orders.py`).
- Use case file: `<verb>_<entity>.py` (`create_order.py`, `release_order.py`).
- Repository interface file: `<entity>_repository.py` inside `application/`. Implementation inside `infrastructure/`.
- Test file: mirror the source path, prefix `test_` (`tests/domain/test_manufacturing_order.py`).

### Classes

- `PascalCase`.
- Domain entities: noun, singular (`ManufacturingOrder`, not `MOrder` and not `ManufacturingOrders`).
- Value objects: noun, often with a unit suffix (`MoneyCents`, `PercentBasisPoints`).
- Exceptions: `<Context><Verb>Error` (`OrderTransitionError`, not `BadStateException`).
- Protocols (Python `typing.Protocol`): suffix `Repository`, `Publisher`, `Reader`, `Writer` — never the bare `IFoo` Java idiom.

### Functions

- `snake_case`, verb first (`create_order`, `release_order`, `compute_oee_for_shift`).
- Async: same name; the `async`/`await` keywords carry the intent. No `_async` suffix.
- Test functions: `test_<unit>_<scenario>_<expected>` — e.g., `test_release_order_in_draft_state_raises`. Long is fine; the test name is the spec.

### Variables

- `snake_case`.
- Booleans: predicates (`is_released`, `has_open_ncr`), never `released_flag`.
- Counts: plural noun (`open_orders` not `order_count`).
- Datetimes: suffix `_at` for events (`released_at`), `_on` for dates without time.

---

## Layer-by-layer patterns

`ARCHITECTURE.md` defines the rules; this section shows them in working code shapes. Each example is the **minimum** you write for a feature touching the layer.

### Domain — pure Python, no framework

```python
# apps/orders/domain/manufacturing_order.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime
from .exceptions import OrderTransitionError
from .order_status import OrderStatus

@dataclass(frozen=True)
class ManufacturingOrder:
    id: str
    product_id: str
    qty: int
    status: OrderStatus
    created_at: datetime

    def release(self) -> "ManufacturingOrder":
        if self.status is not OrderStatus.DRAFT:
            raise OrderTransitionError(
                f"can only release from draft; current state is {self.status.value}"
            )
        return ManufacturingOrder(
            id=self.id,
            product_id=self.product_id,
            qty=self.qty,
            status=OrderStatus.RELEASED,
            created_at=self.created_at,
        )
```

Rules:
- Frozen dataclass for entities — state transitions return a **new instance** (immutability surfaces bugs).
- Invariants enforced in the method that performs the transition; never spread across getters.
- No Django, no DRF, no ORM. Stdlib + the bounded context's own modules only.
- Raise context-specific exceptions (GP-012). Never `ValueError`.

### Application — use cases as functions over Protocol-typed dependencies

```python
# apps/orders/application/release_order.py
from __future__ import annotations
from typing import Protocol
from apps.orders.domain.manufacturing_order import ManufacturingOrder

class OrderRepository(Protocol):
    def get(self, order_id: str) -> ManufacturingOrder | None: ...
    def save(self, order: ManufacturingOrder) -> None: ...

class EventPublisher(Protocol):
    def publish(self, event_name: str, payload: dict[str, object]) -> None: ...

def release_order(
    order_id: str,
    *,
    repo: OrderRepository,
    publisher: EventPublisher,
) -> ManufacturingOrder:
    order = repo.get(order_id)
    if order is None:
        raise OrderNotFoundError(order_id)
    released = order.release()  # domain enforces invariants
    repo.save(released)
    publisher.publish(
        "orders.released",
        {"order_id": released.id, "schema_version": 1},
    )
    return released
```

Rules:
- Use cases are **functions**, not classes (no `OrderService` god-objects).
- Dependencies arrive as Protocol-typed keyword args — testable without Django.
- Use case orchestrates: load → call domain → save → publish. **Domain logic does not live here.**
- Publishing happens **after** the save succeeds. If the save raises, no event escapes.
- Return the new entity so the interface layer can serialise it.

### Infrastructure — Django glue

```python
# apps/orders/infrastructure/order_repository.py
from apps.orders.domain.manufacturing_order import ManufacturingOrder
from .models import OrderModel

class DjangoOrderRepository:
    def get(self, order_id: str) -> ManufacturingOrder | None:
        row = OrderModel.objects.filter(pk=order_id).first()
        return _to_domain(row) if row else None

    def save(self, order: ManufacturingOrder) -> None:
        OrderModel.objects.update_or_create(
            pk=order.id,
            defaults={
                "product_id": order.product_id,
                "qty": order.qty,
                "status": order.status.value,
                "created_at": order.created_at,
            },
        )

def _to_domain(row: OrderModel) -> ManufacturingOrder:
    return ManufacturingOrder(
        id=row.pk,
        product_id=row.product_id,
        qty=row.qty,
        status=OrderStatus(row.status),
        created_at=row.created_at,
    )
```

Rules:
- Repository is a thin adapter — **no business logic here**.
- Mapping `ORM row ↔ domain entity` lives in private helpers (`_to_domain`).
- Repository never returns ORM model instances to the application layer. The Protocol promises a domain entity.

### Interface — DRF view + serializer

```python
# apps/orders/interface/views.py
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.orders.application.release_order import release_order
from apps.orders.domain.exceptions import OrderNotFoundError, OrderTransitionError
from apps.orders.infrastructure.order_repository import DjangoOrderRepository
from apps.orders.infrastructure.event_publisher import RedisEventPublisher
from .serializers import OrderSerializer

class ReleaseOrderView(APIView):
    def post(self, request: Request, order_id: str) -> Response:
        try:
            order = release_order(
                order_id,
                repo=DjangoOrderRepository(),
                publisher=RedisEventPublisher(),
            )
        except OrderNotFoundError:
            return _problem(404, "order-not-found", "Order does not exist.")
        except OrderTransitionError as exc:
            return _problem(409, "invalid-transition", str(exc))
        return Response(OrderSerializer(order).data, status=200)
```

Rules:
- View is wiring: parse request → call use case → serialise response.
- Each domain exception maps to a specific HTTP status + a `problem+json` document (see Error handling below).
- Dependency wiring (`DjangoOrderRepository()`, `RedisEventPublisher()`) happens **here**, not deeper. Future: move to a DI container if the duplication grows.

---

## Error handling

### The contract

Each layer has its own kind of error:

| Layer | Raises | Why |
|---|---|---|
| Domain | `<Context><Verb>Error` (per GP-012) | Invariant violation. |
| Application | Re-raises domain errors; raises `<Context>NotFoundError`. | Use-case-level errors. |
| Infrastructure | Lets DB/network errors surface; wraps unknown errors in `<Context>InfrastructureError`. | Boundary failures. |
| Interface | Catches everything above; emits `problem+json`. | Translation to HTTP. |

### Domain exceptions

```python
# apps/orders/domain/exceptions.py
class OrdersDomainError(Exception):
    """Base for everything raised inside the orders bounded context."""

class OrderNotFoundError(OrdersDomainError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"order {order_id!r} does not exist")
        self.order_id = order_id

class OrderTransitionError(OrdersDomainError):
    """Raised when a state transition is rejected by the state machine."""
```

Subclass the context's base so a catch-all `except OrdersDomainError` exists for tests and middleware.

### `problem+json` mapping (RFC 7807)

The interface layer translates exceptions into a stable URI-keyed format:

```json
{
  "type": "https://nsg.mx/problems/orders/invalid-transition",
  "title": "Invalid order transition",
  "status": 409,
  "detail": "can only release from draft; current state is closed",
  "instance": "/api/v1/orders/abc-123"
}
```

Keep the mapping table in each context's `interface/problems.py`. **Never** return bare `{"error": "..."}` — agents and frontend clients depend on the stable `type` URI.

### What NOT to do

- **No bare `except:` or `except Exception:`.** If you genuinely need to swallow, catch a specific exception and log it.
- **No re-raise without context.** If you wrap an exception, attach `from exc` so the chain survives.
- **No `print()` for errors.** Use the logger (see below).

---

## Testing patterns

### Test pyramid

| Layer | Tool | Coverage target | Style |
|---|---|---|---|
| Domain | `pytest` + dataclass equality | 80% | Pure Python; no fixtures beyond entities. |
| Application | `pytest` + `pytest-asyncio` for async | 60% | **Fake repository/publisher** (in-memory classes implementing the Protocol). Mocks are a last resort. |
| Infrastructure | `pytest` + Django test DB | 40% | Real DB transactions; one test per query shape. |
| Interface | `pytest` + DRF `APIClient` | 40% | One test per AC. |
| E2E | Playwright | (QA Smoke gate) | Happy path only. |

### One test per AC

The Worker prompt requires every AC to be covered by a test annotated `# AC-N: <copy of AC text>`. Example:

```python
def test_release_order_in_draft_state_moves_to_released():
    # AC-1: A draft order can be released by a supervisor and emits orders.released.
    repo = FakeOrderRepository(...)
    publisher = FakeEventPublisher()
    result = release_order("abc-123", repo=repo, publisher=publisher)
    assert result.status is OrderStatus.RELEASED
    assert publisher.published == [("orders.released", {"order_id": "abc-123", "schema_version": 1})]
```

The annotation lets the Reviewer (and future grep) verify AC↔test coverage cheaply.

### Fakes over mocks

```python
# tests/application/_fakes.py
class FakeOrderRepository:
    def __init__(self) -> None:
        self._store: dict[str, ManufacturingOrder] = {}

    def get(self, order_id: str) -> ManufacturingOrder | None:
        return self._store.get(order_id)

    def save(self, order: ManufacturingOrder) -> None:
        self._store[order.id] = order

    # Helpers for assertions
    def seed(self, order: ManufacturingOrder) -> None:
        self._store[order.id] = order
```

Fakes are real objects that satisfy the Protocol. They're more honest than mocks (you'd notice if you forgot to implement `save`) and they're reusable across the suite.

### Fixtures

- Pytest fixtures for **shared seed data** (`@pytest.fixture def draft_order()`).
- Plain helper functions for **one-off builders** with overrideable defaults.
- **No factory libraries** (factory-boy, model-bakery) until the duplication actually justifies the dependency.

### Property-based tests

Use Hypothesis for value objects with arithmetic or invariants (GP-002 monetary computations, GP-006 OEE aggregations). One Hypothesis test per invariant is worth ten example-based tests.

---

## Logging discipline

```python
import logging
log = logging.getLogger(__name__)

# YES
log.info("released order", extra={"order_id": order.id, "user_id": user.id})

# NO — f-string formats even when log level filters this out
log.info(f"released order {order.id}")
```

Rules:
- One `log = logging.getLogger(__name__)` at module top. Never `logging.info(...)` directly.
- Structured fields go in `extra=`. **Never** f-string in `log.X` calls — Python's logger lazy-formats, and f-strings waste CPU when the level is filtered.
- Level discipline:
  - `debug`: developer-only, off in prod.
  - `info`: business event (order released, ticket transitioned).
  - `warning`: degraded but recoverable (retry succeeded, fallback applied).
  - `error`: unrecoverable in this context, but the system continues.
  - `critical`: paging-worthy.
- Never log secrets, tokens, PII, or full request bodies.

---

## Migrations

- One migration per logical change. **Never edit a migration after it's been deployed** — write a new one.
- Generate with `python manage.py makemigrations <app>` immediately after touching models. Commit the migration in the same PR.
- Name migrations descriptively if the auto-name is opaque: `python manage.py makemigrations --name add_idempotency_key_to_orders`.
- Forward-only in `main`. Reverse migrations exist for local dev but the production path is always forward.
- Schema-affecting migrations on tables with > 100k rows need a Question — locks during ALTER are not free.

---

## Common gotchas (the "don't do this" list)

The Reviewer agent rejects PRs that include any of these. Most have a corresponding GP rule already.

1. **`Model.objects.save()` from a use case.** Use cases must depend on a repository Protocol, not on Django ORM directly.
2. **String literals for enum states.** Use `OrderStatus.RELEASED`, never `"released"` (GP-010).
3. **Bare `ValueError` or `RuntimeError` from `domain/` or `application/`.** Subclass the context's base exception (GP-012).
4. **`from apps.X.infrastructure import *` inside `apps.X.domain/`.** Domain imports stdlib only (GP-001, arch linter).
5. **`# noqa`, `# type: ignore`, `importlib.import_module()` as a layer-bypass.** Fix the underlying issue (`CLAUDE.md` hard rule).
6. **`datetime.now()` without `tz=UTC`.** Use `datetime.now(UTC)` (GP-003).
7. **`float` for money.** Use `int` cents or `Decimal` (GP-002).
8. **Skipping the test for a new domain entity.** Every new domain class needs a test file (GP-011).
9. **Migrations missing from the PR.** Models without migrations break CI.
10. **TODO without a ticket link.** `# TODO: NSG-XXX — <what>` or nothing.
11. **`print()` left behind.** It's not even a warning; it's a Reviewer reject.
12. **Catching and silently ignoring.** `except SomeError: pass` is a Reviewer reject. Log + comment WHY, or don't catch.
13. **Tests that touch the network.** Use respx (HTTP) or in-process fakes. Tests must be runnable offline.
14. **Wide diffs.** If your PR touches 4 unrelated files, it's actually 4 tickets. Split.

---

## When you don't know

In order of preference:

1. **Read existing code** in the same bounded context. Patterns are local — `apps/orders/` may differ from `apps/quality/` because their domains differ.
2. **Read `golden-principles.md` + this file.** Most ambiguity is already addressed.
3. **Read the relevant `docs/product-specs/{module}/README.md`** and any ADR < 90 days old that touches the area.
4. **Query `context7` MCP** for current library docs — even libraries you "know" (Django changes, DRF changes, asyncua changes).
5. **Invoke Consultant** (escalation flow). Real strategic ambiguity gets a Question; small details don't.

The order matters: jumping straight to Consultant for a question already answered in `golden-principles.md` is a learning event for the Gardener — and an apology PR for you next cycle.
