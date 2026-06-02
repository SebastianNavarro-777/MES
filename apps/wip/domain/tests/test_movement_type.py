"""Tests for the WipMovementType enum (GP-010: no bare string literals)."""

from __future__ import annotations

from enum import StrEnum

from apps.wip.domain.movement_type import WipMovementType


def test_movement_type_is_str_enum_with_three_members() -> None:
    # GP-010: movement type is a StrEnum, not a string literal.
    assert issubclass(WipMovementType, StrEnum)
    assert {m.value for m in WipMovementType} == {"in", "out", "scrap"}


def test_movement_type_round_trips_through_value() -> None:
    assert WipMovementType("scrap") is WipMovementType.SCRAP
    assert WipMovementType.IN.value == "in"
