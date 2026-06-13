"""Domain exceptions for the orders bounded context (GP-012).

Every error raised from `apps/orders/domain/` or `apps/orders/application/`
subclasses :class:`OrdersDomainError`, so the application and interface layers
can translate them into precise event types and HTTP status codes. Domain code
never raises bare built-ins such as ``ValueError`` or ``RuntimeError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .order_status import OrderStatus


class OrdersDomainError(Exception):
    """Base class for every error raised inside the orders bounded context."""


class InvalidOrderQuantity(OrdersDomainError):
    """Raised when a manufacturing order is built with a non-positive quantity."""

    def __init__(self, quantity: int) -> None:
        super().__init__(
            f"order quantity must be a positive integer; got {quantity!r}"
        )
        self.quantity = quantity


class MissingOrderProduct(OrdersDomainError):
    """Raised when a manufacturing order is built without a product."""

    def __init__(self) -> None:
        super().__init__(
            "a manufacturing order requires a non-empty product identifier"
        )


class MissingOrderRoute(OrdersDomainError):
    """Raised when a manufacturing order is built without a route."""

    def __init__(self) -> None:
        super().__init__(
            "a manufacturing order requires a non-empty route identifier"
        )


class NaiveDueDate(OrdersDomainError):
    """Raised when a manufacturing order's due date is a naive datetime (GP-003)."""

    def __init__(self) -> None:
        super().__init__(
            "due_date must be a timezone-aware UTC datetime; a naive value was given"
        )


class InvalidOrderStateTransition(OrdersDomainError):
    """Raised when the state machine rejects a status transition (GP-010)."""

    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        super().__init__(
            f"cannot transition order from {current.value!r} to {target.value!r}"
        )
        self.current = current
        self.target = target
