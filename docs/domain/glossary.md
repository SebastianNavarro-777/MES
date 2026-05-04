---
title: Glosario MES
description: Términos del dominio en español, con equivalente en inglés (que es el que se usa en código).
audience: humanos + agentes (verifican que el código respeta el lenguaje ubicuo).
last_updated: 2026-05-04
---

# Glosario MES

Lenguaje ubicuo del proyecto. **El código usa los términos en inglés**; este archivo existe para que los humanos NSG y los agentes mapeen la conversación con el cliente al modelo del software. Si un Worker o Spec Writer detecta un término del cliente que no está aquí, debe agregarlo en su PR.

| Término (es) | Término (en) | Definición |
|---|---|---|
| **Orden de fabricación (OF)** | Manufacturing Order (MO) | Documento que autoriza producir una cantidad específica de un producto siguiendo una ruta. Tiene estados (`draft → released → in_progress → completed → closed`). |
| **Lote** | Lot / Batch | Conjunto de unidades producidas juntas, con identidad única para trazabilidad. |
| **Lote padre** | Parent lot | Lote consumido para producir otro lote. |
| **Lote hijo** | Child lot | Lote producido a partir de uno o más lotes padre. |
| **Materia prima** | Raw material | Componente al inicio de la cadena de transformación. |
| **Semielaborado** | Semi-finished good / WIP item | Producto intermedio entre materia prima y producto terminado. |
| **Producto terminado** | Finished good | Salida final de la cadena, lista para envío. |
| **Trazabilidad genealógica** | Genealogical traceability | Reconstrucción del árbol completo de lotes consumidos y producidos para un lote dado. |
| **OEE** | Overall Equipment Effectiveness | Métrica compuesta = Disponibilidad × Rendimiento × Calidad. |
| **Disponibilidad** | Availability | Tiempo operando ÷ tiempo planeado de producción. |
| **Rendimiento** | Performance | Producción real ÷ producción teórica al ritmo ideal. |
| **Calidad** | Quality (in OEE context) | Unidades buenas ÷ unidades totales producidas. |
| **Paro programado** | Planned downtime | Tiempo de no-producción que estaba en el calendario (mantenimiento, almuerzo, cambio de turno). |
| **Paro no programado** | Unplanned downtime | Cualquier paro no agendado: falla, falta de material, falta de operario. |
| **Ruta de manufactura** | Routing | Secuencia de pasos por los que pasa un producto, cada uno asociado a un equipo. |
| **BOM** | Bill of Materials | Lista de componentes (con cantidades) necesarios para fabricar una unidad de un producto. |
| **WIP** | Work-in-Process | Inventario en proceso de transformación, asociado a una OF en un paso de ruta. |
| **Takt time** | Takt time | Ritmo de demanda del cliente: tiempo disponible ÷ unidades demandadas. |
| **Cycle time** | Cycle time | Tiempo real que tarda producir una unidad en un equipo. |
| **Setup / cambio** | Setup / changeover | Tiempo improductivo entre dos corridas distintas en el mismo equipo. |
| **FPY** | First Pass Yield | % de unidades que salen buenas a la primera, sin retrabajo. |
| **Scrap** | Scrap | Unidades rechazadas que se desechan. |
| **Retrabajo** | Rework | Unidades rechazadas que se reprocesan para recuperar. |
| **No conformidad (NC)** | Non-conformance (NCR) | Hallazgo de calidad fuera de especificación que dispara contención + análisis + acción correctiva. |
| **SPC** | Statistical Process Control | Control estadístico de procesos: gráficos X-barra/R, reglas Western Electric. |
| **Cp / Cpk** | Cp / Cpk | Índices de capacidad de proceso. Cp = ancho de tolerancia ÷ variación. Cpk = corregido por centrado. |
| **MTTR** | Mean Time To Repair | Tiempo medio para reparar tras una falla. |
| **MTBF** | Mean Time Between Failures | Tiempo medio entre dos fallas consecutivas. |
| **Andon** | Andon | Sistema de señalización visual que comunica el estado de un equipo (verde/amarillo/rojo). |
| **Kanban** | Kanban | Señal (tarjeta o digital) que autoriza producir o mover un componente. |

## Términos prohibidos

- **"Job"** en lugar de "Manufacturing Order" — no es ambiguo en inglés general, pero en MES "job" suele referirse al trabajo de un operario en un turno. Usar `manufacturing_order` (o `MO`).
- **"Batch"** sin contexto — usar `lot` por defecto. `batch` solo para productos de manufactura química/farmacéutica.
