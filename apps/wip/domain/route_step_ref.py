"""The :class:`RouteStepRef` value object.

A ``RouteStepRef`` identifies one step of a manufacturing order's route by
**identifier only** — the owning order's id plus the route-step id. It never
imports ``apps/orders`` (cross-context isolation, ARCHITECTURE.md): WIP refers
to orders by value, and real balances are seeded later by consuming
``orders.events``, not by reaching into the orders context directly.

Immutable and compared by value.
"""

from __future__ import annotations

from dataclasses import dataclass

from .exceptions import InvalidRouteStepRefError


@dataclass(frozen=True)
class RouteStepRef:
    """A by-id reference to a manufacturing order's route step.

    :param order_id: identifier of the owning manufacturing order.
    :param route_step_id: identifier of the route step within that order.
    """

    order_id: str
    route_step_id: str

    def __post_init__(self) -> None:
        self._require_non_blank("order_id", self.order_id)
        self._require_non_blank("route_step_id", self.route_step_id)

    @staticmethod
    def _require_non_blank(field_name: str, value: str) -> None:
        if not isinstance(value, str):
            raise InvalidRouteStepRefError(
                f"{field_name} must be a str, got {type(value).__name__}"
            )
        if not value.strip():
            raise InvalidRouteStepRefError(f"{field_name} must not be blank")
