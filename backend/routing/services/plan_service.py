"""Build a trip plan: routes -> checkpoints -> weather -> risk -> ranking."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, replace

from django.core.cache import cache

from ..domain.checkpoints import CheckpointPosition, sample_checkpoints
from ..domain.geometry import haversine_mi, simplify
from ..domain.models import Assessment, LonLat, Place, RouteCandidate, Weather
from ..domain.ranking import RankInput, RouteSummary, explain, rank, summarize
from ..domain.risk import assess
from . import route_service, weather_service
from .errors import InvalidTripError, PlanNotFoundError
from .weather_service import ForecastWindow

PLAN_TTL_S = 3600
# Departures may be slightly in the past (the form was filled in a few minutes ago).
MAX_PAST_DEPARTURE_S = 15 * 60
MIN_TRIP_MI = 0.5
ROUTE_NAMES = ("Route A", "Route B", "Route C")


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure_ts: int
    load_lb: float
    interval_mi: float


@dataclass(frozen=True)
class AssessedCheckpoint:
    position: CheckpointPosition
    weather: Weather | None
    assessment: Assessment


@dataclass(frozen=True)
class PlannedRoute:
    id: str
    name: str
    candidate: RouteCandidate
    display_geometry: list[LonLat]
    departure_ts: int
    checkpoints: list[AssessedCheckpoint]
    summary: RouteSummary
    rank: int

    @property
    def arrival_ts(self) -> int:
        return self.departure_ts + round(self.candidate.duration_s)


@dataclass(frozen=True)
class Plan:
    id: str
    generated_at: int
    request: TripRequest
    window: ForecastWindow
    routes: list[PlannedRoute]
    recommended_route_id: str
    recommendation_reason: str
    warnings: list[str]


def validate(trip: TripRequest, window: ForecastWindow, now: float) -> None:
    if trip.departure_ts < now - MAX_PAST_DEPARTURE_S:
        raise InvalidTripError("departure_in_past", "Departure time is in the past.")
    if trip.departure_ts > window.end:
        raise InvalidTripError(
            "departure_beyond_forecast",
            f"Departure must be within the next {weather_service.WINDOW_HOURS} hours, "
            "the range of the weather forecast.",
        )
    if haversine_mi(trip.origin.coord, trip.destination.coord) < MIN_TRIP_MI:
        raise InvalidTripError("same_place", "Origin and destination are the same place.")


def create_plan(trip: TripRequest, *, now: float | None = None) -> Plan:
    now = time.time() if now is None else now
    window = ForecastWindow.current(now)
    validate(trip, window, now)
    departure = max(trip.departure_ts, int(now))

    route_set = route_service.get_routes(
        trip.origin.coord, trip.destination.coord, depart_at=departure, load_lb=trip.load_lb
    )
    warnings = list(route_set.warnings)

    fastest = min(route_set.routes, key=lambda r: r.duration_s)
    if window.hour_of(departure + round(fastest.duration_s)) is None:
        raise InvalidTripError(
            "trip_beyond_forecast",
            f"This trip would end more than {weather_service.WINDOW_HOURS} hours from now, "
            "beyond the weather forecast. Choose an earlier departure.",
        )

    positions = [
        sample_checkpoints(r.geometry, r.timeline, trip.interval_mi, departure)
        for r in route_set.routes
    ]
    weather = weather_service.get_weather(
        (c.coord for cps in positions for c in cps), window, allow_nws_fallback=True
    )
    warnings += weather.warnings

    planned: list[PlannedRoute] = []
    for i, (candidate, cps) in enumerate(zip(route_set.routes, positions, strict=True)):
        assessed = [_assess(c, weather, window, trip.load_lb) for c in cps]
        planned.append(
            PlannedRoute(
                id=f"r{i + 1}",
                name=ROUTE_NAMES[i],
                candidate=candidate,
                display_geometry=simplify(candidate.geometry),
                departure_ts=departure,
                checkpoints=assessed,
                summary=summarize((c.position.segment_mi, c.assessment.final) for c in assessed),
                rank=0,
            )
        )

    ranked = rank([RankInput(r.id, r.name, r.summary, r.candidate.duration_s) for r in planned])
    order = {r.id: n + 1 for n, r in enumerate(ranked)}
    planned = [replace(r, rank=order[r.id]) for r in planned]
    warnings += _risk_warnings(planned)

    plan = Plan(
        id=uuid.uuid4().hex,
        generated_at=int(now),
        request=trip,
        window=window,
        routes=planned,
        recommended_route_id=ranked[0].id,
        recommendation_reason=explain(ranked),
        warnings=warnings,
    )
    cache.set(_plan_key(plan.id), plan, PLAN_TTL_S)
    return plan


def get_plan(plan_id: str) -> Plan:
    plan = cache.get(_plan_key(plan_id))
    if plan is None:
        raise PlanNotFoundError("plan_not_found", "This plan has expired. Please plan again.")
    return plan


def _plan_key(plan_id: str) -> str:
    return f"plan:{plan_id}"


def _assess(
    position: CheckpointPosition,
    weather: weather_service.WeatherResult,
    window: ForecastWindow,
    load_lb: float,
) -> AssessedCheckpoint:
    hour = window.hour_of(position.eta)
    wx = weather.at(position.coord, hour)
    assessment = assess(wx, load_lb)
    if hour is None:
        assessment = replace(assessment, reason="Arrival is beyond the 48-hour forecast")
    return AssessedCheckpoint(position=position, weather=wx, assessment=assessment)


def _risk_warnings(routes: list[PlannedRoute]) -> list[str]:
    warnings = []
    if routes and all(r.summary.has_no_travel for r in routes):
        warnings.append(
            "Every route passes through No Travel conditions. Consider a later departure."
        )
    unknown = [r.name for r in routes if r.summary.unknown_miles > 0]
    if unknown:
        warnings.append(
            f"Weather is unknown for part of {', '.join(unknown)}; those miles are not scored."
        )
    return warnings
