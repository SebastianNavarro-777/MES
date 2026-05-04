---
title: Design — system-wide design principles
status: skeleton
last_updated: 2026-05-04
---

# DESIGN

System-level design principles that span layers and contexts. Refines and complements [/ARCHITECTURE.md](../ARCHITECTURE.md) and [golden-principles.md](golden-principles.md). Skeleton — populated by Architect agent as patterns crystallise.

## Read models vs. write models

_(CQRS-lite: write through bounded context use cases; read through projections fed by events. Pattern documented when first projection lands.)_

## Soft delete strategy

_(Compliance entities: never hard delete. Non-compliance: hard delete allowed. Mixin to be implemented in `packages/infrastructure/`.)_

## Pagination contract

_(Default: cursor-based on ordered timestamp. Page size 50; max 200. To be enforced via DRF mixin.)_

## Error responses

_(`application/problem+json` (RFC 7807) on every 4xx/5xx. Mapping table from domain exceptions to problem types lives in each context's `interface/`.)_

## Concurrency

_(Optimistic locking on writes that race: `version` column + `If-Match` header on PUT/PATCH.)_

## Feature flags

_(Not in v1. Configurable behaviour goes through Django settings or per-tenant configuration tables.)_
