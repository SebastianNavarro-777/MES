---
title: Layers (deep dive)
status: skeleton
last_updated: 2026-05-04
---

# Layers — deep dive

The hard rules are in [/ARCHITECTURE.md](../../ARCHITECTURE.md). This document expands them with worked examples and anti-patterns. The Architect agent grows this file as new patterns emerge.

## Domain (L0)

### Allowed
- Pure Python, stdlib (`dataclasses`, `enum`, `typing`, `decimal`, `datetime`).
- Hand-written value objects and entities.

### Forbidden
- Any framework import.
- I/O of any kind (no DB calls, no HTTP, no file system).

### Worked example
_(Architect/Worker fills with a concrete example once the first domain entity is implemented.)_

## Application (L1)

### Allowed
- Import `domain`. Define use cases as plain functions taking dependencies as parameters.
- Define `Protocol` types for repositories and external services; concrete classes live in L2.

### Forbidden
- Direct DB or HTTP calls.

## Infrastructure (L2)

### Allowed
- Implement L1 Protocols using Django ORM, httpx, asyncua, redis-py, etc.

### Forbidden
- Domain logic. If a piece of business rule appears here, it belongs in L0/L1.

## Interface (L3)

### Allowed
- DRF views, serializers, URL routing, Django admin, CLI commands.

### Forbidden
- Business rules. The view is glue between HTTP and the application layer.

## Anti-patterns to reject in code review

_(populated by Reviewer agent as it learns)_
