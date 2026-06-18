"""Tests for the :class:`RouteStepRef` value object (GP-011)."""

from __future__ import annotations

import dataclasses

import pytest

from apps.wip.domain.exceptions import InvalidRouteStepRefError, WipDomainError
from apps.wip.domain.route_step_ref import RouteStepRef


def test_route_step_ref_references_order_step_by_id() -> None:
    # AC-4: RouteStepRef referencia el paso de ruta de una OF por identificadores.
    ref = RouteStepRef(order_id="OF-001", route_step_id="step-10")
    assert ref.order_id == "OF-001"
    assert ref.route_step_id == "step-10"


def test_route_step_ref_with_blank_identifier_raises_wip_domain_error() -> None:
    # AC-6: identificadores inválidos lanzan WipDomainError, nunca ValueError.
    with pytest.raises(WipDomainError):
        RouteStepRef(order_id="", route_step_id="step-10")
    with pytest.raises(InvalidRouteStepRefError):
        RouteStepRef(order_id="OF-001", route_step_id="   ")


def test_route_step_ref_is_immutable() -> None:
    # AC-4: es inmutable (frozen value object).
    ref = RouteStepRef(order_id="OF-001", route_step_id="step-10")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.order_id = "OF-002"  # type: ignore[misc]  # frozen dataclass


def test_route_step_ref_equality_is_by_value() -> None:
    # AC-4: con igualdad por valor.
    a = RouteStepRef(order_id="OF-001", route_step_id="step-10")
    b = RouteStepRef(order_id="OF-001", route_step_id="step-10")
    c = RouteStepRef(order_id="OF-001", route_step_id="step-20")
    assert a == b
    assert a != c
    assert hash(a) == hash(b)
