"""Liveness/readiness endpoint for the staging stand.

``/healthz`` is the contract QA Smoke and ``deploy_staging.sh`` rely on to
decide the stand is up. It returns 200 only when the process can reach the
database (which implies migrations have been applied during container
start-up). Any failure returns 503 so the orchestrator treats the deploy
as not-ready rather than silently green.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.db import connection
from django.http import HttpRequest, JsonResponse


def healthz(_request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # report any DB failure as unhealthy (boundary)
        return JsonResponse(
            {"status": "unhealthy", "detail": str(exc)},
            status=503,
        )
    return JsonResponse(
        {
            "status": "ok",
            "checked_at": datetime.now(UTC).isoformat(),
        },
        status=200,
    )
