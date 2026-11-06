"""Provider parsing and failure handling, against recorded real responses (no network)."""

import time
from datetime import UTC, datetime

import httpx
import pytest
import respx

from routing.domain.geometry import cumulative_distances
from routing.providers import base, nws, open_meteo, osrm, photon, tomtom
from routing.providers.base import NoRouteError, ProviderError

from .conftest import load_fixture

CHICAGO = (-87.6298, 41.8781)
MILWAUKEE = (-87.9065, 43.0389)
TOMTOM_ROUTE = "https://api.tomtom.com/routing/1/calculateRoute/"
NOW = int(time.time())


@pytest.fixture
def mock() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        yield router


# --- Shared HTTP behaviour -----------------------------------------------------------------


def test_retries_transient_errors_then_succeeds(mock: respx.MockRouter) -> None:
    route = mock.get("https://example.test/x").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )

    assert base.request_json("test", "https://example.test/x") == {"ok": True}
    assert route.call_count == 2


def test_gives_up_after_max_attempts(mock: respx.MockRouter) -> None:
    route = mock.get("https://example.test/x").mock(side_effect=httpx.ConnectTimeout("slow"))

    with pytest.raises(ProviderError, match="timed out"):
        base.request_json("test", "https://example.test/x")
    assert route.call_count == base.MAX_ATTEMPTS


def test_client_errors_are_not_retried(mock: respx.MockRouter) -> None:
    route = mock.get("https://example.test/x").mock(
        return_value=httpx.Response(400, json={"reason": "bad"})
    )

    with pytest.raises(ProviderError) as info:
        base.request_json("test", "https://example.test/x")
    assert route.call_count == 1
    assert info.value.status == 400
    assert info.value.body == {"reason": "bad"}


def test_error_messages_never_contain_the_url(mock: respx.MockRouter) -> None:
    mock.get(url__startswith=TOMTOM_ROUTE).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ProviderError) as info:
        tomtom.calculate_route(CHICAGO, MILWAUKEE, depart_at=NOW, load_lb=0)
    assert "test-key" not in str(info.value)


def test_cached_skips_fetch_on_hit() -> None:
    calls = []

    def fetch() -> int:
        calls.append(1)
        return 42

    assert base.cached("k", 60, fetch) == 42
    assert base.cached("k", 60, fetch) == 42
    assert len(calls) == 1


# --- TomTom routing -------------------------------------------------------------------------


def test_tomtom_route_parses_all_alternatives(mock: respx.MockRouter) -> None:
    mock.get(url__startswith=TOMTOM_ROUTE).mock(
        return_value=httpx.Response(200, json=load_fixture("tomtom_route"))
    )

    routes = tomtom.calculate_route(
        CHICAGO, MILWAUKEE, depart_at=NOW, load_lb=20_000, max_alternatives=2
    )

    assert len(routes) == 3
    for r in routes:
        assert r.source == "tomtom"
        assert not r.is_fallback_profile
        assert len(r.geometry) > 100
        # Our measured polyline length agrees with TomTom's reported length.
        assert cumulative_distances(r.geometry)[-1] == pytest.approx(r.distance_mi, rel=0.02)
        # The timeline starts at zero, ends at the route totals and never goes backwards.
        tl = r.timeline
        assert (tl[0].distance_mi, tl[0].elapsed_s) == (0, 0)
        assert tl[-1].distance_mi == pytest.approx(r.distance_mi)
        assert tl[-1].elapsed_s == r.duration_s
        assert all(a.distance_mi <= b.distance_mi for a, b in zip(tl, tl[1:], strict=False))
        assert all(a.elapsed_s <= b.elapsed_s for a, b in zip(tl, tl[1:], strict=False))


def test_tomtom_route_sends_truck_parameters(mock: respx.MockRouter) -> None:
    call = mock.get(url__startswith=TOMTOM_ROUTE).mock(
        return_value=httpx.Response(200, json=load_fixture("tomtom_route"))
    )
    departure = NOW + 3 * 3600

    tomtom.calculate_route(
        CHICAGO, MILWAUKEE, depart_at=departure, load_lb=20_000, max_alternatives=5
    )

    params = call.calls.last.request.url.params
    assert call.calls.last.request.url.path.endswith(
        "/41.878100,-87.629800:43.038900,-87.906500/json"
    )
    assert params["travelMode"] == "truck"
    assert params["vehicleWeight"] == str(round(55_000 * 0.45359237))  # 35,000 lb truck + load
    assert params["maxAlternatives"] == "5"
    assert params["departAt"] == datetime.fromtimestamp(departure, UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def test_tomtom_departure_in_the_past_becomes_now(mock: respx.MockRouter) -> None:
    call = mock.get(url__startswith=TOMTOM_ROUTE).mock(
        return_value=httpx.Response(200, json=load_fixture("tomtom_route"))
    )

    tomtom.calculate_route(CHICAGO, MILWAUKEE, depart_at=NOW - 600, load_lb=0)

    assert call.calls.last.request.url.params["departAt"] == "now"


def test_tomtom_via_route_joins_legs_without_duplicate_point(mock: respx.MockRouter) -> None:
    fixture = load_fixture("tomtom_route_via")
    mock.get(url__startswith=TOMTOM_ROUTE).mock(return_value=httpx.Response(200, json=fixture))

    [route] = tomtom.calculate_route(
        CHICAGO, MILWAUKEE, depart_at=NOW, load_lb=0, via=[(-88.3, 42.5)]
    )

    legs = fixture["routes"][0]["legs"]
    assert len(legs) == 2
    assert len(route.geometry) == len(legs[0]["points"]) + len(legs[1]["points"]) - 1
    assert (
        len(set(zip(route.geometry, route.geometry[1:], strict=False))) == len(route.geometry) - 1
    )


def test_tomtom_no_route_is_a_distinct_error(mock: respx.MockRouter) -> None:
    mock.get(url__startswith=TOMTOM_ROUTE).mock(
        return_value=httpx.Response(
            400, json={"detailedError": {"code": "NO_ROUTE_FOUND", "message": "..."}}
        )
    )

    with pytest.raises(NoRouteError):
        tomtom.calculate_route(CHICAGO, (-0.12, 51.5), depart_at=NOW, load_lb=0)


def test_tomtom_bad_key_is_a_provider_error(mock: respx.MockRouter) -> None:
    mock.get(url__startswith=TOMTOM_ROUTE).mock(return_value=httpx.Response(401, json={}))

    with pytest.raises(ProviderError) as info:
        tomtom.calculate_route(CHICAGO, MILWAUKEE, depart_at=NOW, load_lb=0)
    assert not isinstance(info.value, NoRouteError)
    assert info.value.status == 401


def test_tomtom_requires_api_key(settings) -> None:
    settings.TOMTOM_API_KEY = ""

    with pytest.raises(ProviderError, match="not configured"):
        tomtom.calculate_route(CHICAGO, MILWAUKEE, depart_at=NOW, load_lb=0)


# --- Geocoding -----------------------------------------------------------------------------


def test_tomtom_geocode_parses_and_caches(mock: respx.MockRouter) -> None:
    call = mock.get(url__startswith="https://api.tomtom.com/search/2/search/").mock(
        return_value=httpx.Response(200, json=load_fixture("tomtom_geocode"))
    )

    places = tomtom.geocode("Denver", limit=3)
    again = tomtom.geocode("  denver ", limit=3)

    assert places[0].label == "Denver, CO, United States"
    assert places[0].lat == pytest.approx(39.74, abs=0.05)
    assert places[0].lon == pytest.approx(-104.98, abs=0.05)
    assert again == places
    assert call.call_count == 1


def test_photon_geocode_builds_readable_labels(mock: respx.MockRouter) -> None:
    mock.get("https://photon.komoot.io/api/").mock(
        return_value=httpx.Response(200, json=load_fixture("photon_geocode"))
    )

    places = photon.geocode("Denver", limit=3)

    assert places
    assert places[0].label.startswith("Denver")
    assert "United States" in places[0].label
    assert places[0].lat == pytest.approx(39.74, abs=0.1)


def test_empty_query_makes_no_request(mock: respx.MockRouter) -> None:
    assert tomtom.geocode("   ") == []
    assert photon.geocode("") == []
    assert not mock.calls


# --- OSRM ----------------------------------------------------------------------------------


def test_osrm_route_is_flagged_as_car_profile(mock: respx.MockRouter) -> None:
    mock.get(url__startswith="https://router.project-osrm.org/").mock(
        return_value=httpx.Response(200, json=load_fixture("osrm_route"))
    )

    routes = osrm.route(CHICAGO, MILWAUKEE)

    assert routes
    r = routes[0]
    assert r.source == "osrm"
    assert r.is_fallback_profile
    assert cumulative_distances(r.geometry)[-1] == pytest.approx(r.distance_mi, rel=0.02)
    assert r.timeline[-1].elapsed_s == pytest.approx(r.duration_s, abs=1)
    assert r.timeline[-1].distance_mi == pytest.approx(r.distance_mi, rel=0.001)


def test_osrm_no_route(mock: respx.MockRouter) -> None:
    mock.get(url__startswith="https://router.project-osrm.org/").mock(
        return_value=httpx.Response(400, json={"code": "NoRoute", "message": "Impossible route"})
    )

    with pytest.raises(NoRouteError):
        osrm.route(CHICAGO, (-0.12, 51.5))


# --- Open-Meteo ----------------------------------------------------------------------------


def test_open_meteo_multi_location_keeps_order_and_units(mock: respx.MockRouter) -> None:
    fixture = load_fixture("open_meteo_multi")
    call = mock.get(open_meteo.URL).mock(return_value=httpx.Response(200, json=fixture))
    start = fixture[0]["hourly"]["time"][0]

    series = open_meteo.fetch_hourly([CHICAGO, MILWAUKEE], start, start + 5 * 3600)

    assert len(series) == 2
    assert sorted(series[0]) == fixture[0]["hourly"]["time"]
    first = series[1][start]
    hourly = fixture[1]["hourly"]
    assert first.wind_mph == hourly["wind_speed_10m"][0]
    assert first.rain_in_hr == pytest.approx(hourly["rain"][0] + hourly["showers"][0])
    assert first.snow_in_hr == hourly["snowfall"][0]
    assert first.source == "open-meteo"
    params = call.calls.last.request.url.params
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["latitude"] == "41.8781,43.0389"


def test_open_meteo_single_location_object_is_handled(mock: respx.MockRouter) -> None:
    fixture = load_fixture("open_meteo_single")
    mock.get(open_meteo.URL).mock(return_value=httpx.Response(200, json=fixture))
    start = fixture["hourly"]["time"][0]

    [series] = open_meteo.fetch_hourly([CHICAGO], start, start + 5 * 3600)

    assert len(series) == len(fixture["hourly"]["time"])


def _om_item(times: list[int], **cols: list) -> dict:
    return {"hourly": {"time": times, **cols}}


def test_open_meteo_sums_rain_and_showers_and_keeps_nulls(mock: respx.MockRouter) -> None:
    item = _om_item(
        [0, 3600],
        wind_speed_10m=[10, None],
        wind_direction_10m=[270, None],
        wind_gusts_10m=[20, None],
        rain=[0.1, None],
        showers=[0.2, 0.3],
        snowfall=[0, 0],
    )
    mock.get(open_meteo.URL).mock(return_value=httpx.Response(200, json=item))

    [series] = open_meteo.fetch_hourly([CHICAGO], 0, 3600)

    assert series[0].rain_in_hr == pytest.approx(0.3)
    assert series[0].wind_dir_deg == 270  # wind from the west
    assert series[3600].wind_mph is None  # stays missing -> assessed as Unknown
    assert series[3600].rain_in_hr is None


def test_open_meteo_splits_large_requests(mock: respx.MockRouter) -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        n = len(request.url.params["latitude"].split(","))
        return httpx.Response(200, json=[_om_item([0], rain=[0], snowfall=[0])] * n)

    call = mock.get(open_meteo.URL).mock(side_effect=reply)
    points = [(-100 + i * 0.01, 40.0) for i in range(open_meteo.CHUNK_SIZE + 50)]

    series = open_meteo.fetch_hourly(points, 0, 0)

    assert call.call_count == 2
    assert len(series) == len(points)


def test_open_meteo_wrong_location_count_is_an_error(mock: respx.MockRouter) -> None:
    mock.get(open_meteo.URL).mock(
        return_value=httpx.Response(200, json=[_om_item([0], rain=[0], snowfall=[0])])
    )

    with pytest.raises(ProviderError, match="expected 2 locations"):
        open_meteo.fetch_hourly([CHICAGO, MILWAUKEE], 0, 0)


# --- NWS -------------------------------------------------------------------------------------


def _mock_nws(mock: respx.MockRouter, grid: dict) -> None:
    mock.get(url__startswith="https://api.weather.gov/points/").mock(
        return_value=httpx.Response(200, json=load_fixture("nws_points"))
    )
    mock.get(url__startswith="https://api.weather.gov/gridpoints/").mock(
        return_value=httpx.Response(200, json=grid)
    )


def test_nws_converts_units_and_spreads_windows(mock: respx.MockRouter) -> None:
    t0 = int(datetime(2026, 11, 6, 6, tzinfo=UTC).timestamp())
    grid = {
        "properties": {
            "windSpeed": {
                "uom": "wmoUnit:km_h-1",
                "values": [{"validTime": "2026-11-06T06:00:00+00:00/PT2H", "value": 80.4672}],
            },
            "windDirection": {
                "uom": "wmoUnit:degree_(angle)",
                "values": [{"validTime": "2026-11-06T06:00:00+00:00/PT2H", "value": 200}],
            },
            "quantitativePrecipitation": {
                "uom": "wmoUnit:mm",
                # 15.24 mm over 3 h = 0.2 in/hr total precipitation
                "values": [{"validTime": "2026-11-06T06:00:00+00:00/PT3H", "value": 15.24}],
            },
            "snowfallAmount": {
                "uom": "wmoUnit:mm",
                # 76.2 mm over 3 h = 1.0 in/hr of snow (~0.1 in/hr of water)
                "values": [{"validTime": "2026-11-06T06:00:00+00:00/PT3H", "value": 76.2}],
            },
        }
    }
    _mock_nws(mock, grid)

    series = nws.fetch_hourly(CHICAGO, t0, t0 + 3 * 3600)

    assert list(series) == [t0, t0 + 3600, t0 + 7200, t0 + 10800]
    hour = series[t0 + 3600]
    assert hour.wind_mph == pytest.approx(50, abs=0.01)  # 80.4672 km/h
    assert hour.wind_dir_deg == 200
    assert hour.snow_in_hr == pytest.approx(1.0)
    assert hour.rain_in_hr == pytest.approx(0.1)  # 0.2 total - 1.0 snow / 10
    assert hour.source == "nws"
    assert series[t0 + 7200].wind_mph is None  # the 2 h wind window has ended
    assert series[t0 + 10800].rain_in_hr is None  # beyond the 3 h precip window


def test_nws_parses_recorded_gridpoint(mock: respx.MockRouter) -> None:
    grid = load_fixture("nws_gridpoint")
    _mock_nws(mock, grid)
    first = grid["properties"]["windSpeed"]["values"][0]["validTime"].split("/")[0]
    t0 = int(datetime.fromisoformat(first).timestamp())

    series = nws.fetch_hourly(CHICAGO, t0, t0 + 5 * 3600)

    assert series[t0].wind_mph is not None
    assert all(w.source == "nws" for w in series.values())


def test_nws_rejects_unknown_units(mock: respx.MockRouter) -> None:
    grid = {
        "properties": {
            "windSpeed": {
                "uom": "wmoUnit:furlong_per_fortnight",
                "values": [{"validTime": "2026-11-06T06:00:00+00:00/PT1H", "value": 1}],
            }
        }
    }
    _mock_nws(mock, grid)

    with pytest.raises(ProviderError, match="unexpected unit"):
        nws.fetch_hourly(CHICAGO, 0, 0)


@pytest.mark.parametrize(
    ("iso", "hours"), [("PT1H", 1), ("PT6H", 6), ("P1D", 24), ("P1DT6H", 30), ("PT30M", 0.5)]
)
def test_nws_durations(iso: str, hours: float) -> None:
    assert nws._duration_hours(iso) == hours


# --- International search --------------------------------------------------------------------


def test_tomtom_geocode_is_worldwide_and_biased_to_the_map(mock: respx.MockRouter) -> None:
    call = mock.get(url__startswith="https://api.tomtom.com/search/2/search/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    tomtom.geocode("Lahore", near=(74.31, 31.52))
    tomtom.geocode("Lahore")

    biased, unbiased = (c.request.url.params for c in call.calls)
    assert "countrySet" not in biased
    assert (biased["lon"], biased["lat"]) == ("74", "32")  # rounded to whole degrees
    assert "lat" not in unbiased
    assert call.call_count == 2  # different bias -> separate cache entries


def test_photon_geocode_bias(mock: respx.MockRouter) -> None:
    call = mock.get("https://photon.komoot.io/api/").mock(
        return_value=httpx.Response(200, json={"features": []})
    )

    photon.geocode("Karachi", near=(67.0, 24.86))

    params = call.calls.last.request.url.params
    assert (params["lon"], params["lat"]) == ("67", "25")
    assert params["lang"] == "en"  # English names instead of the local script


@pytest.mark.parametrize(
    ("point", "covered"),
    [
        ((-87.63, 41.88), True),  # Chicago
        ((-149.9, 61.2), True),  # Anchorage
        ((-157.86, 21.31), True),  # Honolulu
        ((74.31, 31.52), False),  # Lahore
        ((-0.12, 51.5), False),  # London
        ((-79.38, 43.65), True),  # Toronto sits inside the lower-48 box; NWS 404s -> Unknown
    ],
)
def test_nws_coverage(point, covered) -> None:
    assert nws.covers(point) is covered
