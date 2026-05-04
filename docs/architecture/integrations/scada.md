---
title: SCADA integration
status: skeleton
last_updated: 2026-05-04
---

# SCADA integration

Most SCADA systems already expose OPC-UA, in which case we reuse [plc-opcua.md](plc-opcua.md). This document covers the cases that don't.

## Channels

| SCADA brand           | Native protocol | Our adapter                              |
|-----------------------|-----------------|------------------------------------------|
| Wonderware / AVEVA    | MQTT or REST    | `infrastructure/scada/wonderware.py`     |
| Ignition              | OPC-UA / REST   | reuse `opcua/`                           |
| Siemens WinCC         | OPC-UA          | reuse `opcua/`                           |

## Data we consume

- Equipment status (`running`, `idle`, `fault`).
- Production counters.
- Process variables (temperature, pressure, etc.) — when relevant for SPC.

## Data we publish

Generally none (SCADA is read-mostly). Exceptions documented per project.

## Open questions

- TODO: política de muestreo (todo evento, downsampled, on-change?).
