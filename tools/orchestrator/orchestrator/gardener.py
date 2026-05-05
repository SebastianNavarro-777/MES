"""Gardener one-shot runner.

Receives the dispatcher's lists of unconsumed learning events and
unconsumed PRs (from the safety net), runs the Gardener agent prompt,
and on success consumes them.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .trigger_dispatcher import AgentName, GardenerDecision

__all__ = ["run_gardener"]

log = logging.getLogger(__name__)


async def run_gardener(
    decision: GardenerDecision,
    *,
    settings: Settings,
    db: Database,
    claude: ClaudeRunner,
) -> int:
    if not decision.fire:
        log.info("gardener: not firing (%s)", decision.reason)
        return 0

    user_prompt = (
        "Sweep the latest learning events and consider harness changes. "
        f"You have {len(decision.learning_event_ids)} unconsumed learning "
        f"event(s) and {len(decision.pr_numbers)} unconsumed PR(s) since "
        "the last sweep. Follow tools/orchestrator/prompts/gardener.md."
    )
    result = await claude.run(
        agent_name="gardener",
        user_prompt=user_prompt,
        workspace=settings.worktrees_path,
    )
    if result.exit_code == 0:
        db.mark_learning_events_consumed(decision.learning_event_ids)
        db.mark_prs_consumed_by_gardener(decision.pr_numbers)
    else:
        log.warning(
            "gardener run exited %s; events stay unconsumed for retry",
            result.exit_code,
        )
    db.record_agent_run(AgentName.GARDENER.value, when=datetime.now(UTC))
    return result.exit_code
