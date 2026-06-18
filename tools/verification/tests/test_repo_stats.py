"""Unit tests for :mod:`tools.verification.repo_stats`.

These exercise the scanning heuristics on a synthetic tree so the counts are
deterministic and hermetic (no dependency on the real repo's evolving state).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tools.verification import repo_stats

GIT = shutil.which("git")


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """A minimal repo: one context with a domain entity, an event and routes."""
    _write(tmp_path / "apps" / "orders" / "domain" / "order.py", "class Order:\n    pass\n")
    _write(
        tmp_path / "apps" / "orders" / "domain" / "events.py",
        "class OrderReleased:\n    pass\n",
    )
    _write(
        tmp_path / "apps" / "orders" / "urls.py",
        "from django.urls import path\n\nurlpatterns = [path('o', None)]\n",
    )
    _write(
        tmp_path / "config" / "urls.py",
        "from django.urls import path\n\nurlpatterns = [path('healthz', None)]\n",
    )
    _write(
        tmp_path / "apps" / "orders" / "tests" / "test_order.py",
        "def test_order_constructs() -> None:\n    pass\n",
    )
    _write(tmp_path / "apps" / "quality" / ".gitkeep", "")
    _write(tmp_path / "docs" / "exec-plans" / "active" / "plan-1.md", "# plan\n")
    return tmp_path


# AC-2: counts are derived from the live tree and are coherent (contexts,
# domain entities, API endpoints, domain events all reflect reality).
def test_counts_reflect_the_tree(sample_repo: Path) -> None:
    stats = repo_stats.gather(sample_repo, git_bin="git-does-not-exist")
    assert stats.bounded_contexts_scaffolded == 2  # orders + quality
    assert stats.bounded_contexts_with_code == 1  # only orders has real .py
    assert stats.domain_entities == 1  # Order (events.py excluded)
    assert stats.domain_events == 1  # OrderReleased
    assert stats.api_endpoints == 2  # config healthz + orders route
    assert stats.test_functions == 1


# AC-2: a layer is only "present" when it carries non-trivial code; empty
# scaffolds must not be reported as implemented.
def test_layers_present_only_for_real_code(sample_repo: Path) -> None:
    contexts = {c.name: c for c in repo_stats.collect_context_stats(sample_repo)}
    assert contexts["orders"].layers_present == ("D", "X")
    assert contexts["orders"].public_symbols == 2  # Order + OrderReleased
    assert contexts["orders"].loc > 0
    assert contexts["quality"].layers_present == ()
    assert contexts["quality"].loc == 0


# AC-2: an empty __init__ does not make a context count as "implemented".
def test_trivial_init_does_not_count_as_code(tmp_path: Path) -> None:
    _write(tmp_path / "apps" / "oee" / "__init__.py", "")
    _write(tmp_path / "apps" / "oee" / "domain" / "__init__.py", '"""docstring only."""\n')
    stats = repo_stats.gather(tmp_path, git_bin="git-does-not-exist")
    assert stats.bounded_contexts_scaffolded == 1
    assert stats.bounded_contexts_with_code == 0


# AC-3: active exec-plans are discovered from docs/exec-plans/active/.
def test_active_exec_plans_listed(sample_repo: Path) -> None:
    assert repo_stats.active_exec_plans(sample_repo) == ("plan-1.md",)


# AC-7 / robustness: a missing/broken git binary yields no PRs, never raises.
def test_merged_prs_degrades_without_git(sample_repo: Path) -> None:
    assert repo_stats.merged_prs(sample_repo, git_bin="git-does-not-exist") == ()


# AC-3: merged PRs are parsed from git log subjects, including the ticket id.
@pytest.mark.skipif(GIT is None, reason="git is required for this test")
def test_merged_prs_parsed_from_git_log(tmp_path: Path) -> None:
    assert GIT is not None
    env_args = [
        [GIT, "init", "-q"],
        [GIT, "config", "user.email", "t@example.com"],
        [GIT, "config", "user.name", "Tester"],
    ]
    for cmd in env_args:
        subprocess.run(cmd, cwd=tmp_path, check=True, capture_output=True)
    _write(tmp_path / "a.txt", "a\n")
    subprocess.run([GIT, "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [GIT, "commit", "-q", "-m", "feat(orders): add thing (NSG-21) (#7)"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    _write(tmp_path / "b.txt", "b\n")
    subprocess.run([GIT, "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [GIT, "commit", "-q", "-m", "chore: no pr marker here"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    prs = repo_stats.merged_prs(tmp_path)
    assert len(prs) == 1
    assert prs[0].number == 7
    assert prs[0].ticket == "NSG-21"
