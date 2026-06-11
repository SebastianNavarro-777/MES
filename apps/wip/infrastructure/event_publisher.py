"""Redis Streams publisher for ``wip.updated`` events (AC-5).

The event bus is Redis Streams, accessed only from this infrastructure layer
(ARCHITECTURE.md). Each context publishes to its own stream; here it is
``wip.events``.

We do not hard-import ``redis`` here: the publisher depends on a structural
``StreamClient`` Protocol that matches ``redis.Redis.xadd`` / the async client's
signature. The real client is injected at the composition root. This keeps the
adapter unit-testable offline (no network) and avoids a hard dependency until
the runtime wiring story lands.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol

from apps.wip.application.record_wip_movement import WipEventPublisher
from apps.wip.domain.events import EVENT_NAME, WipUpdated

log = logging.getLogger(__name__)

#: The WIP context's own stream on the event bus.
WIP_EVENTS_STREAM = "wip.events"


class StreamClient(Protocol):
    """Structural type for the subset of a Redis client we use.

    ``redis.Redis`` satisfies this: ``xadd(name, fields, ...) -> str``. We only
    ever append (``XADD``); events are immutable and never rewritten (AC-6).
    """

    def xadd(self, name: str, fields: Mapping[str, str]) -> object: ...


def to_stream_fields(event: WipUpdated) -> dict[str, str]:
    """Serialize a ``WipUpdated`` event to a flat Redis stream entry (AC-2, AC-5).

    All values are strings, the wire format for Redis stream fields. The
    ``event_id`` and ``schema_version`` travel in the payload so consumers can
    de-duplicate (AC-6) and version their parsing (AC-3).
    """
    return {
        "event_name": EVENT_NAME,
        "event_id": event.event_id,
        "schema_version": str(event.schema_version),
        "order_id": event.order_id,
        "route_step_id": event.route_step_id,
        "qty_in": str(event.qty_in),
        "qty_out": str(event.qty_out),
        "qty_scrap": str(event.qty_scrap),
        "movement_type": event.movement_type.value,
        "movement_qty": str(event.movement_qty),
        # GP-003: timezone-aware UTC, serialized in ISO-8601 with offset.
        "occurred_at": event.occurred_at.isoformat(),
    }


class RedisStreamWipEventPublisher(WipEventPublisher):
    """Appends ``wip.updated`` events to the ``wip.events`` stream.

    Append-only by construction: it only ever issues ``XADD`` and never mutates
    or rewrites a previously published entry (AC-6, event-bus rule).
    """

    def __init__(self, client: StreamClient, *, stream: str = WIP_EVENTS_STREAM) -> None:
        self._client = client
        self._stream = stream

    def publish(self, event: WipUpdated) -> None:
        fields = to_stream_fields(event)
        self._client.xadd(self._stream, fields)
        log.info(
            "published wip.updated",
            extra={
                "stream": self._stream,
                "event_id": event.event_id,
                "order_id": event.order_id,
                "route_step_id": event.route_step_id,
            },
        )
