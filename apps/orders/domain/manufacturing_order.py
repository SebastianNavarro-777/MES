"""The :class:`ManufacturingOrder` domain entity (the OF).

Pure Python, stdlib only (GP-001). The entity is an immutable frozen dataclass:
state transitions return a *new* instance rather than mutating in place, which
makes accidental shared-state bugs surface immediately. All invariants are
enforced at construction; transitions are delegated to the state-machine helper.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from .exceptions import (
    InvalidOrderQuantity,
    MissingOrderProduct,
    MissingOrderRoute,
    NaiveDueDate,
)
from .order_status import OrderStatus
from .state_machine import assert_can_transition


def _new_internal_id() -> str:
    """Generate a fresh internal surrogate identifier for an order.

    The OF is identified by a system-assigned surrogate, independent of any
    external system. The *external* identifier (e.g. an ERP key) is a deferred,
    irreversible schema decision tracked in NSG-44 and will be added later as an
    additive, nullable field — never baked in as the primary key here.
    """
    return uuid.uuid4().hex


@dataclass(frozen=True)
class ManufacturingOrder:
    """A manufacturing order (orden de fabricación / OF).

    Construct one with a product, a positive quantity, a route and a
    timezone-aware UTC commitment date. A freshly built order starts in
    :attr:`OrderStatus.DRAFT` and is assigned a unique internal :attr:`id`.
    """

    product_id: str
    quantity: int
    route_id: str
    due_date: datetime
    status: OrderStatus = OrderStatus.DRAFT
    id: str = field(default_factory=_new_internal_id)

    def __post_init__(self) -> None:
        if not self.product_id:
            raise MissingOrderProduct()
        if not self.route_id:
            raise MissingOrderRoute()
        if self.quantity <= 0:
            raise InvalidOrderQuantity(self.quantity)
        if self.due_date.tzinfo is None or self.due_date.utcoffset() is None:
            raise NaiveDueDate()
        # Normalise any timezone-aware datetime to UTC so the invariant
        # "every datetime on the OF is UTC" holds regardless of input zone
        # (GP-003). Frozen dataclasses require object.__setattr__ to mutate.
        object.__setattr__(self, "due_date", self.due_date.astimezone(UTC))

    def transition_to(self, target: OrderStatus) -> ManufacturingOrder:
        """Return a copy of this order in ``target`` state.

        Raises :class:`InvalidOrderStateTransition` if the move is not part of
        the linear lifecycle.
        """
        assert_can_transition(self.status, target)
        return replace(self, status=target)
