import logging

from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from ..providers import photon, tomtom
from ..providers.base import ProviderError
from ..services import heatmap_service, plan_service
from ..services.errors import UpstreamUnavailableError
from .serializers import (
    GeocodeQuerySerializer,
    PlanRequestSerializer,
    heatmap_json,
    place_json,
    plan_json,
)

log = logging.getLogger(__name__)


@api_view(["GET"])
def health(request: Request) -> Response:
    """Liveness check for Docker and the frontend; also reports whether the cache is reachable."""
    try:
        cache.set("health:ping", "ok", timeout=5)
        cache_ok = cache.get("health:ping") == "ok"
    except Exception:
        cache_ok = False
    return Response({"status": "ok", "cache": "ok" if cache_ok else "unavailable"})


@api_view(["GET"])
def geocode(request: Request) -> Response:
    """Worldwide place search: Photon (OpenStreetMap), falling back to TomTom."""
    query = GeocodeQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    q, near = query.validated_data["q"], query.near

    for provider in (photon, tomtom):
        try:
            return Response([place_json(p) for p in provider.geocode(q, limit=5, near=near)])
        except ProviderError:
            log.warning("Geocoding with %s failed", provider.__name__, exc_info=True)
    raise UpstreamUnavailableError(
        "geocoding_unavailable", "Place search is unavailable. Please try again shortly."
    )


@api_view(["POST"])
def plan(request: Request) -> Response:
    """Plan a trip: three routes with checkpoint weather, risk and a recommendation."""
    body = PlanRequestSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    return Response(plan_json(plan_service.create_plan(body.to_trip())))


@api_view(["GET"])
def heatmap(request: Request, plan_id: str) -> Response:
    """Risk scores over the plan's corridor for every hour of its 0-48 h forecast window."""
    return Response(heatmap_json(heatmap_service.build(plan_service.get_plan(plan_id))))
