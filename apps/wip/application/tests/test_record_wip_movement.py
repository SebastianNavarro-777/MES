"""Tests for the record_wip_movement use case (persist-then-publish ordering)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.wip.application.record_wip_movement import record_wip_movement
from apps.wip.domain.balance import WipBalance, WipMovement
from apps.wip.domain.events import WipUpdated, derive_event_id
from apps.wip.domain.exceptions import WipBalanceError
from apps.wip.domain.movement_type import WipMovementType

_NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


class FakeBalanceRepository:
    """In-memory WipBalanceRepository (fakes over mocks)."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], WipBalance] = {}
        self.saves: list[WipBalance] = []

    def get(self, order_id: str, route_step_id: str) -> WipBalance | None:
        return self._store.get((order_id, route_step_id))

    def save(self, balance: WipBalance) -> None:
        self._store[(balance.order_id, balance.route_step_id)] = balance
        self.saves.append(balance)

    def seed(self, balance: WipBalance) -> None:
        self._store[(balance.order_id, balance.route_step_id)] = balance


class FakeEventPublisher:
    def __init__(self) -> None:
        self.published: list[WipUpdated] = []

    def publish(self, event: WipUpdated) -> None:
        self.published.append(event)


def _movement(
    movement_type: WipMovementType,
    qty: int,
    *,
    movement_id: str = "MOV-1",
) -> WipMovement:
    return WipMovement(
        movement_id=movement_id,
        order_id="OF-1",
        route_step_id="STEP-10",
        movement_type=movement_type,
        qty=qty,
        occurred_at=_NOW,
    )


def test_successful_movement_publishes_exactly_one_event() -> None:
    # AC-1: each balance change publishes exactly one wip.updated event.
    repo = FakeBalanceRepository()
    publisher = FakeEventPublisher()

    event = record_wip_movement(_movement(WipMovementType.IN, 7), repo=repo, publisher=publisher)

    assert len(publisher.published) == 1
    assert publisher.published[0] is event
    assert event.qty_in == 7
    assert event.event_id == derive_event_id("MOV-1")
    assert repo.saves[-1].qty_in == 7  # persisted before publish


def test_persist_happens_before_publish() -> None:
    # AC-1 / AC-4: the balance is saved first; the event reflects the saved state.
    repo = FakeBalanceRepository()
    repo.seed(WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=10))
    publisher = FakeEventPublisher()

    event = record_wip_movement(_movement(WipMovementType.OUT, 4), repo=repo, publisher=publisher)

    assert repo.get("OF-1", "STEP-10") == WipBalance(
        order_id="OF-1", route_step_id="STEP-10", qty_in=10, qty_out=4
    )
    assert (event.qty_in, event.qty_out) == (10, 4)
    assert event.movement_type is WipMovementType.OUT


def test_failed_movement_publishes_nothing_and_persists_nothing() -> None:
    # AC-4: if recording the movement fails (would go negative), no event is
    # published and nothing is persisted.
    repo = FakeBalanceRepository()
    repo.seed(WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=2))
    publisher = FakeEventPublisher()

    with pytest.raises(WipBalanceError):
        record_wip_movement(_movement(WipMovementType.OUT, 5), repo=repo, publisher=publisher)

    assert publisher.published == []
    assert repo.saves == []
