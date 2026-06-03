"""Runtime-only copyleft license gate for CI.

MES is commercial, *distributed* software. Copyleft licenses (AGPL/GPL/LGPL)
in dependencies that ship to customers would contaminate the product, and
customers in regulated industries (21 CFR Part 11, IATF 16949) audit this.

The gate must therefore reject copyleft, but only in what we actually ship:
the **runtime** dependencies declared in ``[project].dependencies`` of
``pyproject.toml`` plus their transitive closure. Dev-group tools (declared in
``[dependency-groups].dev`` — ruff, mypy, pytest, yamllint, ...) are never
distributed, so their licenses cannot contaminate the product. Auditing them
produces false positives: ``yamllint`` is ``GPL-3.0-or-later`` yet is a purely
local/CI linter (see NSG-46).

This module narrows the audited package set to runtime deps while keeping the
list of forbidden copyleft licenses (``--fail-on``) unchanged. It derives the
runtime set from ``uv export --no-dev`` and runs ``pip-licenses`` scoped to
exactly those packages.

The security audit (``pip-audit`` in the ``security-audit`` job) still covers
runtime + dev on purpose — CVEs matter in dev too. Only this license gate is
scoped down.

CLI usage
---------
    uv run --no-dev --with pip-licenses python tools/linters/license_gate.py

Exit code: whatever ``pip-licenses`` returns (non-zero if a runtime dependency
carries a forbidden copyleft license), or 0 if there are no runtime deps.
"""

from __future__ import annotations

import re
import subprocess
import sys

__all__ = [
    "FORBIDDEN_LICENSES",
    "build_fail_on",
    "build_pip_licenses_command",
    "main",
    "runtime_package_names",
]

# Copyleft licenses forbidden in DISTRIBUTED (runtime) dependencies. This list
# is intentionally identical to the historical pip-licenses ``--fail-on`` value
# (NSG-46 changes the audited *set*, never the prohibited *licenses*): every
# AGPL/GPL/LGPL 3.0 spelling, both ``-only`` and ``-or-later``.
FORBIDDEN_LICENSES: tuple[str, ...] = (
    "AGPL-3.0",
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "GPL-3.0",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "LGPL-3.0",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
)

# A distribution name as emitted by ``uv export`` at the start of a line, e.g.
# ``httpx==0.28.1`` or ``markdown-it-py==4.0.0`` (optionally with extras like
# ``httpx[brotli]==...``). Names start alphanumeric; the rest may contain
# ``.``, ``-`` and ``_``.
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def runtime_package_names(export_text: str) -> list[str]:
    """Parse ``uv export --no-dev`` output into the sorted runtime dist names.

    ``uv export`` writes one ``name==version`` requirement per line; provenance
    (``# via ...``) and the header are comment lines, and ``-e``/option lines
    start with ``-``. Dev-group packages (e.g. ``yamllint``) are absent because
    the export is expected to have run with ``--no-dev``.
    """
    names: set[str] = set()
    for raw in export_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = _NAME_PATTERN.match(line)
        if match is not None:
            names.add(match.group(0))
    return sorted(names)


def build_fail_on(forbidden: tuple[str, ...] = FORBIDDEN_LICENSES) -> str:
    """Render the ``pip-licenses --fail-on`` argument (semicolon-separated)."""
    return ";".join(forbidden)


def build_pip_licenses_command(packages: list[str]) -> list[str]:
    """Build the ``pip-licenses`` argv that audits exactly ``packages``.

    The ``--fail-on`` copyleft list is kept intact; only ``--packages`` narrows
    the audited set to the supplied runtime dependencies.
    """
    return [
        "pip-licenses",
        "--fail-on",
        build_fail_on(),
        "--packages",
        *packages,
    ]


def _export_runtime_requirements() -> str:
    """Return the ``uv export`` requirements text for runtime deps only."""
    completed = subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-hashes"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def main() -> int:
    """Run the runtime-only copyleft license gate. Returns an exit code."""
    packages = runtime_package_names(_export_runtime_requirements())
    if not packages:
        print(
            "license-gate: no runtime dependencies to audit; passing.",
            file=sys.stderr,
        )
        return 0

    print(
        "license-gate: auditing runtime dependencies only "
        f"({len(packages)}): {', '.join(packages)}",
        file=sys.stderr,
    )
    completed = subprocess.run(build_pip_licenses_command(packages), check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
