"""Tests for the :class:`Quantity` value object (GP-011)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from apps.wip.domain.exceptions import InvalidQuantityError, WipDomainError
from apps.wip.domain.quantity import Quantity


def test_quantity_accepts_non_negative_decimal() -> None:
    # AC-3: Existe el value object Quantity que representa una cantidad no negativa.
    assert Quantity(Decimal("3.5")).value == Decimal("3.5")
    assert Quantity.zero().value == Decimal(0)


def test_quantity_of_coerces_int_and_str_to_decimal() -> None:
    # AC-3: construir un Quantity con cantidades válidas (discretas o fraccionarias).
    assert Quantity.of(5).value == Decimal(5)
    assert Quantity.of("2.250").value == Decimal("2.250")
    assert isinstance(Quantity.of(5).value, Decimal)


def test_quantity_with_negative_value_raises_wip_domain_error() -> None:
    # AC-3: construirlo con un valor negativo lanza WipDomainError.
    with pytest.raises(WipDomainError):
        Quantity(Decimal("-1"))
    with pytest.raises(InvalidQuantityError):
        Quantity.of("-0.001")


def test_quantity_rejects_float_to_protect_precision() -> None:
    # AC-6: el dominio de wip nunca lanza built-ins; rechaza float con WipDomainError.
    with pytest.raises(WipDomainError):
        Quantity.of(1.1)  # type: ignore[arg-type]  # intentional: float is rejected at runtime


def test_quantity_rejects_non_decimal_value() -> None:
    # AC-6: datos inválidos producen WipDomainError, no ValueError/TypeError.
    with pytest.raises(WipDomainError):
        Quantity.of("not-a-number")


def test_quantity_is_immutable() -> None:
    # AC-3: es inmutable (frozen value object).
    qty = Quantity(Decimal("1"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        qty.value = Decimal("2")  # type: ignore[misc]  # frozen dataclass


def test_quantity_equality_is_by_value() -> None:
    # AC-3: dos Quantity con el mismo valor son iguales (igualdad por valor).
    assert Quantity(Decimal("4")) == Quantity(Decimal("4"))
    assert Quantity(Decimal("4")) == Quantity.of(4)
    assert Quantity(Decimal("4")) != Quantity(Decimal("5"))
    assert hash(Quantity(Decimal("4"))) == hash(Quantity.of(4))
