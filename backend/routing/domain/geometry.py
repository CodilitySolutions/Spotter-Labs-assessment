"""Distance and polyline helpers. Pure Python; coordinates are ``(lon, lat)`` degrees.

Distances are in statute miles and use the haversine formula. Only grid spacing and the
detour offset use a local flat-earth approximation, where a small error does not matter.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from .models import LonLat

EARTH_RADIUS_MI = 3958.7613
MI_PER_DEG_LAT = math.pi * EARTH_RADIUS_MI / 180  # ~69.09


def haversine_mi(a: LonLat, b: LonLat) -> float:
    """Great-circle distance between two points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def _require_line(polyline: Sequence[LonLat]) -> None:
    if len(polyline) < 2:
        raise ValueError("A polyline needs at least 2 points")


def cumulative_distances(polyline: Sequence[LonLat]) -> list[float]:
    """Distance from the start to each vertex; the first value is 0 and the last is the length."""
    _require_line(polyline)
    out = [0.0]
    for prev, cur in zip(polyline, polyline[1:], strict=False):
        out.append(out[-1] + haversine_mi(prev, cur))
    return out


def point_at_distance(polyline: Sequence[LonLat], cumdist: Sequence[float], d: float) -> LonLat:
    """The point ``d`` miles along the line, interpolated within the segment containing it.

    ``d`` is clamped to ``[0, length]``.
    """
    if d <= 0:
        return polyline[0]
    if d >= cumdist[-1]:
        return polyline[-1]

    i = bisect_right(cumdist, d) - 1  # segment i runs from vertex i to vertex i + 1
    seg_len = cumdist[i + 1] - cumdist[i]
    t = 0.0 if seg_len == 0 else (d - cumdist[i]) / seg_len
    (lon1, lat1), (lon2, lat2) = polyline[i], polyline[i + 1]
    return (lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t)


def resample(polyline: Sequence[LonLat], step_mi: float) -> list[LonLat]:
    """Points every ``step_mi`` along the line, always including both endpoints."""
    if step_mi <= 0:
        raise ValueError("step_mi must be positive")
    cumdist = cumulative_distances(polyline)
    total = cumdist[-1]
    # The epsilon stops float drift (e.g. 100.0000001 / 10) from adding a spurious extra step.
    n = max(1, math.ceil(total / step_mi - 1e-9))
    return [point_at_distance(polyline, cumdist, total * k / n) for k in range(n + 1)]


def simplify(polyline: Sequence[LonLat], tolerance_mi: float = 0.02) -> list[LonLat]:
    """Douglas-Peucker simplification for display: drops vertices that deviate less than
    ``tolerance_mi`` (default ~30 m) from the simplified line. Endpoints are always kept.

    Uses a local flat projection, which is accurate at these tolerances. Iterative, so very
    long routes cannot hit the recursion limit.
    """
    n = len(polyline)
    if n <= 2:
        return list(polyline)

    mid_lat = math.radians((min(p[1] for p in polyline) + max(p[1] for p in polyline)) / 2)
    kx, ky = MI_PER_DEG_LAT * math.cos(mid_lat), MI_PER_DEG_LAT
    xy = [(p[0] * kx, p[1] * ky) for p in polyline]

    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        (ax, ay), (bx, by) = xy[first], xy[last]
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        max_d, index = -1.0, -1
        for i in range(first + 1, last):
            px, py = xy[i]
            if seg_len2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if d > max_d:
                max_d, index = d, i
        if max_d > tolerance_mi:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))

    return [p for p, k in zip(polyline, keep, strict=True) if k]


# --- Spatial index ---------------------------------------------------------------------------


class _PointIndex:
    """Points bucketed into lon/lat cells for fast "is any point within r miles?" queries.

    Cells are ``r`` miles tall and at least ``r`` miles wide everywhere the index is used (the
    width in degrees is taken at the highest latitude, where a degree of longitude is
    shortest). So every point within ``r`` lies in the query's cell or one of its 8 neighbours,
    and candidates are confirmed with the exact haversine distance.
    """

    def __init__(self, points: Iterable[LonLat], radius_mi: float) -> None:
        pts = list(points)
        if not pts:
            raise ValueError("Cannot index an empty set of points")
        self.radius_mi = radius_mi
        pad_deg = radius_mi / MI_PER_DEG_LAT
        max_abs_lat = min(max(abs(p[1]) for p in pts) + 2 * pad_deg, 89.0)
        self._lat_cell = pad_deg
        self._lon_cell = radius_mi / (MI_PER_DEG_LAT * math.cos(math.radians(max_abs_lat)))
        self._buckets: dict[tuple[int, int], list[LonLat]] = defaultdict(list)
        for p in pts:
            self._buckets[self._key(p)].append(p)

    def _key(self, p: LonLat) -> tuple[int, int]:
        return (math.floor(p[0] / self._lon_cell), math.floor(p[1] / self._lat_cell))

    def has_neighbor(self, p: LonLat) -> bool:
        kx, ky = self._key(p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in self._buckets.get((kx + dx, ky + dy), ()):
                    if haversine_mi(p, q) <= self.radius_mi:
                        return True
        return False


# --- Route comparison and detours ------------------------------------------------------------


def overlap_fraction(
    a: Sequence[LonLat],
    b: Sequence[LonLat],
    tolerance_mi: float = 0.125,
    sample_step_mi: float = 0.5,
) -> float:
    """Share of route ``a`` (sampled every ``sample_step_mi``) lying within ``tolerance_mi`` of
    route ``b``. Not symmetric: see :func:`route_similarity`.
    """
    # Densify b finer than the tolerance so long straight segments still have nearby points.
    index = _PointIndex(resample(b, tolerance_mi * 0.8), tolerance_mi)
    samples = resample(a, sample_step_mi)
    return sum(index.has_neighbor(p) for p in samples) / len(samples)


def route_similarity(a: Sequence[LonLat], b: Sequence[LonLat]) -> float:
    """How much two routes are "the same road", from 0 to 1.

    Takes the lower of the two directions, so a route is only a duplicate if each one mostly
    follows the other. A short route that lies entirely on a much longer one is not a duplicate.
    """
    return min(overlap_fraction(a, b), overlap_fraction(b, a))


def detour_waypoint(
    origin: LonLat, destination: LonLat, side: Literal["left", "right"], ratio: float
) -> LonLat:
    """A point offset sideways from the trip's midpoint by ``ratio`` x the straight-line
    distance. "left" is relative to the direction of travel.

    Routing through it produces a meaningfully different alternative route.
    """
    mid_lat = (origin[1] + destination[1]) / 2
    mi_per_deg_lon = MI_PER_DEG_LAT * math.cos(math.radians(mid_lat))

    # Work in a local flat projection measured in miles.
    dx = (destination[0] - origin[0]) * mi_per_deg_lon
    dy = (destination[1] - origin[1]) * MI_PER_DEG_LAT
    length = math.hypot(dx, dy)
    if length == 0:
        raise ValueError("Origin and destination are the same point")

    # Unit vector perpendicular to travel: rotate 90 degrees counter-clockwise for "left".
    px, py = -dy / length, dx / length
    if side == "right":
        px, py = -px, -py

    offset = ratio * length
    mid_lon = (origin[0] + destination[0]) / 2
    return (mid_lon + px * offset / mi_per_deg_lon, mid_lat + py * offset / MI_PER_DEG_LAT)


# --- Heatmap corridor --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CorridorGrid:
    points: list[LonLat]
    spacing_mi: float  # distance between neighbouring grid points


def corridor_grid(
    polylines: Sequence[Sequence[LonLat]],
    corridor_mi: float = 40,
    target_points: int = 300,
) -> CorridorGrid:
    """A regular grid of points covering every place within ``corridor_mi`` of any route.

    The spacing is tuned so the grid has roughly ``target_points`` points (within ~25%).
    """
    if not polylines:
        raise ValueError("At least one route is required")
    for line in polylines:
        _require_line(line)

    # First guess: the corridor is about (longest route) x (corridor width). Routes that
    # diverge widely make it bigger, so the spacing is then corrected from the actual count.
    longest = max(cumulative_distances(line)[-1] for line in polylines)
    spacing_mi = math.sqrt((longest + 2 * corridor_mi) * 2 * corridor_mi / target_points)

    best = CorridorGrid([], 0.0)
    for _ in range(4):
        spacing_mi = max(spacing_mi, 1.0)
        best = CorridorGrid(_grid_at_spacing(polylines, corridor_mi, spacing_mi), spacing_mi)
        ratio = len(best.points) / target_points
        if 0.75 <= ratio <= 1.25:
            break
        spacing_mi *= math.sqrt(ratio)  # count scales with 1 / spacing^2
    return best


def _grid_at_spacing(
    polylines: Sequence[Sequence[LonLat]], corridor_mi: float, spacing_mi: float
) -> list[LonLat]:
    # Route samples every half-spacing are dense enough that "near a sample" ~ "near the route".
    route_points = [p for line in polylines for p in resample(line, min(spacing_mi / 2, 5.0))]
    index = _PointIndex(route_points, corridor_mi)

    lats = [p[1] for p in route_points]
    lons = [p[0] for p in route_points]
    mid_lat = (min(lats) + max(lats)) / 2
    mi_per_deg_lon = MI_PER_DEG_LAT * math.cos(math.radians(mid_lat))
    pad_lat = corridor_mi / MI_PER_DEG_LAT
    pad_lon = corridor_mi / (MI_PER_DEG_LAT * math.cos(math.radians(max(map(abs, lats)))))
    step_lat, step_lon = spacing_mi / MI_PER_DEG_LAT, spacing_mi / mi_per_deg_lon

    rows = math.floor((max(lats) - min(lats) + 2 * pad_lat) / step_lat) + 1
    cols = math.floor((max(lons) - min(lons) + 2 * pad_lon) / step_lon) + 1
    grid: list[LonLat] = []
    for r in range(rows):
        lat = min(lats) - pad_lat + r * step_lat
        for c in range(cols):
            p = (min(lons) - pad_lon + c * step_lon, lat)
            if index.has_neighbor(p):
                grid.append((round(p[0], 4), round(p[1], 4)))
    return grid
