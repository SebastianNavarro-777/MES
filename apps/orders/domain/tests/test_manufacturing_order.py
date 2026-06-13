"""Tests for the :class:`ManufacturingOrder` domain entity.

Covers construction, invariants, the internal identity and one state
transition. Each Acceptance Criterion from NSG-16 is referenced with an
``# AC-N:`` comment so the Reviewer can verify coverage cheaply.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from apps.orders.domain.exceptions import (
    InvalidOrderQuantity,
    MissingOrderProduct,
    MissingOrderRoute,
    NaiveDueDate,
    OrdersDomainError,
)
from apps.orders.domain.manufacturing_order import ManufacturingOrder
from apps.orders.domain.order_status import OrderStatus


def _valid_order(**overrides: object) -> ManufacturingOrder:
    """Build a valid order, overriding individual fields per test."""
    kwargs: dict[str, object] = {
        "product_id": "PROD-1",
        "quantity": 10,
        "route_id": "ROUTE-1",
        "due_date": datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return ManufacturingOrder(**kwargs)  # type: ignore[arg-type]


def test_valid_order_is_built_in_draft_state() -> None:
    # AC-2: Se puede construir una ManufacturingOrder válida (producto, cantidad,
    # ruta, fecha de compromiso) y queda en estado inicial `draft`.
    order = _valid_order()
    assert order.product_id == "PROD-1"
    assert order.quantity == 10
    assert order.route_id == "ROUTE-1"
    assert order.status is OrderStatus.DRAFT


def test_non_positive_quantity_is_rejected() -> None:
    # AC-3: cantidad <= 0 es rechazada con una excepción específica del dominio
    # (subclase de OrdersDomainError), nunca ValueError/RuntimeError.
    with pytest.raises(InvalidOrderQuantity) as exc_info:
        _valid_order(quantity=0)
    assert isinstance(exc_info.value, OrdersDomainError)
    with pytest.raises(InvalidOrderQuantity):
        _valid_order(quantity=-5)


def test_missing_product_or_route_is_rejected() -> None:
    # AC-3: sin producto o sin ruta es rechazado con una excepción específica
    # del dominio (subclase de OrdersDomainError).
    with pytest.raises(MissingOrderProduct) as product_exc:
        _valid_order(product_id="")
    assert isinstance(product_exc.value, OrdersDomainError)
    with pytest.raises(MissingOrderRoute) as route_exc:
        _valid_order(route_id="")
    assert isinstance(route_exc.value, OrdersDomainError)


def test_status_is_represented_with_the_enum() -> None:
    # AC-4: El estado se representa con el enum OrderStatus; no se compara contra
    # literales de string.
    order = _valid_order()
    assert isinstance(order.status, OrderStatus)
    assert order.status is OrderStatus.DRAFT
    assert {s.value for s in OrderStatus} == {
        "draft",
        "released",
        "in_progress",
        "completed",
        "closed",
    }


def test_released_transition_returns_new_released_order() -> None:
    # AC-5: el helper permite la transición draft -> released (caso feliz; la
    # malla completa de transiciones se prueba en test_state_machine.py).
    order = _valid_order()
    released = order.transition_to(OrderStatus.RELEASED)
    assert released.status is OrderStatus.RELEASED
    # Immutability: the original instance is untouched.
    assert order.status is OrderStatus.DRAFT
    assert released.id == order.id


def test_naive_due_date_is_rejected() -> None:
    # AC-6: pasar una datetime naive es rechazada en el borde de construcción.
    with pytest.raises(NaiveDueDate) as exc_info:
        _valid_order(due_date=datetime(2026, 7, 1, 12, 0))  # naive on purpose
    assert isinstance(exc_info.value, OrdersDomainError)


def test_aware_non_utc_due_date_is_normalised_to_utc() -> None:
    # AC-6: toda datetime de la OF queda timezone-aware en UTC.
    minus_six = timezone(timedelta(hours=-6))
    order = _valid_order(due_date=datetime(2026, 7, 1, 6, 0, tzinfo=minus_six))
    assert order.due_date.tzinfo is UTC
    assert order.due_date == datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def test_order_exposes_unique_system_assigned_internal_id() -> None:
    # AC-7: una OF recién construida expone un identificador interno único
    # asignado por el sistema, independiente de cualquier sistema externo.
    first = _valid_order()
    second = _valid_order()
    assert first.id
    assert isinstance(first.id, str)
    assert first.id != second.id
