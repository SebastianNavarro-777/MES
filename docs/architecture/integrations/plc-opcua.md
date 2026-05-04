---
title: PLC integration via OPC-UA
status: skeleton
last_updated: 2026-05-04
---

# PLC integration — OPC-UA

Library: `asyncua` (async Python OPC-UA client). Lives in `packages/infrastructure/opcua/`. **All reads/writes are async** (per `golden-principles.md` GP-007).

## Topology

- One connection per PLC (or per group of PLCs).
- Subscriptions for variables of interest; periodic poll as fallback.
- Connection supervisor reconnects with exponential backoff on failure.

## Mapping

A configurable map from OPC-UA node ID → internal event type. Lives in BD (table `infra_opcua_mapping`) so non-developers can adjust it. Workers consult `docs/generated/db-schema.md` for the schema.

## Authentication

Username + password over secure channel (`Basic256Sha256`). Credentials stored encrypted (Django `Fernet` over `SECRET_KEY`).

## Reliability

- Buffer last N (configurable, default 10000) events on disk if Redis unreachable.
- Backpressure: if buffer fills, log + alert; do NOT silently drop.

## Open questions

- TODO: protocolo de heartbeat para detectar PLCs colgados.
- TODO: mapeo de tipos OPC-UA → tipos internos (especialmente strings vs. enumeraciones).

## References

- [asyncua](https://github.com/FreeOpcUa/opcua-asyncio) — fetch via `context7` MCP for current docs.
