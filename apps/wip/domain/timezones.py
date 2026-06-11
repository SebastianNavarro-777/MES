"""Datetime boundary guard for the WIP domain (GP-003)."""

from __future__ import annotations

from datetime import UTC, datetime

from .exceptions import WipDomainError


def ensure_utc(value: datetime, *, field: str, error: type[WipDomainError]) -> datetime:
    """Reject naive or non-UTC datetimes, raising ``error`` (GP-003).

    Each caller passes the exception type appropriate to its boundary
    (e.g. ``WipBalanceError`` for a movement, ``InvalidWipEventError`` for an
    event), so the failure stays specific while the rule stays in one place.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise error(f"{field} must be timezone-aware (GP-003)")
    if value.utcoffset() != UTC.utcoffset(None):
        raise error(f"{field} must be UTC, got offset {value.utcoffset()}")
    return value
