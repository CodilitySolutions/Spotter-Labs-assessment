import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from tenacity import wait_none

from routing.domain.models import Weather
from routing.providers import base
from routing.services import plan_service, route_service, weather_service

from .factories import NOW, calm, candidate

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def _isolated_settings(settings: Any) -> Iterator[None]:
    """Every test gets a fresh in-memory cache, a fake API key and no retry delays."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "OPTIONS": {"MAX_ENTRIES": 20_000},
        }
    }
    settings.TOMTOM_API_KEY = "test-key"
    cache.clear()
    original_wait = base.RETRY_WAIT
    base.RETRY_WAIT = wait_none()
    yield
    base.RETRY_WAIT = original_wait


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Providers for a 100-mile northbound trip with three parallel routes.

    Route A (fastest) has 50 mph wind over its north half; everything else is calm.
    The clock is frozen at ``NOW``.
    """
    routes = [candidate(0, hours=2), candidate(0.5, hours=2.5), candidate(-0.5, hours=3)]
    monkeypatch.setattr(route_service.tomtom, "calculate_route", lambda *a, **k: list(routes))

    def weather(points, start, end):
        out = []
        for lon, lat in points:
            windy = abs(lon + 100.0) < 0.05 and lat > 35.7  # Route A's north half
            wx = Weather(wind_mph=50, rain_in_hr=0, snow_in_hr=0) if windy else calm()
            out.append({start + h * 3600: wx for h in range(49)})
        return out

    monkeypatch.setattr(weather_service.open_meteo, "fetch_hourly", weather)
    monkeypatch.setattr(plan_service.time, "time", lambda: NOW)
