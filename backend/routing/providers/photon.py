"""Photon (komoot, OpenStreetMap data): primary place search. Free, no key.

Chosen over TomTom Search for its worldwide coverage: TomTom's index misses major cities in
some regions (e.g. it has no entry for the city of Lahore), while OpenStreetMap has them.
"""

from __future__ import annotations

from typing import Any

from ..domain.models import LonLat, Place
from .base import cache_key, cached, request_json

PROVIDER = "photon"
BASE_URL = "https://photon.komoot.io"
GEOCODE_TTL_S = 24 * 3600


def geocode(query: str, limit: int = 5, near: LonLat | None = None) -> list[Place]:
    """Worldwide place search; ``near`` ranks results close to that point first."""
    q = query.strip()
    if not q:
        return []
    bias = (round(near[0]), round(near[1])) if near else None

    def fetch() -> list[Place]:
        # English names and labels; without this, names come back in the local script.
        params: dict[str, Any] = {"q": q, "limit": limit, "lang": "en"}
        if bias:
            params["lon"], params["lat"] = bias
        data = request_json(PROVIDER, f"{BASE_URL}/api/", params=params)
        return [_parse_feature(f) for f in data.get("features", [])]

    return cached(cache_key("geocode:photon", q.lower(), limit, bias), GEOCODE_TTL_S, fetch)


def _parse_feature(feature: dict[str, Any]) -> Place:
    props = feature.get("properties", {})
    parts: list[str] = []
    for key in ("name", "city", "state", "country"):
        value = props.get(key)
        if value and value not in parts:
            parts.append(value)
    lon, lat = feature["geometry"]["coordinates"][:2]
    return Place(label=", ".join(parts), lon=lon, lat=lat)
