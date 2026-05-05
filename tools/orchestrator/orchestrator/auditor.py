"""Auditor one-shot runner.

Hands the Auditor agent the exact list of merged PRs (no sampling) the
trigger dispatcher decided are due for audit. The agent then operates
deterministically on that list.

After the agent exits successfully, the runner marks the PRs as
``audited`` in SQLite and stamps the agent state for cooldown.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .trigger_dispatcher import AgentName, AuditorDecision

__all__ = ["run_auditor"]

log = logging.getLogger(__name__)


async def run_auditor(
    decision: AuditorDecision,
    *,
    settings: Settings,
    db: Database,
    claude: ClaudeRunner,
) -> int:
    if not decision.fire:
        log.info("auditor: not firing (%s)", decision.reason)
        return 0

    pr_list = ", ".join(f"#{n}" for n in decision.pr_numbers)
    user_prompt = (
        f"Audit the following {len(decision.pr_numbers)} merged PR(s): "
        f"{pr_list}. Follow tools/orchestrator/prompts/auditor.md."
    )
    result = await claude.run(
        agent_name="auditor",
        user_prompt=user_prompt,
        workspace=settings.worktrees_path,
    )
    if result.exit_code == 0:
        db.mark_prs_audited(decision.pr_numbers)
    else:
        log.warning(
            "auditor run exited %s; not marking PRs audited", result.exit_code
        )
    db.record_agent_run(AgentName.AUDITOR.value, when=datetime.now(UTC))
    return result.exit_code
