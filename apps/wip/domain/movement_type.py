"""WIP movement type as an enum, never a bare string literal (GP-010)."""

from __future__ import annotations

from enum import StrEnum


class WipMovementType(StrEnum):
    """The kind of stock movement recorded at a route step.

    - ``IN``: units entering the step (production/transfer in).
    - ``OUT``: good units leaving the step toward the next one.
    - ``SCRAP``: units removed from process as scrap.
    """

    IN = "in"
    OUT = "out"
    SCRAP = "scrap"
