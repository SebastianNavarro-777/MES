"""Tests for the orders state-machine helper.

Exhaustively pins the legal lifecycle and rejects every illegal move.
"""

from __future__ import annotations

import pytest

from apps.orders.domain.exceptions import InvalidOrderStateTransition, OrdersDomainError
from apps.orders.domain.order_status import OrderStatus
from apps.orders.domain.state_machine import assert_can_transition, can_transition

_LEGAL_TRANSITIONS = [
    (OrderStatus.DRAFT, OrderStatus.RELEASED),
    (OrderStatus.RELEASED, OrderStatus.IN_PROGRESS),
    (OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED),
    (OrderStatus.COMPLETED, OrderStatus.CLOSED),
]


@pytest.mark.parametrize(("current", "target"), _LEGAL_TRANSITIONS)
def test_legal_linear_transitions_are_allowed(
    current: OrderStatus, target: OrderStatus
) -> None:
    # AC-5: el helper permite únicamente las transiciones
    # draft -> released -> in_progress -> completed -> closed.
    assert can_transition(current, target) is True
    assert_can_transition(current, target)  # does not raise


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (OrderStatus.DRAFT, OrderStatus.COMPLETED),  # skipping states
        (OrderStatus.DRAFT, OrderStatus.IN_PROGRESS),
        (OrderStatus.RELEASED, OrderStatus.DRAFT),  # backwards
        (OrderStatus.COMPLETED, OrderStatus.RELEASED),
        (OrderStatus.CLOSED, OrderStatus.COMPLETED),  # leaving terminal state
        (OrderStatus.DRAFT, OrderStatus.DRAFT),  # no-op is not a transition
    ],
)
def test_illegal_transitions_raise_domain_error(
    current: OrderStatus, target: OrderStatus
) -> None:
    # AC-5: rechaza cualquier otra transición (salto o salto hacia atrás) con una
    # excepción específica del dominio.
    assert can_transition(current, target) is False
    with pytest.raises(InvalidOrderStateTransition) as exc_info:
        assert_can_transition(current, target)
    assert isinstance(exc_info.value, OrdersDomainError)
    assert exc_info.value.current is current
    assert exc_info.value.target is target
