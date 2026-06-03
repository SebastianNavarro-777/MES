"""Sync the canonical NSG label set into Linear and backfill seed tickets.

Three modes (mutually exclusive):

* ``--list`` — print every label currently in the team. Read-only.
* ``--ensure`` — make sure the canonical label set exists. Idempotent: existing
  names are left alone, missing ones are created via ``issueLabelCreate``.
* ``--backfill`` — apply the right labels to the 9 seed tickets (NSG-1..NSG-9).
  Implies ``--ensure``. Idempotent.

The script never deletes a label and never strips a ticket of labels it
already has — backfill always *unions* with the existing label set on each
issue.

Live credentials are required for all three modes. ``--list`` is the safest
to run first; ``--ensure`` is required before the orchestrator can route
tickets correctly; ``--backfill`` is the one-shot fix for the 9 tickets that
landed without labels.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Resolve repo root so the orchestrator package imports when this script is
# run directly (`python tools/orchestrator/seed/sync_labels.py`).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from tools.orchestrator.orchestrator.config import Settings  # noqa: E402
from tools.orchestrator.orchestrator.linear_client import LinearClient  # noqa: E402
from tools.orchestrator.seed.initial_tickets import SEEDS  # noqa: E402

# ---------------------------------------------------------------------------
# Canonical label set
# ---------------------------------------------------------------------------

# Routing labels read by the orchestrator code itself.
#   - needs-human-decision: consultant_resolver.py looks for this on Done
#     Questions to detect freshly-answered ones.
#   - harness-fix: recolector.py routes tickets carrying this label to the
#     harness improvement queue.
#   - low-risk / high-risk: control Reviewer escalation policy.
#   - applied-default-decision: marks Epics created under a Consultant
#     fallback verdict (3-question backlog) so the human can audit later.
#   - needs-human: the recovery daemons apply this when a ticket exhausts
#     its auto-retry budget (spec_writer_runner.py / failed_recovery.py),
#     so the loops stop and a human picks it up.
ROUTING_LABELS: tuple[str, ...] = (
    "needs-human-decision",
    "needs-human",
    "low-risk",
    "high-risk",
    "harness-fix",
    "applied-default-decision",
)

# Type labels are the source of truth for ticket type
# (docs/workflows/ticket-types.md).
TYPE_LABELS: tuple[str, ...] = (
    "type:epic",
    "type:story",
    "type:bug",
    "type:question",
    "type:harness-fix",
)

# Bounded-context / module labels. The Worker reads these to know which
# directories it may touch; the Reviewer enforces the scope rule.
#
# All five product phases pre-seeded so the Architect never has to call
# issueLabelCreate when it crosses into Phase 2+. See /ROADMAP.md.
MODULE_LABELS: tuple[str, ...] = (
    # Cross-cutting + Phase 1
    "module:harness",       # tools/, .claude/, docs/workflows/, prompts
    "module:platform",      # cross-cutting Django setup, settings, base classes
    "module:orders",        # apps/orders/         (Phase 1)
    "module:frontend",      # frontend/            (all phases)
    # Phase 2 — Trazabilidad + OPC-UA
    "module:traceability",  # apps/traceability/   (Phase 2)
    # Phase 3 — OEE + Downtime
    "module:oee",           # apps/oee/            (Phase 3)
    "module:downtime",      # apps/downtime/       (Phase 3)
    # Phase 4 — Quality / SPC / NCR
    "module:quality",       # apps/quality/        (Phase 4)
    # Phase 5 — Scheduling + Maintenance
    "module:scheduling",    # apps/scheduling/     (Phase 5)
    "module:maintenance",   # apps/maintenance/    (Phase 5)
)

CANONICAL_LABELS: tuple[str, ...] = ROUTING_LABELS + TYPE_LABELS + MODULE_LABELS


# Map seed ticket identifier → labels it should carry. Derived from
# ``initial_tickets.SEEDS`` so there is a single source of truth. Linear
# assigns identifiers sequentially per team starting at NSG-1, so the
# i-th seed corresponds to ``NSG-{i+1}`` on a fresh team. The backfill
# mode uses this mapping; if a team already had unrelated tickets before
# the seed ran, the operator needs to adjust the prefix range manually.
SEED_TICKET_LABELS: dict[str, tuple[str, ...]] = {
    f"NSG-{i + 1}": seed.labels for i, seed in enumerate(SEEDS)
}


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


async def _op_list(settings: Settings) -> int:
    async with LinearClient(
        settings.LINEAR_API_KEY, settings.LINEAR_TEAM_ID
    ) as client:
        labels = await client.list_team_labels()
    if not labels:
        print("(no labels in this team)")
        return 0
    print(f"{len(labels)} labels in team {settings.LINEAR_TEAM_ID}:")
    for name in sorted(labels):
        print(f"  {name:32s} {labels[name]}")
    missing = [n for n in CANONICAL_LABELS if n not in labels]
    if missing:
        print()
        print(f"Missing from canonical set ({len(missing)}):")
        for name in missing:
            print(f"  - {name}")
        print()
        print("Run `--ensure` to create them.")
    else:
        print()
        print("All canonical labels present.")
    return 0


async def _op_ensure(settings: Settings) -> int:
    async with LinearClient(
        settings.LINEAR_API_KEY, settings.LINEAR_TEAM_ID
    ) as client:
        existing = await client.list_team_labels()
        missing = [n for n in CANONICAL_LABELS if n not in existing]
        if not missing:
            print("All canonical labels already exist. Nothing to do.")
            return 0
        print(f"Creating {len(missing)} label(s):")
        for name in missing:
            uuid = await client.create_label(name)
            print(f"  + {name:32s} {uuid}")
    return 0


async def _op_backfill(settings: Settings) -> int:
    async with LinearClient(
        settings.LINEAR_API_KEY, settings.LINEAR_TEAM_ID
    ) as client:
        # First, make sure every label we need exists.
        needed = sorted({n for labels in SEED_TICKET_LABELS.values() for n in labels})
        name_to_uuid = await client.ensure_labels(needed)

        for identifier, target_labels in SEED_TICKET_LABELS.items():
            issue = await client.get_issue(identifier)
            if issue is None:
                print(f"  ! {identifier} not found in Linear, skipping")
                continue
            # Union the existing labels with the target set so we never
            # strip something a human added manually.
            current_names = set(issue.labels)
            wanted_names = set(target_labels) | current_names
            wanted_ids = sorted({name_to_uuid[n] for n in wanted_names if n in name_to_uuid})
            await client.update_issue_labels(issue.id, wanted_ids)
            added = sorted(set(target_labels) - current_names)
            if added:
                print(f"  {identifier}: +{', '.join(added)}")
            else:
                print(f"  {identifier}: already labelled")
    return 0


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync NSG canonical labels into Linear and backfill seed tickets."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", dest="op", action="store_const", const="list")
    mode.add_argument("--ensure", dest="op", action="store_const", const="ensure")
    mode.add_argument("--backfill", dest="op", action="store_const", const="backfill")
    args = parser.parse_args(argv)

    settings = Settings()
    if not settings.LINEAR_API_KEY or not settings.LINEAR_TEAM_ID:
        print(
            "Refusing to run: LINEAR_API_KEY or LINEAR_TEAM_ID missing in .env.",
            file=sys.stderr,
        )
        return 2

    if args.op == "list":
        return asyncio.run(_op_list(settings))
    if args.op == "ensure":
        return asyncio.run(_op_ensure(settings))
    if args.op == "backfill":
        return asyncio.run(_op_backfill(settings))
    return 2  # unreachable thanks to required=True


if __name__ == "__main__":
    sys.exit(main())
