"""WIP balance value object and the movement that mutates it.

Pure domain logic: applying a movement returns a *new* balance instance and
enforces the invariant that the net in-process quantity can never go negative.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from .exceptions import WipBalanceError
from .movement_type import WipMovementType
from .timezones import ensure_utc


@dataclass(frozen=True)
class WipMovement:
    """A single in/out/scrap delta recorded at a route step of an order.

    ``movement_id`` is the stable identifier of the originating record (e.g. the
    ledger row primary key / idempotency key). It is what makes the emitted
    event's ``event_id`` stable and de-duplicable downstream (AC-6).
    """

    movement_id: str
    order_id: str
    route_step_id: str
    movement_type: WipMovementType
    qty: int
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.movement_id:
            raise WipBalanceError("movement_id must be a non-empty identifier")
        if self.qty <= 0:
            raise WipBalanceError(f"movement qty must be positive, got {self.qty}")
        ensure_utc(self.occurred_at, field="occurred_at", error=WipBalanceError)


@dataclass(frozen=True)
class WipBalance:
    """The in-process balance of a single (order, route step) pair.

    Quantities are non-negative integer unit counts. The net in-process amount
    is ``qty_in - qty_out - qty_scrap`` and must never be negative.
    """

    order_id: str
    route_step_id: str
    qty_in: int = 0
    qty_out: int = 0
    qty_scrap: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("qty_in", self.qty_in),
            ("qty_out", self.qty_out),
            ("qty_scrap", self.qty_scrap),
        ):
            if value < 0:
                raise WipBalanceError(f"{name} cannot be negative, got {value}")
        if self.net < 0:
            raise WipBalanceError(
                f"net balance cannot be negative (in={self.qty_in}, "
                f"out={self.qty_out}, scrap={self.qty_scrap})"
            )

    @property
    def net(self) -> int:
        """Units currently in process at this step."""
        return self.qty_in - self.qty_out - self.qty_scrap

    def apply(self, movement: WipMovement) -> WipBalance:
        """Return a new balance with ``movement`` applied.

        Raises ``WipBalanceError`` if the movement does not belong to this
        (order, route step) pair, or if it would drive the net balance negative.
        """
        if movement.order_id != self.order_id or movement.route_step_id != self.route_step_id:
            raise WipBalanceError(
                "movement does not match this balance "
                f"(balance={self.order_id}/{self.route_step_id}, "
                f"movement={movement.order_id}/{movement.route_step_id})"
            )

        if movement.movement_type is WipMovementType.IN:
            updated = replace(self, qty_in=self.qty_in + movement.qty)
        elif movement.movement_type is WipMovementType.OUT:
            updated = replace(self, qty_out=self.qty_out + movement.qty)
        else:  # WipMovementType.SCRAP
            updated = replace(self, qty_scrap=self.qty_scrap + movement.qty)

        # __post_init__ on the new instance re-checks the non-negative invariant.
        return updated
