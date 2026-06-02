"""Use case: record a WIP movement and publish the resulting ``wip.updated``.

This orchestrates the persist-then-publish ordering that the event contract
relies on:

- The balance change is persisted **first** (``repo.save``).
- The event is published **after** a successful save (AC-4): if applying the
  movement is rejected by the domain (e.g. it would drive the net balance
  negative) the repository is never touched and no event is published.
- Exactly **one** ``wip.updated`` event is published per successful change
  (AC-1).

Delivery is therefore at-least-once: persistence and publication are not a
single atomic write (dual-write). The event carries a stable ``event_id``
derived from the movement (AC-6) so downstream consumers can de-duplicate.
A guaranteed-delivery outbox is a possible follow-up and is out of scope here.
"""

from __future__ import annotations

from typing import Protocol

from apps.wip.domain.balance import WipBalance, WipMovement
from apps.wip.domain.events import WipUpdated


class WipBalanceRepository(Protocol):
    """Persists and loads the WIP balance for an (order, route step) pair."""

    def get(self, order_id: str, route_step_id: str) -> WipBalance | None: ...

    def save(self, balance: WipBalance) -> None: ...


class WipEventPublisher(Protocol):
    """Publishes a ``wip.updated`` event to the ``wip.events`` stream."""

    def publish(self, event: WipUpdated) -> None: ...


def record_wip_movement(
    movement: WipMovement,
    *,
    repo: WipBalanceRepository,
    publisher: WipEventPublisher,
) -> WipUpdated:
    """Apply ``movement`` to the current balance, persist it, then publish.

    Returns the published ``wip.updated`` event.
    """
    current = repo.get(movement.order_id, movement.route_step_id)
    if current is None:
        current = WipBalance(
            order_id=movement.order_id,
            route_step_id=movement.route_step_id,
        )

    # Domain enforces the non-negative invariant; raises before any I/O (AC-4).
    updated = current.apply(movement)

    # Persist first so no event escapes for a change that was not stored (AC-4).
    repo.save(updated)

    # Exactly one event per successful balance change (AC-1).
    event = WipUpdated.from_movement(movement, updated)
    publisher.publish(event)
    return event
