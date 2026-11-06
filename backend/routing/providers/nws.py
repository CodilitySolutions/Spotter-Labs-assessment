"""US National Weather Service gridpoint forecasts: weather fallback (US only). Free, no key.

NWS reports values in SI units over windows of 1-12 hours, e.g. "6 mm of precipitation
from 06:00 for 6 hours". This module converts them to mph and inches per hour and spreads
each window evenly over its hours.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..domain.models import LonLat, Weather
from .base import ProviderError, cache_key, cached, request_json

PROVIDER = "nws"
BASE_URL = "https://api.weather.gov"
# A point's forecast grid cell never changes.
POINTS_TTL_S = 7 * 24 * 3600

MPH_PER = {"wmoUnit:km_h-1": 0.621371, "wmoUnit:m_s-1": 2.236936}
INCHES_PER = {"wmoUnit:mm": 1 / 25.4, "wmoUnit:cm": 1 / 2.54, "wmoUnit:m": 39.3701}
# Snow-to-liquid ratio used to remove snow's water content from total precipitation.
SNOW_TO_LIQUID = 10

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")

HourlyWeather = dict[int, Weather]

# Rough boxes around the areas NWS forecasts (lon_min, lat_min, lon_max, lat_max): the lower
# 48, Alaska, Hawaii and Puerto Rico. Anything outside is skipped without a request.
COVERAGE = (
    (-125.0, 24.0, -66.5, 49.5),
    (-170.0, 51.0, -129.0, 71.5),
    (-161.0, 18.5, -154.5, 22.5),
    (-67.5, 17.5, -65.0, 18.6),
)


def covers(point: LonLat) -> bool:
    lon, lat = point
    return any(x0 <= lon <= x1 and y0 <= lat <= y1 for x0, y0, x1, y1 in COVERAGE)


def fetch_hourly(point: LonLat, start_ts: int, end_ts: int) -> HourlyWeather:
    """Hourly weather at one point from ``start_ts`` to ``end_ts`` (inclusive)."""
    props = request_json(PROVIDER, _grid_url(point), headers={"Accept": "application/geo+json"})[
        "properties"
    ]

    start = start_ts - start_ts % 3600
    hours = range(start, end_ts + 1, 3600)
    wind = _hourly_values(props.get("windSpeed"), MPH_PER, per_hour=False)
    gust = _hourly_values(props.get("windGust"), MPH_PER, per_hour=False)
    precip = _hourly_values(props.get("quantitativePrecipitation"), INCHES_PER, per_hour=True)
    snow = _hourly_values(props.get("snowfallAmount"), INCHES_PER, per_hour=True)

    return {
        ts: Weather(
            wind_mph=wind.get(ts),
            rain_in_hr=_rain_rate(precip.get(ts), snow.get(ts)),
            snow_in_hr=snow.get(ts),
            gust_mph=gust.get(ts),
            source=PROVIDER,
        )
        for ts in hours
    }


def _grid_url(point: LonLat) -> str:
    lon, lat = point
    key = cache_key("nws:points", round(lat, 4), round(lon, 4))

    def fetch() -> str:
        data = request_json(
            PROVIDER,
            f"{BASE_URL}/points/{lat:.4f},{lon:.4f}",
            headers={"Accept": "application/geo+json"},
        )
        try:
            return data["properties"]["forecastGridData"]
        except (KeyError, TypeError) as exc:
            raise ProviderError(PROVIDER, "point lookup returned no forecast grid") from exc

    return cached(key, POINTS_TTL_S, fetch)


def _rain_rate(precip: float | None, snow: float | None) -> float | None:
    """Total precipitation includes melted snow; subtract it so snow isn't counted as rain."""
    if precip is None:
        return None
    return max(precip - (snow or 0.0) / SNOW_TO_LIQUID, 0.0)


def _hourly_values(
    series: dict[str, Any] | None, factors: dict[str, float], *, per_hour: bool
) -> dict[int, float]:
    """Expand ``[{"validTime": "<start>/<duration>", "value": v}, ...]`` to one value per hour.

    With ``per_hour``, ``v`` is a total over the window and is divided by its length in hours;
    otherwise ``v`` (e.g. a wind speed) applies to every hour of the window.
    """
    if not series:
        return {}
    unit = series.get("uom")
    if unit not in factors:
        raise ProviderError(PROVIDER, f"unexpected unit {unit!r}")
    factor = factors[unit]

    out: dict[int, float] = {}
    for entry in series.get("values", []):
        if entry.get("value") is None:
            continue
        start_s, duration_s = entry["validTime"].split("/")
        start = int(datetime.fromisoformat(start_s).timestamp())
        n_hours = max(1, round(_duration_hours(duration_s)))
        value = entry["value"] * factor / (n_hours if per_hour else 1)
        for h in range(n_hours):
            out[start + h * 3600] = value
    return out


def _duration_hours(iso: str) -> float:
    match = _DURATION.match(iso)
    if not match:
        raise ProviderError(PROVIDER, f"unexpected duration {iso!r}")
    days, hours, minutes = (int(g) if g else 0 for g in match.groups())
    return days * 24 + hours + minutes / 60
