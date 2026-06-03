"""The lifecycle states of a manufacturing order (GP-010).

States are modelled as a :class:`enum.StrEnum` so the rest of the codebase
compares against members (``OrderStatus.RELEASED``) rather than bare string
literals, which typo silently and are not refactor-safe.
"""

from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    """Lifecycle state of a :class:`ManufacturingOrder`.

    The only legal progression is the linear lifecycle enforced by
    :mod:`apps.orders.domain.state_machine`::

        draft -> released -> in_progress -> completed -> closed
    """

    DRAFT = "draft"
    RELEASED = "released"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"
