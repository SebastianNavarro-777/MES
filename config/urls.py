"""Root URL configuration for the staging skeleton.

Only the health endpoint exists today. Bounded contexts mount their own
routers under ``/api/v1/<context>/`` in later Stories.
"""

from __future__ import annotations

from django.urls import path

from config.health import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
]
