"""Tests for the Redis Streams publisher and event serialization."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from apps.wip.domain.balance import WipBalance, WipMovement
from apps.wip.domain.events import WipUpdated
from apps.wip.domain.movement_type import WipMovementType
from apps.wip.infrastructure.event_publisher import (
    WIP_EVENTS_STREAM,
    RedisStreamWipEventPublisher,
    to_stream_fields,
)

_NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


class FakeStreamClient:
    """In-memory stand-in for redis.Redis; records every XADD (no network)."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, Mapping[str, str]]] = []
        self._seq = 0

    def xadd(self, name: str, fields: Mapping[str, str]) -> object:
        self._seq += 1
        self.entries.append((name, dict(fields)))
        return f"{self._seq}-0".encode()


def _event() -> WipUpdated:
    movement = WipMovement(
        movement_id="MOV-7",
        order_id="OF-1",
        route_step_id="STEP-10",
        movement_type=WipMovementType.SCRAP,
        qty=3,
        occurred_at=_NOW,
    )
    balance = WipBalance(order_id="OF-1", route_step_id="STEP-10", qty_in=10, qty_scrap=3)
    return WipUpdated.from_movement(movement, balance)


def test_publish_appends_exactly_one_entry_to_wip_events_stream() -> None:
    # AC-1: one balance change -> exactly one entry on the wip.events stream.
    client = FakeStreamClient()
    publisher = RedisStreamWipEventPublisher(client)

    publisher.publish(_event())

    assert len(client.entries) == 1
    stream_name, _fields = client.entries[0]
    assert stream_name == WIP_EVENTS_STREAM == "wip.events"


def test_serialized_payload_contains_all_contract_fields() -> None:
    # AC-2 / AC-5: serialization happens in infrastructure and the payload
    # carries the order, route step, resulting balance, movement and timestamp.
    fields = to_stream_fields(_event())

    assert fields["event_name"] == "wip.updated"
    assert fields["order_id"] == "OF-1"
    assert fields["route_step_id"] == "STEP-10"
    assert fields["qty_in"] == "10"
    assert fields["qty_out"] == "0"
    assert fields["qty_scrap"] == "3"
    assert fields["movement_type"] == "scrap"
    assert fields["movement_qty"] == "3"
    assert fields["occurred_at"] == _NOW.isoformat()
    # AC-3: schema_version is present for consumer-side versioning.
    assert fields["schema_version"] == "1"


def test_payload_carries_stable_event_id_for_dedup() -> None:
    # AC-6: the event_id travels in the payload so consumers can de-duplicate.
    event = _event()
    fields = to_stream_fields(event)
    assert fields["event_id"] == event.event_id


def test_publisher_only_appends_and_never_rewrites_prior_entries() -> None:
    # AC-6: append-only — publishing twice adds entries, never mutates earlier ones.
    client = FakeStreamClient()
    publisher = RedisStreamWipEventPublisher(client)

    publisher.publish(_event())
    first_snapshot = dict(client.entries[0][1])
    publisher.publish(_event())

    assert len(client.entries) == 2
    assert client.entries[0][1] == first_snapshot  # earlier entry untouched
