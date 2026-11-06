"""Route risk summaries and the recommendation (docs/PROJECT_SPEC.md §5).

Routes are ranked by, in order:

1. has any No Travel segment  (routes without one always win)
2. severe-or-worse miles      (Severe + No Travel)
3. high miles
4. average risk               (distance-weighted, over miles with known weather)
5. travel time
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .models import RiskLevel

LEVEL_KEYS = ("low", "moderate", "high", "severe", "no_travel", "unknown")
# Totals are compared at 0.1 mi and 0.001 risk points so float noise can't decide a ranking.
MILE_PRECISION = 1
RISK_PRECISION = 3


@dataclass(frozen=True, slots=True)
class RouteSummary:
    miles_by_level: dict[str, float]
    avg_risk: float | None  # None when no mile of the route has known weather
    worst_level: RiskLevel | None

    @property
    def severe_miles(self) -> float:
        """Miles at Severe or worse (No Travel counts as Severe, spec §5.3)."""
        return self.miles_by_level["severe"] + self.miles_by_level["no_travel"]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level["high"]

    @property
    def has_no_travel(self) -> bool:
        return self.miles_by_level["no_travel"] > 0

    @property
    def unknown_miles(self) -> float:
        return self.miles_by_level["unknown"]


def summarize(segments: Iterable[tuple[float, RiskLevel | None]]) -> RouteSummary:
    """Summarize a route from ``(covered_miles, level)`` pairs, one per checkpoint; ``None``
    means Unknown. A checkpoint covering no road (only possible on degenerate input) can't set
    the worst level.
    """
    miles = dict.fromkeys(LEVEL_KEYS, 0.0)
    weighted = known = 0.0
    worst: RiskLevel | None = None

    for covers_mi, level in segments:
        if level is None:
            miles["unknown"] += covers_mi
            continue
        miles[level.label] += covers_mi
        weighted += int(level) * covers_mi
        known += covers_mi
        if covers_mi > 0 and (worst is None or level > worst):
            worst = level

    return RouteSummary(
        miles_by_level=miles,
        avg_risk=weighted / known if known > 0 else None,
        worst_level=worst,
    )


@dataclass(frozen=True, slots=True)
class RankInput:
    id: str
    name: str
    summary: RouteSummary
    duration_s: float


def rank_key(route: RankInput) -> tuple[bool, float, float, float, float]:
    s = route.summary
    return (
        s.has_no_travel,
        round(s.severe_miles, MILE_PRECISION),
        round(s.high_miles, MILE_PRECISION),
        round(s.avg_risk, RISK_PRECISION) if s.avg_risk is not None else math.inf,
        route.duration_s,
    )


def rank(routes: Sequence[RankInput]) -> list[RankInput]:
    """Best route first. Ties keep the input order (the router's own preference)."""
    return sorted(routes, key=rank_key)


def explain(ranked: Sequence[RankInput]) -> str:
    """Why the first route beat the second, naming the first criterion that differed."""
    if not ranked:
        return ""
    if len(ranked) == 1:
        return "Only one route was available."

    win, other = ranked[0], ranked[1]
    ws, os_ = win.summary, other.summary
    if ws.has_no_travel != os_.has_no_travel:
        return f"{win.name} avoids No Travel conditions; {other.name} does not."
    w_key, o_key = rank_key(win), rank_key(other)
    if w_key[1] != o_key[1]:
        return (
            f"Fewest severe-or-worse miles: {_mi(ws.severe_miles)} vs "
            f"{_mi(os_.severe_miles)} on {other.name}."
        )
    if w_key[2] != o_key[2]:
        return (
            f"Equal severe miles; fewest high-risk miles: {_mi(ws.high_miles)} vs "
            f"{_mi(os_.high_miles)} on {other.name}."
        )
    if w_key[3] != o_key[3]:
        return (
            f"Equal severe and high miles; lowest average risk: {_score(ws.avg_risk)} vs "
            f"{_score(os_.avg_risk)} on {other.name}."
        )
    if w_key[4] != o_key[4]:
        return (
            f"Equal weather risk; fastest: {_duration(win.duration_s)} vs "
            f"{_duration(other.duration_s)} on {other.name}."
        )
    return f"Routes are equal on every criterion; {win.name} is listed first."


def _mi(miles: float) -> str:
    return f"{miles:.1f} mi" if 0 < miles < 10 else f"{miles:.0f} mi"


def _score(avg: float | None) -> str:
    return "unknown" if avg is None else f"{avg:.2f}"


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min"
