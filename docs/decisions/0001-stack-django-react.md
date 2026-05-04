---
adr: 0001
title: Stack — Django + DRF + React + Vite
status: Accepted
date: 2026-05-04
deciders: Sebas (NSG founder)
tags: [stack, foundational]
---

# 0001 — Stack: Django + DRF + React + Vite

## Status

Accepted — 2026-05-04.

## Context and problem statement

Building a Manufacturing Execution System (MES) from scratch with two simultaneous goals:

1. Ship a usable v1 to a first paying customer in ~6 months.
2. Operate sustainably for years (compliance, integrations, multi-customer maintenance).

The system is a long-lived data-heavy backend (orders, traceability, OEE, quality, scheduling) coupled to a real-time-ish frontend (Gantt, andon, dashboards) and to industrial protocols (OPC-UA, MQTT, SAP). The team is small; we cannot afford bespoke infrastructure or exotic stacks.

We need a stack that maximises:
- Boring, well-documented frameworks (so agents have abundant training data and Context7 has current docs).
- Tooling maturity (migrations, admin, ORM, async support).
- Operational simplicity (one deployment per customer; no multi-tenant complexity in v1).
- Pluggability for industrial protocols.

## Decision drivers

- **Time to first customer.** Greenfield architectures with bleeding-edge stacks lose 3-6 months on yak-shaving.
- **Compliance fit.** Audit logs, soft delete, signed records — all easier when the stack has mature ORM and admin idioms.
- **Agent compatibility.** Models with abundant training corpus get cleaner code from LLM agents than niche frameworks.
- **Async industrial protocols.** OPC-UA via `asyncua` requires a runtime that interleaves sync (HTTP) and async (PLC) gracefully.
- **Frontend developer experience.** Real-time Gantt and andon dashboards need a modern reactive UI with hot reload.

## Considered options

### A) Django 5 + DRF + React 18 + Vite + TypeScript ← **chosen**

Pros:
- Massive Python and TypeScript training corpus.
- Django's ORM, migrations, admin, and signals match MES needs (audit log, soft delete, etc.) idiomatically.
- DRF gives REST + browsable API for free.
- React + Vite has the fastest HMR and best ecosystem for charts (Recharts, ECharts) and Gantt (e.g., DHTMLX).
- `asyncua` runs cleanly outside the Django request loop in a Celery worker.

Cons:
- Two languages (Python + TS).
- Async story in Django 5 is improving but still requires care across sync/async boundaries.

### B) FastAPI + React

Pros:
- Native async throughout.
- Lighter weight.

Cons:
- No equivalent to Django admin or migrations out of the box; we'd build them.
- Less idiomatic ORM + audit log patterns (would have to choose SQLAlchemy/Alembic stack).
- Smaller training corpus for some MES patterns we'll need.

### C) Rails + Hotwire (single-language)

Pros:
- Single language; very productive.
- Rails idioms map well to MES backend.

Cons:
- Industrial protocol libraries (OPC-UA, MQTT) are weaker in Ruby than Python.
- Hotwire-based frontend is constraining for a Gantt + real-time dashboard.

### D) Spring Boot + React

Pros:
- Strong type system, mature.

Cons:
- Heavier; longer iteration cycle.
- Smaller MES-specific corpus for agents.

## Decision outcome

**Option A.** Django 5 + DRF + React 18 + Vite + TypeScript. Plus PostgreSQL 16, Redis 7, Celery, `asyncua`, Playwright, `uv`, `pnpm`, `ruff`, `mypy strict`.

### Positive consequences

- Time to first feature is short; Django scaffolding handles auth, admin, migrations, ORM idioms.
- LLM agents produce idiomatic code with abundant Context7 references.
- Industrial protocol libraries (`asyncua`, `paho-mqtt`, `pyrfc` for SAP) are first-class in Python.
- Frontend can ship a Gantt and dashboards quickly with Vite's HMR and React's ecosystem.

### Negative consequences

- Two languages to maintain.
- Async/sync boundary in Django 5 requires team discipline (mitigated by `golden-principles.md` GP-007).
- React ecosystem churn risk (mitigated by sticking to mainstream libraries and pinning versions).

## Pros and cons summary

Option A wins on time-to-market and agent compatibility, both of which dominate everything else for a 6-month-to-customer timeline. The async caveat is real but manageable with `asyncua` running in Celery, not in the Django request thread.

## Links

- Stack table in [README.md](../../README.md) and [SETUP_FOR_SEBAS.md](../../SETUP_FOR_SEBAS.md).
- Layer rules: [/ARCHITECTURE.md](../../ARCHITECTURE.md).
- Async PLC discipline: [golden-principles.md](../golden-principles.md) GP-007.
