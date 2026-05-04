---
title: Escalation — cuándo y cómo crear un ticket Question
description: Reglas que el Consultant agent (y todo otro agente) sigue al toparse con ambigüedad estratégica.
audience: todos los agentes; Sebas (lee y responde Questions).
last_updated: 2026-05-04
---

# Escalation

Cuando un agente (Worker, Spec Writer, Architect, Reviewer, QA Smoke) encuentra una decisión que no puede tomar leyendo `docs/`, `ARCHITECTURE.md`, `golden-principles.md` y el ticket actual, **invoca al Consultant agent**. El Consultant decide entre:

1. **Responder él mismo**, si la pregunta SÍ es respondible con docs (significa que el agente original no leyó suficiente).
2. **Crear un ticket `Question` para Sebas**.
3. **Aplicar el camino de menor riesgo** según `golden-principles.md`, si ya hay 3 `Question` abiertos en Linear (límite duro para no saturar a Sebas).

---

## Triggers — cuándo SÍ se escala

| Trigger | Ejemplo |
|---|---|
| Decisión que afecta **esquema de BD de manera irreversible**. | "¿La OF se identifica con el ID del ERP o con un secuencial nuestro?" |
| Decisión que cambia **integración con sistema externo**. | "El cliente pidió enviar confirmaciones por IDoc en vez de por API REST." |
| **Trade-off de compliance** (qué normativa aplica al cliente X). | "Este cliente automotriz pidió datos formato PPAP — ¿lo generamos o no?" |
| **Spec del ticket es ambigua** y los docs no la resuelven. | "El AC dice 'el operario puede aprobar' pero no dice si requiere firma electrónica." |
| **Conflicto entre dos golden-principles**. | "GP-005 dice eventos inmutables; el cliente pidió poder corregir un lote — ¿soft delete con motivo cuenta como inmutable?" |

---

## Anti-triggers — cuándo NO se escala

- Detalles de implementación menor (nombres de funciones, organización de archivos).
- Imports y módulos.
- Trade-offs que ya están resueltos en `docs/decisions/` (ADRs vigentes).
- Preguntas cuya respuesta está en `docs/product-specs/{módulo}/` (lee primero).
- Cuestiones de estilo cubiertas por `ruff` y `mypy strict`.

Si no estás seguro de si es trigger o anti-trigger: **lee los docs un poco más**. El costo de leer es bajo; el costo de saturar a Sebas con preguntas evitables es alto.

---

## Formato exacto de un ticket `Question`

El Consultant crea el ticket con título corto y este cuerpo. **Usar este formato literal** — los demás agentes parsean estos tickets cuando se cierran.

```markdown
## Bloquea
NSG-<id> ([título del ticket original])

## Contexto
<3-6 líneas, en español>

- ¿Qué se está intentando hacer?
- ¿Qué docs ya se consultaron?
- ¿Qué se descartó y por qué?
- ¿Cuál es el impacto si se elige mal (irreversibilidad, costo de retrabajo)?

## La pregunta
<UNA pregunta concreta, redactada en una sola oración>

## Opciones
- **A) <opción>** — implicaciones: <2-3 puntos>.
- **B) <opción>** — implicaciones: <2-3 puntos>.
- **C) <opción>** — implicaciones: <2-3 puntos>.

(Si solo hay 2 opciones, omitir C. Mínimo 2.)

## Mi recomendación
<1-2 líneas, en español: qué haría el Consultant si tuviera que elegir, y por qué>

## Tu decisión
- [ ] A
- [ ] B
- [ ] C
- [ ] Otra: ____________________

(Sebas marca una casilla y comenta cualquier matiz.)

## Después de tu respuesta se actualiza
- `docs/decisions/<NNNN>-<slug>.md` (ADR nuevo si la decisión es estratégica).
- O `docs/golden-principles.md` (si es regla mecánica nueva).
- Y se mueve NSG-<id> de vuelta a `Ready for Agent`.
```

**Label obligatoria:** `needs-human-decision`.
**Estado inicial:** `Backlog` (Linear lo muestra al supervisor humano).
**Estado al cerrarse:** `Done` con resumen del Consultant Resolver indicando dónde quedó documentada la decisión.

---

## Límite duro: 3 `Question` abiertos a la vez

Si al invocar al Consultant ya hay 3 tickets con label `needs-human-decision` en estados distintos a `Done` / `Cancelled`, el Consultant **no crea otro**. En su lugar:

1. Aplica el camino de menor riesgo según `golden-principles.md` (privilegia inmutabilidad, idempotencia, no-destrucción).
2. Lo documenta en un comentario en el ticket original explicando el razonamiento.
3. Marca el ticket original con label `applied-default-decision` para que Sebas lo revise después.

Esto previene saturación de la cola humana. Cuando Sebas resuelva uno, el siguiente Consultant que necesite escalar puede crear un nuevo ticket.

---

## Después de la respuesta de Sebas

El daemon `consultant_resolver` en el orquestador detecta que el ticket `Question` cambió a `Resolved` / `Done`:

1. Parsea la decisión (qué casilla marcó Sebas + comentarios).
2. Actualiza el archivo destino (`docs/decisions/<NNNN>-<slug>.md` o `docs/golden-principles.md`).
3. Comenta en el ticket original con la decisión y un link al ADR.
4. Mueve el ticket original de `Blocked` → `Ready for Agent`.

Si la respuesta es ambigua (Sebas no marcó casilla o escribió "depende"), el resolver re-abre el `Question` con un comentario pidiendo desambiguación, y mantiene el ticket original `Blocked`.
