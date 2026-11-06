"""TomTom Routing API (truck routes; primary) and Search API (geocoding; fallback)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from django.conf import settings

from ..domain.models import LonLat, Place, RouteCandidate, TimelinePoint
from .base import NoRouteError, ProviderError, cache_key, cached, request_json

PROVIDER = "tomtom"
BASE_URL = "https://api.tomtom.com"

M_PER_MI = 1609.344
KG_PER_LB = 0.45359237
# The user enters the *load* (cargo) weight, but TomTom's vehicleWeight is the gross weight.
# A typical empty tractor-trailer weighs about 35,000 lb.
EMPTY_TRUCK_LB = 35_000

GEOCODE_TTL_S = 24 * 3600

NO_ROUTE_CODES = frozenset({"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"})

# Measured on Chicago -> Denver (~1,000 mi): 2 alternatives take ~4 s and return ~1.8 MB;
# 5 alternatives take ~12 s and ~4 MB. Long truck routes legitimately need more than the
# default timeout, so routing gets its own.
ROUTE_TIMEOUT_S = 20.0


def _api_key() -> str:
    if not settings.TOMTOM_API_KEY:
        raise ProviderError(PROVIDER, "TOMTOM_API_KEY is not configured")
    return settings.TOMTOM_API_KEY


# --- Geocoding -----------------------------------------------------------------------------


def geocode(query: str, limit: int = 5, near: LonLat | None = None) -> list[Place]:
    """Worldwide place search. ``near`` ranks results close to that point first (e.g. the
    map's centre), so "Hyderabad" finds the one in the region the user is looking at.
    """
    q = query.strip()
    if not q:
        return []
    bias = _round_bias(near)

    def fetch() -> list[Place]:
        params: dict[str, Any] = {"key": _api_key(), "limit": limit, "typeahead": "true"}
        if bias:
            params["lon"], params["lat"] = bias
        data = request_json(
            PROVIDER, f"{BASE_URL}/search/2/search/{quote(q, safe='')}.json", params=params
        )
        return [_parse_place(r) for r in data.get("results", [])]

    return cached(cache_key("geocode:tomtom", q.lower(), limit, bias), GEOCODE_TTL_S, fetch)


def _round_bias(near: LonLat | None) -> LonLat | None:
    # Whole degrees: precise enough to rank by region, coarse enough to share cache entries.
    return (round(near[0]), round(near[1])) if near else None


def _parse_place(result: dict[str, Any]) -> Place:
    address = result.get("address", {})
    parts = [result.get("poi", {}).get("name"), address.get("freeformAddress")]
    country = address.get("country")
    # Searches are worldwide, so the country is part of every label.
    if country and not any(p and country in p for p in parts):
        parts.append(country)
    label = ", ".join(p for p in parts if p)
    pos = result["position"]
    return Place(label=label, lon=pos["lon"], lat=pos["lat"])


# --- Routing -------------------------------------------------------------------------------


def calculate_route(
    origin: LonLat,
    destination: LonLat,
    *,
    depart_at: int,
    load_lb: float,
    max_alternatives: int = 0,
    via: Sequence[LonLat] = (),
) -> list[RouteCandidate]:
    """Truck routes from ``origin`` to ``destination`` (through ``via`` points, if any).

    Returns the best route first, then up to ``max_alternatives`` alternatives.
    """
    locations = ":".join(f"{lat:.6f},{lon:.6f}" for lon, lat in (origin, *via, destination))
    params: dict[str, Any] = {
        "key": _api_key(),
        "travelMode": "truck",
        "vehicleWeight": round((EMPTY_TRUCK_LB + load_lb) * KG_PER_LB),
        "routeType": "fastest",
        "traffic": "true",
        "departAt": _depart_at_param(depart_at),
        "instructionsType": "coded",
        "routeRepresentation": "polyline",
    }
    if max_alternatives:
        params["maxAlternatives"] = max_alternatives

    try:
        data = request_json(
            PROVIDER,
            f"{BASE_URL}/routing/1/calculateRoute/{locations}/json",
            params=params,
            timeout_s=ROUTE_TIMEOUT_S,
        )
    except ProviderError as exc:
        body = exc.body if isinstance(exc.body, dict) else {}
        if body.get("detailedError", {}).get("code") in NO_ROUTE_CODES:
            raise NoRouteError(
                PROVIDER, "no route between these points", status=exc.status
            ) from exc
        raise

    routes = data.get("routes") or []
    if not routes:
        raise NoRouteError(PROVIDER, "response contained no routes")
    return [_parse_route(r) for r in routes]


def _depart_at_param(depart_at: int) -> str:
    # TomTom rejects departure times in the past; anything within a minute of now is "now".
    if depart_at <= time.time() + 60:
        return "now"
    return datetime.fromtimestamp(depart_at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_route(route: dict[str, Any]) -> RouteCandidate:
    geometry: list[LonLat] = []
    for leg in route["legs"]:
        points = [(p["longitude"], p["latitude"]) for p in leg["points"]]
        # Consecutive legs share the waypoint: skip the duplicate.
        if geometry and points and points[0] == geometry[-1]:
            points = points[1:]
        geometry.extend(points)

    summary = route["summary"]
    length_m = summary["lengthInMeters"]
    duration_s = summary["travelTimeInSeconds"]

    return RouteCandidate(
        source=PROVIDER,
        geometry=tuple(geometry),
        distance_mi=length_m / M_PER_MI,
        duration_s=duration_s,
        timeline=_timeline(route.get("guidance", {}).get("instructions", []), length_m, duration_s),
    )


def _timeline(
    instructions: list[dict[str, Any]], length_m: float, duration_s: float
) -> tuple[TimelinePoint, ...]:
    """Distance -> elapsed time at every maneuver, bracketed by the start and the end.

    Points that would make the timeline go backwards are dropped, so it is always monotonic.
    """
    raw = [(0.0, 0.0)]
    raw += [(i["routeOffsetInMeters"], i["travelTimeInSeconds"]) for i in instructions]
    raw.append((length_m, duration_s))

    out: list[TimelinePoint] = []
    for offset_m, elapsed in raw:
        point = TimelinePoint(offset_m / M_PER_MI, float(elapsed))
        if out and (point.distance_mi < out[-1].distance_mi or point.elapsed_s < out[-1].elapsed_s):
            continue
        out.append(point)
    return tuple(out)
