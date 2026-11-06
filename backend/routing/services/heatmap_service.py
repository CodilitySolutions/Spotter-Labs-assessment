"""Weather-risk heatmap over the trip corridor for every hour of the forecast window (spec §8).

The whole 49-hour grid is computed once per plan, so the frontend's forecast slider only
switches which column it draws and never calls the API.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.geometry import corridor_grid
from ..domain.models import LonLat
from ..domain.risk import assess
from ..providers.base import cache_key, cached
from . import weather_service
from .plan_service import Plan
from .weather_service import WINDOW_HOURS

CORRIDOR_MI = 40
TARGET_POINTS = 300
HEATMAP_TTL_S = 3600


@dataclass(frozen=True)
class Heatmap:
    plan_id: str
    start_hour: int
    hours: int
    points: list[LonLat]
    # scores[i][h] is the risk score (0-4) at points[i] in hour h, or None when unknown.
    scores: list[list[int | None]]
    spacing_mi: float  # grid spacing; the frontend sizes the heatmap blur from it


def build(plan: Plan) -> Heatmap:
    return cached(cache_key("heatmap:v2", plan.id), HEATMAP_TTL_S, lambda: _build(plan))


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

    scores: list[list[int | None]] = []
    for point in points:
        row: list[int | None] = []
        for hour in hours:
            level = assess(weather.at(point, hour), load_lb).final
            row.append(int(level) if level is not None else None)
        scores.append(row)

    return Heatmap(
        plan_id=plan.id,
        start_hour=window.start,
        hours=len(hours),
        points=points,
        scores=scores,
        spacing_mi=grid.spacing_mi,
    )
