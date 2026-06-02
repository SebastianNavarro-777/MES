"""Tests for WipBalance and WipMovement domain logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from apps.wip.domain.balance import WipBalance, WipMovement
from apps.wip.domain.exceptions import WipBalanceError
from apps.wip.domain.movement_type import WipMovementType

_NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def _movement(
    movement_type: WipMovementType,
    qty: int,
    *,
    order_id: str = "OF-1",
    route_step_id: str = "STEP-10",
    movement_id: str = "MOV-1",
) -> WipMovement:
    return WipMovement(
        movement_id=movement_id,
        order_id=order_id,
        route_step_id=route_step_id,
        movement_type=movement_type,
        qty=qty,
        occurred_at=_NOW,
    )


def test_apply_in_increments_qty_in_and_returns_new_instance() -> None:
    balance = WipBalance(order_id="OF-1", route_step_id="STEP-10")
    updated = balance.apply(_movement(WipMovementType.IN, 5))
    assert (updated.qty_in, updated.qty_out, updated.qty_scrap) == (5, 0, 0)
    assert updated.net == 5
    assert balance.qty_in == 0  # original is unchanged (frozen)


def test_apply_out_and_scrap_reduce_net_balance() -> None:
    balance = WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=10)
    after_out = balance.apply(_movement(WipMovementType.OUT, 3))
    after_scrap = after_out.apply(_movement(WipMovementType.SCRAP, 2))
    assert (after_scrap.qty_in, after_scrap.qty_out, after_scrap.qty_scrap) == (10, 3, 2)
    assert after_scrap.net == 5


def test_apply_movement_that_would_go_negative_raises() -> None:
    # AC-4: a movement that would drive the net balance negative is rejected,
    # so the caller never reaches the publish step.
    balance = WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=2)
    with pytest.raises(WipBalanceError):
        balance.apply(_movement(WipMovementType.OUT, 5))


def test_apply_movement_for_other_step_raises() -> None:
    balance = WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=5)
    with pytest.raises(WipBalanceError):
        balance.apply(_movement(WipMovementType.OUT, 1, route_step_id="STEP-99"))


def test_movement_with_non_positive_qty_raises() -> None:
    with pytest.raises(WipBalanceError):
        _movement(WipMovementType.IN, 0)


def test_movement_with_naive_datetime_raises() -> None:
    # GP-003: naive datetimes are rejected at the domain boundary.
    with pytest.raises(WipBalanceError):
        WipMovement(
            movement_id="MOV-1",
            order_id="OF-1",
            route_step_id="STEP-10",
            movement_type=WipMovementType.IN,
            qty=1,
            occurred_at=datetime(2026, 6, 2, 12, 0),  # intentionally naive
        )


def test_movement_with_non_utc_datetime_raises() -> None:
    # GP-003: aware-but-not-UTC datetimes are also rejected.
    with pytest.raises(WipBalanceError):
        WipMovement(
            movement_id="MOV-1",
            order_id="OF-1",
            route_step_id="STEP-10",
            movement_type=WipMovementType.IN,
            qty=1,
            occurred_at=datetime(2026, 6, 2, 12, 0, tzinfo=timezone(timedelta(hours=2))),
        )


def test_balance_constructed_negative_raises() -> None:
    with pytest.raises(WipBalanceError):
        WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=1, qty_out=5)
