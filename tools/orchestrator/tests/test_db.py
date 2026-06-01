"""Tests for the SQLite wrapper.

Focused on the contracts that other daemons rely on for correctness —
specifically the dedup semantics of ``record_learning_event_once``,
which the recolector uses on every poll to avoid inflating the Gardener's
learning counter.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.orchestrator.orchestrator.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


# ---------------------------------------------------------------------------
# record_learning_event_once
# ---------------------------------------------------------------------------


def test_record_learning_event_once_inserts_when_table_empty(db: Database) -> None:
    row_id = db.record_learning_event_once("default_decision_applied", "NSG-42")
    assert row_id > 0
    rows = db.list_learning_events()
    assert len(rows) == 1
    assert rows[0].event_type == "default_decision_applied"
    assert rows[0].ticket_id == "NSG-42"
    assert rows[0].consumed_by_gardener is False


def test_record_learning_event_once_dedups_unconsumed_duplicate(db: Database) -> None:
    first = db.record_learning_event_once("default_decision_applied", "NSG-42")
    second = db.record_learning_event_once("default_decision_applied", "NSG-42")
    third = db.record_learning_event_once("default_decision_applied", "NSG-42")
    assert first > 0
    assert second == 0  # dedup → 0 means "not inserted"
    assert third == 0
    rows = db.list_learning_events()
    assert len(rows) == 1


def test_record_learning_event_once_inserts_again_after_consumption(
    db: Database,
) -> None:
    """Once the Gardener consumes an event, the recolector may legitimately
    re-emit the same (event_type, ticket_id) — circumstances may have
    changed between Gardener cycles."""
    first = db.record_learning_event_once("default_decision_applied", "NSG-42")
    db.mark_learning_events_consumed([first])
    second = db.record_learning_event_once("default_decision_applied", "NSG-42")
    assert second > 0
    assert second != first
    rows = db.list_learning_events()
    assert len(rows) == 2
    # Original consumed, new one unconsumed
    consumed_flags = sorted(r.consumed_by_gardener for r in rows)
    assert consumed_flags == [False, True]


def test_record_learning_event_once_different_event_types_dont_collide(
    db: Database,
) -> None:
    """Same ticket can legitimately produce multiple unconsumed events
    if they're of different types (e.g., a ticket failed AND a default
    decision was applied to it)."""
    a = db.record_learning_event_once("ticket_failed", "NSG-42")
    b = db.record_learning_event_once("default_decision_applied", "NSG-42")
    assert a > 0
    assert b > 0
    assert a != b
    rows = db.list_learning_events()
    assert len(rows) == 2


def test_record_learning_event_once_different_tickets_dont_collide(
    db: Database,
) -> None:
    a = db.record_learning_event_once("default_decision_applied", "NSG-42")
    b = db.record_learning_event_once("default_decision_applied", "NSG-43")
    assert a > 0
    assert b > 0
    rows = db.list_learning_events()
    assert len(rows) == 2


# Sanity: the *non*-idempotent record_learning_event still inserts duplicates.
# This is the behaviour the worker.py path relies on (one failure = one event),
# so we lock it in to prevent silent regressions if someone "fixes" it.
def test_record_learning_event_remains_non_idempotent(db: Database) -> None:
    a = db.record_learning_event("ticket_failed", "NSG-42")
    b = db.record_learning_event("ticket_failed", "NSG-42")
    assert a > 0
    assert b > 0
    assert a != b
    assert len(db.list_learning_events()) == 2
