"""Liveness check, answered before Django's host validation.

Platform health checks (e.g. Render's) may not send the public hostname, which would make
Django reject them with 400 and mark every deploy unhealthy. This middleware answers only
the exact health path and only for GET/HEAD; every other request keeps strict host checks.
"""

from __future__ import annotations

from collections.abc import Callable

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

HEALTH_PATH = "/api/health"


def health_status() -> dict[str, str]:
    """Process is up; also reports whether the cache answers."""
    try:
        cache.set("health:ping", "ok", timeout=5)
        cache_ok = cache.get("health:ping") == "ok"
    except Exception:
        cache_ok = False
    return {"status": "ok", "cache": "ok" if cache_ok else "unavailable"}


class HealthCheckMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path_info == HEALTH_PATH and request.method in ("GET", "HEAD"):
            return JsonResponse(health_status())
        return self.get_response(request)
