"""Tests for the :class:`WipBalance` entity (GP-011)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from apps.wip.domain.exceptions import InvalidWipBalanceError, WipDomainError
from apps.wip.domain.quantity import Quantity
from apps.wip.domain.route_step_ref import RouteStepRef
from apps.wip.domain.wip_balance import WipBalance


def _ref() -> RouteStepRef:
    return RouteStepRef(order_id="OF-001", route_step_id="step-10")


def test_wip_balance_is_identified_by_route_step_and_exposes_in_process() -> None:
    # AC-5: WipBalance identificada por su RouteStepRef y expone el balance en proceso.
    balance = WipBalance(route_step=_ref(), in_process=Quantity.of(7))
    assert balance.route_step == _ref()
    assert balance.in_process == Quantity.of(7)


def test_wip_balance_built_with_non_negative_quantity() -> None:
    # AC-5: construible con cantidades no negativas (Quantity).
    empty = WipBalance.empty(_ref())
    assert empty.in_process == Quantity.zero()
    assert empty.is_empty is True
    assert WipBalance(route_step=_ref(), in_process=Quantity.of(2)).is_empty is False


def test_wip_balance_with_negative_quantity_raises_wip_domain_error() -> None:
    # AC-5: construirla con datos inválidos lanza WipDomainError (cantidad negativa).
    with pytest.raises(WipDomainError):
        WipBalance(route_step=_ref(), in_process=Quantity(Decimal("-1")))


def test_wip_balance_with_wrong_types_raises_wip_domain_error() -> None:
    # AC-6: datos inválidos producen WipDomainError, no built-ins.
    with pytest.raises(InvalidWipBalanceError):
        WipBalance(route_step="OF-001", in_process=Quantity.zero())  # type: ignore[arg-type]
    with pytest.raises(InvalidWipBalanceError):
        WipBalance(route_step=_ref(), in_process=Decimal("1"))  # type: ignore[arg-type]


def test_wip_balance_is_immutable() -> None:
    # AC-5: la entidad es inmutable (frozen); las mutaciones llegan en NSG-34.
    balance = WipBalance.empty(_ref())
    with pytest.raises(dataclasses.FrozenInstanceError):
        balance.in_process = Quantity.of(1)  # type: ignore[misc]  # frozen dataclass
