---
title: Definition of Done (DoD)
description: Checklist mecánica que cada Story tiene que pasar antes de cerrarse. El Spec Writer copia este bloque al cuerpo del ticket.
audience: Worker (la cumple), Reviewer (la verifica), QA Smoke (extiende).
last_updated: 2026-05-04
---

# Definition of Done

Toda Story se considera `Done` solo cuando **todas** estas casillas están marcadas. El Reviewer agent corre el verificador (`./tools/verification/verify_ticket.sh <ticket-id>`) que automatiza la mayoría.

```
- [ ] Linter `ruff check` pasa sobre el código modificado.
- [ ] `mypy --strict` pasa para `packages/` y `apps/<contexto>/`.
- [ ] Linter de arquitectura (`tools/linters/architecture.py`) pasa sin warnings.
- [ ] Tests unitarios del módulo afectado pasan localmente y en CI.
- [ ] Coverage del módulo afectado **no decrece** respecto a `main`.
- [ ] Tests E2E (Playwright) cubren el happy path si el ticket afecta `interface/` o `frontend/`.
- [ ] Si el ticket tocó modelos Django: migración generada (`python manage.py makemigrations`) y commiteada en el mismo PR.
- [ ] `docs/generated/STATE.md` se actualizó automáticamente vía hook (`.claude/hooks/stop.sh` lo regenera).
- [ ] Cada Acceptance Criterion (AC) del ticket tiene al menos un test que lo cubre, identificado con un comentario `# AC-N: ...`.
- [ ] Si el ticket afecta UI: screenshot o video del happy path adjunto al ticket Linear vía MCP `linear`.
- [ ] Reviewer agent aprobó el PR (o, en modo ramp-up, escaló como `Question` si era `high-risk`).
- [ ] QA Smoke pasó en el entorno `staging` (o lo abrió como `Question` si staging no estaba disponible).
```

## Reglas

- **No se permite saltarse un punto.** Si una casilla no aplica (e.g., el ticket no tiene UI, no aplica Playwright), el Worker debe escribir explícitamente "N/A — razón" en el comentario del ticket. Marcar la casilla sin justificación es motivo de rechazo del PR.
- **Coverage no decrece** se mide sobre el módulo modificado, no sobre el repo entero. El Reviewer agent calcula con `coverage report --include="apps/<context>/*"`.
- **Migraciones**: si el modelo cambia y la migración no se commitea, el `stop.sh` hook lo detecta (corre `makemigrations --check --dry-run`) y exige al agente generarla.

## Cuándo se actualiza esta DoD

Solo via PR a este archivo, revisado por Sebas. El Gardener agent puede proponer adiciones (e.g., nueva regla de seguridad o performance) cuando observa fallas recurrentes. Las adiciones aplican a Stories nuevas, no retroactivamente.
