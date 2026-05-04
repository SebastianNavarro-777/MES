---
title: Architecture — index
description: Detailed architecture docs. The hard rules live in /ARCHITECTURE.md at the repo root.
last_updated: 2026-05-04
---

# Architecture — index

The non-negotiable rules live in [`/ARCHITECTURE.md`](../../ARCHITECTURE.md) at the repo root. This folder hosts the deeper documents that expand on those rules and document specific architectural concerns.

| Archivo | Propósito | Quién lo edita | Última actualización |
|---|---|---|---|
| [layers.md](layers.md) | Per-layer responsibilities and examples. | Architect agent | 2026-05-04 |
| [bounded-contexts.md](bounded-contexts.md) | Catalog of bounded contexts and their boundaries. | Architect agent | 2026-05-04 |
| [event-bus.md](event-bus.md) | Redis Streams contract: streams, partitions, schema versioning. | Architect agent | 2026-05-04 |
| [integrations/plc-opcua.md](integrations/plc-opcua.md) | OPC-UA client design. | Workers (per ticket) | 2026-05-04 |
| [integrations/erp-sap.md](integrations/erp-sap.md) | SAP integration (IDoc/REST). | Workers (per ticket) | 2026-05-04 |
| [integrations/scada.md](integrations/scada.md) | SCADA data ingestion. | Workers (per ticket) | 2026-05-04 |
| [integrations/iot-mqtt.md](integrations/iot-mqtt.md) | MQTT consumer for IoT sensors. | Workers (per ticket) | 2026-05-04 |
