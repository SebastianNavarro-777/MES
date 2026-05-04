# ARCHITECTURE.md

Hard rules. Non-negotiable. Enforced by `tools/linters/architecture.py` (CI-blocking).

## Layers

The codebase has four layers. A layer can only import from layers **at the same level or deeper** (deeper = closer to `domain`).

```
┌──────────────────────────────────────────────────┐
│ interface  (HTTP views, CLI, Celery tasks)       │  L3
├──────────────────────────────────────────────────┤
│ infrastructure  (DB, HTTP clients, message bus)  │  L2
├──────────────────────────────────────────────────┤
│ application  (use cases, orchestration)          │  L1
├──────────────────────────────────────────────────┤
│ domain  (entities, value objects, invariants)    │  L0  ← deepest
└──────────────────────────────────────────────────┘
```

## Dependency rules

| From \ To       | domain | application | infrastructure | interface |
|-----------------|:------:|:-----------:|:--------------:|:---------:|
| domain          |   ✓    |     ✗       |       ✗        |     ✗     |
| application     |   ✓    |     ✓       |       ✗        |     ✗     |
| infrastructure  |   ✓    |     ✓       |       ✓        |     ✗     |
| interface       |   ✓    |     ✓       |       ✓        |     ✓     |

A `✓` means "may import"; `✗` means "linter rejects".

## Per-layer rules

### `domain/` (L0)

- Pure Python + stdlib only.
- **MUST NOT** import Django, DRF, httpx, asyncua, Celery, Redis, SQLAlchemy, Pydantic, or any third-party package.
- Lives in `packages/domain/` (cross-context primitives) and `apps/{context}/domain/` (per-context).
- Defines entities, value objects, domain events, exceptions, invariants. No I/O.

### `application/` (L1)

- May import `domain`. May not import `infrastructure` or `interface`.
- Defines use cases as plain functions or callable classes. Receives infrastructure as injected dependencies (typed Protocols defined here, implementations in L2).
- Lives in `apps/{context}/application/`.

### `infrastructure/` (L2)

- May import `domain` and `application`. May not import `interface`.
- Concrete implementations: Django ORM repositories, OPC-UA clients, HTTP clients, Redis publishers, Celery tasks, MQTT consumers.
- Lives in `packages/infrastructure/` (shared) and `apps/{context}/infrastructure/`.

### `interface/` (L3)

- May import all lower layers.
- Django views (DRF), URL routers, CLI entry points, Django admin, management commands.
- Lives in `apps/{context}/interface/` and includes top-level `apps/{context}/views.py`, `apps/{context}/admin.py`, `apps/{context}/urls.py` for Django convention compatibility.

## Bounded contexts

Each Django app under `apps/` is one bounded context (e.g., `orders`, `traceability`, `oee`).

- **`apps/X/` MUST NOT import from `apps/Y/`** — the architecture linter rejects it. Cross-context communication goes through the event bus.
- Shared primitives (e.g., `Money`, `EquipmentId`, `LotNumber`) live in `packages/shared/` (L0, importable by anyone).
- Cross-cutting infrastructure (event bus, audit log, auth) lives in `packages/infrastructure/` (L2).

## Event bus

- Implementation: Redis Streams, accessed only from `infrastructure/`.
- A bounded context **publishes** domain events to its own stream (e.g., `orders.events`) and **subscribes** to other contexts' streams via Celery consumers.
- Events are immutable, versioned (`schema_version` field), and append-only.
- No cross-context synchronous calls. If you need a synchronous read of another context's data, that context must expose it via its `interface/` (HTTP) or via a read-model projection populated from events.

## Path-to-layer resolution (used by the linter)

| Path glob                                      | Layer |
|------------------------------------------------|-------|
| `packages/domain/**`                           | L0    |
| `packages/shared/**`                           | L0    |
| `apps/*/domain/**`                             | L0    |
| `apps/*/application/**`                        | L1    |
| `packages/infrastructure/**`                   | L2    |
| `apps/*/infrastructure/**`                     | L2    |
| `apps/*/interface/**`                          | L3    |
| `apps/*/views.py`, `apps/*/admin.py`, `apps/*/urls.py` | L3 |

Anything under `tools/` is exempt from layer rules but still subject to the cross-context import ban.

## Deviations

If you believe these rules are wrong for a real case, open a `Harness-Fix` ticket. Do **not** add `# noqa`, hide an import inside a function, or use `importlib` to bypass the linter.
