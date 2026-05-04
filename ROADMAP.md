# ROADMAP.md

Plan de producto del MES en 5 fases. El **Architect agent** lee este documento al cerrar cada Epic y proponer el siguiente. Cada fase suma sobre la anterior; no hay regresiones de alcance.

Las fases son objetivos de producto, no compromisos de fecha. Las fechas son orientativas asumiendo el ritmo del orquestador (~3-6 PRs/día con la laptop encendida).

---

## Fase 1 — Núcleo de órdenes (Mes 1-2)

**Meta:** un operador puede crear, listar y avanzar el estado de una orden de fabricación desde una pantalla web. Auth básica.

**Entregables clave:**
1. Bounded context `orders`: modelo de orden de fabricación (OF), ruta, paso de ruta, estados (`draft → released → in_progress → completed → closed`).
2. API REST: CRUD de OFs, transiciones de estado validadas en `application/`.
3. Bounded context `wip` mínimo: stock por paso de ruta, vinculado a la OF.
4. Auth Django + DRF (sesión + token). Roles: `operator`, `supervisor`, `admin`.
5. Frontend React: pantalla de lista de OFs con filtros, pantalla de detalle con cambio de estado.

**Definición de éxito:** un usuario `supervisor` puede crear una OF y un `operator` puede avanzarla por sus estados desde la UI; auditoría básica en BD.

---

## Fase 2 — Trazabilidad e integración OPC-UA básica (Mes 2-3)

**Meta:** la OF queda enlazada a lotes consumidos y producidos. Un PLC lee/escribe variables vía OPC-UA.

**Entregables clave:**
1. Bounded context `traceability`: modelo de lote padre/hijo, evento de consumo y producción (genealogía).
2. Cliente OPC-UA con `asyncua` en `packages/infrastructure/opcua/`. Configuración por equipo en BD.
3. Worker Celery que escucha eventos OPC-UA y publica `traceability.events` al event bus.
4. Reportes de genealogía (forward y backward) accesibles desde el detalle de OF.
5. Pantalla "scan" para registrar consumo manual de lotes (escaneo de código de barras).

**Definición de éxito:** dado un lote terminado, el sistema reconstruye su genealogía hasta materias primas; al menos un PLC en simulación se integra y produce eventos de consumo.

---

## Fase 3 — OEE, paros y dashboards en tiempo real (Mes 3-4)

**Meta:** medir y visualizar Disponibilidad × Rendimiento × Calidad por equipo, con paros (causa, duración, categoría).

**Entregables clave:**
1. Bounded context `oee`: cálculo periódico (turno, día) de A × R × C por equipo.
2. Bounded context `downtime`: registro manual y automático (vía OPC-UA) de paros con catálogo de causas.
3. Stream de eventos OEE publicado a Redis; consumer agrega métricas para dashboard.
4. Dashboard React en tiempo real: andon por equipo, top causas de paro, OEE por turno.
5. Cálculo y enforcement de las reglas: GP-006 (OEE siempre a nivel de equipo), GP-007 (PLC reads async).

**Definición de éxito:** dashboard muestra OEE en vivo de al menos un equipo conectado; paros mayores a un umbral disparan alerta visual.

---

## Fase 4 — Calidad, SPC y no conformidades (Mes 4-5)

**Meta:** registrar mediciones de calidad, calcular Cp/Cpk y abrir/cerrar no conformidades vinculadas a lote y OF.

**Entregables clave:**
1. Bounded context `quality`: planes de inspección, características críticas, mediciones por lote.
2. Cálculo SPC: gráficos X-barra/R, Cp, Cpk, tendencias automáticas (reglas Western Electric).
3. Flujo de no conformidad (NCR): apertura, contención, análisis causa-raíz, acción correctiva, cierre.
4. Pantalla de inspección móvil-friendly para registro en planta.
5. Compliance hook: si el módulo `compliance/21-cfr-part-11.md` aplica al cliente, audit log inmutable y firma electrónica en cada NCR.

**Definición de éxito:** un inspector registra una medición que dispara una NCR automáticamente; supervisor cierra el ciclo con CAPA documentada.

---

## Fase 5 — Programación, mantenimiento e integración ERP (Mes 5-6)

**Meta:** el MES recibe órdenes desde el ERP, las programa contra capacidad de equipos, y dispara mantenimientos preventivos por horas de operación.

**Entregables clave:**
1. Bounded context `scheduling`: secuenciación finita por equipo, gantt visual, drag & drop.
2. Bounded context `maintenance`: planes preventivos (por horas, por ciclos, por calendario), órdenes de trabajo.
3. Integración ERP (SAP) bidireccional: importar OFs, exportar consumos y producción terminada vía IDoc o API REST según corresponda al cliente.
4. Cálculo de MTTR/MTBF por equipo, dashboard de salud de planta.
5. API webhooks para que sistemas terceros se suscriban a eventos clave (`order.completed`, `lot.produced`, `ncr.opened`).

**Definición de éxito:** orden creada en SAP aparece programada automáticamente en el MES; al ejecutarla, consumos y producción regresan al ERP sin intervención manual.

---

## Reglas de evolución del roadmap

- **El Architect agent NO altera el roadmap.** Solo crea Epics que materializan la fase actual.
- **Pasar de fase requiere aprobación humana** (Sebas) en un ticket `Question`. El Architect propone el cierre de fase cuando todos los entregables están en `Done` y QA Smoke pasó en staging.
- **Cualquier cambio al roadmap se hace vía PR a este archivo, revisado por Sebas.** El Gardener puede proponer cambios pero no los mergea.
