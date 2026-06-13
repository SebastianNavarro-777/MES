#!/usr/bin/env python
"""Django management entry point for the MES staging skeleton.

This is the minimal deployable project that the staging stand
(`docker-compose.staging.yml` + `tools/verification/deploy_staging.sh`)
builds and runs. Bounded contexts under ``apps/`` are added by later
Stories; this file only wires the project settings.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
