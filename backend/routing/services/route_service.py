"""Get three distinct route options (docs/PROJECT_SPEC.md §7).

1. TomTom truck routing with 2 alternatives.
2. Drop near-duplicates.
3. If fewer than 3 remain, route through detour waypoints left and right of the midpoint.
4. If TomTom is down, fall back to OSRM (car profile) and say so.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..domain.geometry import detour_waypoint, route_similarity
from ..domain.models import LonLat, RouteCandidate
from ..providers import osrm, tomtom
from ..providers.base import NoRouteError, ProviderError, cache_key, cached
from .errors import NoRouteFoundError, UpstreamUnavailableError

log = logging.getLogger(__name__)

TARGET_ROUTES = 3
TOMTOM_ALTERNATIVES = 2
DUPLICATE_SIMILARITY = 0.85
# Detour waypoints sit this far sideways, as a share of the straight-line trip distance.
DETOUR_RATIOS = (0.15, 0.30)
# A detour that takes this much longer than the fastest route isn't a sensible option.
MAX_DETOUR_DURATION_RATIO = 1.5
ROUTES_TTL_S = 10 * 60
# Departure times in the same 15 minutes share cached routes (traffic barely changes).
DEPART_BUCKET_S = 15 * 60


@dataclass(frozen=True)
class RouteSet:
    routes: list[RouteCandidate]
    warnings: list[str] = field(default_factory=list)


def get_routes(origin: LonLat, destination: LonLat, *, depart_at: int, load_lb: float) -> RouteSet:
    key = cache_key(
        "routes",
        round(origin[0], 4),
        round(origin[1], 4),
        round(destination[0], 4),
        round(destination[1], 4),
        depart_at // DEPART_BUCKET_S,
        round(load_lb),
    )
    return cached(
        key,
        ROUTES_TTL_S,
        lambda: _fetch_routes(origin, destination, depart_at=depart_at, load_lb=load_lb),
    )


def _fetch_routes(
    origin: LonLat, destination: LonLat, *, depart_at: int, load_lb: float
) -> RouteSet:
    warnings: list[str] = []
    try:
        routes = tomtom.calculate_route(
            origin,
            destination,
            depart_at=depart_at,
            load_lb=load_lb,
            max_alternatives=TOMTOM_ALTERNATIVES,
        )
    except NoRouteError as exc:
        raise NoRouteFoundError("no_route", "No truck route exists between these places.") from exc
    except ProviderError:
        log.warning("TomTom routing failed; falling back to OSRM", exc_info=True)
        return _fallback_routes(origin, destination)

    distinct = dedupe(routes)
    if len(distinct) < TARGET_ROUTES:
        distinct = _add_detours(distinct, origin, destination, depart_at=depart_at, load_lb=load_lb)
    if len(distinct) < TARGET_ROUTES:
        warnings.append(
            f"Only {len(distinct)} distinct route{'s' if len(distinct) != 1 else ''} "
            "could be found for this trip."
        )
    return RouteSet(distinct[:TARGET_ROUTES], warnings)


def dedupe(routes: Sequence[RouteCandidate]) -> list[RouteCandidate]:
    """Keep routes in order, dropping any that is the same road as one already kept."""
    kept: list[RouteCandidate] = []
    for candidate in routes:
        if all(
            route_similarity(candidate.geometry, k.geometry) < DUPLICATE_SIMILARITY for k in kept
        ):
            kept.append(candidate)
    return kept


def _add_detours(
    routes: list[RouteCandidate],
    origin: LonLat,
    destination: LonLat,
    *,
    depart_at: int,
    load_lb: float,
) -> list[RouteCandidate]:
    fastest = min(r.duration_s for r in routes)

    def detour(args: tuple[str, float]) -> RouteCandidate | None:
        side, ratio = args
        try:
            waypoint = detour_waypoint(origin, destination, side, ratio)  # type: ignore[arg-type]
            [route] = tomtom.calculate_route(
                origin, destination, depart_at=depart_at, load_lb=load_lb, via=[waypoint]
            )[:1]
        except (ProviderError, ValueError):
            log.info("Detour route %s/%s failed", side, ratio, exc_info=True)
            return None
        return route if route.duration_s <= fastest * MAX_DETOUR_DURATION_RATIO else None

    out = list(routes)
    for ratio in DETOUR_RATIOS:
        if len(out) >= TARGET_ROUTES:
            break
        with ThreadPoolExecutor(max_workers=2) as pool:
            candidates = list(pool.map(detour, [("left", ratio), ("right", ratio)]))
        out = dedupe(out + sorted((c for c in candidates if c), key=lambda r: r.duration_s))
    return out


def _fallback_routes(origin: LonLat, destination: LonLat) -> RouteSet:
    try:
        routes = osrm.route(origin, destination, alternatives=TARGET_ROUTES)
    except NoRouteError as exc:
        raise NoRouteFoundError("no_route", "No route exists between these places.") from exc
    except ProviderError as exc:
        raise UpstreamUnavailableError(
            "routing_unavailable", "Routing services are unavailable. Please try again shortly."
        ) from exc

    distinct = dedupe(routes)[:TARGET_ROUTES]
    warnings = [
        "TomTom truck routing is unavailable, so these routes come from a car-routing "
        "fallback (OSRM). Truck restrictions and travel times may differ."
    ]
    if len(distinct) < TARGET_ROUTES:
        warnings.append(f"Only {len(distinct)} distinct route(s) could be found for this trip.")
    return RouteSet(distinct, warnings)
