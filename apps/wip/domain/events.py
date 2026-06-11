"""The ``wip.updated`` domain event.

Pure Python value object (GP-001): no Redis, no Django, no third-party imports.
Serialization to the ``wip.events`` stream payload lives exclusively in
``apps/wip/infrastructure/`` (AC-5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from .balance import WipBalance, WipMovement
from .exceptions import InvalidWipEventError
from .movement_type import WipMovementType
from .timezones import ensure_utc

#: Logical name of the event on the bus.
EVENT_NAME = "wip.updated"

#: Current contract version. Incremented only on incompatible changes (AC-3).
SCHEMA_VERSION = 1

#: Fixed namespace used to derive a stable ``event_id`` from a movement id.
#: Constant on purpose: the same originating movement always yields the same
#: event_id, which is what lets consumers de-duplicate retries (AC-6).
_WIP_EVENT_NAMESPACE = uuid.UUID("6f9b8d2e-1c47-4a3e-9b21-0d5f7c8a4e10")


def derive_event_id(movement_id: str) -> str:
    """Deterministically derive a stable event id from the movement id (AC-6)."""
    if not movement_id:
        raise InvalidWipEventError("movement_id must be a non-empty identifier")
    return str(uuid.uuid5(_WIP_EVENT_NAMESPACE, movement_id))


@dataclass(frozen=True)
class WipUpdated:
    """Emitted exactly once whenever a WIP balance changes (AC-1).

    Carries the resulting balance plus the movement that caused it, so a
    consumer can rebuild a read model without calling back into ``wip``.
    """

    event_id: str
    schema_version: int
    order_id: str
    route_step_id: str
    qty_in: int
    qty_out: int
    qty_scrap: int
    movement_type: WipMovementType
    movement_qty: int
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.event_id:
            raise InvalidWipEventError("event_id must be a non-empty identifier")
        if self.schema_version < 1:
            raise InvalidWipEventError(
                f"schema_version must be >= 1, got {self.schema_version}"
            )
        if self.movement_qty <= 0:
            raise InvalidWipEventError(
                f"movement_qty must be positive, got {self.movement_qty}"
            )
        for name, value in (
            ("qty_in", self.qty_in),
            ("qty_out", self.qty_out),
            ("qty_scrap", self.qty_scrap),
        ):
            if value < 0:
                raise InvalidWipEventError(f"{name} cannot be negative, got {value}")
        ensure_utc(self.occurred_at, field="occurred_at", error=InvalidWipEventError)

    @classmethod
    def from_movement(cls, movement: WipMovement, resulting_balance: WipBalance) -> WipUpdated:
        """Build the event from the originating movement and the new balance.

        The ``event_id`` is derived from ``movement.movement_id`` so retries of
        the same movement produce an identical, de-duplicable event (AC-6).
        """
        return cls(
            event_id=derive_event_id(movement.movement_id),
            schema_version=SCHEMA_VERSION,
            order_id=resulting_balance.order_id,
            route_step_id=resulting_balance.route_step_id,
            qty_in=resulting_balance.qty_in,
            qty_out=resulting_balance.qty_out,
            qty_scrap=resulting_balance.qty_scrap,
            movement_type=movement.movement_type,
            movement_qty=movement.qty,
            occurred_at=movement.occurred_at,
        )
