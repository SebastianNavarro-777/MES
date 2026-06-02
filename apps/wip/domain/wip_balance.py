"""The :class:`WipBalance` entity.

A ``WipBalance`` is the amount of product currently *in process* at one route
step of one manufacturing order. It is identified by its :class:`RouteStepRef`
and holds a non-negative :class:`Quantity`.

WIP is mutable stock — GP-005 (append-only immutability) deliberately does
**not** apply here; that constraint belongs to ``apps/traceability``. The
skeleton story (NSG-33) only models construction and the read-side balance.
Stock-movement operations (input / output / scrap) and the "never negative"
movement invariant arrive in NSG-34.
"""

from __future__ import annotations

from dataclasses import dataclass

from .exceptions import InvalidWipBalanceError
from .quantity import Quantity
from .route_step_ref import RouteStepRef


@dataclass(frozen=True)
class WipBalance:
    """Work-in-process balance for a single order route step.

    :param route_step: the route step this balance belongs to (its identity).
    :param in_process: the current non-negative quantity in process.
    """

    route_step: RouteStepRef
    in_process: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.route_step, RouteStepRef):
            raise InvalidWipBalanceError(
                f"route_step must be a RouteStepRef, got {type(self.route_step).__name__}"
            )
        if not isinstance(self.in_process, Quantity):
            raise InvalidWipBalanceError(
                f"in_process must be a Quantity, got {type(self.in_process).__name__}"
            )

    @classmethod
    def empty(cls, route_step: RouteStepRef) -> WipBalance:
        """A balance for ``route_step`` with nothing in process yet."""
        return cls(route_step=route_step, in_process=Quantity.zero())

    @property
    def is_empty(self) -> bool:
        """Whether there is currently nothing in process at this step."""
        return self.in_process == Quantity.zero()
