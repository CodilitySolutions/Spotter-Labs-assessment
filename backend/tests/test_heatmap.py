"""GET /api/plan/{id}/heatmap, with providers stubbed."""

import pytest
from django.test import Client

from routing.domain.geometry import haversine_mi, resample
from routing.domain.models import Weather
from routing.providers.base import ProviderError
from routing.services import heatmap_service, weather_service

from .factories import NOW, body, post


@pytest.fixture
def plan(stubbed):
    response = post(body(load_weight_lb=35_000))
    assert response.status_code == 200
    return response.json()


def get_heatmap(plan_id: str):
    return Client().get(f"/api/plan/{plan_id}/heatmap")


def test_heatmap_shape(plan) -> None:
    response = get_heatmap(plan["plan_id"])

    assert response.status_code == 200
    hm = response.json()
    assert hm["plan_id"] == plan["plan_id"]
    assert hm["start_hour"] == plan["forecast_window"]["start"] == NOW - NOW % 3600
    assert hm["hours"] == 49
    assert hm["step_s"] == 3600
    assert hm["spacing_mi"] > 0
    assert len(hm["scores"]) == len(hm["points"])
    assert 0.75 * heatmap_service.TARGET_POINTS <= len(hm["points"]) <= 1.25 * 300
    assert all(len(row) == 49 for row in hm["scores"])


def test_heatmap_covers_the_corridor_of_every_route(plan) -> None:
    hm = get_heatmap(plan["plan_id"]).json()
    route_samples = [p for r in plan["routes"] for p in resample(r["geometry"], 2)]

    for lon, lat in hm["points"]:
        nearest = min(haversine_mi((lon, lat), q) for q in route_samples)
        assert nearest <= heatmap_service.CORRIDOR_MI + 1


def test_heatmap_scores_apply_risk_and_load_rules(plan) -> None:
    hm = get_heatmap(plan["plan_id"]).json()
    # The stub puts 50 mph wind over Route A's north half; with a 35,000 lb load that is
    # No Travel (4). Everything else is calm (0).
    values = {score for row in hm["scores"] for score in row}

    assert values == {0, 4}


def test_heatmap_is_cached(plan, monkeypatch) -> None:
    get_heatmap(plan["plan_id"])

    def fail(*args, **kwargs):
        raise AssertionError("weather should come from the cache")

    monkeypatch.setattr(weather_service.open_meteo, "fetch_hourly", fail)
    assert get_heatmap(plan["plan_id"]).status_code == 200


def test_unknown_weather_is_null(stubbed, monkeypatch) -> None:
    missing = Weather(wind_mph=None, rain_in_hr=None, snow_in_hr=None)
    monkeypatch.setattr(
        weather_service.open_meteo,
        "fetch_hourly",
        lambda points, start, end: [{start + h * 3600: missing for h in range(49)} for _ in points],
    )
    plan_id = post(body()).json()["plan_id"]

    hm = get_heatmap(plan_id).json()

    assert {s for row in hm["scores"] for s in row} == {None}


def test_unknown_plan_is_404(stubbed) -> None:
    response = get_heatmap("does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "plan_not_found"


def test_weather_outage_is_502_without_nws_fallback(plan, monkeypatch) -> None:
    def down(*args, **kwargs):
        raise ProviderError("open-meteo", "down")

    def nws_must_not_be_called(*args, **kwargs):
        raise AssertionError("NWS is too slow for a whole grid")

    monkeypatch.setattr(weather_service.open_meteo, "fetch_hourly", down)
    monkeypatch.setattr(weather_service.nws, "fetch_hourly", nws_must_not_be_called)

    response = get_heatmap(plan["plan_id"])

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "weather_unavailable"
