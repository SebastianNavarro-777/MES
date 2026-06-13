"""Tests for the Recolector daemon.

The recolector mirrors Linear state into SQLite and emits learning
events that the Gardener consumes. These tests focus on the contract
the Gardener depends on:

* Every actionable-state ticket gets enqueued.
* ``applied-default-decision`` produces a ``default_decision_applied``
  learning event regardless of which state the ticket is in.
* ``harness-fix`` on a Done ticket produces a ``harness_fix_closed``
  learning event.
* Polling the same ticket multiple times never inflates the event count
  (idempotency via ``record_learning_event_once``).

A small fake ``LinearClient`` returns canned issue lists per state, so
the tests run fully offline.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from tools.orchestrator.orchestrator.db import Database
from tools.orchestrator.orchestrator.linear_client import Issue, LinearClient
from tools.orchestrator.orchestrator.recolector import Recolector

# ---------------------------------------------------------------------------
# Fake Linear client
# ---------------------------------------------------------------------------


class FakeLinearClient:
    """Stub with the minimal surface the recolector uses."""

    def __init__(self, issues_by_state: dict[str, list[Issue]]) -> None:
        self._issues = issues_by_state
        self.calls: list[str] = []

    async def list_issues_by_state(self, state: str) -> list[Issue]:
        self.calls.append(state)
        return list(self._issues.get(state, []))


def _issue(
    identifier: str,
    *,
    state: str = "Ready for Agent",
    labels: tuple[str, ...] = (),
) -> Issue:
    return Issue(
        id=f"uuid-{identifier}",
        identifier=identifier,
        title=f"Title for {identifier}",
        description="",
        state=state,
        labels=labels,
        parent_id=None,
    )


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


# ---------------------------------------------------------------------------
# Enqueue behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_actionable_tickets_get_enqueued(db: Database) -> None:
    fake = FakeLinearClient(
        {
            "Ready for Agent": [_issue("NSG-10", state="Ready for Agent")],
            "In Review": [_issue("NSG-11", state="In Review")],
        }
    )
    rec = Recolector(linear=cast(LinearClient, fake), db=db)
    await rec.tick()
    items = db.list_work_items()
    enqueued = sorted(i.ticket_id for i in items)
    assert enqueued == ["NSG-10", "NSG-11"]


@pytest.mark.asyncio
async def test_question_tickets_are_not_enqueued(db: Database) -> None:
    """A `needs-human-decision` Question has no code surface; enqueuing one
    lets a Worker dequeue it, find nothing to build, and churn it into Blocked
    (NSG-42/44). Even sitting in an actionable state, it must be skipped while
    real Stories in the same state are still enqueued."""
    fake = FakeLinearClient(
        {
            "Ready for Agent": [
                _issue("NSG-50", state="Ready for Agent", labels=("needs-human-decision",)),
                _issue(
                    "NSG-51",
                    state="Ready for Agent",
                    labels=("type:story", "module:orders"),
                ),
            ],
            "In Review": [
                _issue("NSG-52", state="In Review", labels=("needs-human-decision",)),
            ],
        }
    )
    rec = Recolector(linear=cast(LinearClient, fake), db=db)
    await rec.tick()
    enqueued = sorted(i.ticket_id for i in db.list_work_items())
    assert enqueued == ["NSG-51"]  # only the real Story, never the Questions


# ---------------------------------------------------------------------------
# applied-default-decision detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_decision_label_on_actionable_state_emits_event(
    db: Database,
) -> None:
    fake = FakeLinearClient(
        {
            "Ready for Agent": [
                _issue(
                    "NSG-20",
                    state="Ready for Agent",
                    labels=("type:story", "module:orders", "applied-default-decision"),
                )
            ],
        }
    )
    rec = Recolector(linear=cast(LinearClient, fake), db=db)
    await rec.tick()
    events = db.list_learning_events()
    assert len(events) == 1
    assert events[0].event_type == "default_decision_applied"
    assert events[0].ticket_id == "NSG-20"


@pytest.mark.asyncio
async def test_default_decision_label_on_done_emits_event(db: Database) -> None:
    fake = FakeLinearClient(
        {"Done": [_issue("NSG-21", state="Done", labels=("applied-default-decision",))]}
    )
    rec = Recolector(linear=cast(LinearClient, fake), db=db)
    await rec.tick()
    events = db.list_learning_events()
    assert len(events) == 1
    assert events[0].event_type == "default_decision_applied"
    assert events[0].ticket_id == "NSG-21"


@pytest.mark.asyncio
async def test_repeated_ticks_do_not_inflate_default_decision_events(
    db: Database,
) -> None:
    fake = FakeLinearClient(
        {
            "Ready for Agent": [
                _issue(
                    "NSG-22",
                    state="Ready for Agent",
                    labels=("applied-default-decision",),
                )
            ],
        }
    )
    rec = Recolector(linear=cast(LinearClient, fake), db=db)
    await rec.tick()
    await rec.tick()
    await rec.tick()
    events = db.list_learning_events()
    assert len(events) == 1  # idempotent across polls


@pytest.mark.asyncio
async def test_default_decision_re_emits_after_gardener_consumed(
    db: Database,
) -> None:
    """If the Gardener consumed the event but the label is still on the
    ticket on a later poll, a fresh event should be recorded — the
    recolector treats consumption as a reset."""
    fake = FakeLinearClient(
        {
            "Ready for Agent": [
                _issue(
                    "NSG-23",
                    state="Ready for Agent",
                    labels=("applied-default-decision",),
                )
            ],
        }
    )
    rec = Recolector(linear=cast(LinearClient, fake), db=db)
    await rec.tick()
    first = db.list_learning_events()
    db.mark_learning_events_consumed([e.id for e in first])
    await rec.tick()
    after = db.list_learning_events()
    assert len(after) == 2
    consumed_flags = sorted(e.consumed_by_gardener for e in after)
    assert consumed_flags == [False, True]


# ---------------------------------------------------------------------------
# harness-fix detection (regression: must use idempotent variant too)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_harness_fix_closed_emits_event_only_once(db: Database) -> None:
    fake = FakeLinearClient(
        {"Done": [_issue("NSG-30", state="Done", labels=("harness-fix",))]}
    )
    rec = Recolector(linear=cast(LinearClient, fake), db=db)
    await rec.tick()
    await rec.tick()
    events = db.list_learning_events()
    assert len(events) == 1
    assert events[0].event_type == "harness_fix_closed"
    assert events[0].ticket_id == "NSG-30"


# ---------------------------------------------------------------------------
# Label hygiene
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tickets_without_relevant_labels_emit_no_learning_events(
    db: Database,
) -> None:
    fake = FakeLinearClient(
        {
            "Ready for Agent": [
                _issue(
                    "NSG-40",
                    state="Ready for Agent",
                    labels=("type:story", "module:orders", "low-risk"),
                )
            ],
            "Done": [_issue("NSG-41", state="Done", labels=("type:story",))],
        }
    )
    rec = Recolector(linear=cast(LinearClient, fake), db=db)
    await rec.tick()
    assert db.list_learning_events() == []
