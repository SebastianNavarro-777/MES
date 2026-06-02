"""Exceptions for the WIP bounded context (GP-012).

Every error raised from WIP domain/application code subclasses
``WipDomainError`` so callers and middleware can catch the whole family.
Never raise built-ins (``ValueError``/``RuntimeError``) from these layers.
"""

from __future__ import annotations


class WipDomainError(Exception):
    """Base for everything raised inside the WIP bounded context."""


class WipBalanceError(WipDomainError):
    """Raised when a movement would produce an invalid WIP balance.

    Examples: a non-positive movement quantity, or a movement that would drive
    the net in-process balance negative (more out/scrap than ever entered).
    """


class InvalidWipEventError(WipDomainError):
    """Raised when a ``WipUpdated`` event is constructed with invalid data.

    Examples: a naive (timezone-unaware) ``occurred_at`` (GP-003), a
    non-positive movement magnitude, or an unsupported ``schema_version``.
    """
