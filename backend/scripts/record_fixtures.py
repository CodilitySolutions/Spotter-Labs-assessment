"""Record real provider responses into tests/fixtures/ for offline tests.

Run inside the backend container (needs TOMTOM_API_KEY):

    docker compose run --rm backend python scripts/record_fixtures.py

Responses are captured through the real provider functions, so fixtures match exactly what
the code requests. API keys live only in request URLs, which are never saved.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["REDIS_URL"] = ""  # local-memory cache: always hit the real APIs

import django  # noqa: E402

django.setup()

import httpx  # noqa: E402

from routing.providers import base, nws, open_meteo, osrm, photon, tomtom  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
CHICAGO = (-87.6298, 41.8781)
MILWAUKEE = (-87.9065, 43.0389)
DETOUR = (-88.30, 42.50)
NWS_KEEP = ("windSpeed", "windGust", "quantitativePrecipitation", "snowfallAmount")


def record(name: str, call, trim=None) -> None:
    """Run ``call`` and save the JSON body of the last response it received."""
    captured: list[httpx.Response] = []

    def hook(response: httpx.Response) -> None:
        response.read()
        captured.append(response)

    client = base.get_client()
    client.event_hooks["response"] = [hook]
    try:
        call()
    finally:
        client.event_hooks["response"] = []

    body = captured[-1].json()
    if trim:
        body = trim(body)
    path = FIXTURES / f"{name}.json"
    path.write_text(json.dumps(body, separators=(",", ":")))
    print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size // 1024} KB)")


def trim_nws_grid(body: dict) -> dict:
    """Keep only the series we parse; the full gridpoint document is ~500 KB."""
    props = body["properties"]
    return {"properties": {k: props[k] for k in NWS_KEEP if k in props}}


def main() -> None:
    now = int(time.time())
    hour = now - now % 3600
    FIXTURES.mkdir(parents=True, exist_ok=True)
    print("Recording fixtures:")

    record(
        "tomtom_route",
        lambda: tomtom.calculate_route(
            CHICAGO, MILWAUKEE, depart_at=now, load_lb=20_000, max_alternatives=2
        ),
    )
    record(
        "tomtom_route_via",
        lambda: tomtom.calculate_route(
            CHICAGO, MILWAUKEE, depart_at=now, load_lb=20_000, via=[DETOUR]
        ),
    )
    record("tomtom_geocode", lambda: tomtom.geocode("Denver", limit=3))
    record("osrm_route", lambda: osrm.route(CHICAGO, MILWAUKEE))
    record("photon_geocode", lambda: photon.geocode("Denver", limit=3))
    record(
        "open_meteo_multi",
        lambda: open_meteo.fetch_hourly([CHICAGO, MILWAUKEE], hour, hour + 5 * 3600),
    )
    record(
        "open_meteo_single",
        lambda: open_meteo.fetch_hourly([CHICAGO], hour, hour + 5 * 3600),
    )
    record("nws_points", lambda: nws._grid_url(CHICAGO))
    record(
        "nws_gridpoint",
        lambda: nws.fetch_hourly(CHICAGO, hour, hour + 5 * 3600),
        trim=trim_nws_grid,
    )


if __name__ == "__main__":
    main()
