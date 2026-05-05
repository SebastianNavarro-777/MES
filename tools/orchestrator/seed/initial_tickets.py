"""Seed Linear with the first 9 tickets that bootstrap the MES.

Phase 9 of the harness bootstrap creates these. The script supports a
``--dry-run`` mode (default) that lists what would be created without
touching Linear, and a ``--commit`` mode that actually writes them.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

# This script can run directly (`python tools/orchestrator/seed/initial_tickets.py`).
# Inject the repo root onto sys.path so the orchestrator package resolves.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.orchestrator.orchestrator.config import Settings  # noqa: E402
from tools.orchestrator.orchestrator.linear_client import LinearClient  # noqa: E402


@dataclass(frozen=True)
class SeedTicket:
    title: str
    description: str
    is_epic: bool = False


# The seed set defined in the prompt. Numbered for clarity; descriptions
# are intentionally short — Spec Writer enriches each Story when picked.
SEEDS: list[SeedTicket] = [
    SeedTicket(
        title="MES Fase 1 -- Nucleo de ordenes",
        description=(
            "Epic that bundles the first eight Stories of phase 1: a working "
            "vertical slice from order creation in the UI to status changes "
            "persisted in Postgres. See /ROADMAP.md."
        ),
        is_epic=True,
    ),
    SeedTicket(
        title="Setup Django project + base config",
        description=(
            "Bootstrap the Django 5 project with DRF, settings split per env, "
            "auth, audit-log mixin scaffolding, and the initial migration."
        ),
    ),
    SeedTicket(
        title="Crear bounded context `orders` con modelos base",
        description=(
            "Create apps/orders/{domain,application,infrastructure,interface}/ "
            "with the ManufacturingOrder entity and a state-machine helper."
        ),
    ),
    SeedTicket(
        title="Endpoint REST: crear orden de fabricacion",
        description=(
            "POST /api/v1/orders/ with serializer + use case wired into the "
            "orders application layer; emits orders.created."
        ),
    ),
    SeedTicket(
        title="Endpoint REST: listar ordenes por estado",
        description=(
            "GET /api/v1/orders/?state=... with cursor pagination + filtering."
        ),
    ),
    SeedTicket(
        title="Setup React + Vite + integracion con DRF",
        description=(
            "Scaffold frontend/ with Vite, TS strict, TanStack Query, and an "
            "OpenAPI-generated client from drf-spectacular."
        ),
    ),
    SeedTicket(
        title="Pantalla: lista de ordenes con filtros",
        description=(
            "Operator-facing list view with state filter, cursor pagination, "
            "and a search box on identifier."
        ),
    ),
    SeedTicket(
        title="Pantalla: detalle de orden + cambio de estado",
        description=(
            "Detail page showing order + transitions allowed by the state "
            "machine, with a confirmation modal for transitions."
        ),
    ),
    SeedTicket(
        title="Setup tools/verification/deploy_staging.sh + docker-compose staging",
        description=(
            "QA Smoke depends on this. docker-compose for Postgres + Redis + "
            "the Django app + the React bundle, plus a deploy_staging.sh "
            "wrapper that takes a merge SHA."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def _print_dry_run() -> None:
    print("Seed tickets (dry-run -- nothing is created):")
    for i, t in enumerate(SEEDS):
        kind = "Epic " if t.is_epic else "Story"
        print(f"  {i + 1:2d}. [{kind}] {t.title}")
        print(f"       {t.description[:100]}")


async def _commit(settings: Settings) -> int:
    if not settings.is_configured():
        print("Refusing to --commit: live credentials missing.", file=sys.stderr)
        return 2
    async with LinearClient(
        settings.LINEAR_API_KEY, settings.LINEAR_TEAM_ID
    ) as client:
        epic_id: str | None = None
        for t in SEEDS:
            issue = await client.create_issue(
                title=t.title,
                description=t.description,
                parent_id=epic_id if not t.is_epic else None,
            )
            print(f"created {issue.identifier}: {t.title}")
            if t.is_epic:
                epic_id = issue.id
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed Linear with the first 9 NSG MES tickets."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually create the tickets in Linear (default: dry-run).",
    )
    args = parser.parse_args(argv)

    if not args.commit:
        _print_dry_run()
        return 0
    settings = Settings()
    return asyncio.run(_commit(settings))


if __name__ == "__main__":
    sys.exit(main())
