"""Domain exceptions for the wip bounded context (GP-012).

Every error raised from ``apps/wip/domain`` (and later ``application``) is a
subclass of :class:`WipDomainError`. Domain code never raises stdlib built-ins
such as ``ValueError`` or ``RuntimeError`` — a context-specific exception lets
the interface layer translate failures into precise HTTP problem documents.
"""

from __future__ import annotations


class WipDomainError(Exception):
    """Base class for every error raised inside the wip bounded context."""


class InvalidQuantityError(WipDomainError):
    """Raised when a :class:`~apps.wip.domain.quantity.Quantity` value is not a
    valid non-negative decimal amount."""


class InvalidRouteStepRefError(WipDomainError):
    """Raised when a :class:`~apps.wip.domain.route_step_ref.RouteStepRef` is
    built with missing or blank identifiers."""


class InvalidWipBalanceError(WipDomainError):
    """Raised when a :class:`~apps.wip.domain.wip_balance.WipBalance` is built
    with inconsistent or wrongly typed data."""
