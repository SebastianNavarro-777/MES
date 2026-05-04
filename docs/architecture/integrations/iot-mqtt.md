---
title: IoT integration via MQTT
status: skeleton
last_updated: 2026-05-04
---

# IoT integration — MQTT

For sensors and devices that don't speak OPC-UA. Library: `paho-mqtt` (chosen by Architect when the first IoT ticket arrives) or `asyncio-mqtt`.

## Topology

- One MQTT broker on customer site (Mosquitto or HiveMQ).
- MES connects as subscriber. Topics namespaced per planta.

## Topic conventions

```
<plant>/<line>/<equipment>/<metric>
```

Example: `mtycito/line-1/EQ-23/temperature`.

## QoS and reliability

- Default QoS 1 for measurements.
- Persistent session so we don't lose messages during reconnect.
- TLS mandatory in production.

## Message format

JSON with `timestamp`, `value`, `unit`, `device_id`. Adapter translates to internal events in `infrastructure/`.

## Open questions

- TODO: estrategia para devices que pierden hora (NTP no disponible).
- TODO: límite de retención del broker vs. nuestra capacidad de consumo.
