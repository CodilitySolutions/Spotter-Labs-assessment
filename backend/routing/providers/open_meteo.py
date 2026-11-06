"""Open-Meteo hourly forecasts: primary weather provider. Free, no key.

Requests ask for mph and inches directly, so values map straight onto the risk rules. Each
hourly value is the total for that hour, i.e. already a rate in inches per hour.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import batched
from typing import Any

from ..domain.models import LonLat, Weather
from .base import ProviderError, request_json

PROVIDER = "open-meteo"
URL = "https://api.open-meteo.com/v1/forecast"
# Coordinates per request. 100 points x 49 hours is ~225 KB and returns in ~1 s.
CHUNK_SIZE = 100
HOURLY_VARS = "wind_speed_10m,wind_direction_10m,wind_gusts_10m,rain,showers,snowfall"

HourlyWeather = dict[int, Weather]
"""Weather keyed by the Unix timestamp (UTC) of the start of each hour."""


def fetch_hourly(points: Sequence[LonLat], start_ts: int, end_ts: int) -> list[HourlyWeather]:
    """Hourly weather from ``start_ts`` to ``end_ts`` (inclusive, rounded to whole hours)
    for each point. The result has one entry per point, in the same order.
    """
    out: list[HourlyWeather] = []
    for chunk in batched(points, CHUNK_SIZE, strict=False):  # last chunk may be short
        data = request_json(
            PROVIDER,
            URL,
            params={
                "latitude": ",".join(f"{lat:.4f}" for _, lat in chunk),
                "longitude": ",".join(f"{lon:.4f}" for lon, _ in chunk),
                "hourly": HOURLY_VARS,
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "timeformat": "unixtime",
                "timezone": "GMT",
                "start_hour": _hour_param(start_ts),
                "end_hour": _hour_param(end_ts),
            },
        )
        # One location comes back as an object, several as a list.
        items = data if isinstance(data, list) else [data]
        if len(items) != len(chunk):
            raise ProviderError(PROVIDER, f"expected {len(chunk)} locations, got {len(items)}")
        out.extend(_parse_location(item) for item in items)
    return out


def _hour_param(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:00")


def _parse_location(item: dict[str, Any]) -> HourlyWeather:
    hourly = item.get("hourly")
    if not hourly or "time" not in hourly:
        raise ProviderError(PROVIDER, "response has no hourly data")

    def column(name: str) -> list[float | None]:
        values = hourly.get(name)
        return values if values is not None else [None] * len(hourly["time"])

    wind, gust = column("wind_speed_10m"), column("wind_gusts_10m")
    wind_dir = column("wind_direction_10m")
    rain, showers, snow = column("rain"), column("showers"), column("snowfall")

    return {
        int(ts): Weather(
            wind_mph=wind[i],
            rain_in_hr=_liquid_rate(rain[i], showers[i]),
            snow_in_hr=snow[i],
            gust_mph=gust[i],
            wind_dir_deg=wind_dir[i],
            source=PROVIDER,
        )
        for i, ts in enumerate(hourly["time"])
    }


def _liquid_rate(rain: float | None, showers: float | None) -> float | None:
    """Open-Meteo splits liquid precipitation into large-scale ``rain`` and convective
    ``showers``; both count as rain. Missing ``showers`` alone is treated as none.
    """
    if rain is None:
        return None
    return rain + (showers or 0.0)
