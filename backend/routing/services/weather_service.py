"""Hourly weather for many places over the fixed 0-48 h forecast window.

Places are snapped to 0.1-degree cells (at most ~4 mi away, close to the forecast models'
own resolution). Each cell's whole 49-hour window is cached for an hour, so checkpoints of
different routes, repeated plans and the heatmap all share one cache.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import batched

from django.core.cache import cache

from ..domain.models import LonLat, Weather
from ..providers import nws, open_meteo
from ..providers.base import ProviderError
from .errors import UpstreamUnavailableError

log = logging.getLogger(__name__)

WINDOW_HOURS = 48
CELL_DEG = 0.1
WEATHER_TTL_S = 3600
OPEN_METEO_WORKERS = 4
NWS_WORKERS = 8

Cell = tuple[float, float]
HourlyWeather = dict[int, Weather]


@dataclass(frozen=True)
class ForecastWindow:
    """Hours ``start .. start + 48 h`` (inclusive), starting at the current UTC hour."""

    start: int

    @classmethod
    def current(cls, now: float | None = None) -> ForecastWindow:
        ts = int(now if now is not None else time.time())
        return cls(start=ts - ts % 3600)

    @property
    def end(self) -> int:
        return self.start + WINDOW_HOURS * 3600

    def hour_of(self, ts: int) -> int | None:
        """The forecast hour containing ``ts``, or ``None`` if it's outside the window."""
        hour = ts - ts % 3600
        return hour if self.start <= hour <= self.end else None


@dataclass
class WeatherResult:
    by_cell: dict[Cell, HourlyWeather]
    warnings: list[str] = field(default_factory=list)

    def at(self, point: LonLat, hour: int | None) -> Weather | None:
        if hour is None:
            return None
        return self.by_cell.get(to_cell(point), {}).get(hour)


def to_cell(point: LonLat) -> Cell:
    return (round(point[0] / CELL_DEG) * CELL_DEG, round(point[1] / CELL_DEG) * CELL_DEG)


def _cell_key(cell: Cell, window: ForecastWindow) -> str:
    # "wx2": Weather gained wind_dir_deg; entries cached before that must not be read.
    return f"wx2:{window.start}:{cell[0]:.1f}:{cell[1]:.1f}"


def get_weather(
    points: Iterable[LonLat], window: ForecastWindow, *, allow_nws_fallback: bool = True
) -> WeatherResult:
    """Weather for every point's cell across the window.

    Missing cells are fetched from Open-Meteo in parallel batches. If Open-Meteo fails, cells
    fall back to NWS one by one (US only; slower, so only for small sets like checkpoints).
    Cells that no provider could serve are simply absent, and read back as Unknown.
    """
    cells = sorted({to_cell(p) for p in points})
    result = WeatherResult(by_cell=_read_cache(cells, window))
    missing = [c for c in cells if c not in result.by_cell]
    if not missing:
        return result

    try:
        fetched = _fetch_open_meteo(missing, window)
    except ProviderError:
        log.warning("Open-Meteo failed for %d cells", len(missing), exc_info=True)
        if not allow_nws_fallback:
            raise UpstreamUnavailableError(
                "weather_unavailable", "Weather data is unavailable. Please try again shortly."
            ) from None
        fetched = _fetch_nws(missing, window)
        result.warnings.append(
            "The primary weather service is unavailable. US checkpoints use the National "
            "Weather Service instead; elsewhere weather is unknown."
        )
        if not fetched:
            raise UpstreamUnavailableError(
                "weather_unavailable", "Weather data is unavailable. Please try again shortly."
            ) from None

    result.by_cell.update(fetched)
    _write_cache(fetched, window)
    return result


def _read_cache(cells: Sequence[Cell], window: ForecastWindow) -> dict[Cell, HourlyWeather]:
    keys = {_cell_key(c, window): c for c in cells}
    try:
        hits = cache.get_many(list(keys))
    except Exception:
        log.warning("weather cache read failed", exc_info=True)
        return {}
    return {keys[k]: v for k, v in hits.items()}


def _write_cache(by_cell: dict[Cell, HourlyWeather], window: ForecastWindow) -> None:
    try:
        cache.set_many({_cell_key(c, window): s for c, s in by_cell.items()}, WEATHER_TTL_S)
    except Exception:
        log.warning("weather cache write failed", exc_info=True)


def _fetch_open_meteo(cells: Sequence[Cell], window: ForecastWindow) -> dict[Cell, HourlyWeather]:
    chunks = [list(c) for c in batched(cells, open_meteo.CHUNK_SIZE, strict=False)]

    def fetch(chunk: list[Cell]) -> list[HourlyWeather]:
        return open_meteo.fetch_hourly(chunk, window.start, window.end)

    with ThreadPoolExecutor(max_workers=OPEN_METEO_WORKERS) as pool:
        results = list(pool.map(fetch, chunks))  # re-raises the first ProviderError
    return {
        cell: series
        for chunk, chunk_series in zip(chunks, results, strict=True)
        for cell, series in zip(chunk, chunk_series, strict=True)
    }


def _fetch_nws(cells: Sequence[Cell], window: ForecastWindow) -> dict[Cell, HourlyWeather]:
    # NWS only forecasts for the US; elsewhere these cells stay Unknown without a request.
    cells = [c for c in cells if nws.covers(c)]

    def fetch(cell: Cell) -> tuple[Cell, HourlyWeather | None]:
        try:
            return cell, nws.fetch_hourly(cell, window.start, window.end)
        except ProviderError:
            log.info("NWS failed for cell %s", cell, exc_info=True)
            return cell, None

    with ThreadPoolExecutor(max_workers=NWS_WORKERS) as pool:
        return {cell: s for cell, s in pool.map(fetch, cells) if s is not None}
