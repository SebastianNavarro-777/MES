# NSG MES

Repositorio agent-native que hospeda el **Manufacturing Execution System (MES)** de NSG Engineering.

Este repo no se construye a mano: lo construyen agentes. Hay 8 agentes (Architect, Spec Writer, Consultant, Worker, Reviewer, QA Smoke, Auditor, Gardener) que viven dentro de un orquestador Python corriendo localmente. El orquestador conecta Linear (tickets) con Claude Code (ejecución) y GitHub (entrega).

## Setup

Lee **[SETUP_FOR_SEBAS.md](SETUP_FOR_SEBAS.md)** — es el único documento que un humano necesita para arrancar el sistema.

## Para los agentes

- **[AGENTS.md](AGENTS.md)** — entrada maestra de enrutamiento de contexto.
- **[CLAUDE.md](CLAUDE.md)** — instrucciones específicas de Claude Code.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — reglas duras de capas, no negociables.
- **[ROADMAP.md](ROADMAP.md)** — fases del producto MES.
- **[docs/](docs/)** — progressive disclosure por carpeta. Lee solo lo que tu ticket requiera.

## Estructura

```
.
├── docs/                      Conocimiento del proyecto
├── apps/                      Bounded contexts del MES (Django apps)
├── packages/                  Domain / infrastructure / shared
├── frontend/                  React + Vite + TS
├── tools/
│   ├── linters/               Linter de arquitectura por capas
│   ├── verification/          Scripts de verificación pre-cierre
│   └── orchestrator/          Orquestador + prompts de los 8 agentes
├── .claude/                   Hooks y settings de Claude Code
└── .github/workflows/         CI de validación de PRs
```

## Stack

Python 3.12 (uv) · Django 5 · DRF · PostgreSQL 16 · Redis 7 + Celery · React 18 + Vite + TS · `asyncua` (OPC-UA) · Playwright · ruff · mypy strict.

## Idiomas

Código, identificadores, commits, PRs y prompts internos en **inglés**. Documentos de dominio, visión y tickets de pregunta para el operador humano en **español**.
