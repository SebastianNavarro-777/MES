"""Linear ticket state machine for the NSG MES orchestrator.

Encodes the valid Linear states and the allowed transitions between them.
Every state change made by any agent (or daemon) goes through
:func:`assert_can_transition` so that the audit log is unambiguous.

The full transition graph mirrors the agent contracts in
``tools/orchestrator/prompts/`` and ``docs/workflows/`` — keep this file in
sync if those files change. Tests live at
``tools/orchestrator/tests/test_state_machine.py``.
"""

from __future__ import annotations

import enum

__all__ = [
    "ALLOWED_TRANSITIONS",
    "InvalidTransitionError",
    "TicketState",
    "actionable_states",
    "assert_can_transition",
    "can_transition",
    "inflight_states",
    "terminal_states",
]


class TicketState(enum.StrEnum):
    """Workflow states that exist in the team's Linear project.

    Sebas creates these states in Linear once (see SETUP_FOR_SEBAS.md).
    The string value MUST match the state name in Linear exactly,
    including case, because we serialise it into GraphQL filters.
    """

    BACKLOG = "Backlog"
    SPEC_DRAFT = "Spec Draft"
    READY_FOR_AGENT = "Ready for Agent"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    IN_REVIEW = "In Review"
    READY_FOR_QA = "Ready for QA"
    FAILED = "Failed"
    DONE = "Done"


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------


# Each entry says: from this state, you may move to any of these states.
# Matches the prose in docs/workflows/escalation.md and the agent prompts.
ALLOWED_TRANSITIONS: dict[TicketState, frozenset[TicketState]] = {
    # Architect creates Stories in Backlog.
    # Spec Writer picks one up → Spec Draft.
    TicketState.BACKLOG: frozenset(
        {
            TicketState.SPEC_DRAFT,  # Spec Writer started enriching.
            TicketState.READY_FOR_AGENT,  # Direct path; only when no enrichment needed.
            TicketState.BLOCKED,  # Architect escalated before creating Stories.
            TicketState.FAILED,  # Architect cancelled an Epic mid-creation.
        }
    ),
    # Spec Writer is enriching.
    TicketState.SPEC_DRAFT: frozenset(
        {
            TicketState.READY_FOR_AGENT,  # Spec Writer finished.
            TicketState.BLOCKED,  # Consultant invoked → Question opened.
            TicketState.FAILED,  # Spec Writer rejected as duplicate / unsalvageable.
        }
    ),
    # Worker pool will dequeue this.
    TicketState.READY_FOR_AGENT: frozenset(
        {
            TicketState.IN_PROGRESS,  # Worker picked it up.
            TicketState.BLOCKED,  # Pre-flight escalation by Worker before any code.
        }
    ),
    # Worker is implementing.
    TicketState.IN_PROGRESS: frozenset(
        {
            TicketState.IN_REVIEW,  # PR opened.
            TicketState.BLOCKED,  # Consultant invoked mid-implementation.
            TicketState.FAILED,  # Worker gave up after 2 retries.
            TicketState.READY_FOR_AGENT,  # Orphan re-claim: the Worker
            # crashed mid-run and left the ticket stranded here; the
            # failed_recovery daemon re-queues it after a grace period.
        }
    ),
    # Question opened; waiting on Sebas.
    TicketState.BLOCKED: frozenset(
        {
            TicketState.READY_FOR_AGENT,  # Consultant Resolver re-opened after Sebas decided.
            TicketState.FAILED,  # Sebas declined to answer / cancelled the work.
        }
    ),
    # PR open under review by the Reviewer agent.
    TicketState.IN_REVIEW: frozenset(
        {
            TicketState.READY_FOR_QA,  # Reviewer merged the PR.
            TicketState.FAILED,  # Reviewer rejected and asked for retry.
        }
    ),
    # Merged. QA Smoke is up next.
    TicketState.READY_FOR_QA: frozenset(
        {
            TicketState.DONE,  # QA Smoke green; ticket closes.
            TicketState.FAILED,  # QA Smoke failed; merge auto-reverted.
            TicketState.BLOCKED,  # Staging unavailable; Question opened.
        }
    ),
    # Failure can be re-opened by the Spec Writer with revised notes.
    TicketState.FAILED: frozenset(
        {
            TicketState.READY_FOR_AGENT,  # Re-attempt with additional notes.
            TicketState.SPEC_DRAFT,  # Re-enrichment needed before another attempt.
        }
    ),
    # Terminal.
    TicketState.DONE: frozenset(),
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidTransitionError(ValueError):
    """Raised when an agent attempts a state transition that's not allowed."""

    def __init__(self, src: TicketState, dst: TicketState) -> None:
        super().__init__(
            f"Invalid transition: {src.value!r} → {dst.value!r}. "
            f"From {src.value!r}, allowed targets: "
            f"{sorted(s.value for s in ALLOWED_TRANSITIONS[src])}."
        )
        self.src = src
        self.dst = dst


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def can_transition(src: TicketState, dst: TicketState) -> bool:
    """Whether the transition ``src → dst`` is allowed by the contract."""
    return dst in ALLOWED_TRANSITIONS.get(src, frozenset())


def assert_can_transition(src: TicketState, dst: TicketState) -> None:
    """Raise :class:`InvalidTransitionError` if the transition is not allowed."""
    if not can_transition(src, dst):
        raise InvalidTransitionError(src, dst)


def terminal_states() -> frozenset[TicketState]:
    """States from which no transition is possible."""
    return frozenset(s for s, dests in ALLOWED_TRANSITIONS.items() if not dests)


def inflight_states() -> frozenset[TicketState]:
    """States that represent unfinished, in-flight work.

    Every state except :attr:`TicketState.DONE` (terminal) and
    :attr:`TicketState.FAILED` (awaiting recovery, not fresh backlog the
    Architect should top up). The trigger dispatcher sums issues across
    these states to gauge real backlog pressure: a Story that has advanced
    past ``Backlog`` (e.g. into ``Ready for Agent`` or ``In Review``) is
    still unfinished work, so a fully-decomposed phase must not be misread
    as "backlog exhausted" and trigger a spurious Architect run (NSG-49).
    """
    return frozenset(TicketState) - {TicketState.DONE, TicketState.FAILED}


def actionable_states() -> frozenset[TicketState]:
    """States the recolector daemon enqueues for downstream daemons.

    These are states where SOMETHING in the harness needs to act on the
    ticket. ``Backlog`` is excluded (the Architect creates tickets there;
    we don't pick them up automatically — the Spec Writer daemon polls
    Linear directly and promotes them into ``Spec Draft``). ``Failed`` is
    likewise excluded: the ``failed_recovery`` daemon polls it directly and
    re-queues to ``Ready for Agent``. ``Done`` is terminal.
    """
    return frozenset(
        {
            TicketState.SPEC_DRAFT,
            TicketState.READY_FOR_AGENT,
            TicketState.IN_REVIEW,
            TicketState.READY_FOR_QA,
        }
    )
