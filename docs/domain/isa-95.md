---
title: ISA-95 — niveles y dónde vive nuestro MES
description: Marco de referencia que define dónde encaja un MES en la arquitectura industrial.
audience: humanos + agentes (entender por qué hablamos con el PLC abajo y con el ERP arriba).
last_updated: 2026-05-04
---

# ISA-95 — niveles

ISA-95 (norma ANSI/ISA-95, equivalente a IEC 62264) divide la arquitectura industrial en **5 niveles** (0 a 4). Nuestro MES vive en **Nivel 3**.

```
┌────────────────────────────────────────────────────────┐
│  Nivel 4 — ERP / Business Planning                     │   horizonte: meses
│  SAP, Oracle, etc. Plan maestro, finanzas, compras.    │
├────────────────────────────────────────────────────────┤
│  Nivel 3 — MES (Manufacturing Operations Management)   │   horizonte: turnos a días
│  ← AQUÍ VIVE NUESTRO SISTEMA                           │
│  Órdenes, trazabilidad, OEE, calidad, scheduling.      │
├────────────────────────────────────────────────────────┤
│  Nivel 2 — SCADA / Supervisory Control                 │   horizonte: minutos
│  HMIs, paneles, lazos de control.                      │
├────────────────────────────────────────────────────────┤
│  Nivel 1 — Sensing & Manipulation                      │   horizonte: segundos
│  PLCs, drivers, lógica determinista.                   │
├────────────────────────────────────────────────────────┤
│  Nivel 0 — Production Process                          │   horizonte: real
│  Equipos físicos, sensores, actuadores.                │
└────────────────────────────────────────────────────────┘
```

## Qué hace cada nivel y por qué nos importa

### Nivel 0 — Proceso físico
Equipos, máquinas, sensores, actuadores. No hablamos directo con este nivel; lo vemos a través de Nivel 1.

### Nivel 1 — Sensado y manipulación
PLCs (Allen-Bradley, Siemens, etc.) y sus I/O. Nuestro punto de contacto **arriba** de este nivel: leemos variables vía OPC-UA. Ver [docs/architecture/integrations/plc-opcua.md](../architecture/integrations/plc-opcua.md).

### Nivel 2 — SCADA / control supervisorio
HMIs, paneles del operario. Algunos clientes tienen SCADA potente (Wonderware, Ignition); otros no. Cuando lo tienen, lo aprovechamos como fuente de eventos en lugar de ir directo al PLC.

### Nivel 3 — MES (nosotros)
**Operaciones de manufactura**: planeación de corto plazo (turnos, días), trazabilidad, calidad, OEE, programación finita, mantenimiento. Recibimos órdenes desde Nivel 4 (ERP) y datos crudos desde Niveles 1-2.

### Nivel 4 — ERP / planeación de negocio
SAP, Oracle. Plan maestro, contabilidad, MRP. **Hablamos con este nivel pero no somos este nivel** (ver [vision/non-goals.md](../vision/non-goals.md): "no somos un ERP").

## Implicaciones para nuestro diseño

1. **Latencia esperada por nivel:** lo que sube de Nivel 1 a Nivel 3 puede tener segundos de retardo; lo que baja a Nivel 4 puede tener minutos. Diseñar consumidores async.
2. **Criticidad:** un fallo en Nivel 3 (nosotros) **no debe** detener Niveles 1-2. Si caemos, los PLCs siguen produciendo; perdemos visibilidad pero no producción.
3. **Lenguaje:** los términos que usamos en código (`manufacturing_order`, `lot`, `equipment`) son los que ISA-95 propone. Ver [glossary.md](glossary.md).

## Referencia

ANSI/ISA-95 — *Enterprise-Control System Integration*. Lectura obligada para el Architect cuando proponga un nuevo bounded context.
