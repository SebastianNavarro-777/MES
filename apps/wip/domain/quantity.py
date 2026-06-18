"""The :class:`Quantity` value object.

A ``Quantity`` is a **non-negative** amount of product in process. Work in
process can be discrete (pieces) or fractional (kg, m), so the amount is stored
as :class:`decimal.Decimal` — never ``float`` — to avoid the silent precision
errors that ``float`` arithmetic accumulates (the spirit of GP-002).

The value object is immutable and compares by value. Stock-movement arithmetic
(input / output / scrap) is intentionally **out of scope** for the skeleton
story (NSG-33); it arrives with the balance invariants in NSG-34.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .exceptions import InvalidQuantityError


@dataclass(frozen=True)
class Quantity:
    """An immutable, non-negative amount of work in process.

    Construct directly from a :class:`~decimal.Decimal` (``Quantity(Decimal("3"))``)
    or, more ergonomically and from a wider set of inputs, via :meth:`of`.
    """

    value: Decimal

    def __post_init__(self) -> None:
        value = self.value
        if not isinstance(value, Decimal):
            raise InvalidQuantityError(
                f"quantity must be a Decimal, got {type(value).__name__}"
            )
        if not value.is_finite():
            raise InvalidQuantityError(f"quantity must be a finite number, got {value!r}")
        if value < Decimal(0):
            raise InvalidQuantityError(f"quantity must be non-negative, got {value!r}")

    @classmethod
    def of(cls, value: Decimal | int | str) -> Quantity:
        """Build a ``Quantity`` from a ``Decimal``, ``int`` or decimal ``str``.

        ``float`` is rejected on purpose: feeding binary floating point into a
        decimal amount reintroduces the precision errors this value object
        exists to prevent.
        """
        if isinstance(value, bool):
            raise InvalidQuantityError("quantity cannot be built from a bool")
        if isinstance(value, float):
            raise InvalidQuantityError(
                "quantity cannot be built from a float; use Decimal or str (GP-002)"
            )
        try:
            decimal_value = Decimal(value)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise InvalidQuantityError(f"cannot build a quantity from {value!r}") from exc
        return cls(decimal_value)

    @classmethod
    def zero(cls) -> Quantity:
        """The empty quantity (``0``)."""
        return cls(Decimal(0))
