"""Subprocess helpers shared across the orchestrator.

``asyncio.create_subprocess_exec`` does NOT resolve executables the way
``subprocess.run`` does — on Windows it ignores ``PATHEXT``, so a bare
name like ``"gh"``, ``"git"`` or ``"claude"`` misses the actual
``.cmd`` / ``.exe`` shim installed on PATH and raises a confusing
``FileNotFoundError: [WinError 2]``. Every place that spawns an external
tool must resolve the binary to an absolute path first.
"""

from __future__ import annotations

import shutil

__all__ = ["resolve_executable"]


def resolve_executable(name: str) -> str:
    """Resolve an executable by name, honouring PATHEXT on Windows.

    ``shutil.which`` does the full resolution (PATH + PATHEXT on Windows,
    executable bit on POSIX) and returns an absolute path we can hand
    directly to ``asyncio.create_subprocess_exec``. Absolute paths that
    are already executable come back unchanged. A bare name that can't be
    resolved is returned as-is so the eventual subprocess failure still
    names the original binary — the upstream error stays actionable.
    """
    return shutil.which(name) or name
