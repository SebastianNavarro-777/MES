# Setup — qué tienes que hacer tú, Sebas

Este es el único documento que necesitas leer para arrancar el sistema. Si no funciona algo siguiendo solo estas instrucciones, eso es un bug — repórtalo o ábrelo como `Harness-Fix`.

Tiempo aproximado de setup completo: **45–60 minutos** (la mayoría es esperar a que Claude Code descargue MCPs y a que `uv sync` instale).

---

## TL;DR — el camino feliz

```bash
git clone <repo-url> MES && cd MES
uv sync --extra dev
cp .env.example .env && $EDITOR .env       # llenar credenciales
cd tools/orchestrator
python -m orchestrator trigger-dispatcher --inspect    # verifica
python -m orchestrator run-all                          # arranca
```

Si todo lo de arriba corrió sin error, ya está. Las secciones siguientes son: (1) lo que hay que configurar **una sola vez**, y (2) cómo operar día a día.

---

## Parte 1 — Setup que se hace una sola vez

### 1. Configurar tu proyecto en Linear

#### 1.1. Estados del workflow
Crea estos 9 estados, exactamente con estos nombres y respetando mayúsculas:

| Categoría | Nombre exacto |
|---|---|
| Backlog | `Backlog` |
| Unstarted | `Spec Draft` |
| Unstarted | `Ready for Agent` |
| Started | `In Progress` |
| Started | `Blocked` |
| Started | `In Review` |
| Started | `Ready for QA` |
| Completed | `Failed` |
| Completed | `Done` |

> Si renombras alguno, el orquestador no lo va a reconocer y los daemons quedarán idle. Los nombres están hard-coded en `tools/orchestrator/orchestrator/state_machine.py` y se compara case-sensitive.

#### 1.2. Labels
Crea estos 5 labels:

- `needs-human-decision` — el Consultant agent lo pone en cada `Question` que abre.
- `low-risk` — Story segura para que el Reviewer apruebe sin escalar.
- `high-risk` — toca migraciones, auth, integraciones o golden-principles. En modo ramp-up el Reviewer escala vía Consultant en lugar de aprobar.
- `harness-fix` — tickets de mejora del propio harness (los abre el Auditor o el Gardener).
- `applied-default-decision` — el Consultant lo pone cuando ya había 3 `Question` abiertos y aplicó la opción de menor riesgo.

#### 1.3. Tipos de ticket
Linear no obliga a tener un campo "Type" estructurado. Para identificar el tipo de cada ticket usamos **labels `type:*`** (más simple, funciona en cualquier plan de Linear y no necesita admin features).

Crea estos 5 labels adicionales en la misma sección Settings → NSG Engineering → Labels donde creaste los del paso 1.2:

| Nombre exacto | Para qué |
|---|---|
| `type:epic` | Epics que el Architect crea como contenedor de Stories. |
| `type:story` | Unidad de trabajo que un Worker implementa. |
| `type:bug` | Defecto reproducible en código mergeado. Lo abre QA Smoke o Sebas. |
| `type:question` | Decisión que requiere criterio humano (Sebas). Lo abre el Consultant. |
| `type:harness-fix` | Mejora al propio harness. Lo abren Auditor o Gardener. |

> **Alternativa (custom field):** si tienes plan Standard+ de Linear, podrías usar un custom field "Select" llamado `Type` en lugar de labels. Funcionalmente equivalente, pero los prompts de los agentes están escritos para leer labels `type:*`. Si eliges custom field, tendrás que ajustar los prompts (un `Harness-Fix` chico).

#### 1.4. Templates de descripción
El formato exacto de cada tipo de ticket está en [`docs/workflows/ticket-types.md`](docs/workflows/ticket-types.md). Linear soporta plantillas: copia los bloques markdown de ese archivo y crea una plantilla por tipo. Esto te ahorra que el Architect agent escriba el formato a mano cada vez.

---

### 2. Generar API keys

#### Linear
Settings → API → Personal API key. Copia el valor — solo se muestra una vez.

#### GitHub
Settings → Developer settings → Personal access tokens → Fine-grained token. Permisos mínimos:
- Contents: Read & write
- Pull requests: Read & write
- Issues: Read & write
- Metadata: Read

> No uses tokens con scopes globales; usa fine-grained limitado al repo `nsg-engineering/mes` (o como se llame tu repo).

---

### 3. Configurar `.env`

```bash
cp .env.example .env
```

Llena los valores reales. Los **thresholds** vienen con defaults razonables; las primeras 2 semanas considera bajarlos para ver el sistema trabajar más seguido:

| Variable | Default | Sugerencia primeras 2 semanas |
|---|---:|---:|
| `AUDITOR_PR_THRESHOLD` | 5 | 3 |
| `GARDENER_LEARNING_THRESHOLD` | 10 | 5 |
| `ARCHITECT_BACKLOG_THRESHOLD` | 5 | igual |
| `AGENT_COOLDOWN_MINUTES` | 30 | igual |

> **Nunca** commitees `.env` — `.gitignore` ya lo excluye.

---

### 4. Login en Claude Code con tu suscripción

```bash
claude login
```

Elige tu cuenta Pro/Max. Verifica que quedó funcional:

```bash
claude --version
claude doctor
```

Si `claude doctor` reporta algo en rojo, arréglalo antes de seguir — el orquestador no va a poder lanzar agentes sin una sesión válida.

---

### 5. Conectar los MCPs que el orquestador asume

Cada Worker, Reviewer, QA Smoke y Consultant es Claude Code corriendo headless. Para que tengan las herramientas que `tools/orchestrator/prompts/*.md` invocan, los MCPs deben estar configurados en tu instalación de Claude Code.

| MCP | Para qué se usa | Cómo configurarlo |
|---|---|---|
| **Linear** | Leer tickets, comentar, mover de estado, adjuntar archivos. | OAuth vía claude.ai. Si ves `claude.ai Linear: ✓ Connected` en `claude mcp list`, listo. (No usa el `LINEAR_API_KEY` de `.env` — el orquestador y el MCP son canales paralelos contra el mismo team.) |
| **GitHub** | Crear PRs, comentar, mergear. (También vía `gh` CLI). | Ver sección 5.A abajo. Dos rutas: Copilot o stdio local. |
| **Context7** | Traer docs vivas de Django/DRF/asyncua/React/etc. en cada sesión. | Usualmente preinstalado en Claude Code o vía un plugin (ej. `plugin:odoo-owl-dev:context7`); verifica con `claude mcp list`. |
| **Playwright** | Manejar el browser desde Worker (capturar screenshots de UI) y QA Smoke (E2E happy-path en staging). Lo asumen `prompts/worker.md` y `prompts/qa_smoke.md`. | Ver sección 5.C abajo. |
| **Semgrep** | Scan de patrones inseguros sobre el diff. | **Saltar en Windows.** Ver sección 5.B abajo. |

Verifica el inventario con:

```bash
claude mcp list
```

Linear, Context7, GitHub y Playwright deben estar `✓ Connected`. Semgrep puede faltar — los 7 checks mecánicos del Reviewer no lo requieren, es defense-in-depth opcional.

#### 5.A — GitHub MCP

GitHub tiene dos MCP servers; cuál uses depende de si tienes suscripción a Copilot:

**Si tienes GitHub Copilot (Pro/Business/Enterprise):** ya viene un MCP hosted en `api.githubcopilot.com/mcp/`. Solo re-autentica si está en `Failed to connect`.

**Si NO tienes Copilot (caso común):** instala el MCP stdio local. Usa tu `GITHUB_TOKEN` del `.env`. En PowerShell:

```powershell
# 1. Pre-instalar el binario para que npx no prompttee
npm install -g @modelcontextprotocol/server-github

# 2. Verificar que quedó
Get-Command mcp-server-github

# 3. Registrar en Claude (extrae el token de .env automáticamente)
$token = (Get-Content .env | Where-Object { $_ -match '^GITHUB_TOKEN=' }) -replace '^GITHUB_TOKEN=', ''
if ([string]::IsNullOrWhiteSpace($token)) { Write-Host "ERROR: GITHUB_TOKEN no encontrado en .env"; return }
claude mcp add -e "GITHUB_PERSONAL_ACCESS_TOKEN=$token" -s user github mcp-server-github
Remove-Variable token
Clear-History -CommandLine "*GITHUB_PERSONAL_ACCESS_TOKEN*","*GITHUB_TOKEN*"
```

Quirks conocidos (te ahorran tiempo):

- **NO uses `npx -y` después de `--`**: el parser de Claude (commander.js) y/o PowerShell trata `-y` como flag propio y rompe. Pre-instala el binario con `npm install -g` y referéncialo directamente.
- **NO uses el separador `--`** entre el `<name>` y `<commandOrUrl>` cuando pasas `-e`. El `-e` es variadic (`<env...>`) y con `--` commander toma todos los posicionales como args para el comando, no como `<name>` y `<commandOrUrl>`. Sin `--`, los posicionales se parsean correctamente.

Valida con:

```powershell
claude mcp list
```

Debe aparecer `github: mcp-server-github - ✓ Connected`.

#### 5.B — Semgrep MCP

**En Windows nativo: salta este paso.** Semgrep depende de toolchain Unix; en Windows requiere Docker o WSL para funcionar bien y los retornos no valen la fricción del setup.

**Cuando muevas a la VPS Linux** (Parte 2 de este documento), agrega Semgrep así:

```bash
python -m uv tool install semgrep-mcp
claude mcp add -s user semgrep semgrep-mcp
```

Mientras tanto, los 7 checks del Reviewer son suficientes para empezar. Si en algún momento el Reviewer detecta que necesita Semgrep, va a abrir un `Question` para que sepas que falta — pero no es bloqueante.

#### 5.C — Playwright MCP

El Worker y QA Smoke esperan tener `playwright` MCP para navegar el browser, hacer screenshots y validar flows E2E. Si falta, el primer ticket que toque UI (NSG-6 en el seed) se va a bloquear con un `Question` de "MCP missing".

Microsoft mantiene el MCP oficial en `@playwright/mcp`. En PowerShell, **desde `C:\Users\SebasNavarro\MES\MES`** (cualquier directorio funcionaría, pero mantenemos la convención del resto del setup):

```powershell
# 1. Pre-cachear el paquete para que npx no prompttee en runtime headless
npx -y @playwright/mcp@latest --version

# 2. Descargar Chromium (lo que Playwright maneja por default).
#    Esto es ~120 MB; corre una sola vez.
npx playwright install chromium

# 3. Registrar el MCP a user scope (igual que GitHub MCP)
claude mcp add -s user playwright npx "@playwright/mcp@latest"
```

Valida con:

```powershell
claude mcp list
```

Debe aparecer `playwright: npx @playwright/mcp@latest - ✓ Connected`.

Quirks conocidos:

- **No necesita token ni env var** — el servidor levanta Chromium local, no llama a ningún API.
- **Aísla por sesión**: cada vez que Claude Code arranca, lanza un browser nuevo. No persistente. Bueno para reproducibilidad, malo si necesitas estado entre llamadas (no es el caso aquí).
- **El binario `npx @playwright/mcp@latest` resuelve el paquete por nombre**, no necesitas `npm install -g` como con GitHub MCP. Microsoft publicó el paquete así específicamente para el flow de `claude mcp add`.
- **Si Chromium no descarga** (firewall corporativo, proxy), corre `npx playwright install chromium --dry-run` para ver qué URL está intentando, y agrega excepción en tu proxy.

---

### 6. Instalar dependencias del repo

Una sola vez:

```bash
# desde la raíz del repo
uv sync
```

Esto crea `.venv/` con Python 3.12 e instala:
- **Runtime** (`[project.dependencies]`): httpx, rich, pydantic, pydantic-settings.
- **Dev** (`[dependency-groups].dev`): pytest, pytest-asyncio, ruff, mypy, respx, yamllint.

Las versiones quedan ancladas en `uv.lock` (commiteado en el repo).

> **Por qué `uv sync` simple, no `--extra dev`**: pasamos las dev deps de `[project.optional-dependencies]` a `[dependency-groups]`. La diferencia: `[dependency-groups]` se incluye por default en `uv sync` y NO se elimina cuando corres `uv run`. Con `optional-dependencies`, cada `uv run` sin `--extra dev` re-podaba la venv y rompía el stop hook silenciosamente. Si por algún motivo quieres una venv minimal sin dev: `uv sync --no-group dev`.
>
> No necesitas `uv sync` adicional dentro de `tools/orchestrator/` — el sub-pyproject de ahí es solo metadata; las deps reales viven en el root.

---

### 7. Configurar el bit ejecutable de los hooks (solo si clonaste en Mac/Linux)

Los hooks de Claude Code en `.claude/hooks/*.sh` están commiteados con `mode 100755`. Si por algún motivo perdieron el bit:

```bash
chmod +x .claude/hooks/*.sh
```

`.gitattributes` fuerza LF en archivos `.sh` para que los shebangs no se rompan tras un round-trip por Windows.

---

### 8. Validar que la base está sana antes de arrancar

```bash
# desde la raíz del repo
uv run ruff check .
uv run mypy --strict
uv run pytest -q
uv run python tools/linters/architecture.py
```

Los cuatro deben terminar exit 0. Si alguno falla con el repo recién clonado (sin haber tocado nada), eso es un bug — repórtalo.

---

### 9. Ejecutar el seed inicial de tickets en Linear

Antes de "commit", revisa con dry-run:

```bash
python tools/orchestrator/seed/initial_tickets.py
```

Imprime los 9 tickets que va a crear. Cuando estés conforme:

```bash
python tools/orchestrator/seed/initial_tickets.py --commit
```

Esto crea 1 Epic + 8 Stories en `Backlog`. El Architect agent al primer disparo verá el Epic ya creado y empezará a operar sobre Stories en cola.

---

### 10. (Opcional pero recomendado) Configurar branch protection en GitHub

Settings → Branches → Add rule para `main`. Marca como required (la primera tanda es la que tenías; los 4 nuevos son del pipeline de seguridad que se agregó):

**Tanda original (lint/test/arch):**
- `CI / Lint (ruff + mypy + architecture)`
- `CI / Test (pytest)`
- `Architecture Lint / tools/linters/architecture.py`

**Tanda de seguridad (agregar después de que corra al menos una vez cada uno):**
- `CI / Security audit (pip-audit)` — CVE scanner sobre `uv.lock`
- `CI / License check (pip-licenses)` — rechaza AGPL/GPL/LGPL
- `Security / Secret scan (gitleaks)` — scan full-history de tokens
- `CodeQL / CodeQL — python` — SAST nativo de GitHub

> **Por qué "después de que corra al menos una vez":** GitHub solo te deja seleccionar un check como required si ya lo ha visto pasar (o fallar) en algún PR. Después de mergear este commit a `main`, los 4 checks van a correr — entonces vuelves a Settings → Branches y los marcas required en bloque.

Esto previene que se mergee algo a `main` con CI rojo. El Reviewer agent ya intenta esto; los protected branches son la red de seguridad si un agente se equivoca, y los 4 checks de seguridad cierran los huecos de supply chain + leak de credenciales.

---

## Parte 2 — Cómo correr el orquestador en tu laptop

### Opción simple (las primeras 2-3 semanas — recomendada)

Abre una terminal en `tools/orchestrator/` y deja corriendo:

```bash
cd tools/orchestrator
python -m orchestrator run-all
```

Mientras esta terminal esté abierta, el sistema avanza. Cuando cierres la laptop o esta terminal, el orquestador se detiene. Al volver, lo levantas igual. Ver logs en vivo te enseña mucho del comportamiento del sistema en su primera fase.

### Opción "siempre que mi sesión esté abierta"

#### En macOS — launchd

1. Edita `tools/orchestrator/launchd/com.nsg.mes-orchestrator.plist.template`. Reemplaza `{{HOME_PATH}}` y `{{USER}}` con valores reales.
2. Copia a `~/Library/LaunchAgents/`:
   ```bash
   cp tools/orchestrator/launchd/com.nsg.mes-orchestrator.plist.template \
      ~/Library/LaunchAgents/com.nsg.mes-orchestrator.plist
   ```
3. Carga:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.nsg.mes-orchestrator.plist
   ```
4. Ver logs: `~/MES/MES/.orchestrator-state/logs/launchd-stderr.log`.

#### En Linux — systemd --user

1. Edita `tools/orchestrator/systemd/mes-orchestrator.service.template`. Reemplaza `{{HOME_PATH}}` y `{{USER}}`.
2. Copia:
   ```bash
   cp tools/orchestrator/systemd/mes-orchestrator.service.template \
      ~/.config/systemd/user/mes-orchestrator.service
   ```
3. Habilita y arranca:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable mes-orchestrator
   systemctl --user start mes-orchestrator
   ```
4. Logs en vivo: `journalctl --user -u mes-orchestrator -f`.

### Opción 24/7 (cuando pase a producción)

Mover a una VPS chica (Hetzner CX22, ~$4/mes). El código no cambia: mismo `python -m orchestrator run-all`. La transición toma ~30 minutos: copia el repo, instala uv, sigue los pasos 3, 5, 6 de Parte 1, arranca con systemd. No hay refactor pendiente.

---

## Parte 3 — Cómo se disparan los agentes

| Agente | Cómo se dispara |
|---|---|
| **Recolector** | Daemon, polea Linear cada 60 s. |
| **Worker (pool)** | Daemon, dequeue de SQLite cuando hay tickets `Ready for Agent`. |
| **Reviewer** | Daemon, reacciona a tickets en `In Review` con PR abierto. |
| **QA Smoke** | Daemon, reacciona a tickets en `Ready for QA`. Serial — uno a la vez por staging compartido. |
| **Consultant Resolver** | Daemon, reacciona a tickets `Question` resueltos por ti. |
| **Architect** | Trigger reactivo — `Backlog` < `ARCHITECT_BACKLOG_THRESHOLD`, cooldown 1 h. |
| **Auditor** | Trigger reactivo — cada `AUDITOR_PR_THRESHOLD` PRs mergeados sin auditar. |
| **Gardener** | Trigger reactivo — `GARDENER_LEARNING_THRESHOLD` learning events o `GARDENER_PR_SAFETY_THRESHOLD` PRs mergeados (lo que pase primero). |

Todos viven dentro del mismo proceso `python -m orchestrator run-all`. **No hay cron de sistema, no hay GitHub Actions cron, no hay API key separada.** Eventos reactivos, contadores SQLite, cooldown global de `AGENT_COOLDOWN_MINUTES` (30 min default) por agente.

### Disparar un agente manualmente

```bash
cd tools/orchestrator
python -m orchestrator architect --run-now
python -m orchestrator auditor   --run-now
python -m orchestrator gardener  --run-now
```

`--run-now` ignora el cooldown pero **no inventa trabajo**: si no hay PRs sin auditar, el Auditor no se dispara aunque uses `--run-now`.

### Inspeccionar el estado de los contadores

```bash
cd tools/orchestrator
python -m orchestrator trigger-dispatcher --inspect
```

Imprime un snapshot: cuántos tickets hay en `Backlog`, cuántos PRs sin auditar, cuántos learning events sin consumir, qué agente está en cooldown.

---

## Parte 4 — Sleep y triggers

Los triggers son **eventually-consistent**, no temporales. **Nunca se pierde nada cuando duermes la laptop**:

- Cuando despiertas y arrancas el orquestador, evalúa todos los contadores apenas inicia.
- Si una condición ya estaba cumplida desde antes de dormir, dispara apenas inicia.
- El cooldown de 30 min entre disparos del mismo agente previene loops si algo sale mal.

---

## Parte 5 — Tu rol diario

1. **Abrir Linear**, filtrar por label `needs-human-decision`.
2. **Responder los tickets `Question`** marcando una de las casillas A/B/C u escribiendo "Otra: …". Los formatos están diseñados para que respondas en 30 segundos.
3. **Cada cierto tiempo**, revisar PRs que abrió el Gardener (label `harness-fix`). Estos son cambios al harness mismo; revísalos como cualquier PR.
4. **Aprobar releases a producción** cuando llegue ese ticket (lo abrirás manualmente cuando estés listo de cerrar una fase del roadmap).

Eso es todo. **No revises tickets `Story` rutinarios** — el flujo agentes los procesa. Solo intervén cuando un `Question` te lo pida o cuando un PR de `harness-fix` espere tu aprobación.

---

## Parte 6 — Qué esperar las primeras semanas

El sistema solo avanza **cuando tu laptop está prendida y el orquestador corriendo**:

- Con la laptop prendida 8 h al día y 2 Workers concurrentes, espera **3–6 PRs/día** con tickets de tamaño normal.
- Si te vas el fin de semana, el sistema duerme. Al volver el lunes, el Architect chequea backlog y crea más tickets si hace falta.
- Los `Question` no tienen urgencia automática. Si abres uno antes de cerrar laptop, el ticket original queda `Blocked` hasta que respondes Y el orquestador esté corriendo.
- **Esto es deliberado** para esta fase de demo. Cuando quieras 24/7, mover a VPS toma ~30 min y no requiere cambios de código.

### Ritmo realista de las primeras 2 semanas

| Día | Esperado |
|---|---|
| 1 | Architect crea Epic + 8 Stories. Spec Writer enriquece la primera. Worker abre primer PR. Reviewer probablemente lo rechaza (estás aprendiendo). |
| 2-3 | Workers aprenden el patrón. Reviewer empieza a aprobar. QA Smoke da su primer veredicto. Posible primer revert. |
| 4-5 | Auditor tiene 5 PRs y dispara su primera ronda. Empiezan a aparecer `Question` reales. |
| 6-7 | Primer disparo del Gardener. PR proponiendo una nueva regla en `golden-principles.md` (que requerirá `Question` previo). |
| 14 | El sistema ha iterado sobre sí mismo varias veces. Los tickets nuevos requieren menos `Question`. |

Si después de 2 semanas estás abriendo más de 5 `Question` por día, eso es señal de que `docs/` necesita mejorarse — abre un `Harness-Fix` para que el Gardener priorice docs.

---

## Parte 7 — Cuándo intervenir manualmente

| Síntoma | Acción |
|---|---|
| El sistema entra en loop de errores (mismo ticket falla 3+ veces). | Detén el orquestador (`Ctrl+C` en la terminal o `launchctl unload` / `systemctl stop`). Revisa logs en `.orchestrator-state/logs/`. |
| El Gardener propone un cambio mayor (toca `golden-principles.md` o `ARCHITECTURE.md`). | Lo verás como `Question` previo al PR. Léelo bien antes de aprobar. |
| Un `Question` lleva 3 días sin respuesta y bloquea trabajo. | Considera reformular o dar más contexto. Los `Question` están diseñados para responderse en 30 s; si tardas más es que falta info. |
| QA Smoke marca como `Failed` algo que sospechas que es flaky. | El Bug ticket que abrió tiene la evidencia. Si es flaky real, escribe `flaky` en la severidad y un Worker estabilizará el test. |
| Hay 3 `Question` abiertos. | Cualquier nuevo Consultant aplicará "decisión por defecto" en lugar de abrir un 4to. Resuelve los abiertos para liberar la cola. |

---

## Parte 8 — Troubleshooting común

### El stop hook falla con "no Python interpreter found"
Corre `uv sync --extra dev` desde la raíz del repo. El hook busca `.venv/Scripts/python.exe` (Windows) o `.venv/bin/python` (Mac/Linux).

### `python -m orchestrator` da "No module named orchestrator"
Estás en la carpeta equivocada. `cd tools/orchestrator/` primero. Alternativa desde la raíz: `python -m tools.orchestrator.orchestrator --help`.

### Linear devuelve 401 al recolector
La API key expiró o no tiene scope correcto. Regénerala (paso 2.1) y actualiza `.env`. Reinicia el orquestador para que re-lea `.env`.

### El Reviewer no encuentra el PR linkeado al ticket
Verifica que el Worker esté incluyendo `Linked ticket NSG-XXX` en el body del PR (template en [`worker.md`](tools/orchestrator/prompts/worker.md)). Si no, abre `Harness-Fix` para reforzar la regla.

### Claude Code se cuelga en una sesión
El claude_runner tiene timeout de 30 min por agente. Pasado eso, mata el proceso y registra `learning_event` para el Gardener. Si pasa repetidamente con el mismo agente, abre `Harness-Fix`.

### Los hooks ralentizan demasiado las ediciones
Edita `.claude/hooks/post_tool_use.sh` para que el linter de arquitectura solo corra sobre archivos en `apps/` o `packages/` (ya lo hace) — y haz una pausa entre ediciones masivas. Si el problema persiste, abre `Harness-Fix`.

### El Auditor reporta drift entre `STATE.md` y el código
El generador `tools/verification/update_state.py` no existe todavía (se entrega en una Story de Fase 1 del roadmap). Mientras tanto, el Auditor abrirá `Harness-Fix` reportando la falta — ignóralo hasta que esa Story cierre.

### Quiero parar el orquestador limpiamente
`Ctrl+C` en la terminal del `run-all`. Los daemons reciben SIGINT, terminan su tick actual y salen. SIGTERM también funciona (para systemd).

### `git update-index --chmod=+x` me da error en Windows
Usa Git Bash, no `cmd.exe`. Los hooks ya están commiteados con el bit ejecutable (`mode 100755`); solo es necesario regenerar si los recreas desde cero.

---

## Parte 9 — Glosario rápido (es ↔ en)

Como referencia cruzada, los términos del MES están en [`docs/domain/glossary.md`](docs/domain/glossary.md). Los del harness:

| Término | Significado |
|---|---|
| **Harness** | El sistema que construye el MES (este repo, sin contar `apps/` ni `frontend/`). |
| **Tick** | Una iteración del loop de un daemon. |
| **Cooldown** | Tiempo mínimo entre dos ejecuciones del mismo agente. |
| **Trigger** | Condición que dispara un agente one-shot (Architect/Auditor/Gardener). |
| **Workspace** | Worktree git per-ticket bajo `$WORKTREES_DIR/<ticket-id>/`. |
| **Learning event** | Fila en SQLite que el Gardener consume para evolucionar el harness. |
| **Ramp-up mode** | Los primeros 30 PRs del proyecto, en los que el Reviewer es más conservador con `high-risk`. |

---

## Última cosa

Este sistema está diseñado para mejorarse solo. Las primeras corridas van a fallar. Los Workers van a romper cosas. El Reviewer va a aprobar PRs imperfectos. **Eso es correcto y esperado**: cada falla la come el Gardener y la convierte en una regla nueva en `docs/golden-principles.md` o un hook nuevo. Tu trabajo NO es construir un sistema perfecto — es darle al Gardener material para iterar.

Si dudas entre intervenir manualmente o dejar al sistema fallar y aprender: **deja al sistema fallar**. Solo intervén cuando vea un loop infinito, una decisión que solo tú puedes tomar (ese es lo que un `Question` señala), o un PR de `harness-fix` esperando tu OK.
