"""Tests for the WipUpdated domain event (the published contract)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.wip.domain.balance import WipBalance, WipMovement
from apps.wip.domain.events import (
    EVENT_NAME,
    SCHEMA_VERSION,
    WipUpdated,
    derive_event_id,
)
from apps.wip.domain.exceptions import InvalidWipEventError
from apps.wip.domain.movement_type import WipMovementType

_NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def _movement(movement_id: str = "MOV-1", qty: int = 4) -> WipMovement:
    return WipMovement(
        movement_id=movement_id,
        order_id="OF-1",
        route_step_id="STEP-10",
        movement_type=WipMovementType.IN,
        qty=qty,
        occurred_at=_NOW,
    )


def test_from_movement_carries_order_step_balance_movement_and_timestamp() -> None:
    # AC-2: the event includes the order id, route step, resulting balance
    # (qty_in/out/scrap), the movement type and magnitude, and occurred_at.
    movement = _movement(qty=4)
    balance = WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=4)
    event = WipUpdated.from_movement(movement, balance)

    assert event.order_id == "OF-1"
    assert event.route_step_id == "STEP-10"
    assert (event.qty_in, event.qty_out, event.qty_scrap) == (4, 0, 0)
    assert event.movement_type is WipMovementType.IN
    assert event.movement_qty == 4
    assert event.occurred_at == _NOW
    assert event.occurred_at.tzinfo is not None  # GP-003: timezone-aware


def test_event_carries_schema_version_starting_at_one() -> None:
    # AC-3: the event exposes an integer schema_version starting at 1.
    event = WipUpdated.from_movement(
        _movement(), WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=4)
    )
    assert event.schema_version == 1
    assert SCHEMA_VERSION == 1
    assert EVENT_NAME == "wip.updated"


def test_event_id_is_stable_and_derived_from_movement() -> None:
    # AC-6: event_id is unique and stable, derived from the originating movement,
    # so a consumer can de-duplicate retries.
    balance = WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=4)
    first = WipUpdated.from_movement(_movement("MOV-42"), balance)
    retry = WipUpdated.from_movement(_movement("MOV-42"), balance)
    other = WipUpdated.from_movement(_movement("MOV-99"), balance)

    assert first.event_id == retry.event_id == derive_event_id("MOV-42")
    assert first.event_id != other.event_id


def test_event_with_naive_datetime_raises() -> None:
    # GP-003: a naive occurred_at is rejected by the event constructor.
    with pytest.raises(InvalidWipEventError):
        WipUpdated(
            event_id="e1",
            schema_version=SCHEMA_VERSION,
            order_id="OF-1",
            route_step_id="STEP-10",
            qty_in=1,
            qty_out=0,
            qty_scrap=0,
            movement_type=WipMovementType.IN,
            movement_qty=1,
            occurred_at=datetime(2026, 6, 2, 12, 0),  # intentionally naive
        )


def test_event_with_zero_schema_version_raises() -> None:
    with pytest.raises(InvalidWipEventError):
        WipUpdated(
            event_id="e1",
            schema_version=0,
            order_id="OF-1",
            route_step_id="STEP-10",
            qty_in=1,
            qty_out=0,
            qty_scrap=0,
            movement_type=WipMovementType.IN,
            movement_qty=1,
            occurred_at=_NOW,
        )
