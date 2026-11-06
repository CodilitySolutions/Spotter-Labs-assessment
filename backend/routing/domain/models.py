"""Core value types shared by the domain logic. No I/O, no Django."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

LonLat = tuple[float, float]
"""A coordinate as ``(longitude, latitude)`` in degrees, matching GeoJSON order."""


class RiskLevel(IntEnum):
    """Ordered risk levels. The integer value is the score used for averaging and ranking."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        """Stable machine name used in the API, e.g. ``"no_travel"``."""
        return self.name.lower()

    @property
    def display(self) -> str:
        """Human-readable name, e.g. ``"No Travel"``."""
        return self.name.replace("_", " ").title()


@dataclass(frozen=True, slots=True)
class Place:
    """A geocoded location."""

    label: str
    lon: float
    lat: float

    @property
    def coord(self) -> LonLat:
        return (self.lon, self.lat)


@dataclass(frozen=True, slots=True)
class TimelinePoint:
    """Elapsed driving time at a distance along the route, as reported by the routing API."""

    distance_mi: float
    elapsed_s: float


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """A route as returned by a routing provider, before any weather analysis.

    ``distance_mi`` and ``duration_s`` are the provider's own figures; ``timeline`` maps
    distance along the route to elapsed time and is used to estimate checkpoint ETAs.
    """

    source: str
    geometry: tuple[LonLat, ...]
    distance_mi: float
    duration_s: float
    timeline: tuple[TimelinePoint, ...]
    is_fallback_profile: bool = False  # True when the router had no truck profile (OSRM)


@dataclass(frozen=True, slots=True)
class Weather:
    """Forecast conditions for one place and hour, already in the units the rules use.

    A field is ``None`` when the provider did not return it.
    """

    wind_mph: float | None
    rain_in_hr: float | None
    snow_in_hr: float | None
    gust_mph: float | None = None
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class Assessment:
    """The result of applying the risk rules to one checkpoint.

    ``final`` is ``None`` when the weather was incomplete: the level is Unknown, never Low.
    """

    wind: RiskLevel | None
    rain: RiskLevel | None
    snow: RiskLevel | None
    load_override: RiskLevel | None
    final: RiskLevel | None
    reason: str

    @property
    def is_unknown(self) -> bool:
        return self.final is None
