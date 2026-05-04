---
title: External references
description: Pointers to external standards, vendor docs, and libraries. Read only when implementing with a specific library/standard.
last_updated: 2026-05-04
---

# References

Library and standard references. **Do not read these unless your ticket touches the corresponding tech.** Use the `context7` MCP to fetch current docs at session time — pinning external docs in this repo causes drift.

## Standards

- **ISA-95 (ANSI/ISA-95, IEC 62264)** — *Enterprise-Control System Integration*. Foundational. See [domain/isa-95.md](../domain/isa-95.md).
- **21 CFR Part 11** — FDA regulation for electronic records and signatures. See [domain/compliance/21-cfr-part-11.md](../domain/compliance/21-cfr-part-11.md).
- **IATF 16949** — automotive quality management. See [domain/compliance/iatf-16949.md](../domain/compliance/iatf-16949.md).
- **ISO 9001** — generic quality management. See [domain/compliance/iso-9001.md](../domain/compliance/iso-9001.md).

## Industrial protocols

- **OPC-UA** — IEC 62541. Library: `asyncua` (Python).
- **MQTT** — OASIS standard. Library: `paho-mqtt` or `asyncio-mqtt`.
- **SAP integration** — IDoc, BAPI (via `pyrfc`), or OData / REST. Per-customer.

## Frameworks

For framework docs (Django, DRF, React, Vite, asyncua, Playwright, Celery, redis-py), **fetch via `context7` MCP at session time**. Do not hardcode versions or pin examples here.

## Books / talks

_(populated as the team reads)_
