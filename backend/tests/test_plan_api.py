"""POST /api/plan and GET /api/geocode end to end, with providers stubbed."""

import pytest
from django.test import Client

from routing.domain.models import Place, Weather
from routing.providers.base import ProviderError
from routing.services import plan_service, weather_service

from .factories import NOW, body, calm, iso, post


def test_plan_recommends_the_safer_route(stubbed) -> None:
    response = post(body(load_weight_lb=20_000))

    assert response.status_code == 200
    plan = response.json()
    assert [r["id"] for r in plan["routes"]] == ["r1", "r2", "r3"]
    a, b, c = plan["routes"]

    # Route A: 50 mph wind at its mile-75 and mile-100 checkpoints, which cover 25 + 12.5 mi.
    assert a["summary"]["severe_miles"] == pytest.approx(37.5, abs=1)
    assert a["summary"]["worst_level"] == "severe"
    assert b["summary"]["severe_miles"] == 0
    # B and C are equally safe; B is faster, so B wins and A ranks last.
    assert plan["recommended_route_id"] == "r2"
    assert [a["summary"]["rank"], b["summary"]["rank"], c["summary"]["rank"]] == [3, 1, 2]
    assert plan["recommendation_reason"] == (
        "Equal weather risk; fastest: 2 h 30 min vs 3 h 00 min on Route C."
    )


def test_load_rules_are_applied(stubbed) -> None:
    # Same weather, but > 30,000 lb in 45-54 mph wind is No Travel.
    plan = post(body(load_weight_lb=42_000)).json()
    a = plan["routes"][0]

    assert a["summary"]["miles_by_level"]["no_travel"] == pytest.approx(37.5, abs=1)
    windy = [cp for cp in a["checkpoints"] if cp["risk"] == "no_travel"]
    assert windy[0]["levels"]["load_override"] == "no_travel"
    assert windy[0]["reason"] == "No Travel: Wind 50 mph with load 42,000 lb > 30,000 lb"


def test_checkpoint_shape_and_etas(stubbed) -> None:
    plan = post(body()).json()
    cps = plan["routes"][0]["checkpoints"]

    assert [cp["mile"] for cp in cps] == pytest.approx([0, 25, 50, 75, 100], abs=0.2)
    assert cps[0]["eta"] == NOW
    assert cps[-1]["eta"] == NOW + 2 * 3600
    assert set(cps[0]) == {
        "index", "mile", "covers_mi", "lon", "lat", "eta",
        "weather", "levels", "risk", "risk_score", "reason",
    }  # fmt: skip
    assert cps[0]["weather"]["source"] == "open-meteo"
    route = plan["routes"][0]
    assert route["arrival_time"] == NOW + 2 * 3600
    assert len(route["geometry"]) >= 2


def test_plan_is_stored_for_the_heatmap(stubbed) -> None:
    plan_id = post(body()).json()["plan_id"]

    assert plan_service.get_plan(plan_id).id == plan_id


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"departure_time": iso(NOW - 3600)}, "departure_in_past"),
        ({"departure_time": iso(NOW + 49 * 3600)}, "departure_beyond_forecast"),
        ({"destination": {"lat": 35.0, "lon": -100.0}}, "same_place"),
    ],
)
def test_trip_validation_errors(stubbed, overrides, code) -> None:
    response = post(body(**overrides))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


def test_trip_ending_beyond_forecast_is_rejected(stubbed) -> None:
    response = post(body(departure_time=iso(NOW + 47 * 3600)))  # +2 h trip ends at ~49 h

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "trip_beyond_forecast"


@pytest.mark.parametrize(
    "overrides",
    [
        {"load_weight_lb": -1},
        {"load_weight_lb": 90_000},
        {"checkpoint_interval_mi": 15},
        {"origin": {"lat": 95, "lon": 0}},
        {"departure_time": "tomorrow"},
    ],
)
def test_invalid_fields(stubbed, overrides) -> None:
    response = post(body(**overrides))

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert set(error["details"]) <= {
        "load_weight_lb", "checkpoint_interval_mi", "origin", "departure_time",
    }  # fmt: skip


def test_total_weather_outage_returns_502(stubbed, monkeypatch) -> None:
    def down(*args, **kwargs):
        raise ProviderError("weather", "down")

    monkeypatch.setattr(weather_service.open_meteo, "fetch_hourly", down)
    monkeypatch.setattr(weather_service.nws, "fetch_hourly", down)

    response = post(body())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "weather_unavailable"


# --- Geocoding -------------------------------------------------------------------------------


def test_geocode_falls_back_to_tomtom(monkeypatch) -> None:
    def photon_down(q, limit=5, near=None):
        raise ProviderError("photon", "down")

    monkeypatch.setattr("routing.api.views.photon.geocode", photon_down)
    monkeypatch.setattr(
        "routing.api.views.tomtom.geocode",
        lambda q, limit=5, near=None: [Place("Denver, CO", -104.98, 39.74)],
    )

    response = Client().get("/api/geocode", {"q": "Denver"})

    assert response.status_code == 200
    assert response.json() == [{"label": "Denver, CO", "lat": 39.74, "lon": -104.98}]


def test_geocode_requires_a_query() -> None:
    response = Client().get("/api/geocode", {"q": "a"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_warns_when_every_route_has_no_travel(stubbed, monkeypatch) -> None:
    storm = Weather(wind_mph=60, rain_in_hr=0, snow_in_hr=0)
    monkeypatch.setattr(
        weather_service.open_meteo,
        "fetch_hourly",
        lambda points, start, end: [{start + h * 3600: storm for h in range(49)} for _ in points],
    )

    plan = post(body()).json()

    assert all(r["summary"]["worst_level"] == "no_travel" for r in plan["routes"])
    assert "Every route passes through No Travel conditions" in plan["warnings"][0]
    assert plan["recommended_route_id"] == "r1"  # all equally bad -> fastest


def test_geocode_passes_the_map_centre_as_bias(monkeypatch) -> None:
    seen = {}

    def photon_geocode(q, limit=5, near=None):
        seen["near"] = near
        return [Place("Hyderabad, Sindh, Pakistan", 68.37, 25.39)]

    monkeypatch.setattr("routing.api.views.photon.geocode", photon_geocode)

    response = Client().get("/api/geocode", {"q": "Hyderabad", "lat": 30.4, "lon": 69.3})

    assert response.status_code == 200
    assert seen["near"] == (69.3, 30.4)
    assert response.json()[0]["label"] == "Hyderabad, Sindh, Pakistan"


def test_geocode_bias_needs_both_coordinates() -> None:
    response = Client().get("/api/geocode", {"q": "Lahore", "lat": 31.5})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_weather_at_departure_counts_against_the_route(stubbed, monkeypatch) -> None:
    """Regression: a route starting in severe weather must not be summarised as all Low."""

    def storm_at_origin(points, start, end):
        out = []
        for _lon, lat in points:
            severe = lat < 35.05  # only the departure area
            wx = Weather(wind_mph=50, rain_in_hr=0, snow_in_hr=0) if severe else calm()
            out.append({start + h * 3600: wx for h in range(49)})
        return out

    monkeypatch.setattr(weather_service.open_meteo, "fetch_hourly", storm_at_origin)

    plan = post(body(load_weight_lb=20_000)).json()

    for route in plan["routes"]:
        assert route["checkpoints"][0]["risk"] == "severe"
        assert route["summary"]["worst_level"] == "severe"
        # The origin checkpoint covers the first half-interval (12.5 of 25 miles).
        assert route["summary"]["severe_miles"] == pytest.approx(12.5, abs=0.5)
