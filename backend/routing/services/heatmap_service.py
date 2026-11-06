"""Weather-risk heatmap over the trip corridor for every hour of the forecast window (spec §8).

The whole 49-hour grid is computed once per plan, so the frontend's forecast slider only
switches which column it draws and never calls the API.

Besides the overall level, each point and hour carries the level from each condition and the
raw forecast values, so the map can show *why* an area is risky (wind, rain, snow or the load
rule) and draw wind arrows. All of it comes from the same `assess()` call that scores the
checkpoints, so the map and the checkpoints can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.geometry import corridor_grid
from ..domain.models import LonLat, RiskLevel
from ..domain.risk import assess
from ..providers.base import cache_key, cached
from . import weather_service
from .plan_service import Plan
from .weather_service import WINDOW_HOURS

CORRIDOR_MI = 40
TARGET_POINTS = 300
HEATMAP_TTL_S = 3600

Matrix = list[list[int | None]]
FloatMatrix = list[list[float | None]]


@dataclass(frozen=True)
class Heatmap:
    """Per-point, per-hour matrices: ``m[i][h]`` is point ``i`` in hour ``h``; None = unknown."""

    plan_id: str
    start_hour: int
    hours: int
    points: list[LonLat]
    spacing_mi: float  # grid spacing; the frontend sizes the heatmap blur from it
    scores: Matrix  # overall risk score 0-4
    # Level each condition produces on its own. Wind includes the load rules, which are
    # about wind; `load_raised` marks where they raised it.
    wind_levels: Matrix = field(default_factory=list)
    rain_levels: Matrix = field(default_factory=list)
    snow_levels: Matrix = field(default_factory=list)
    load_raised: Matrix = field(default_factory=list)  # 1 or 0
    wind_mph: Matrix = field(default_factory=list)
    wind_dir_deg: Matrix = field(default_factory=list)  # direction the wind comes FROM
    rain_in_hr: FloatMatrix = field(default_factory=list)
    snow_in_hr: FloatMatrix = field(default_factory=list)


def build(plan: Plan) -> Heatmap:
    return cached(cache_key("heatmap:v3", plan.id), HEATMAP_TTL_S, lambda: _build(plan))


def _build(plan: Plan) -> Heatmap:
    window = plan.window
    grid = corridor_grid(
        [r.display_geometry for r in plan.routes],
        corridor_mi=CORRIDOR_MI,
        target_points=TARGET_POINTS,
    )
    points = grid.points
    # The grid can be hundreds of cells, too many for NWS's one-request-per-point fallback.
    weather = weather_service.get_weather(points, window, allow_nws_fallback=False)
    hours = [window.start + h * 3600 for h in range(WINDOW_HOURS + 1)]
    load_lb = plan.request.load_lb

    m: dict[str, list] = {
        k: []
        for k in (
            "scores",
            "wind_levels",
            "rain_levels",
            "snow_levels",
            "load_raised",
            "wind_mph",
            "wind_dir_deg",
            "rain_in_hr",
            "snow_in_hr",
        )
    }
    for point in points:
        rows: dict[str, list] = {k: [] for k in m}
        for hour in hours:
            wx = weather.at(point, hour)
            a = assess(wx, load_lb)
            known = a.final is not None
            wind_level = (
                max(a.wind, a.load_override) if a.wind is not None and a.load_override else a.wind
            )
            rows["scores"].append(_int(a.final))
            rows["wind_levels"].append(_int(wind_level) if known else None)
            rows["rain_levels"].append(_int(a.rain) if known else None)
            rows["snow_levels"].append(_int(a.snow) if known else None)
            raised = a.load_override is not None and a.wind is not None and a.load_override > a.wind
            rows["load_raised"].append(int(raised) if known else None)
            rows["wind_mph"].append(_round(wx.wind_mph if wx else None, 0))
            rows["wind_dir_deg"].append(_round(wx.wind_dir_deg if wx else None, 0))
            rows["rain_in_hr"].append(_round(wx.rain_in_hr if wx else None, 2))
            rows["snow_in_hr"].append(_round(wx.snow_in_hr if wx else None, 2))
        for k, row in rows.items():
            m[k].append(row)

    return Heatmap(
        plan_id=plan.id,
        start_hour=window.start,
        hours=len(hours),
        points=points,
        spacing_mi=grid.spacing_mi,
        **m,
    )


def _int(level: RiskLevel | None) -> int | None:
    return int(level) if level is not None else None


def _round(value: float | None, digits: int) -> float | int | None:
    if value is None:
        return None
    return round(value) if digits == 0 else round(value, digits)
