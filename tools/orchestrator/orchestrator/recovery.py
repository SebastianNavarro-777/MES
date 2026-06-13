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

__all__ = [
    "NEEDS_HUMAN_DECISION_LABEL",
    "NEEDS_HUMAN_LABEL",
    "escalate_to_human",
    "is_question",
    "needs_human",
]

log = logging.getLogger(__name__)

# Mirrors the canonical label in ``seed/sync_labels.py``.
NEEDS_HUMAN_LABEL = "needs-human"

# Mirrors the label the Consultant applies to every Question it opens (see
# ``prompts/consultant.md`` and ``seed/sync_labels.py``). Every Question
# carries this; ``type:question`` is applied inconsistently, so this is the
# reliable marker.
NEEDS_HUMAN_DECISION_LABEL = "needs-human-decision"


def needs_human(issue: Issue) -> bool:
    """Whether a ticket has already been escalated to a human."""
    return NEEDS_HUMAN_LABEL in issue.labels


def is_question(issue: Issue) -> bool:
    """Whether ``issue`` is a human-decision Question, not implementable work.

    A Question ticket has no code surface (no ``module:*`` label, no ACs); it
    exists only so a human can pick an option in Linear. It must never enter
    the work pipeline: a Worker that dequeues one finds nothing to build and
    shoves it into ``Blocked`` — which is exactly how *already-answered*
    Questions (NSG-42, NSG-44) got dragged Done → In Progress → Blocked after
    the human had resolved them. The recolector skips enqueuing these and the
    recovery daemon skips re-driving them, so an answered Question stays put
    and an unanswered one waits untouched until the Consultant Resolver acts.
    """
    return NEEDS_HUMAN_DECISION_LABEL in issue.labels


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
