"""Cell-based weather lookup, caching and the NWS fallback."""

import pytest

from routing.providers.base import ProviderError
from routing.services import weather_service
from routing.services.errors import UpstreamUnavailableError
from routing.services.weather_service import ForecastWindow, to_cell

from .factories import calm

WINDOW = ForecastWindow(start=1_800_000_000 - 1_800_000_000 % 3600)


def series(source: str = "open-meteo"):
    return {WINDOW.start + h * 3600: calm(source) for h in range(49)}


@pytest.fixture
def providers(monkeypatch):
    log = {"open_meteo": [], "nws": []}
    state = {"open_meteo_error": None, "nws_fails_for": set()}

    def open_meteo(points, start, end):
        log["open_meteo"].append(list(points))
        if state["open_meteo_error"]:
            raise state["open_meteo_error"]
        return [series() for _ in points]

    def nws(point, start, end):
        log["nws"].append(point)
        if point in state["nws_fails_for"]:
            raise ProviderError("nws", "404")
        return series("nws")

    monkeypatch.setattr(weather_service.open_meteo, "fetch_hourly", open_meteo)
    monkeypatch.setattr(weather_service.nws, "fetch_hourly", nws)
    return log, state


def test_forecast_window() -> None:
    window = ForecastWindow.current(now=WINDOW.start + 1234)

    assert window.start == WINDOW.start
    assert window.end == WINDOW.start + 48 * 3600
    assert window.hour_of(WINDOW.start + 3599) == WINDOW.start
    assert window.hour_of(window.end + 10) == window.end
    assert window.hour_of(window.end + 3600) is None
    assert window.hour_of(WINDOW.start - 1) is None


def test_nearby_points_share_a_cell_and_one_request(providers) -> None:
    log, _ = providers
    points = [(-100.01, 35.01), (-100.02, 34.98), (-99.5, 35.5)]

    result = weather_service.get_weather(points, WINDOW)

    assert len(log["open_meteo"]) == 1
    assert len(log["open_meteo"][0]) == 2  # two distinct cells
    assert result.at(points[0], WINDOW.start) == calm()
    assert result.at(points[0], None) is None


def test_cells_are_cached_between_calls(providers) -> None:
    log, _ = providers
    weather_service.get_weather([(-100, 35)], WINDOW)
    weather_service.get_weather([(-100, 35), (-99, 36)], WINDOW)

    assert [len(c) for c in log["open_meteo"]] == [1, 1]  # second call fetches only the new cell


def test_large_sets_are_split_into_parallel_batches(providers) -> None:
    log, _ = providers
    points = [(-100 + i * 0.2, 35.0) for i in range(150)]

    result = weather_service.get_weather(points, WINDOW)

    assert sorted(len(c) for c in log["open_meteo"]) == [50, 100]
    assert len(result.by_cell) == 150


def test_falls_back_to_nws_per_cell(providers) -> None:
    log, state = providers
    state["open_meteo_error"] = ProviderError("open-meteo", "HTTP 503")
    state["nws_fails_for"] = {to_cell((-99.0, 36.0))}

    result = weather_service.get_weather([(-100, 35), (-99, 36)], WINDOW)

    assert len(log["nws"]) == 2
    assert result.at((-100, 35), WINDOW.start).source == "nws"
    assert result.at((-99, 36), WINDOW.start) is None  # NWS failed too -> Unknown
    assert "National Weather Service" in result.warnings[0]


def test_no_fallback_when_disallowed(providers) -> None:
    _, state = providers
    state["open_meteo_error"] = ProviderError("open-meteo", "HTTP 503")

    with pytest.raises(UpstreamUnavailableError):
        weather_service.get_weather([(-100, 35)], WINDOW, allow_nws_fallback=False)


def test_all_weather_providers_down(providers) -> None:
    _, state = providers
    state["open_meteo_error"] = ProviderError("open-meteo", "HTTP 503")
    state["nws_fails_for"] = {to_cell((-100, 35))}

    with pytest.raises(UpstreamUnavailableError):
        weather_service.get_weather([(-100, 35)], WINDOW)


def test_nws_fallback_skips_cells_outside_the_us(providers) -> None:
    log, state = providers
    state["open_meteo_error"] = ProviderError("open-meteo", "HTTP 503")
    lahore, chicago = (74.3, 31.5), (-87.6, 41.9)

    result = weather_service.get_weather([lahore, chicago], WINDOW)

    assert log["nws"] == [to_cell(chicago)]  # no request for Lahore
    assert result.at(lahore, WINDOW.start) is None
    assert result.at(chicago, WINDOW.start).source == "nws"
