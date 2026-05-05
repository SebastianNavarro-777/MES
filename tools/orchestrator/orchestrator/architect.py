"""Architect one-shot runner.

Invoked by the trigger dispatcher when the Linear backlog falls below
``ARCHITECT_BACKLOG_THRESHOLD``, or manually via ``--run-now``. Spawns
Claude Code with the ``architect`` system prompt; on exit, stamps the
agent state in the DB so cooldown takes effect.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .trigger_dispatcher import AgentName, ArchitectDecision

__all__ = ["run_architect"]

log = logging.getLogger(__name__)


async def run_architect(
    decision: ArchitectDecision,
    *,
    settings: Settings,
    db: Database,
    claude: ClaudeRunner,
) -> int:
    """Run the Architect agent based on a dispatcher decision.

    Returns the exit code from Claude Code (0 = success).
    """
    if not decision.fire:
        log.info("architect: not firing (%s)", decision.reason)
        return 0

    user_prompt = (
        "Decompose the next deliverable from the active /ROADMAP.md phase "
        "into a single Epic plus 5-12 Stories. The current Linear backlog "
        f"has {decision.backlog_count} ticket(s). Follow tools/orchestrator/"
        "prompts/architect.md exactly."
    )
    result = await claude.run(
        agent_name="architect",
        user_prompt=user_prompt,
        workspace=settings.worktrees_path,
    )
    if result.exit_code != 0:
        log.warning(
            "architect run exited %s: %s", result.exit_code, result.stderr[-500:]
        )
    db.record_agent_run(AgentName.ARCHITECT.value, when=datetime.now(UTC))
    return result.exit_code
