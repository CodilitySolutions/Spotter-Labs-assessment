"""Small builders for synthetic routes, weather and plan requests used across tests."""

from datetime import UTC, datetime

from django.test import Client

from routing.domain.geometry import MI_PER_DEG_LAT, cumulative_distances
from routing.domain.models import RouteCandidate, TimelinePoint, Weather

ORIGIN = (-100.0, 35.0)


def candidate(
    lon_offset: float = 0.0,
    miles: float = 100,
    hours: float = 2,
    source: str = "tomtom",
    fallback: bool = False,
) -> RouteCandidate:
    """A straight northbound route; ``lon_offset`` (degrees) makes a parallel, distinct one."""
    geometry = tuple(
        (ORIGIN[0] + lon_offset, ORIGIN[1] + miles * k / 20 / MI_PER_DEG_LAT) for k in range(21)
    )
    length = cumulative_distances(geometry)[-1]
    return RouteCandidate(
        source=source,
        geometry=geometry,
        distance_mi=length,
        duration_s=hours * 3600,
        timeline=(TimelinePoint(0, 0), TimelinePoint(length, hours * 3600)),
        is_fallback_profile=fallback,
    )


def calm(source: str = "open-meteo") -> Weather:
    return Weather(wind_mph=5, rain_in_hr=0, snow_in_hr=0, gust_mph=8, source=source)


# --- Plan API helpers ------------------------------------------------------------------------

NOW = 1_800_000_000 - 1_800_000_000 % 3600 + 600  # 10 minutes past an hour


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat()


def body(**overrides):
    """A valid POST /api/plan body for the ``stubbed`` fixture's 100-mile trip."""
    data = {
        "origin": {"lat": 35.0, "lon": -100.0, "label": "Origin"},
        "destination": {"lat": 36.45, "lon": -100.0, "label": "Destination"},
        "departure_time": iso(NOW),
        "load_weight_lb": 42_000,
        "checkpoint_interval_mi": 25,
    }
    data.update(overrides)
    return data


def post(data):
    return Client().post("/api/plan", data, content_type="application/json")
