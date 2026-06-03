"""Shared recovery helpers for the orchestrator's self-healing daemons.

Two daemons re-drive stuck tickets on a bounded budget:

* ``spec_writer_runner.py`` re-spawns the Spec Writer on Spec Drafts that
  a previous agent run left without completing the Spec Draft → Ready for
  Agent transition.
* ``failed_recovery.py`` re-queues Failed tickets back to Ready for Agent.

Both stop after ``Settings.MAX_AUTO_RETRIES`` attempts and hand the ticket
to a human by applying the ``needs-human`` label — the signal both daemons
honour as "stop touching this; a person needs to look." This module owns
that escalation so the two paths behave identically.
"""

from __future__ import annotations

import logging

from .linear_client import Issue, LinearClient

__all__ = ["NEEDS_HUMAN_LABEL", "escalate_to_human", "needs_human"]

log = logging.getLogger(__name__)

# Mirrors the canonical label in ``seed/sync_labels.py``.
NEEDS_HUMAN_LABEL = "needs-human"


def needs_human(issue: Issue) -> bool:
    """Whether a ticket has already been escalated to a human."""
    return NEEDS_HUMAN_LABEL in issue.labels


async def escalate_to_human(
    linear: LinearClient, issue: Issue, *, reason: str
) -> None:
    """Label ``issue`` ``needs-human`` (preserving existing labels) + comment.

    Idempotent: if the label is already present we do nothing, so the
    comment fires exactly once across daemon ticks. The label is the
    sole stop signal — neither recovery daemon re-drives a ticket that
    carries it.
    """
    if needs_human(issue):
        return
    label_map = await linear.ensure_labels([NEEDS_HUMAN_LABEL, *issue.labels])
    await linear.update_issue_labels(issue.id, list(label_map.values()))
    await linear.add_comment(
        issue.id,
        f"Auto-recovery exhausted ({reason}). Labelled "
        f"`{NEEDS_HUMAN_LABEL}` — needs manual attention; the orchestrator "
        f"will not retry it again.",
    )
    log.info("escalated %s to human: %s", issue.identifier, reason)
