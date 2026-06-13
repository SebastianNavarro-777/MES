"""Tests for the Linear state machine."""

from __future__ import annotations

import pytest

from tools.orchestrator.orchestrator.state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    TicketState,
    actionable_states,
    assert_can_transition,
    can_transition,
    inflight_states,
    terminal_states,
)

# ---------------------------------------------------------------------------
# Coverage of the canonical transitions documented in the prompts and docs.
# Each row (src, dst, expected) is checked against can_transition.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        # Backlog
        (TicketState.BACKLOG, TicketState.SPEC_DRAFT),
        (TicketState.BACKLOG, TicketState.READY_FOR_AGENT),
        (TicketState.BACKLOG, TicketState.BLOCKED),
        # Spec Draft
        (TicketState.SPEC_DRAFT, TicketState.READY_FOR_AGENT),
        (TicketState.SPEC_DRAFT, TicketState.BLOCKED),
        (TicketState.SPEC_DRAFT, TicketState.FAILED),
        # Ready for Agent
        (TicketState.READY_FOR_AGENT, TicketState.IN_PROGRESS),
        (TicketState.READY_FOR_AGENT, TicketState.BLOCKED),
        # In Progress
        (TicketState.IN_PROGRESS, TicketState.IN_REVIEW),
        (TicketState.IN_PROGRESS, TicketState.BLOCKED),
        (TicketState.IN_PROGRESS, TicketState.FAILED),
        # In Progress → Ready for Agent: orphan re-claim after a Worker
        # crash (failed_recovery re-queues a stale In Progress ticket).
        (TicketState.IN_PROGRESS, TicketState.READY_FOR_AGENT),
        # Blocked → unblocked by Consultant Resolver
        (TicketState.BLOCKED, TicketState.READY_FOR_AGENT),
        (TicketState.BLOCKED, TicketState.FAILED),
        # In Review
        (TicketState.IN_REVIEW, TicketState.READY_FOR_QA),
        (TicketState.IN_REVIEW, TicketState.FAILED),
        # Ready for QA
        (TicketState.READY_FOR_QA, TicketState.DONE),
        (TicketState.READY_FOR_QA, TicketState.FAILED),
        (TicketState.READY_FOR_QA, TicketState.BLOCKED),
        # Failed → re-attempt
        (TicketState.FAILED, TicketState.READY_FOR_AGENT),
        (TicketState.FAILED, TicketState.SPEC_DRAFT),
    ],
)
def test_valid_transitions(src: TicketState, dst: TicketState) -> None:
    assert can_transition(src, dst), f"expected {src.value} → {dst.value} to be allowed"
    assert_can_transition(src, dst)  # should not raise


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        # Skipping the spec phase isn't allowed when going from Backlog directly to In Progress.
        (TicketState.BACKLOG, TicketState.IN_PROGRESS),
        (TicketState.BACKLOG, TicketState.IN_REVIEW),
        # Re-entering Spec Draft from Ready for Agent isn't allowed (Spec Writer is one-way).
        (TicketState.READY_FOR_AGENT, TicketState.SPEC_DRAFT),
        # Workers can't mark a ticket Done directly; QA Smoke owns Done.
        (TicketState.IN_PROGRESS, TicketState.DONE),
        (TicketState.IN_REVIEW, TicketState.DONE),
        # Reviewer doesn't move tickets back to In Progress; that's a Worker re-take from Failed.
        (TicketState.IN_REVIEW, TicketState.IN_PROGRESS),
        # No state escapes from Done (terminal).
        (TicketState.DONE, TicketState.READY_FOR_AGENT),
        (TicketState.DONE, TicketState.FAILED),
        (TicketState.DONE, TicketState.IN_REVIEW),
        # Blocked doesn't go directly to Done; Sebas's answer routes back through the workflow.
        (TicketState.BLOCKED, TicketState.DONE),
        # Self-loops aren't transitions.
        (TicketState.IN_PROGRESS, TicketState.IN_PROGRESS),
    ],
)
def test_invalid_transitions(src: TicketState, dst: TicketState) -> None:
    assert not can_transition(src, dst), f"{src.value} → {dst.value} should be rejected"
    with pytest.raises(InvalidTransitionError):
        assert_can_transition(src, dst)


def test_invalid_transition_error_carries_src_and_dst() -> None:
    err: InvalidTransitionError | None = None
    try:
        assert_can_transition(TicketState.DONE, TicketState.IN_PROGRESS)
    except InvalidTransitionError as e:
        err = e
    assert err is not None
    assert err.src == TicketState.DONE
    assert err.dst == TicketState.IN_PROGRESS
    # Message contains both state names so logs are self-explanatory.
    assert "Done" in str(err)
    assert "In Progress" in str(err)


def test_terminal_states_only_contains_done() -> None:
    assert terminal_states() == frozenset({TicketState.DONE})


def test_inflight_states_excludes_done_and_failed() -> None:
    """In-flight = every unfinished state; Done and Failed are not in flight."""
    inflight = inflight_states()
    assert TicketState.DONE not in inflight
    assert TicketState.FAILED not in inflight
    # Stories that advanced past Backlog are still unfinished work.
    assert inflight == frozenset(
        {
            TicketState.BACKLOG,
            TicketState.SPEC_DRAFT,
            TicketState.READY_FOR_AGENT,
            TicketState.IN_PROGRESS,
            TicketState.BLOCKED,
            TicketState.IN_REVIEW,
            TicketState.READY_FOR_QA,
        }
    )


def test_actionable_states_match_recolector_contract() -> None:
    """The recolector daemon polls Linear for these states, no others."""
    assert actionable_states() == frozenset(
        {
            TicketState.SPEC_DRAFT,
            TicketState.READY_FOR_AGENT,
            TicketState.IN_REVIEW,
            TicketState.READY_FOR_QA,
        }
    )


def test_every_state_appears_in_transition_table() -> None:
    """If a Linear state is documented but missing from the table, that's a bug."""
    missing = [s for s in TicketState if s not in ALLOWED_TRANSITIONS]
    assert not missing, f"missing entries in ALLOWED_TRANSITIONS: {missing}"


def test_no_transition_targets_an_unknown_state() -> None:
    """Sanity check: every dst is a valid TicketState (no typos in the table)."""
    for src, dests in ALLOWED_TRANSITIONS.items():
        for dst in dests:
            assert isinstance(dst, TicketState), (
                f"{src.value} has invalid destination: {dst!r}"
            )


def test_state_string_values_match_linear_names_exactly() -> None:
    """Linear is case-sensitive; this asserts the exact strings the team uses."""
    expected = {
        "Backlog",
        "Spec Draft",
        "Ready for Agent",
        "In Progress",
        "Blocked",
        "In Review",
        "Ready for QA",
        "Failed",
        "Done",
    }
    assert {s.value for s in TicketState} == expected
