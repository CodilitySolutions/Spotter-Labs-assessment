"""Getting three distinct routes, with detours and the OSRM fallback (spec §7)."""

import pytest

from routing.providers.base import NoRouteError, ProviderError
from routing.services import route_service
from routing.services.errors import NoRouteFoundError, UpstreamUnavailableError

from .factories import candidate

ORIGIN, DEST = (-100.0, 35.0), (-100.0, 36.45)


@pytest.fixture
def calls(monkeypatch):
    """Record TomTom/OSRM calls and serve scripted responses."""
    log: dict[str, list] = {"tomtom": [], "osrm": []}
    script: dict[str, object] = {}

    def tomtom(origin, destination, *, depart_at, load_lb, max_alternatives=0, via=()):
        log["tomtom"].append({"via": list(via), "max_alternatives": max_alternatives})
        key = "detour" if via else "main"
        result = script[key]
        if isinstance(result, Exception):
            raise result
        return result(via) if callable(result) else result

    def osrm(origin, destination, *, alternatives=3):
        log["osrm"].append(alternatives)
        result = script["osrm"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(route_service.tomtom, "calculate_route", tomtom)
    monkeypatch.setattr(route_service.osrm, "route", osrm)
    return log, script


def get():
    return route_service.get_routes(ORIGIN, DEST, depart_at=0, load_lb=20_000)


def test_three_distinct_tomtom_routes_need_no_detours(calls) -> None:
    log, script = calls
    script["main"] = [candidate(0), candidate(0.5, hours=2.2), candidate(-0.5, hours=2.4)]

    result = get()

    assert len(result.routes) == 3
    assert result.warnings == []
    assert len(log["tomtom"]) == 1
    assert log["tomtom"][0]["max_alternatives"] == route_service.TOMTOM_ALTERNATIVES


def test_duplicate_alternatives_are_replaced_by_detours(calls) -> None:
    log, script = calls
    # TomTom returns the same road twice; detours supply the missing routes.
    script["main"] = [candidate(0), candidate(0.0001)]
    script["detour"] = lambda via: [candidate(0.6 if via[0][0] < -100 else -0.6, hours=2.5)]

    result = get()

    assert len(result.routes) == 3
    assert result.routes[0].duration_s == 2 * 3600  # the original fastest route stays first
    detour_sides = sorted(call["via"][0][0] < -100 for call in log["tomtom"] if call["via"])
    assert detour_sides == [False, True]  # one left, one right, requested together


def test_unreasonable_detours_are_rejected(calls) -> None:
    _, script = calls
    script["main"] = [candidate(0)]
    script["detour"] = lambda via: [candidate(0.6, hours=5)]  # 2.5x the fastest route

    result = get()

    assert len(result.routes) == 1
    assert result.warnings == ["Only 1 distinct route could be found for this trip."]


def test_failed_detours_are_ignored(calls) -> None:
    _, script = calls
    script["main"] = [candidate(0), candidate(0.5)]
    script["detour"] = ProviderError("tomtom", "boom")

    result = get()

    assert len(result.routes) == 2
    assert "Only 2 distinct routes" in result.warnings[0]


def test_falls_back_to_osrm_when_tomtom_is_down(calls) -> None:
    log, script = calls
    script["main"] = ProviderError("tomtom", "HTTP 503", status=503)
    script["osrm"] = [candidate(0, source="osrm", fallback=True), candidate(0.5, fallback=True)]

    result = get()

    assert len(log["osrm"]) == 1
    assert all(r.is_fallback_profile for r in result.routes)
    assert "car-routing fallback (OSRM)" in result.warnings[0]


def test_no_route_does_not_fall_back(calls) -> None:
    log, script = calls
    script["main"] = NoRouteError("tomtom", "no route")

    with pytest.raises(NoRouteFoundError):
        get()
    assert log["osrm"] == []


def test_all_routers_down_is_upstream_error(calls) -> None:
    _, script = calls
    script["main"] = ProviderError("tomtom", "down")
    script["osrm"] = ProviderError("osrm", "down")

    with pytest.raises(UpstreamUnavailableError):
        get()


def test_routes_are_cached(calls) -> None:
    log, script = calls
    script["main"] = [candidate(0), candidate(0.5), candidate(-0.5)]

    first, second = get(), get()

    assert len(log["tomtom"]) == 1
    assert [r.duration_s for r in first.routes] == [r.duration_s for r in second.routes]
