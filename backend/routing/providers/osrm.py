"""OSRM public demo server: routing fallback when TomTom is unavailable.

It only has a car profile and asks for at most 1 request/second, so it is used only on
failure, and its routes are flagged with ``is_fallback_profile=True``.
"""

from __future__ import annotations

from typing import Any

from ..domain.models import LonLat, RouteCandidate, TimelinePoint
from .base import NoRouteError, ProviderError, request_json

PROVIDER = "osrm"
BASE_URL = "https://router.project-osrm.org"
M_PER_MI = 1609.344


def route(origin: LonLat, destination: LonLat, *, alternatives: int = 3) -> list[RouteCandidate]:
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in (origin, destination))
    try:
        data = request_json(
            PROVIDER,
            f"{BASE_URL}/route/v1/driving/{coords}",
            params={
                "alternatives": alternatives,
                "overview": "full",
                "geometries": "geojson",
                "steps": "true",
            },
        )
    except ProviderError as exc:
        if isinstance(exc.body, dict) and exc.body.get("code") == "NoRoute":
            raise NoRouteError(PROVIDER, "no route between these points") from exc
        raise

    if data.get("code") != "Ok" or not data.get("routes"):
        raise NoRouteError(PROVIDER, f"no route ({data.get('code')})")
    return [_parse_route(r) for r in data["routes"]]


def _parse_route(r: dict[str, Any]) -> RouteCandidate:
    timeline = [TimelinePoint(0.0, 0.0)]
    dist_m = elapsed = 0.0
    for leg in r["legs"]:
        for step in leg["steps"]:
            dist_m += step["distance"]
            elapsed += step["duration"]
            timeline.append(TimelinePoint(dist_m / M_PER_MI, elapsed))

    return RouteCandidate(
        source=PROVIDER,
        geometry=tuple((c[0], c[1]) for c in r["geometry"]["coordinates"]),
        distance_mi=r["distance"] / M_PER_MI,
        duration_s=r["duration"],
        timeline=tuple(timeline),
        is_fallback_profile=True,
    )
