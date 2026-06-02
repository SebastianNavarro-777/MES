"""Tests for github_client pure helpers.

The ``gh``-shelling methods are exercised by integration runs; here we
lock in the branch-matching logic the Worker pool relies on to tell a
fix (re-queued PR) from a fresh story, since a wrong boundary would mix
up tickets like NSG-1 and NSG-10.
"""

from __future__ import annotations

import pytest

from tools.orchestrator.orchestrator.github_client import branch_matches_ticket


@pytest.mark.parametrize(
    "head_ref",
    [
        "feat/NSG-10-add-orders",
        "fix/NSG-10-handle-null",
        "refactor/NSG-10-extract",
        "harness/NSG-10-linter",
        "NSG-10-bare-branch",
        "NSG-10",
    ],
)
def test_matches_branches_belonging_to_the_ticket(head_ref: str) -> None:
    assert branch_matches_ticket(head_ref, "NSG-10")


@pytest.mark.parametrize(
    "head_ref",
    [
        "feat/NSG-100-other",   # different ticket, shared prefix
        "feat/NSG-1-other",     # NSG-1 must not match NSG-10
        "feat/XSG-10-other",    # different project key
        "main",
    ],
)
def test_rejects_branches_for_other_tickets(head_ref: str) -> None:
    assert not branch_matches_ticket(head_ref, "NSG-10")
