---
title: Ticket types
description: Los 5 tipos de ticket en Linear y el formato que cada uno debe respetar.
audience: todos los agentes (especialmente Architect, Spec Writer, Consultant); Sebas al crear tickets manuales.
last_updated: 2026-05-04
---

# Ticket types

5 tipos. El campo "Type" en Linear es la fuente de verdad. Cada tipo tiene un formato esperado en la descripción.

| Tipo | Quién lo crea | Quién lo trabaja | Cuándo se usa |
|---|---|---|---|
| **Epic** | Architect agent (o Sebas) | Architect lo descompone en Stories | Agrupar 5-12 Stories que entregan un objetivo del [roadmap](../../ROADMAP.md). |
| **Story** | Architect (vacía) → Spec Writer (enriquece) | Worker | Unidad de trabajo que cabe en 1-3 días de Worker. |
| **Bug** | QA Smoke / Auditor / Sebas | Worker | Defecto reproducible en código mergeado. |
| **Question** | Consultant (en nombre de otro agente) | Sebas (humano) | Decisión que requiere criterio humano (ver [escalation.md](escalation.md)). |
| **Harness-Fix** | Auditor / Gardener / cualquier agente que detecte un problema en el harness | Worker | Mejora a `tools/`, prompts de agentes, hooks, linters, docs operativos. |

---

## Formato — Epic

```markdown
## Objetivo
<1-2 líneas: qué entrega este Epic al usuario final / al negocio>

## Tickets hijos
- [ ] NSG-XXX — <título>
- [ ] NSG-XXY — <título>

## Definición de éxito
<medible: una funcionalidad concreta usable por un rol específico>

## Roadmap phase
<1 | 2 | 3 | 4 | 5>
```

---

## Formato — Story

```markdown
## Contexto
<2-4 líneas: por qué importa, dónde encaja>

## Acceptance Criteria
- [ ] AC-1: <criterio observable, escrito en lenguaje del usuario>
- [ ] AC-2: ...
- [ ] AC-3: ...

## Notas técnicas / riesgos
<lo que el Spec Writer ve después de leer docs/, golden-principles, especificaciones del módulo>

## Definition of Done
<copia exacta de docs/workflows/DEFINITION_OF_DONE.md — el Spec Writer la pega al final>
```

---

## Formato — Bug

```markdown
## Resumen
<1 línea>

## Pasos para reproducir
1. ...
2. ...
3. ...

## Resultado actual
<qué pasa>

## Resultado esperado
<qué debería pasar>

## Severidad
<P0 — bloquea | P1 — afecta funcionalidad | P2 — molestia>

## Acceptance Criteria
- [ ] AC-1: <test específico que reproduce el bug y ahora pasa>
- [ ] AC-2: <regresión cubierta>
```

---

## Formato — Question

Ver [escalation.md](escalation.md) para el formato exacto. Resumen rápido:

```markdown
## Bloquea
<NSG-XXX>

## Contexto
<lo que el agente activo ya sabe>

## La pregunta
<una pregunta concreta>

## Opciones
- A) ...
- B) ...
- C) ...

## Mi recomendación
<lo que el Consultant haría si tuviera que elegir>

## Tu decisión
- [ ] A
- [ ] B
- [ ] C
- [ ] Otra: ___
```

Label obligatoria: `needs-human-decision`.

---

## Formato — Harness-Fix

```markdown
## Problema observado
<patrón concreto en N tickets / PRs / fallos>

## Hipótesis de causa raíz
<por qué el harness no lo previno>

## Cambio propuesto
<qué tocar: prompt, hook, linter, doc>

## Acceptance Criteria
- [ ] AC-1: <verificación de que el cambio prevé el problema>
- [ ] AC-2: <no rompe casos positivos existentes>

## Aprobación humana requerida
<sí/no — los Harness-Fix que tocan golden-principles o ARCHITECTURE.md siempre requieren aprobación de Sebas vía Question previo>
```
