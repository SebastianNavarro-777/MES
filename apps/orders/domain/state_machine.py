"""State-machine helper for manufacturing-order status transitions.

The manufacturing-order lifecycle is strictly linear::

    draft -> released -> in_progress -> completed -> closed

Any other move — skipping a state (``draft -> completed``), going backwards
(``released -> draft``) or leaving the terminal ``closed`` state — is rejected
with :class:`InvalidOrderStateTransition`. Keeping the allowed graph here, in
one place, means every caller shares the same definition of "legal".
"""

from __future__ import annotations

from .exceptions import InvalidOrderStateTransition
from .order_status import OrderStatus

# Maps each state to the set of states it may move to directly. A state with an
# empty set (``closed``) is terminal.
_ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.DRAFT: frozenset({OrderStatus.RELEASED}),
    OrderStatus.RELEASED: frozenset({OrderStatus.IN_PROGRESS}),
    OrderStatus.IN_PROGRESS: frozenset({OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset({OrderStatus.CLOSED}),
    OrderStatus.CLOSED: frozenset(),
}


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    """Return whether moving from ``current`` to ``target`` is allowed."""
    return target in _ALLOWED_TRANSITIONS[current]


def assert_can_transition(current: OrderStatus, target: OrderStatus) -> None:
    """Raise :class:`InvalidOrderStateTransition` if the move is not allowed."""
    if not can_transition(current, target):
        raise InvalidOrderStateTransition(current, target)
