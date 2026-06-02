"""Liveness/readiness endpoint for the staging stand.

``/healthz`` is the contract QA Smoke and ``deploy_staging.sh`` rely on to
decide the stand is up. It returns 200 only when the process can reach the
database (which implies migrations have been applied during container
start-up). Any failure returns 503 so the orchestrator treats the deploy
as not-ready rather than silently green.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from django.db import connection
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


def healthz(_request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # report any DB failure as unhealthy (boundary)
        # Log the cause server-side (inspectable via `docker compose logs`,
        # AC-6) but never echo the exception text to the caller: the stack
        # detail would be information exposure on an externally reachable
        # endpoint (CodeQL py/stack-trace-exposure).
        logger.exception("healthz: database connectivity check failed")
        return JsonResponse(
            {"status": "unhealthy"},
            status=503,
        )
    return JsonResponse(
        {
            "status": "ok",
            "checked_at": datetime.now(UTC).isoformat(),
        },
        status=200,
    )
